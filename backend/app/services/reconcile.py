import re

AMT = r"INR\s*([\d,]+(?:\.\d+)?)"


def _find(pattern, text):
    m = re.search(pattern, text, re.I)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _num(value):
    if value is None:
        return None
    cleaned = re.sub(r"[^\d.]", "", str(value))
    try:
        return float(cleaned) if cleaned not in ("", ".") else None
    except ValueError:
        return None


def reconcile_rows(rows: list, raw_text: str) -> dict:
    """Rebuilds debit/credit for each row from balance changes (the balance
    column is reliable even when column alignment is lost in the PDF text),
    then checks the totals against the statement's own summary.
    """
    opening = _find(r"Opening Balance\s*" + AMT, raw_text)
    ending = _find(r"Ending Balance\s*" + AMT, raw_text)
    stated_credits = _find(r"Total Credits\s*\+?\s*" + AMT, raw_text)
    stated_debits = _find(r"Total Debits\s*-?\s*" + AMT, raw_text)

    prev = opening
    corrected = 0
    for r in rows:
        bal = _num(r.get("balance"))
        if bal is None:
            continue
        if prev is not None:
            delta = round(bal - prev, 2)
            old_debit = _num(r.get("debit")) or 0
            old_credit = _num(r.get("credit")) or 0
            if abs((old_credit - old_debit) - delta) > 0.01:
                corrected += 1
            r["debit"] = -delta if delta < 0 else None
            r["credit"] = delta if delta > 0 else None
        prev = bal

    computed_credits = round(sum(_num(r.get("credit")) or 0 for r in rows), 2)
    computed_debits = round(sum(_num(r.get("debit")) or 0 for r in rows), 2)

    matches = None
    if stated_credits is not None and stated_debits is not None:
        matches = (
            abs(computed_credits - stated_credits) <= 1.0
            and abs(computed_debits - stated_debits) <= 1.0
        )

    return {
        "opening_balance": opening,
        "ending_balance": ending,
        "stated_total_credits": stated_credits,
        "stated_total_debits": stated_debits,
        "computed_total_credits": computed_credits,
        "computed_total_debits": computed_debits,
        "rows_corrected": corrected,
        "matches_statement": matches,
    }