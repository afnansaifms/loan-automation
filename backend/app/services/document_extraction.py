"""
Extracts structured fields from a loan document using Groq, given its
classified type. This is our NER-equivalent: instead of a trained model
(which needs labeled training data we don't have yet), we ask the LLM
for a fixed JSON schema per document type - same pattern used for
transaction extraction in categorization.py.
"""
import json
import re

from groq import Groq

from app.core.config import settings

# The fields we expect per document type - kept as a reference/schema,
# and used directly in the extraction prompts below.
FIELD_SCHEMAS = {
    "salary_slip": ["employee_name", "employer_name", "gross_salary", "net_salary", "pan", "pay_period"],
    "itr": ["taxpayer_name", "pan", "assessment_year", "total_income", "tax_paid"],
    "form16": ["employee_name", "employer_name", "pan", "tan", "gross_salary", "tds_deducted", "assessment_year"],
    "kyc": ["full_name", "date_of_birth", "id_number", "id_type", "address"],
}


def _groq_client() -> Groq:
    return Groq(api_key=settings.groq_api_key)


def extract_fields(doc_type: str, raw_text: str) -> dict:
    """Returns a dict of extracted fields for the given document type.
    Unknown document types return an empty dict - nothing meaningful to extract.
    """
    if doc_type not in FIELD_SCHEMAS:
        return {}

    fields = FIELD_SCHEMAS[doc_type]
    client = _groq_client()

    prompt = f"""Extract the following fields from this {doc_type.replace('_', ' ')} document text.
Fields to extract: {", ".join(fields)}

Return ONLY a JSON object with these exact field names as keys. Use null for any field not found in the text.
Do not include any explanation, just the JSON object.

Document text:
{raw_text[:8000]}"""

    response = client.chat.completions.create(
        model=settings.groq_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    content = response.choices[0].message.content.strip()
    content = re.sub(r"^```(json)?|```$", "", content, flags=re.MULTILINE).strip()

    try:
        result = json.loads(content)
        # Defensive: ensure every expected field is present even if the LLM omitted one
        return {field: result.get(field) for field in fields}
    except json.JSONDecodeError:
        return {field: None for field in fields}