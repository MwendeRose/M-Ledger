"""
RAG Engine for M-Ledger
Handles PDF ingestion and AI-powered question answering
"""

from pdf_parser import parse_pdf
import anthropic
import os


def ingest_statement(file_path, password=None):
    """
    Ingest an M-PESA statement PDF and extract transactions.
    Returns a list of transaction dictionaries.
    """
    try:
        transactions, total_income, total_expense, total_charges, balance = parse_pdf(file_path, password)
        return transactions
    except Exception as e:
        raise Exception(f"Failed to ingest statement: {str(e)}") from e


def answer_question(transactions, question):
    """
    Use Claude AI to answer questions about transactions.
    Returns AI-generated answer as a string.
    """
    try:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return "AI chat is not configured. Please set ANTHROPIC_API_KEY environment variable."
        
        transaction_summary = prepare_transaction_summary(transactions)
        client = anthropic.Anthropic(api_key=api_key)
        
        prompt = f"""You are a financial assistant analyzing M-PESA transaction data. 
        
Here is the transaction data:

{transaction_summary}

User question: {question}

Please provide a helpful, accurate answer based on the transaction data above. If calculations are needed, show your work. Be concise but thorough."""

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        return message.content[0].text
        
    except Exception as e:
        return f"Error generating AI response: {str(e)}"


def prepare_transaction_summary(transactions):
    """
    Prepare a summary of transactions for Claude AI.
    """
    if not transactions:
        return "No transactions available."
    
    total_income = sum(t["amount"] for t in transactions if t["category"] == "income")
    total_expenses = sum(t["amount"] for t in transactions if t["category"] == "expense")
    total_charges = sum(t["amount"] for t in transactions if t["category"] == "charge")
    
    dates = [t["date"] for t in transactions if t.get("date")]
    date_range = f"{min(dates)} to {max(dates)}" if dates else "Unknown"
    
    summary = f"""
Transaction Summary:
-------------------
Total Transactions: {len(transactions)}
Date Range: {date_range}
Total Income: KES {total_income:,.2f}
Total Expenses: KES {total_expenses:,.2f}
Total Charges: KES {total_charges:,.2f}
Net Balance: KES {(total_income - total_expenses - total_charges):,.2f}

Recent Transactions (last 10):
"""
    
    for t in transactions[-10:]:
        summary += f"\n- {t['date']} | {t['category'].upper()} | KES {t['amount']:,.2f} | {t['details'][:60]}"
    
    categories = {}
    for t in transactions:
        cat = t['category']
        if cat not in categories:
            categories[cat] = {'count': 0, 'total': 0}
        categories[cat]['count'] += 1
        categories[cat]['total'] += t['amount']
    
    summary += "\n\nCategory Breakdown:"
    for cat, data in categories.items():
        summary += f"\n- {cat.upper()}: {data['count']} transactions, KES {data['total']:,.2f}"
    
    return summary
