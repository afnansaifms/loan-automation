import re

DATE_RE = re.compile(r"^\d{2} [A-Z][a-z]{2} \d{4}$")
AMT_RE = re.compile(r"^INR\s*([\d,]+(?:\.\d+)?)$")
DASH_RE = re.compile(r"^[-\u2013\u2014]$")
HEADER_WORDS = {"Date", "Transaction Details", "Debits", "Credits", "Balance"}


def _cell(line: str):
    """Returns ('amt', value), ('dash', None) or None if the line is not a cell."""
    m = AMT_RE.match(line)
    if m:
        return ("amt", float(m.group(1).replace(",", "")))
    if DASH_RE.match(line):
        return ("dash", None)
    return None


def parse_text_statement(raw_text: str) -> list:
    """Deterministic parser for statements where each transaction is:
    a date line, description lines, then three cells (debit, credit,
    balance), with '-' marking an empty cell. Returns [] if the layout
    doesn't match, so the caller can fall back to the LLM.
    """
    lines = [l.strip() for l in raw_text.split("\n")]

    start = 0
    for i, line in enumerate(lines):
        if line.upper().startswith("ACCOUNT ACTIVITY"):
            start = i + 1
            break

    rows, cur = [], None
    for line in lines[start:]:
        if not line or line in HEADER_WORDS:
            continue

        if DATE_RE.match(line):
            cur = {"date": line, "desc": [], "cells": []}
            continue

        cell = _cell(line)
        if cur is not None and cell is not None:
            cur["cells"].append(cell)
            if len(cur["cells"]) == 3:
                debit_c, credit_c, balance_c = cur["cells"]
                if balance_c[0] == "amt":
                    rows.append({
                        "date": cur["date"],
                        "description": " ".join(cur["desc"]),
                        "debit": debit_c[1],
                        "credit": credit_c[1],
                        "balance": balance_c[1],
                    })
                cur = None
            continue

        # plain text line
        if cur is not None:
            cur["desc"].append(line)
        elif rows:
            # description continued after a page break
            rows[-1]["description"] += " " + line

    return rows
