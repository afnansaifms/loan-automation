"""
Cross-document consistency checks - compares extracted fields from loan
documents (salary slip, KYC) against each other and against actual bank
statement data, to flag potential fraud or inconsistency.

Each check returns a pass/fail plus a human-readable reason, same
transparency principle as scoring.py - an officer needs to know exactly
what was compared and why something was flagged.
"""


def check_pan_consistency(documents_by_type: dict) -> dict:
    """Compares PAN across all documents that have one."""
    pans_found = {}
    for doc_type, fields in documents_by_type.items():
        pan = fields.get("pan") or fields.get("id_number")
        if pan and doc_type == "kyc" and fields.get("id_type", "").lower().find("pan") == -1:
            continue  # KYC doc's id_number might be an Aadhaar, not a PAN - skip if not PAN type
        if pan:
            pans_found[doc_type] = pan.strip().upper()

    if len(pans_found) < 2:
        return {"check": "pan_consistency", "status": "insufficient_data", "reason": "Fewer than two documents with a PAN to compare."}

    unique_pans = set(pans_found.values())
    if len(unique_pans) == 1:
        return {"check": "pan_consistency", "status": "pass", "reason": f"PAN matches across {list(pans_found.keys())}."}
    else:
        return {
            "check": "pan_consistency",
            "status": "fail",
            "reason": f"PAN mismatch detected: {pans_found}",
        }


def check_name_consistency(documents_by_type: dict) -> dict:
    """Compares applicant name across documents that have one."""
    names_found = {}
    for doc_type, fields in documents_by_type.items():
        name = fields.get("employee_name") or fields.get("full_name") or fields.get("taxpayer_name")
        if name:
            names_found[doc_type] = name.strip().lower()

    if len(names_found) < 2:
        return {"check": "name_consistency", "status": "insufficient_data", "reason": "Fewer than two documents with a name to compare."}

    unique_names = set(names_found.values())
    if len(unique_names) == 1:
        return {"check": "name_consistency", "status": "pass", "reason": f"Name matches across {list(names_found.keys())}."}
    else:
        return {
            "check": "name_consistency",
            "status": "fail",
            "reason": f"Name mismatch detected: {names_found}",
        }


def check_salary_vs_bank_credits(salary_slip_fields: dict, bank_metrics: dict, tolerance: float = 0.15) -> dict:
    """Compares declared net salary against actual average monthly salary credits
    seen in the bank statement. Allows a tolerance since exact match isn't expected
    (e.g. slight timing differences, partial months).
    """
    declared_salary = salary_slip_fields.get("net_salary")
    actual_salary = bank_metrics.get("avg_monthly_salary")

    if declared_salary is None or actual_salary is None:
        return {
            "check": "salary_vs_bank_credits",
            "status": "insufficient_data",
            "reason": "Missing declared salary or bank-observed salary credits to compare.",
        }

    try:
        declared_salary = float(declared_salary)
        actual_salary = float(actual_salary)
    except (TypeError, ValueError):
        return {
            "check": "salary_vs_bank_credits",
            "status": "insufficient_data",
            "reason": "Salary values could not be parsed as numbers.",
        }

    if actual_salary == 0:
        return {"check": "salary_vs_bank_credits", "status": "fail", "reason": "No salary credits found in bank statement despite a declared salary."}

    diff_ratio = abs(declared_salary - actual_salary) / actual_salary
    if diff_ratio <= tolerance:
        return {
            "check": "salary_vs_bank_credits",
            "status": "pass",
            "reason": f"Declared salary (₹{declared_salary:,.0f}) is consistent with bank credits (₹{actual_salary:,.0f}).",
        }
    else:
        return {
            "check": "salary_vs_bank_credits",
            "status": "fail",
            "reason": f"Declared salary (₹{declared_salary:,.0f}) differs from bank-observed salary (₹{actual_salary:,.0f}) by {diff_ratio:.0%}, exceeding the {tolerance:.0%} tolerance.",
        }


def run_cross_verification(documents_by_type: dict, bank_metrics: dict) -> list:
    """Runs all available checks and returns a list of results."""
    results = [
        check_pan_consistency(documents_by_type),
        check_name_consistency(documents_by_type),
    ]

    salary_slip_fields = documents_by_type.get("salary_slip")
    if salary_slip_fields:
        results.append(check_salary_vs_bank_credits(salary_slip_fields, bank_metrics))

    return results