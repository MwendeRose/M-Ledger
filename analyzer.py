def analyze_transactions(transactions):
    income = sum(t["amount"] for t in transactions if t["category"] == "income")
    expenses = sum(t["amount"] for t in transactions if t["category"] == "expense")
    charges = sum(t["amount"] for t in transactions if t["category"] == "charge")
    balance = income - expenses - charges
    return {
        "income": round(income, 2),
        "expenses": round(expenses, 2),
        "charges": round(charges, 2),
        "balance": round(balance, 2)
    }
