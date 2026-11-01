import json
import os
import re
import shutil
import uuid

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.models import Application, Statement, Transaction, LoanDocument
from app.services.parsing import parse_statement, extract_tables_native
from app.services.statement_parser import parse_text_statement
from app.services.categorization import categorize_transactions, extract_transactions_via_llm
from app.services.reconcile import reconcile_rows, _find, AMT
from app.services.metrics import compute_financial_health
from app.services.scoring import evaluate_eligibility
from app.services.cross_verification import run_cross_verification

router = APIRouter(prefix="/applications", tags=["applications"])


def _to_float(value):
    if value is None:
        return None
    cleaned = re.sub(r"[^\d.]", "", str(value))
    if cleaned in ("", "."):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


@router.get("/")
def list_applications(db: Session = Depends(get_db)):
    return db.query(Application).order_by(Application.created_at.desc()).all()


@router.post("/")
def create_application(applicant_name: str = None, db: Session = Depends(get_db)):
    app_record = Application(applicant_name=applicant_name)
    db.add(app_record)
    db.commit()
    db.refresh(app_record)
    return app_record


@router.delete("/{application_id}")
def delete_application(application_id: str, db: Session = Depends(get_db)):
    app_record = db.query(Application).filter(Application.id == application_id).first()
    if not app_record:
        raise HTTPException(status_code=404, detail="Application not found")

    paths = [s.file_path for s in app_record.statements]
    docs = db.query(LoanDocument).filter(LoanDocument.application_id == application_id).all()
    paths += [d.file_path for d in docs]

    for d in docs:
        db.delete(d)
    db.flush()
    db.delete(app_record)
    db.commit()

    for p in paths:
        try:
            os.remove(p)
        except OSError:
            pass
    return {"deleted": application_id}


@router.post("/{application_id}/statements")
def upload_statement(application_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    app_record = db.query(Application).filter(Application.id == application_id).first()
    if not app_record:
        raise HTTPException(status_code=404, detail="Application not found")

    os.makedirs(settings.upload_dir, exist_ok=True)
    safe_name = f"{uuid.uuid4()}_{file.filename}"
    file_path = os.path.join(settings.upload_dir, safe_name)
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    statement = Statement(application_id=application_id, filename=file.filename, file_path=file_path, status="uploaded")
    db.add(statement)
    db.commit()
    db.refresh(statement)
    return statement


@router.post("/statements/{statement_id}/process")
def process_statement(statement_id: str, db: Session = Depends(get_db)):
    statement = db.query(Statement).filter(Statement.id == statement_id).first()
    if not statement:
        raise HTTPException(status_code=404, detail="Statement not found")

    # Re-processing replaces old rows instead of duplicating them
    db.query(Transaction).filter(Transaction.statement_id == statement.id).delete()

    parsed = parse_statement(statement.file_path)
    statement.raw_text = parsed["raw_text"]
    statement.parse_method = parsed["parse_method"]

    rows = []
    extraction = None
    reconciliation = None

    # 1. Table extraction (clean digital tables)
    if parsed["parse_method"] == "native_pdf":
        tables = extract_tables_native(statement.file_path)
        for table in tables:
            for row in table[1:]:
                if len(row) >= 5:
                    rows.append({"date": row[0], "description": row[1], "debit": row[2], "credit": row[3], "balance": row[4]})
        if rows:
            extraction = "table"

    # 2. Deterministic text parser, accepted only if it matches the statement's own totals
    if not rows:
        text_rows = parse_text_statement(parsed["raw_text"])
        if text_rows:
            check = reconcile_rows(text_rows, parsed["raw_text"])
            print(f"Text parser: {len(text_rows)} rows, matches statement totals: {check['matches_statement']}")
            if check["matches_statement"]:
                rows, reconciliation, extraction = text_rows, check, "text_parser"

    # 3. LLM fallback
    if not rows:
        rows = extract_transactions_via_llm(parsed["raw_text"])
        if rows:
            reconciliation = reconcile_rows(rows, parsed["raw_text"])
            extraction = "llm"

    rows = categorize_transactions(rows)

    for position, row in enumerate(rows):
        txn = Transaction(
            statement_id=statement.id,
            position=position,
            txn_date=str(row.get("date")) if row.get("date") else None,
            description=row.get("description"),
            debit=_to_float(row.get("debit")),
            credit=_to_float(row.get("credit")),
            balance=_to_float(row.get("balance")),
            category=row.get("category"),
            category_source=row.get("category_source"),
        )
        db.add(txn)

    statement.status = "categorized"
    db.commit()

    metrics = compute_financial_health(rows)

    scoring_result = evaluate_eligibility(metrics)
    application = db.query(Application).filter(Application.id == statement.application_id).first()
    application.risk_score = scoring_result["risk_score"]
    application.eligibility_flag = scoring_result["eligibility_flag"]
    application.status = "processed"
    db.commit()

    return {
        "statement_id": statement.id,
        "extraction": extraction,
        "transaction_count": len(rows),
        "metrics": metrics,
        "reconciliation": reconciliation,
        "risk_score": scoring_result["risk_score"],
        "eligibility_flag": scoring_result["eligibility_flag"],
        "reasons": scoring_result["reasons"],
    }


@router.get("/{application_id}")
def get_application(application_id: str, db: Session = Depends(get_db)):
    app_record = db.query(Application).filter(Application.id == application_id).first()
    if not app_record:
        raise HTTPException(status_code=404, detail="Application not found")
    return app_record


@router.get("/{application_id}/verify")
def verify_application(application_id: str, db: Session = Depends(get_db)):
    app_record = db.query(Application).filter(Application.id == application_id).first()
    if not app_record:
        raise HTTPException(status_code=404, detail="Application not found")

    documents = db.query(LoanDocument).filter(
        LoanDocument.application_id == application_id,
        LoanDocument.status == "extracted",
    ).all()

    documents_by_type = {}
    for doc in documents:
        if doc.extracted_fields:
            documents_by_type[doc.doc_type] = json.loads(doc.extracted_fields)

    statement = db.query(Statement).filter(
        Statement.application_id == application_id,
        Statement.status == "categorized",
    ).order_by(Statement.created_at.desc()).first()

    bank_metrics = {}
    if statement:
        transactions = [
            {"category": t.category, "credit": t.credit, "debit": t.debit, "balance": t.balance}
            for t in statement.transactions
        ]
        bank_metrics = compute_financial_health(transactions)

    results = run_cross_verification(documents_by_type, bank_metrics)

    return {
        "application_id": application_id,
        "documents_checked": list(documents_by_type.keys()),
        "has_bank_statement": statement is not None,
        "checks": results,
    }


@router.get("/{application_id}/statements/latest")
def get_latest_statement(application_id: str, db: Session = Depends(get_db)):
    """Saved results for the most recent processed statement, rebuilt from stored data."""
    statement = db.query(Statement).filter(
        Statement.application_id == application_id,
        Statement.status == "categorized",
    ).order_by(Statement.created_at.desc()).first()

    if not statement:
        return {"exists": False}

    txns = (
        db.query(Transaction)
        .filter(Transaction.statement_id == statement.id)
        .order_by(Transaction.position.asc().nullslast())
        .all()
    )
    rows = [
        {
            "date": t.txn_date,
            "description": t.description,
            "debit": t.debit,
            "credit": t.credit,
            "balance": t.balance,
            "category": t.category,
        }
        for t in txns
    ]
    metrics = compute_financial_health(rows)
    scoring_result = evaluate_eligibility(metrics)

    raw = statement.raw_text or ""
    stated_credits = _find(r"Total Credits\s*\+?\s*" + AMT, raw)
    stated_debits = _find(r"Total Debits\s*-?\s*" + AMT, raw)
    computed_credits = round(sum(r["credit"] or 0 for r in rows), 2)
    computed_debits = round(sum(r["debit"] or 0 for r in rows), 2)
    matches = None
    if stated_credits is not None and stated_debits is not None:
        matches = abs(computed_credits - stated_credits) <= 1.0 and abs(computed_debits - stated_debits) <= 1.0

    return {
        "exists": True,
        "statement_id": statement.id,
        "filename": statement.filename,
        "parse_method": statement.parse_method,
        "transaction_count": len(rows),
        "metrics": metrics,
        "reconciliation": {
            "stated_total_credits": stated_credits,
            "stated_total_debits": stated_debits,
            "computed_total_credits": computed_credits,
            "computed_total_debits": computed_debits,
            "matches_statement": matches,
        },
        "risk_score": scoring_result["risk_score"],
        "eligibility_flag": scoring_result["eligibility_flag"],
        "reasons": scoring_result["reasons"],
        "transactions": rows,
    }