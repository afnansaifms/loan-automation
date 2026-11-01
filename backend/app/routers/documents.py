import json
import os
import shutil
import uuid

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.models import Application, LoanDocument
from app.services.parsing import parse_statement  # reused - same native/OCR logic works for any PDF
from app.services.document_classification import classify_document
from app.services.document_extraction import extract_fields

router = APIRouter(prefix="/applications", tags=["documents"])


@router.post("/{application_id}/documents")
def upload_document(application_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    app_record = db.query(Application).filter(Application.id == application_id).first()
    if not app_record:
        raise HTTPException(status_code=404, detail="Application not found")

    os.makedirs(settings.upload_dir, exist_ok=True)
    safe_name = f"{uuid.uuid4()}_{file.filename}"
    file_path = os.path.join(settings.upload_dir, safe_name)
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    document = LoanDocument(
        application_id=application_id,
        filename=file.filename,
        file_path=file_path,
        status="uploaded",
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


@router.post("/documents/{document_id}/process")
def process_document(document_id: str, db: Session = Depends(get_db)):
    """Runs the full pipeline for one loan document: parse -> classify -> extract fields."""
    document = db.query(LoanDocument).filter(LoanDocument.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    parsed = parse_statement(document.file_path)  # reused: same native/OCR fallback logic
    document.raw_text = parsed["raw_text"]
    document.parse_method = parsed["parse_method"]

    doc_type = classify_document(parsed["raw_text"])
    document.doc_type = doc_type

    fields = extract_fields(doc_type, parsed["raw_text"])
    document.extracted_fields = json.dumps(fields)

    document.status = "extracted"
    db.commit()

    return {
        "document_id": document.id,
        "doc_type": doc_type,
        "parse_method": parsed["parse_method"],
        "extracted_fields": fields,
    }


@router.get("/{application_id}/documents")
def list_documents(application_id: str, db: Session = Depends(get_db)):
    documents = db.query(LoanDocument).filter(LoanDocument.application_id == application_id).all()
    return documents