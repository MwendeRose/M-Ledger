from collections import defaultdict
from datetime import datetime


def analyze(transactions, start=None, end=None):
    filtered = []

    for t in transactions:
        d = datetime.strptime(t["date"], "%Y-%m-%d").date() if isinstance(t["date"], str) else t["date"]
        if start and d < start:
            continue
        if end and d > end:
            continue
        filtered.append(t)

    income = sum(t["amount"] for t in filtered if t["category"] == "income")
    expense = sum(t["amount"] for t in filtered if t["category"] == "expense")
    charges = sum(t["amount"] for t in filtered if t["category"] == "charge")

    by_day = defaultdict(lambda: {"income": 0, "expense": 0, "charge": 0})

    for t in filtered:
        by_day[t["date"]][t["category"]] += t["amount"]

    def best_day(metric):
        if not by_day:
            return None, 0
        d, v = max(by_day.items(), key=lambda x: x[1][metric])
        return d, v[metric]

    hi_day, hi_amt = best_day("income")
    he_day, he_amt = best_day("expense")
    hc_day, hc_amt = best_day("charge")

    return {
        "period": f"{start} to {end}" if start or end else "All Time",
        "total_income": round(income, 2),
        "total_expense": round(expense, 2),
        "total_charges": round(charges, 2),
        "net": round(income - expense - charges, 2),
        "average_income_per_transaction": round(income / max(1, len([t for t in filtered if t["category"] == "income"])), 2),
        "average_expense_per_transaction": round(expense / max(1, len([t for t in filtered if t["category"] == "expense"])), 2),
        "highest_income_day": {"date": hi_day, "amount": hi_amt} if hi_day else None,
        "highest_expense_day": {"date": he_day, "amount": he_amt} if he_day else None,
        "highest_charge_day": {"date": hc_day, "amount": hc_amt} if hc_day else None,
        "transaction_count": len(filtered)
    }
