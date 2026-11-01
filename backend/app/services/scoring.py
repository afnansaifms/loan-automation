"""
Rule-based loan eligibility scoring.

Deterministic gates first — a lender needs to know exactly why an
application was approved/rejected/flagged, not just a black-box number.
Each rule below is a real-world underwriting heuristic; thresholds are
reasonable starting points, tune them once you test on real statements.
"""

# Thresholds - tune these based on real underwriting norms for your context
MIN_AVERAGE_BALANCE = 10000
MAX_EMI_TO_INCOME_RATIO = 0.50
MIN_SALARY_CREDIT_COUNT = 1
MAX_INCOME_STABILITY_CV = 0.35  # higher = more volatile income


def evaluate_eligibility(metrics: dict) -> dict:
    """Returns {"eligibility_flag": ..., "risk_score": ..., "reasons": [...]}.

    eligibility_flag is one of: "approve", "manual_review", "reject"
    risk_score is 0-100, where lower is safer (mirrors typical credit risk scoring)
    reasons is a list of human-readable strings explaining the flags that fired,
    for an officer to see exactly why a decision came out the way it did.
    """
    if not metrics:
        return {
            "eligibility_flag": "manual_review",
            "risk_score": None,
            "reasons": ["No financial data available — insufficient statement data to score."],
        }

    reasons = []
    risk_points = 0  # accumulates; higher = riskier

    avg_balance = metrics.get("average_balance")
    if avg_balance is None:
        reasons.append("Average balance could not be determined.")
        risk_points += 20
    elif avg_balance < MIN_AVERAGE_BALANCE:
        reasons.append(f"Average balance (₹{avg_balance:,.0f}) is below the minimum threshold (₹{MIN_AVERAGE_BALANCE:,.0f}).")
        risk_points += 30

    emi_ratio = metrics.get("emi_to_income_ratio")
    if emi_ratio is not None and emi_ratio > MAX_EMI_TO_INCOME_RATIO:
        reasons.append(f"EMI-to-income ratio ({emi_ratio:.0%}) exceeds the safe threshold ({MAX_EMI_TO_INCOME_RATIO:.0%}).")
        risk_points += 35
    elif emi_ratio is not None:
        # reward low EMI burden slightly
        risk_points += emi_ratio * 20

    salary_count = metrics.get("salary_credit_count", 0)
    if salary_count < MIN_SALARY_CREDIT_COUNT:
        reasons.append("No identifiable salary credits found in the statement period.")
        risk_points += 25

    income_cv = metrics.get("income_stability_cv")
    if income_cv is not None and income_cv > MAX_INCOME_STABILITY_CV:
        reasons.append(f"Income shows high volatility (CV={income_cv}), above the stable threshold ({MAX_INCOME_STABILITY_CV}).")
        risk_points += 20

    risk_score = round(min(risk_points, 100), 1)

    if risk_score >= 60:
        eligibility_flag = "reject"
    elif risk_score >= 30:
        eligibility_flag = "manual_review"
    else:
        eligibility_flag = "approve"

    if not reasons:
        reasons.append("All eligibility checks passed.")

    return {
        "eligibility_flag": eligibility_flag,
        "risk_score": risk_score,
        "reasons": reasons,
    }