import os
import io
import json
import pdfplumber
from datetime import datetime

from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

from rag_engine import ingest_statement, answer_question

app = Flask(__name__)
CORS(app)

# ----------------- CONFIG -----------------
PDF_DIR = "mpesa_statements"
PASSWORD_DIR = "passwords"

os.makedirs(PDF_DIR, exist_ok=True)
os.makedirs(PASSWORD_DIR, exist_ok=True)

# Allow large uploads (50MB)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

transactions_cache = []
scan_results = []
processed_files = set()

CATEGORY_MAP = {
    "paid_in": "income",
    "paid_out": "expense",
    "transaction_cost": "charge",
    "charge": "charge",
    "income": "income",
    "expense": "expense"
}

# ----------------- HELPERS -----------------
@app.template_filter("format_number")
def format_number(value):
    try:
        return "{:,.2f}".format(float(value))
    except Exception:
        return value

def parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except Exception:
        return None

def get_all_passwords():
    passwords = []
    for file in os.listdir(PASSWORD_DIR):
        if file.endswith(".txt") and file != "password_mapping.json":
            try:
                with open(os.path.join(PASSWORD_DIR, file)) as f:
                    pwd = f.read().strip()
                    if pwd:
                        passwords.append(pwd)
            except Exception:
                pass
    return passwords

def try_all_passwords(pdf_path):
    try:
        with pdfplumber.open(pdf_path):
            return None
    except Exception:
        pass

    for pwd in get_all_passwords():
        try:
            with pdfplumber.open(pdf_path, password=pwd):
                return pwd
        except Exception:
            continue

    return None

def get_password(filename):
    base = os.path.splitext(filename)[0]

    exact = os.path.join(PASSWORD_DIR, base + ".txt")
    if os.path.exists(exact):
        return open(exact).read().strip()

    mapping_file = os.path.join(PASSWORD_DIR, "password_mapping.json")
    if os.path.exists(mapping_file):
        try:
            mapping = json.load(open(mapping_file))
            for pattern, pwd_file in mapping.items():
                if pattern.lower() in base.lower():
                    path = os.path.join(PASSWORD_DIR, pwd_file)
                    if os.path.exists(path):
                        return open(path).read().strip()
        except Exception:
            pass

    default = os.path.join(PASSWORD_DIR, "default.txt")
    if os.path.exists(default):
        return open(default).read().strip()

    return None

def auto_scan_pdfs():
    global transactions_cache, scan_results, processed_files

    transactions_cache.clear()
    scan_results.clear()
    processed_files.clear()

    for file in os.listdir(PDF_DIR):
        if not file.lower().endswith(".pdf"):
            continue
        if file in processed_files:
            continue

        path = os.path.join(PDF_DIR, file)
        try:
            password = get_password(file) or try_all_passwords(path)
            result = ingest_statement(path, password=password)
            tx = result if isinstance(result, list) else result.get("transactions", [])

            clean_tx = []
            for t in tx:
                if not {"date", "amount", "category"}.issubset(t):
                    continue
                t["category"] = CATEGORY_MAP.get(t["category"], t["category"])
                clean_tx.append(t)

            transactions_cache.extend(clean_tx)
            processed_files.add(file)

            scan_results.append({
                "file": file,
                "status": "success",
                "message": f"{len(clean_tx)} transactions processed",
                "password_used": password is not None
            })

        except Exception as e:
            scan_results.append({
                "file": file,
                "status": "failed",
                "message": str(e)
            })

# ----------------- ROUTES -----------------
@app.route("/", methods=["GET", "POST"])
def index():
    upload_success = False
    upload_message = ""

    if request.method == "POST":
        uploaded_file = request.files.get("statement")
        pdf_password = request.form.get("pdf_password", "").strip()

        if uploaded_file:
            filename = uploaded_file.filename
            # Only allow PDFs
            if not filename.lower().endswith(".pdf"):
                upload_message = "Only PDF files are allowed."
            else:
                safe_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
                save_path = os.path.join(PDF_DIR, safe_name)

                try:
                    uploaded_file.save(save_path)
                    print(f"File saved: {save_path}")

                    # Use provided password or try all
                    if not pdf_password:
                        pdf_password = try_all_passwords(save_path)
                    print(f"Using password: {pdf_password}")

                    result = ingest_statement(save_path, password=pdf_password)
                    tx = result if isinstance(result, list) else result.get("transactions", [])

                    clean_tx = []
                    for t in tx:
                        if {"date", "amount", "category"}.issubset(t):
                            t["category"] = CATEGORY_MAP.get(t["category"], t["category"])
                            clean_tx.append(t)

                    transactions_cache.extend(clean_tx)
                    processed_files.add(safe_name)

                    upload_success = True
                    upload_message = f"{safe_name} uploaded successfully ({len(clean_tx)} transactions)"

                except Exception as e:
                    upload_message = f"Failed to process PDF: {str(e)}"
                    print("Upload error:", e)
        else:
            upload_message = "No file was selected."

    # Compute summary
    income = sum(t["amount"] for t in transactions_cache if t["category"] == "income")
    expenses = sum(t["amount"] for t in transactions_cache if t["category"] == "expense")
    charges = sum(t["amount"] for t in transactions_cache if t["category"] == "charge")
    balance = income - expenses - charges

    return render_template(
        "index.html",
        income=income,
        expenses=expenses,
        charges=charges,
        balance=balance,
        transactions=transactions_cache,
        scan_results=scan_results,
        upload_success=upload_success,
        upload_message=upload_message
    )

@app.route("/filter_transactions", methods=["POST"])
def filter_transactions():
    data = request.get_json()
    ttype = data.get("type_filter", "all")
    start = parse_date(data.get("start_date")) if data.get("start_date") else None
    end = parse_date(data.get("end_date")) if data.get("end_date") else None

    filtered = transactions_cache
    if ttype != "all":
        filtered = [t for t in filtered if t["category"] == ttype]

    if start:
        filtered = [t for t in filtered if parse_date(t["date"]) and parse_date(t["date"]) >= start]

    if end:
        filtered = [t for t in filtered if parse_date(t["date"]) and parse_date(t["date"]) <= end]

    return jsonify({"transactions": filtered})

@app.route("/ai_chat", methods=["POST"])
def ai_chat():
    question = request.form.get("question")
    answer = answer_question(transactions_cache[-500:], question)
    return jsonify({"answer": answer})

@app.route("/download_pdf")
def download_pdf():
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    text = c.beginText(40, 750)
    y = 750

    for t in transactions_cache:
        if y < 50:
            c.drawText(text)
            c.showPage()
            text = c.beginText(40, 750)
            y = 750
        line = f"{t['date']} | {t['category']} | {t['amount']} | {t.get('details','')}"
        text.textLine(line)
        y -= 14

    c.drawText(text)
    c.save()
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="M-Ledger_Report.pdf",
        mimetype="application/pdf"
    )

@app.route("/rescan")
def rescan():
    auto_scan_pdfs()
    return jsonify({
        "status": "success",
        "total_transactions": len(transactions_cache)
    })

# ----------------- START -----------------
if __name__ == "__main__":
    auto_scan_pdfs()
    app.run(debug=True)
