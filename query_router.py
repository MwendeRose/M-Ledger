def detect_intent(question):
    q = question.lower()

    if "charge" in q:
        return "charges"
    if "highest" in q and "income" in q:
        return "highest_income"
    if "highest" in q and "expense" in q:
        return "highest_expense"
    if "summary" in q or "overview" in q:
        return "summary"

    return "summary"
