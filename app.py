import os, json, hashlib
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
from pdf_parser import extract_text
import rag_engine
from analyzer import parse_transactions
from pdf_generator import generate_pdf
from datetime import datetime
import os
import uuid
from pymongo import MongoClient
from datetime import datetime

# ---------------- CONFIG ----------------
UPLOAD_DIR = "uploads"
MPESA_DIR = "mpesa_statements"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(MPESA_DIR, exist_ok=True)

# ---------------- DATABASE ----------------
client = MongoClient("mongodb://localhost:27017/")
db = client["Mledger"]
statements_col = db["statements"]

# ---------------- FLASK APP ----------------
app = Flask(__name__)

# ---------------- TEMPLATE FILTER ----------------
@app.template_filter("format_number")
def format_number(value):
    try:
        return "{:,.2f}".format(float(value))
    except:
        return value
    

# ---------------- AUTOMATIC INGESTION ----------------
def auto_ingest_mpesa_statements():
    for pdf_file in Path(MPESA_DIR).glob("*.pdf"):
        # Skip already processed files
        if statements_col.find_one({"filename": pdf_file.name}):
            continue

        try:
            # 🔹 Extract text (handle passwords inside your extract_text if needed)
            text = extract_text(str(pdf_file))
            transactions = parse_transactions(text)

            # 🔹 Calculate totals
            totals = {"income": 0, "expenses": 0, "charges": 0, "balance": 0}
            for t in transactions:
                if t["category"] == "income":
                    totals["income"] += t["amount"]
                elif t["category"] == "expense":
                    totals["expenses"] += t["amount"]
                elif t["category"] == "charge":
                    totals["charges"] += t["amount"]

                totals["balance"] = t.get("balance", totals["balance"])

            # 🔹 Save to MongoDB
            statements_col.insert_one({
                "filename": pdf_file.name,
                "uploaded_at": datetime.utcnow(),
                "transactions": transactions,
                "totals": totals
            })
            print(f"✅ Ingested: {pdf_file.name}")
        except Exception as e:
            print(f"❌ Failed to process {pdf_file.name}: {e}")

# ---------------- GET LATEST STATEMENT ----------------
def get_latest_statement():
    return statements_col.find_one({}, sort=[("uploaded_at", -1)])

# ---------------- FLASK ROUTES ----------------
@app.route("/", methods=["GET", "POST"])
def index():
    latest_txs = []
    totals = {"income": 0, "expenses": 0, "charges": 0, "balance": 0}

    # ---------------- POST: Handle manual upload ----------------
    if request.method == "POST":
        file = request.files.get("statement")
        if file:
            filename = file.filename
            path = os.path.join(MPESA_DIR, filename)
            file.save(path)  # save first!

            # 🔹 Auto-ingest after saving
            auto_ingest_mpesa_statements()

    # ---------------- GET: Load latest statement from MongoDB ----------------
    latest = get_latest_statement()
    if latest:
        latest_txs = latest["transactions"]
        totals = latest["totals"]

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

        # --- Category filter ---
        if type_filter != "all" and tx_category != type_filter:
            continue

        # --- Timeline filter ---
        if start_date and tx_date < datetime.strptime(start_date, "%Y-%m-%d"):
            continue
        if end_date and tx_date > datetime.strptime(end_date, "%Y-%m-%d"):
            continue

        # --- Amount filter ---
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
    data = load_cache()["transactions"] # type: ignore
    out = "report.pdf"
    generate_pdf(data, out)
    return send_file(out, as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True)
