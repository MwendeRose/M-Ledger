import os, json, hashlib
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
from pdf_parser import extract_text_from_image_pdf, parse_mpesa_transactions
import rag_engine
from analyzer import parse_transactions
from pdf_generator import generate_pdf
from datetime import datetime
import os
import uuid
from pymongo import MongoClient
from datetime import datetime
from pdfplumber import open as pdf_open
from pathlib import Path
import traceback
from PyPDF2 import PdfReader

UPLOAD_DIR = "uploads"
MPESA_DIR = "mpesa_statements"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(MPESA_DIR, exist_ok=True)

client = MongoClient("mongodb://localhost:27017/")
db = client["Mledger"]
statements_col = db["statements"]


app = Flask(__name__)

@app.template_filter("format_number")
def format_number(value):
    try:
        return "{:,.2f}".format(float(value))
    except:
        return value

def extract_text_try_all_passwords(pdf_path, passwords_dir="passwords"):
    # Load all passwords from text files
    passwords = []
    for txt_file in Path(passwords_dir).glob("*.txt"):
        with open(txt_file, "r") as f:
            passwords.extend([line.strip() for line in f if line.strip()])

    if not passwords:
        raise ValueError("No passwords found in the passwords directory.")

    print(f"Trying {len(passwords)} passwords for PDF: {pdf_path}")

    for pwd in passwords:
        try:
            reader = PdfReader(pdf_path)

            # Decrypt if necessary
            if reader.is_encrypted:
                result = reader.decrypt(pwd)
                if result == 0:  # decryption failed
                    print(f"Password failed: {pwd}")
                    continue

            # Extract text
            text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"

            print(f"Password succeeded: {pwd}")
            return text  # stop at first working password

        except Exception as e:
            print(f"Error with password {pwd}: {e}")
            continue

    # If we get here, no password worked
    raise ValueError(f"All passwords failed for PDF: {pdf_path}")

def auto_ingest_mpesa_statements():
    for pdf_file in Path(MPESA_DIR).glob("*.pdf"):
        # Skip already ingested files
        if statements_col.find_one({"filename": pdf_file.name}):
            continue

        try:
            # OCR extraction
            text = extract_text_from_image_pdf(str(pdf_file))
            transactions = parse_mpesa_transactions(text)

            if not transactions:
                print(f"No transactions found in {pdf_file.name}, skipping.")
                continue

            # Compute totals
            totals = {"income": 0, "expenses": 0, "charges": 0, "balance": 0}
            for t in transactions:
                if t["category"] == "income":
                    totals["income"] += t["amount"]
                elif t["category"] == "expense":
                    totals["expenses"] += t["amount"]
                elif t["category"] == "charge":
                    totals["charges"] += t["amount"]

            totals["balance"] = transactions[-1]["balance"] if transactions else 0

            # Insert into MongoDB
            statements_col.insert_one({
                "filename": pdf_file.name,
                "uploaded_at": datetime.utcnow(),
                "transactions": transactions,
                "totals": totals
            })
            print(f"Ingested: {pdf_file.name}")

        except Exception as e:
            print(f"Failed to process {pdf_file.name}: {e}")
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
            return jsonify({"status": "error", "message": "No file uploaded"}), 400

        filename = file.filename
        path = os.path.join(MPESA_DIR, filename)
        file.save(path)

        try:
          
            text = extract_text_with_passwords(path) # type: ignore
            transactions = parse_transactions(text)

            totals = {"income": 0, "expenses": 0, "charges": 0, "balance": 0}
            for t in transactions:
                if t["category"] == "income":
                    totals["income"] += t["amount"]
                elif t["category"] == "expense":
                    totals["expenses"] += t["amount"]
                elif t["category"] == "charge":
                    totals["charges"] += t["amount"]
                totals["balance"] = t.get("balance", totals["balance"])

            statements_col.insert_one({
                "filename": filename,
                "uploaded_at": datetime.utcnow(),
                "transactions": transactions,
                "totals": totals
            })

            return jsonify({"status": "success", "message": "Statement processed", "latest": totals})

        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 400

    latest = statements_col.find_one({}, sort=[("uploaded_at", -1)])
    latest_txs = latest["transactions"] if latest else []
    totals = latest["totals"] if latest else {"income":0,"expenses":0,"charges":0,"balance":0}

    return render_template(
        "index.html",
        transactions=latest_txs,
        income=totals["income"],
        expenses=totals["expenses"],
        charges=totals["charges"],
        balance=totals["balance"]
    )


@app.route("/ai_chat", methods=["POST"])
def ai_chat():
    question = request.form.get("question", "").strip()
    if not question:
        return jsonify({"answer": "No question provided."})

    try:
        answer = rag_engine.ask(question)
        return jsonify({"answer": answer})
    except Exception as e:
        import traceback
        print("AI Chat Error:", traceback.format_exc())
        return jsonify({"answer": f"Error generating AI response: {str(e)}"}), 500


@app.route("/filter_transactions", methods=["POST"])
def filter_transactions():
    payload = request.get_json(force=True, silent=True) or {}

    type_filter = payload.get("type_filter", "all")  # income/expense/all
    start_date = payload.get("start_date")
    end_date = payload.get("end_date")
    amount_filter_type = payload.get("amount_filter_type")  # "min" or "max"
    amount_filter_value = payload.get("amount_filter_value")

    transactions = load_cache().get("transactions", []) # type: ignore
    result = []

    for t in transactions:
        tx_category = t.get("category")
        tx_date = datetime.strptime(t["date"], "%Y-%m-%d")
        tx_amount = float(t.get("amount", 0))

     
        if type_filter != "all" and tx_category != type_filter:
            continue

      
        if start_date and tx_date < datetime.strptime(start_date, "%Y-%m-%d"):
            continue
        if end_date and tx_date > datetime.strptime(end_date, "%Y-%m-%d"):
            continue


        if amount_filter_type and amount_filter_value:
            filter_val = float(amount_filter_value)

            if tx_category == "income":
                paid_in = tx_amount
                if amount_filter_type == "min" and paid_in < filter_val:
                    continue
                if amount_filter_type == "max" and paid_in > filter_val:
                    continue

            elif tx_category == "expense":
                paid_out = tx_amount
                if amount_filter_type == "min" and paid_out < filter_val:
                    continue
                if amount_filter_type == "max" and paid_out > filter_val:
                    continue

        result.append(t)

    return jsonify({"transactions": result})

@app.route("/download_pdf")
def download_pdf():
    data = load_cache()["transactions"]  # type: ignore
    out = "report.pdf"
    generate_pdf(data, out)
    return send_file(out, as_attachment=True)

if __name__ == "__main__":
    auto_ingest_mpesa_statements()
    app.run(debug=True, use_reloader=False)
   