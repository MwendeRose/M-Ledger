from pdf_parser import parse_pdf

def ingest_statement(pdf_path, password=None):
    """RAG ingestion: parse PDF into transactions"""
    return parse_pdf(pdf_path, password=password)["transactions"]

def answer_question(transactions, question):
    """RAG reasoning: answer questions from transactions"""
    question = question.lower()
    if not transactions:
        return "No transactions available."

    if "income" in question:
        total = sum(t["amount"] for t in transactions if t["category"]=="income")
        return f"Total income: KES {total:,.2f}"

    if "expense" in question or "spending" in question:
        total = sum(t["amount"] for t in transactions if t["category"]=="expense")
        return f"Total expenses: KES {total:,.2f}"

    if "charge" in question or "fee" in question:
        total = sum(t["amount"] for t in transactions if t["category"]=="charge")
        return f"Total charges: KES {total:,.2f}"

    if "balance" in question:
        bal = transactions[-1].get("balance", "Unknown")
        return f"Your latest balance is KES {bal}"

    if "largest" in question or "maximum" in question:
        tx = max(transactions, key=lambda x: x["amount"])
        return f"Largest transaction: KES {tx['amount']:,.2f} on {tx['date']}"

    return "I can answer questions about income, expenses, charges, and balance."
