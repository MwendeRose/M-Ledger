import os, json, hashlib
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for
from datetime import datetime
import traceback
from PyPDF2 import PdfReader
import pytesseract
from pdf2image import convert_from_path
from pymongo import MongoClient 
import re
import pandas as pd

# Import your existing modules (keep these as they are)
try:
    import ai_rag 
    from ai_rag import ask_latest_statement
except ImportError:
    print("Warning: ai_rag module not found")
    ask_latest_statement = None

try:
    from pdf_generator import generate_pdf
except ImportError:
    print("Warning: pdf_generator module not found")
    generate_pdf = None

UPLOAD_DIR = "uploads"
MPESA_DIR = "mpesa_statements"

os.makedirs(UPLOAD_DIR, exist_ok=True) 
os.makedirs(MPESA_DIR, exist_ok=True)

client = MongoClient("mongodb://localhost:27017/")
db = client["Mledger"]
statements_col = db["statements"]

app = Flask(__name__)
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
poppler_path = r"C:\poppler-23.06.0\Library\bin"


@app.template_filter("format_number")
def format_number(value):
    try:
        return "{:,.2f}".format(float(value))
    except:
        return value


def parse_mpesa_transactions(text):
    """
    Parse M-Pesa statement text and extract transactions with proper categorization.
    This is the FIXED version that correctly categorizes M-Shwari transactions.
    """
    transactions = []
    
    # Pattern to match M-Pesa transaction lines
    # Example: "UAUB95B87M 2026-01-30 19:00:20 M-Shwari Withdraw Completed 500.00 729.40"
    pattern = r'([A-Z0-9]+)\s+(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})\s+(.+?)\s+Completed\s+([-]?[\d,]+\.\d{2})\s+([\d,]+\.\d{2})'
    
    matches = re.findall(pattern, text)
    
    for match in matches:
        reference, date_str, time_str, transaction_desc, amount_str, balance_str = match
        
        # Parse datetime
        datetime_str = f"{date_str} {time_str}"
        try:
            transaction_datetime = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        
        # Clean amount and balance (remove commas)
        amount_str_clean = amount_str.replace(',', '')
        balance_str_clean = balance_str.replace(',', '')
        
        try:
            amount_value = float(amount_str_clean)
            balance_value = float(balance_str_clean)
        except ValueError:
            continue
        
        # Determine transaction type and category
        transaction_type, category, party = categorize_transaction(transaction_desc, amount_value)
        
        # Amount should always be positive for storage
        amount_abs = abs(amount_value)
        
        transaction = {
            "datetime": transaction_datetime,
            "date": date_str,
            "time": time_str,
            "reference": reference,
            "transaction_type": transaction_type,
            "party": party,
            "amount": amount_abs,
            "category": category,
            "balance": balance_value,
            "description": transaction_desc.strip()
        }
        
        transactions.append(transaction)
    
    return transactions


def categorize_transaction(description, amount_value):
    """
    Categorize M-Pesa transaction based on description.
    
    Returns: (transaction_type, category, party)
    - transaction_type: Human-readable type
    - category: 'income', 'expense', or 'charge'
    - party: Other party involved (if applicable)
    """
    desc_lower = description.lower()
    party = None
    
    # M-Shwari Withdraw = Money FROM M-Shwari TO M-Pesa = INCOME (money coming in)
    if 'm-shwari withdraw' in desc_lower:
        return ('M-Shwari Withdrawal', 'income', 'M-Shwari')
    
    # M-Shwari Deposit = Money FROM M-Pesa TO M-Shwari = EXPENSE (money going out)
    if 'm-shwari deposit' in desc_lower:
        return ('M-Shwari Deposit', 'expense', 'M-Shwari')
    
    # Airtime purchases - extract phone number if present
    if 'airtime' in desc_lower:
        # Try to extract phone number
        phone_match = re.search(r'(\d{10,12})', description)
        if phone_match:
            party = phone_match.group(1)
        return ('Airtime Purchase', 'expense', party)
    
    # Pay Bill transactions - extract business number/name
    if 'pay bill' in desc_lower:
        if 'charge' in desc_lower:
            return ('PayBill Charge', 'charge', None)
        # Try to extract business number or name
        business_match = re.search(r'(?:pay bill|paybill)\s+(?:to\s+)?([A-Z0-9\s]+?)(?:\s+|$)', description, re.IGNORECASE)
        if business_match:
            party = business_match.group(1).strip()
        return ('PayBill Payment', 'expense', party)
    
    # Withdrawal from agent
    if 'withdrawal' in desc_lower and 'charge' in desc_lower:
        return ('Withdrawal Charge', 'charge', None)
    
    if 'withdraw' in desc_lower and 'agent' in desc_lower:
        # Try to extract agent number
        agent_match = re.search(r'agent\s+(\d+)', description, re.IGNORECASE)
        if agent_match:
            party = f"Agent {agent_match.group(1)}"
        return ('Agent Withdrawal', 'expense', party)
    
    # Send Money transactions - extract recipient name/number
    if 'send money' in desc_lower or 'sent to' in desc_lower:
        # Try multiple patterns for recipient
        party_match = re.search(r'(?:sent to|send money to)\s+([A-Z][A-Z\s\.]+?)(?:\s+\d|$)', description, re.IGNORECASE)
        if not party_match:
            party_match = re.search(r'(?:sent to|send money to)\s+(\d{10,12})', description, re.IGNORECASE)
        if party_match:
            party = party_match.group(1).strip()
        return ('Send Money', 'expense', party)
    
    # Receive Money transactions - extract sender name/number
    if 'received from' in desc_lower or 'customer deposit' in desc_lower:
        # Try multiple patterns for sender
        party_match = re.search(r'(?:received from|from)\s+([A-Z][A-Z\s\.]+?)(?:\s+\d|$)', description, re.IGNORECASE)
        if not party_match:
            party_match = re.search(r'(?:received from|from)\s+(\d{10,12})', description, re.IGNORECASE)
        if party_match:
            party = party_match.group(1).strip()
        return ('Received Money', 'income', party)
    
    # Buy Goods transactions - extract till/merchant
    if 'buy goods' in desc_lower:
        if 'charge' in desc_lower:
            return ('Buy Goods Charge', 'charge', None)
        # Try to extract till number or merchant name
        till_match = re.search(r'(?:buy goods|till)\s+(?:from\s+)?([A-Z0-9][A-Z0-9\s]+?)(?:\s+|$)', description, re.IGNORECASE)
        if till_match:
            party = till_match.group(1).strip()
        return ('Buy Goods', 'expense', party)
    
    # HELB or other specific charges
    if 'helb' in desc_lower:
        return ('HELB Charge', 'charge', 'HELB')
    
    # Savings transactions
    if 'savings contribution' in desc_lower or 'savings' in desc_lower:
        return ('Savings', 'expense', None)
    
    # Fuliza transactions
    if 'fuliza' in desc_lower:
        if 'repayment' in desc_lower:
            return ('Fuliza Repayment', 'expense', 'Fuliza')
        return ('Fuliza Loan', 'income', 'Fuliza')
    
    # Default categorization based on amount sign
    if amount_value < 0:
        if 'charge' in desc_lower or 'fee' in desc_lower:
            return ('Charge/Fee', 'charge', None)
        return ('Expense', 'expense', None)
    else:
        return ('Income', 'income', None)


def calculate_totals(transactions):
    """
    Calculate totals from transactions.
    Returns dict with income, expenses, charges, and balance.
    """
    totals = {
        "income": 0,
        "expenses": 0,
        "charges": 0,
        "balance": 0
    }
    
    for txn in transactions:
        category = txn.get("category", "")
        amount = txn.get("amount", 0)
        
        if category == "income":
            totals["income"] += amount
        elif category == "expense":
            totals["expenses"] += amount
        elif category == "charge":
            totals["charges"] += amount
    
    # Use the last transaction's balance as the final balance
    if transactions:
        totals["balance"] = transactions[-1].get("balance", 0)
    
    return totals


def extract_text_from_image_pdf_with_passwords(pdf_path, passwords_dir="passwords", poppler_path=None):
    """
    Tries passwords to decrypt the PDF.
    Converts pages to images and runs OCR.
    Returns extracted text.
    """
    passwords = []
    for txt_file in Path(passwords_dir).glob("*.txt"):
        with open(txt_file, "r") as f:
            passwords.extend([line.strip() for line in f if line.strip()])

    if not passwords:
        raise ValueError("No passwords found in passwords directory.")

    for pwd in passwords:
        try:
            reader = PdfReader(pdf_path)
            if reader.is_encrypted:
                result = reader.decrypt(pwd)
                if result == 0:
                    continue

            text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"

            if text.strip():
                print(f"Password succeeded (text-based PDF): {pwd}")
                return text

            # If no text extracted, try OCR
            print(f"Converting PDF to images for OCR: {pdf_path}")
            images = convert_from_path(pdf_path, poppler_path=poppler_path)

            ocr_text = ""
            for i, image in enumerate(images, start=1):
                ocr_text += pytesseract.image_to_string(image) + "\n"
                print(f"Processed page {i}/{len(images)}")
            print(f"Password succeeded (OCR): {pwd}")
            return ocr_text

        except Exception as e:
            print(f"Error with password {pwd}: {e}")
            continue

    raise Exception(f"All passwords failed. Could not open PDF: {pdf_path}")


def auto_ingest_mpesa_statements():
    """
    Auto-ingest PDFs from the statements directory.
    Now with CORRECT parsing and totals calculation.
    """
    for pdf_file in Path(MPESA_DIR).glob("*.pdf"):
        # Skip if already processed
        if statements_col.find_one({"filename": pdf_file.name}):
            print(f"Skipping {pdf_file.name} - already in database")
            continue

        try:
            print(f"Processing: {pdf_file.name}")

            # Extract text from PDF
            text = extract_text_from_image_pdf_with_passwords(
                str(pdf_file),
                passwords_dir="passwords",
                poppler_path=poppler_path
            )

            # Parse transactions with FIXED logic
            transactions = parse_mpesa_transactions(text)

            if not transactions:
                print(f"No transactions found in {pdf_file.name}, skipping.")
                continue

            # Calculate totals
            totals = calculate_totals(transactions)

            # Store in MongoDB
            statements_col.insert_one({
                "filename": pdf_file.name,
                "uploaded_at": datetime.utcnow(),
                "transactions": transactions,
                "totals": totals
            })

            print(f" Successfully ingested: {pdf_file.name}")
            print(f"   Transactions: {len(transactions)}")
            print(f"   Income: {totals['income']:.2f}")
            print(f"   Expenses: {totals['expenses']:.2f}")
            print(f"   Charges: {totals['charges']:.2f}")
            print(f"   Balance: {totals['balance']:.2f}")

        except Exception as e:
            print(f" Failed to process {pdf_file.name}: {e}")
            traceback.print_exc()
            continue


def get_latest_statement():
    """Return the most recently uploaded statement."""
    return statements_col.find_one({}, sort=[("uploaded_at", -1)])


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        file = request.files.get("statement")
        if not file:
            return "No file uploaded", 400

        os.makedirs(MPESA_DIR, exist_ok=True)
        path = os.path.join(MPESA_DIR, file.filename)
        file.save(path)

        try:
            # Extract text
            text = extract_text_from_image_pdf_with_passwords(
                path,
                passwords_dir="passwords",
                poppler_path=poppler_path
            )
            
            # Parse with FIXED logic
            transactions = parse_mpesa_transactions(text)

            if not transactions:
                return "No transactions found in the uploaded file", 400

            # Calculate totals
            totals = calculate_totals(transactions)

            # Store in MongoDB
            statements_col.insert_one({
                "filename": file.filename,
                "uploaded_at": datetime.utcnow(),
                "transactions": transactions,
                "totals": totals
            })

            return redirect(url_for("index"))

        except Exception as e:
            return f"Error processing file: {str(e)}", 500

    # Get latest statement
    latest = statements_col.find_one({}, sort=[("uploaded_at", -1)])

    if not latest:
        return render_template(
            "index.html",
            transactions=[],
            totals={},
            uploaded_at=None,
            filename=None
        )

    return render_template(
        "index.html",
        transactions=latest.get("transactions", []),
        totals=latest.get("totals", {}),
        uploaded_at=latest.get("uploaded_at"),
        filename=latest.get("filename"),
        total_transactions=len(latest.get("transactions", []))
    )

@app.route("/ai_chat", methods=["POST"])
def ai_chat():
    """AI chat endpoint - uses your existing ai_rag module"""
    question = request.form.get("question", "").strip()
    if not question:
        return jsonify({"answer": "No question provided."})

    try:
        # Call the function properly
        answer = ask_latest_statement(question)
        return jsonify({"answer": answer})
    except Exception as e:
        return jsonify({"answer": f"AI error: {str(e)}"}), 500



@app.route("/filter_transactions", methods=["POST"])
def filter_transactions():
    """Filter transactions by type and date range"""
    try:
        payload = request.get_json(force=True, silent=True) or {}

        type_filter = payload.get("type_filter", "all").lower()
        start_date = payload.get("start_date")
        end_date = payload.get("end_date")

        # Load transactions from MongoDB
        latest = statements_col.find_one({}, sort=[("uploaded_at", -1)])
        transactions = latest.get("transactions", []) if latest else []

        result = []

        for t in transactions:
            tx_category = (t.get("category") or "").lower()
            tx_date_str = t.get("date")
            tx_amount = t.get("amount") or 0
            tx_balance = t.get("balance") or 0
            tx_description = t.get("description") or "-"
            tx_type = t.get("transaction_type") or "-"

            # Skip if no valid date
            if not tx_date_str:
                continue
            
            try:
                tx_date = datetime.strptime(tx_date_str, "%Y-%m-%d")
            except ValueError:
                continue

            # Type filter
            if type_filter != "all" and tx_category != type_filter:
                continue

            # Date range filter
            if start_date:
                try:
                    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                    if tx_date < start_dt:
                        continue
                except ValueError:
                    pass
            
            if end_date:
                try:
                    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                    if tx_date > end_dt:
                        continue
                except ValueError:
                    pass

            # Add transaction to result
            result.append({
                "date": tx_date_str,
                "time": t.get("time") or "-",
                "reference": t.get("reference") or "-",
                "description": tx_description,
                "type": tx_type,
                "category": tx_category,
                "amount": tx_amount,
                "balance": tx_balance,
                "party": t.get("party") or "-"
            })

        return jsonify({"transactions": result})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"transactions": [], "error": str(e)}), 500


@app.route("/download_pdf")
def download_pdf():
    """Generate PDF report of transactions"""
    try:
        # Get latest statement
        latest = statements_col.find_one({}, sort=[("uploaded_at", -1)])
        
        if not latest:
            return "No statements found", 404
        
        transactions = latest.get("transactions", [])
        
        if generate_pdf:
            out = "report.pdf"
            generate_pdf(transactions, out)
            return send_file(out, as_attachment=True)
        else:
            return "PDF generation not available", 500
            
    except Exception as e:
        return f"Error generating PDF: {str(e)}", 500


if __name__ == "__main__":
    print("=" * 80)
    print("M-PESA STATEMENT PROCESSOR - FIXED VERSION")
    print("=" * 80)
    print("\nAuto-ingesting statements from:", MPESA_DIR)
    print()
    
    auto_ingest_mpesa_statements()
    
    print("\n" + "=" * 80)
    print("Starting Flask application...")
    print("=" * 80)
    
    app.run(debug=True, use_reloader=False)