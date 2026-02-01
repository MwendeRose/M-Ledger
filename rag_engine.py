"""
RAG Engine for M-Ledger
Handles PDF ingestion and AI-powered question answering
"""

from pdf_parser import parse_pdf
import anthropic
import os
from datetime import datetime

def ingest_statement(file_path, password=None):
    """
    Ingest an M-PESA statement PDF and extract transactions.
    Returns a list of transaction dictionaries.
    """
    try:
        print(f"\n[INGEST] Processing: {os.path.basename(file_path)}")
        transactions, total_income, total_expense, total_charges, balance = parse_pdf(file_path, password)
        print(f"[INGEST] Success: {len(transactions)} transactions extracted")
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
            return "⚠️ AI chat is not configured. Please set ANTHROPIC_API_KEY environment variable.\n\nExample: export ANTHROPIC_API_KEY='your-key-here'"
        
        print(f"\n[AI CHAT] Processing question: {question[:50]}...")
        transaction_summary = prepare_transaction_summary(transactions)
        client = anthropic.Anthropic(api_key=api_key)
        
        prompt = f"""You are a financial assistant analyzing M-PESA transaction data. 
        
Here is the transaction data:

{transaction_summary}

User question: {question}

Please provide a helpful, accurate answer based on the transaction data above. 
If calculations are needed, show your work. 
Be concise but thorough. Format numbers with commas for thousands.
Use KES as currency."""

        message = client.messages.create(
            model="claude-3-sonnet-20240229",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        print(f"[AI CHAT] Response generated")
        return message.content[0].text
        
    except Exception as e:
        print(f"[AI CHAT] Error: {e}")
        return f"❌ Error generating AI response: {str(e)}"


def prepare_transaction_summary(transactions):
    """
    Prepare a summary of transactions for Claude AI.
    """
    if not transactions:
        return "No transactions available."
    
    total_income = sum(t.get("amount", 0) for t in transactions if t.get("category") == "income")
    total_expenses = sum(t.get("amount", 0) for t in transactions if t.get("category") == "expense")
    total_charges = sum(t.get("amount", 0) for t in transactions if t.get("category") == "charge")
    
    dates = [t.get("date") for t in transactions if t.get("date")]
    valid_dates = [d for d in dates if isinstance(d, str) and len(d) >= 8]
    
    if valid_dates:
        try:
            date_objects = []
            for d in valid_dates:
                try:
                    if "-" in d:
                        date_obj = datetime.strptime(d, "%Y-%m-%d")
                    elif "/" in d:
                        date_obj = datetime.strptime(d, "%d/%m/%Y")
                    else:
                        continue
                    date_objects.append(date_obj)
                except:
                    continue
            
            if date_objects:
                min_date = min(date_objects).strftime("%Y-%m-%d")
                max_date = max(date_objects).strftime("%Y-%m-%d")
                date_range = f"{min_date} to {max_date}"
            else:
                date_range = "Unknown"
        except:
            date_range = "Unknown"
    else:
        date_range = "Unknown"
    
    summary = f"""TRANSACTION ANALYSIS DATA
=====================
Total Transactions: {len(transactions)}
Date Range: {date_range}

FINANCIAL SUMMARY:
• Total Income: KES {total_income:,.2f}
• Total Expenses: KES {total_expenses:,.2f}
• Total Charges: KES {total_charges:,.2f}
• Net Balance: KES {(total_income - total_expenses - total_charges):,.2f}

RECENT TRANSACTIONS (Last 15):
------------------------------"""
    
    for t in transactions[-15:]:
        category = t.get("category", "unknown").upper()
        amount = t.get("amount", 0)
        details = t.get("details", t.get("description", ""))[:60]
        date = t.get("date", "Unknown")
        summary += f"\n• {date} | {category} | KES {amount:,.2f} | {details}"
    
    # Category breakdown
    categories = {}
    for t in transactions:
        cat = t.get("category", "unknown")
        if cat not in categories:
            categories[cat] = {'count': 0, 'total': 0}
        categories[cat]['count'] += 1
        categories[cat]['total'] += t.get("amount", 0)
    
    summary += "\n\nCATEGORY BREAKDOWN:"
    for cat, data in sorted(categories.items()):
        summary += f"\n• {cat.upper()}: {data['count']} transactions, KES {data['total']:,.2f}"
    
    # Add some statistics
    if transactions:
        amounts = [t.get("amount", 0) for t in transactions]
        if amounts:
            avg_amount = sum(amounts) / len(amounts)
            max_amount = max(amounts)
            min_amount = min(amounts)
            summary += f"\n\nSTATISTICS:"
            summary += f"\n• Average transaction: KES {avg_amount:,.2f}"
            summary += f"\n• Largest transaction: KES {max_amount:,.2f}"
            summary += f"\n• Smallest transaction: KES {min_amount:,.2f}"
    
    return summary