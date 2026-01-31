import pdfplumber
from datetime import datetime

def parse_pdf(pdf_path, password=None):
    transactions = []

    with pdfplumber.open(pdf_path, password=password) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if not table:
                continue

            for row in table[1:]:
                if not row or len(row) < 4:
                    continue

                date_str, details, amount_str, balance_str = row[:4]

                try:
                    date_obj = datetime.strptime(date_str.strip(), "%d/%m/%Y")
                    amount = float(amount_str.replace(",", ""))
                    balance = float(balance_str.replace(",", ""))
                except:
                    continue

                text = details.lower()
                if "received" in text:
                    category = "income"
                elif "charge" in text or "fee" in text:
                    category = "charge"
                else:
                    category = "expense"

                transactions.append({
                    "date": date_obj.strftime("%Y-%m-%d"),
                    "details": details.strip(),
                    "amount": round(amount, 2),
                    "balance": round(balance, 2),
                    "category": category
                })

    return transactions
