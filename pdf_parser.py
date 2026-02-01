import pdfplumber
import re
from datetime import datetime
import os

def parse_pdf(file_path, password=None):
    """
    Parse an M-PESA PDF statement into transactions and totals.
    Returns: (transactions, total_income, total_expense, total_charges, balance)
    """
    transactions = []
    total_income = 0
    total_expense = 0
    total_charges = 0

    print(f"\n--- Parsing PDF: {os.path.basename(file_path)} ---")
    
    try:
        # Try to open the PDF
        with pdfplumber.open(file_path, password=password) as pdf:
            print(f"✓ PDF opened successfully")
            print(f"  Pages: {len(pdf.pages)}")
            
            if len(pdf.pages) == 0:
                raise ValueError("PDF has no pages")
            
            text = ""
            for i, page in enumerate(pdf.pages, 1):
                try:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
                        print(f"  Page {i}: {len(page_text)} characters extracted")
                    else:
                        print(f"  Page {i}: No text extracted (might be image-based)")
                except Exception as e:
                    print(f"  Page {i}: Error extracting text - {e}")
                    continue
            
            if not text.strip():
                raise ValueError("No text could be extracted from PDF. The PDF might be image-based or corrupted.")
            
            print(f"✓ Total text extracted: {len(text)} characters")
    
    except Exception as e:
        error_msg = str(e)
        if "password" in error_msg.lower():
            raise Exception(f"Password required or incorrect password provided for this PDF")
        elif "encrypted" in error_msg.lower():
            raise Exception(f"PDF is encrypted. Please provide the correct password.")
        else:
            raise Exception(f"Could not open PDF: {error_msg}")

    # Parse transactions
    lines = text.splitlines()
    print(f"  Processing {len(lines)} lines...")

    transactions_found = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Pattern: date + KES amount
        # Matches formats like: 29/01/2024 ... KES 1,234.56
        pattern = r'(\d{2}/\d{2}/\d{4}).*?(KES\s*[\d,]+\.\d{2})'
        match = re.search(pattern, line)

        if match:
            try:
                date_str = match.group(1)
                amount_str = match.group(2).replace("KES", "").replace(",", "").strip()
                amount = float(amount_str)

                # Categorize transaction
                lower = line.lower()
                if "received" in lower or "deposit" in lower or "reversal" in lower:
                    category = "income"
                    total_income += amount
                elif "sent" in lower or "withdraw" in lower or "paid" in lower or "buy goods" in lower:
                    category = "expense"
                    total_expense += amount
                elif "charge" in lower or "fee" in lower:
                    category = "charge"
                    total_charges += amount
                else:
                    # Default to expense if unclear
                    category = "expense"
                    total_expense += amount

                # Parse and format date
                try:
                    parsed_date = datetime.strptime(date_str, "%d/%m/%Y")
                    formatted_date = parsed_date.strftime("%Y-%m-%d")
                except:
                    formatted_date = date_str

                transactions.append({
                    "date": formatted_date,
                    "details": line[:120],
                    "amount": amount,
                    "category": category,
                    "balance": None,
                    "filename": os.path.basename(file_path)
                })
                transactions_found += 1
                
            except Exception as e:
                print(f"  Warning: Could not parse transaction from line: {line[:50]}... - {e}")
                continue

    print(f"✓ Extracted {transactions_found} transactions")

    if transactions_found == 0:
        print("⚠️  WARNING: No transactions found in PDF")
        print("  This might indicate:")
        print("    - The PDF format is different than expected")
        print("    - The PDF contains no transaction data")
        print("    - The regex pattern needs adjustment")

    # Sort transactions by date
    transactions.sort(key=lambda x: x["date"])

    # Calculate running balance
    running_balance = 0
    for t in transactions:
        if t["category"] == "income":
            running_balance += t["amount"]
        elif t["category"] in ["expense", "charge"]:
            running_balance -= t["amount"]
        t["balance"] = round(running_balance, 2)

    balance = total_income - total_expense - total_charges

    print(f"\n--- Summary ---")
    print(f"  Income: KES {total_income:,.2f}")
    print(f"  Expenses: KES {total_expense:,.2f}")
    print(f"  Charges: KES {total_charges:,.2f}")
    print(f"  Net Balance: KES {balance:,.2f}")
    print("=" * 50 + "\n")

    return transactions, total_income, total_expense, total_charges, balance
