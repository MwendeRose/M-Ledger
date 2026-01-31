import pdfplumber
import re
from datetime import datetime

def parse_pdf(file_path, password=None):
    """
    Parses an MPESA PDF statement, optionally using a password.
    Returns transactions and summary info.
    """
    transactions = []
    total_income = 0
    total_expense = 0
    total_charges = 0

    try:
        with pdfplumber.open(file_path, password=password) as pdf:
            text = ""
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"

        lines = text.splitlines()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Regex for date and KES amount
            pattern = r'(\d{1,2}/\d{1,2}/\d{4}).*?(?:KES\s*([\d,]+\.?\d*))'
            match = re.search(pattern, line)
            if match:
                date_str = match.group(1)
                amount = float(match.group(2).replace(',', ''))

                if "received" in line.lower() or "deposit" in line.lower():
                    category = "income"
                    total_income += amount
                elif "sent" in line.lower() or "withdraw" in line.lower():
                    category = "expense"
                    total_expense += amount
                elif "charge" in line.lower() or "fee" in line.lower():
                    category = "charge"
                    total_charges += amount
                else:
                    category = "other"

                transactions.append({
                    "date": datetime.strptime(date_str, "%d/%m/%Y").strftime("%Y-%m-%d"),
                    "details": line[:100],
                    "amount": amount,
                    "category": category,
                    "balance": None
                })

    except Exception as e:
        raise e

    balance = total_income - total_expense - total_charges
    return {
        "transactions": transactions,
        "total_income": total_income,
        "total_expense": total_expense,
        "total_charges": total_charges,
        "balance": balance
    }
