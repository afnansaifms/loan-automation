import json
import re
import time

from groq import Groq, RateLimitError

from app.core.config import settings

CATEGORIES = [
    "salary", "emi", "rent", "utilities", "investment",
    "merchant_spend", "transfer", "cash_withdrawal", "other",
]

RULE_PATTERNS = [
    (r"\bsalary\b|\bsal\s?cr\b|\bpayroll\b", "salary"),
    (r"\bemi\b|\bloan\s?repay", "emi"),
    (r"\brent\b|\blandlord\b", "rent"),
    (r"\belectricity\b|\bwater bill\b|\bgas bill\b|\bbroadband\b|\brecharge\b", "utilities"),
    (r"\bmutual fund\b|\bsip\b|\bstocks?\b|\bzerodha\b|\bgroww\b|\bnps\b", "investment"),
    (r"\batm\s+(cash\s+)?(wdl|withdrawal)\b|\bcash\s?wdl\b|\bcash withdrawal\b", "cash_withdrawal"),
    (r"\bneft\b|\bimps\b|\bupi\b.*\btransfer\b|\bfund transfer\b", "transfer"),
]

CHUNK_SIZE = 5000
CHUNK_OVERLAP = 500
BATCH_SIZE = 20


def rule_based_category(description: str):
    desc_lower = (description or "").lower()
    for pattern, category in RULE_PATTERNS:
        if re.search(pattern, desc_lower):
            return category
    return None


def _groq_client():
    return Groq(api_key=settings.groq_api_key)


def _parse_json(content: str):
    content = re.sub(r"^```(json)?|```$", "", content.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        print("JSON PARSE FAILED:", content[:300])
        return None


def _chat_json(prompt: str, model: str = None, max_tokens: int = 4096):
    """One LLM call that returns parsed JSON (or None on failure).
    Retries only on rate limits; other errors fail fast so config
    mistakes (like a wrong model name) show up immediately.
    """
    model = model or settings.groq_model
    kwargs = {}
    if "gpt-oss" in model:
        # reasoning model: keep thinking short, leave token room for it
        kwargs["extra_body"] = {"reasoning_effort": "low"}
        max_tokens = max_tokens + 2048
    else:
        kwargs["response_format"] = {"type": "json_object"}

    client = _groq_client()
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=max_tokens,
                **kwargs,
            )
            choice = response.choices[0]
            if choice.finish_reason == "length":
                print(f"WARNING: LLM hit its token limit (model={model})")
            return _parse_json(choice.message.content or "")
        except RateLimitError:
            wait = 15 * (attempt + 1)
            print(f"Rate limited, waiting {wait}s...")
            time.sleep(wait)
        except Exception as e:
            print(f"LLM call failed: {e}")
            return None
    return None


def llm_categorize_batch(descriptions: list) -> list:
    results = []
    for i in range(0, len(descriptions), BATCH_SIZE):
        batch = descriptions[i:i + BATCH_SIZE]
        prompt = f"""Classify each bank transaction description into exactly one of these categories:
{", ".join(CATEGORIES)}

Return ONLY a JSON object like {{"categories": ["salary", "other"]}} with one category per
description, in the same order as the input.

Transactions:
{json.dumps(batch)}"""
        data = _chat_json(prompt, max_tokens=1024)
        cats = data.get("categories") if isinstance(data, dict) else data
        if isinstance(cats, list) and len(cats) == len(batch):
            results.extend(c if c in CATEGORIES else "other" for c in cats)
        else:
            results.extend(["other"] * len(batch))
    return results


def categorize_transactions(transactions: list) -> list:
    llm_indices, llm_descriptions = [], []
    for i, txn in enumerate(transactions):
        description = txn.get("description") or ""
        rule_cat = rule_based_category(description)
        if rule_cat:
            txn["category"] = rule_cat
            txn["category_source"] = "rule"
        else:
            llm_indices.append(i)
            llm_descriptions.append(description)

    if llm_descriptions:
        llm_results = llm_categorize_batch(llm_descriptions)
        for idx, category in zip(llm_indices, llm_results):
            transactions[idx]["category"] = category
            transactions[idx]["category_source"] = "llm"
    return transactions


def _chunk_text(text: str) -> list:
    chunks, start = [], 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        if end < len(text):
            newline = text.rfind("\n", start, end)
            if newline > start + CHUNK_SIZE // 2:
                end = newline
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return chunks


def extract_transactions_via_llm(raw_text: str) -> list:
    """Extracts transactions chunk by chunk so long statements never
    exceed the model's output limit, then removes duplicates caused
    by the overlap between chunks.
    """
    model = settings.groq_extraction_model or settings.groq_model
    chunks = _chunk_text(raw_text)
    print(f"Extracting from {len(raw_text)} chars in {len(chunks)} chunks (model={model})")

    all_rows = []
    for n, chunk in enumerate(chunks, start=1):
        prompt = f"""Extract every transaction from this bank statement excerpt.
Return ONLY a JSON object: {{"transactions": [{{"date": "...", "description": "...", "debit": 0.0, "credit": 0.0, "balance": 0.0}}]}}

Rules:
- debit, credit and balance are plain numbers (no currency symbols or commas). A "-" or blank means null.
- balance is the running balance after that transaction.
- description is the full transaction detail text joined into one line.
- Ignore headers, account details, summaries and totals.
- Skip any transaction that is cut off at the start or end of the excerpt.

Excerpt:
{chunk}"""
        data = _chat_json(prompt, model=model, max_tokens=4096)
        rows = data.get("transactions") if isinstance(data, dict) else data
        rows = rows if isinstance(rows, list) else []
        print(f"  chunk {n}/{len(chunks)}: {len(rows)} rows")
        all_rows.extend(r for r in rows if isinstance(r, dict))

    seen, unique = set(), []
    for r in all_rows:
        if not r.get("date") or r.get("balance") is None:
            continue
        key = (r.get("date"), r.get("debit"), r.get("credit"), r.get("balance"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)
    return unique