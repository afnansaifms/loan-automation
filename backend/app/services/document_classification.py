"""
Classifies an uploaded loan document into one of: salary_slip, itr, form16, kyc, unknown.
Same two-tier pattern as transaction categorization: keyword rules first
(fast, free, deterministic), LLM fallback only when rules don't match confidently.
"""
import re

DOC_TYPES = ["salary_slip", "itr", "form16", "kyc", "unknown"]

# Keyword patterns checked in order - each tuple is (pattern, doc_type)
CLASSIFICATION_PATTERNS = [
    (r"form\s?16|traces|tax deducted at source certificate", "form16"),
    (r"income tax return|itr-?\d|acknowledgement number.*income tax", "itr"),
    (r"pay\s?slip|salary slip|payslip|net pay|gross earnings", "salary_slip"),
    (r"permanent account number|aadhaar|passport no|driving licen[cs]e|know your customer", "kyc"),
]


def classify_document(raw_text: str) -> str:
    text_lower = raw_text.lower()
    for pattern, doc_type in CLASSIFICATION_PATTERNS:
        if re.search(pattern, text_lower):
            return doc_type
    return "unknown"