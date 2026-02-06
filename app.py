import os, json
from flask import Flask, render_template, request, jsonify, send_file
from pdf_parser import extract_text
import rag_engine
from analyzer import parse_transactions
from pdf_generator import generate_pdf

UPLOAD_DIR = "uploads"
MPESA_DIR = "mpesa_statements"
CACHE_FILE = "data_cache.json"

os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)

# ✅ FIX: add format_number filter for your HTML
@app.template_filter("format_number")
def format_number(value):
    try:
        return "{:,.2f}".format(float(value))
    except:
        return value

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    return {"transactions": []}

def save_cache(data):
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f, indent=2)

@app.route("/", methods=["GET", "POST"])
def index():
    data = load_cache()

    if request.method == "POST":
        file = request.files["statement"]
        password = request.form.get("pdf_password")

        path = os.path.join(UPLOAD_DIR, file.filename)
        file.save(path)

        text = extract_text(path)
        if not text:
            return "Could not decrypt PDF", 400

        txs = parse_transactions(text)
        data["transactions"].extend(txs)
        save_cache(data)

        rag_engine.ingest_text(text, file.filename)

    totals = {"income":0,"expenses":0,"charges":0,"balance":0}
    for t in data["transactions"]:
        if t["category"]=="income":
            totals["income"] += t["amount"]
        if t["category"]=="expense":
            totals["expenses"] += t["amount"]
        if t["category"]=="charge":
            totals["charges"] += t["amount"]
        totals["balance"] = t.get("balance", totals["balance"])

    return render_template(
        "index.html",
        transactions=data["transactions"],
        income=totals["income"],
        expenses=totals["expenses"],
        charges=totals["charges"],
        balance=totals["balance"]
    )

@app.route("/ai_chat", methods=["POST"])
def ai_chat():
    q = request.form["question"]
    answer = rag_engine.ask(q)
    return jsonify({"answer": answer})

@app.route("/filter_transactions", methods=["POST"])
def filter_transactions():
    data = load_cache()["transactions"]
    f = request.json

    result = []
    for t in data:
        if f["type_filter"] != "all" and t["category"] != f["type_filter"]:
            continue
        if f["start_date"] and t["date"] < f["start_date"]:
            continue
        if f["end_date"] and t["date"] > f["end_date"]:
            continue
        result.append(t)

    return jsonify({"transactions": result})

@app.route("/download_pdf")
def download_pdf():
    data = load_cache()["transactions"]
    out = "report.pdf"
    generate_pdf(data, out)
    return send_file(out, as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True)
