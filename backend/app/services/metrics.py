import pandas as pd


def compute_financial_health(transactions: list) -> dict:
    if not transactions:
        return {}

    df = pd.DataFrame(transactions)
    for col in ("debit", "credit", "balance"):
        if col not in df.columns:
            df[col] = None
        df[col] = pd.to_numeric(df[col], errors="coerce")

    salary_credits = df[df.get("category") == "salary"]["credit"].dropna()
    emi_debits = df[df.get("category") == "emi"]["debit"].dropna()
    total_credits = df["credit"].dropna().sum()
    total_debits = df["debit"].dropna().sum()
    avg_balance = df["balance"].dropna().mean() if df["balance"].notna().any() else None

    income_stability = None
    if len(salary_credits) > 1 and salary_credits.mean() != 0:
        income_stability = round(float(salary_credits.std() / salary_credits.mean()), 3)

    emi_to_income = None
    if not emi_debits.empty and not salary_credits.empty and salary_credits.sum() != 0:
        emi_to_income = round(float(emi_debits.sum() / salary_credits.sum()), 3)

    return {
        "average_balance": round(float(avg_balance), 2) if avg_balance is not None else None,
        "income_stability_cv": income_stability,
        "emi_to_income_ratio": emi_to_income,
        "total_credits": round(float(total_credits), 2),
        "total_debits": round(float(total_debits), 2),
        "salary_credit_count": int(len(salary_credits)),
        "avg_monthly_salary": round(float(salary_credits.mean()), 2) if not salary_credits.empty else None,
    }