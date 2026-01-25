from flask import Flask, render_template, request, jsonify
from datetime import datetime
from pdf_parser import parse_mpesa_pdf
from analyzer import analyze
from llm_explainer import explain

app = Flask(__name__)
app.secret_key = "mledger_secret"

# Persistent server-side storage
app.config["STORED_TRANSACTIONS"] = []


# -------------------------------------------------
# HOME ROUTE (UPLOAD + DASHBOARD)
# -------------------------------------------------
@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        file = request.files.get("statement")
        password = request.form.get("pdf_password")

        if file:
            tx = parse_mpesa_pdf(file, password)
            app.config["STORED_TRANSACTIONS"] = tx

    stored_transactions = app.config["STORED_TRANSACTIONS"]

    sorted_transactions = sorted(
        stored_transactions, key=lambda t: t["date"], reverse=True
    )

    summary = analyze(sorted_transactions)

    return render_template(
        "index.html",
        transactions=sorted_transactions[:10],
        income=summary["total_income"],
        expenses=summary["total_expense"],
        charges=summary["total_charges"],
        balance=summary["net"],
        page=1,
        total_pages=max(1, (len(sorted_transactions) - 1) // 10 + 1)
    )


# -------------------------------------------------
# TRANSACTIONS API (FILTERS + PAGINATION)
# -------------------------------------------------
@app.route("/transactions")
def transactions_endpoint():
    tx_type = request.args.get("type", "all")
    start = request.args.get("start_date")
    end = request.args.get("end_date")
    page = int(request.args.get("page", 1))
    sort_order = request.args.get("sort_order", "desc")
    per_page = 10

    filtered = app.config["STORED_TRANSACTIONS"]

    if start:
        start_date = datetime.strptime(start, "%Y-%m-%d").date()
        filtered = [t for t in filtered if t["date"] >= start_date]

    if end:
        end_date = datetime.strptime(end, "%Y-%m-%d").date()
        filtered = [t for t in filtered if t["date"] <= end_date]

    if tx_type == "income":
        filtered = [t for t in filtered if t["category"] == "income"]
    elif tx_type == "expense":
        filtered = [t for t in filtered if t["category"] == "expense"]
    elif tx_type == "charges":
        filtered = [t for t in filtered if t["category"] == "charge"]

    reverse_sort = sort_order == "desc"
    filtered = sorted(filtered, key=lambda t: t["date"], reverse=reverse_sort)

    total_pages = max(1, (len(filtered) - 1) // per_page + 1)
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    page_tx = filtered[start_idx:end_idx]

    summary = analyze(filtered)

    # Serialize dates for JSON
    def serialize(tx):
        tx = dict(tx)
        tx["date"] = tx["date"].isoformat()
        return tx

    return jsonify({
        "transactions": [serialize(t) for t in page_tx],
        "income": summary["total_income"],
        "expenses": summary["total_expense"],
        "charges": summary["total_charges"],
        "balance": summary["net"],
        "page": page,
        "total_pages": total_pages
    })


# -------------------------------------------------
# AI EXPLANATION ROUTE (FINANCIALLY CORRECT)
# -------------------------------------------------
@app.route("/ai_action", methods=["POST"])
def ai_action():
    payload = request.get_json(silent=True) or request.form

    action = payload.get("action")   # summarize | min | max | totals
    metric = payload.get("metric")   # income | expense | tcost
    start = payload.get("start_date")
    end = payload.get("end_date")

    all_tx = app.config["STORED_TRANSACTIONS"]

    if not all_tx:
        return jsonify({
            "ai_explanation": "No transactions found. Please upload an M-PESA statement first."
        })

    filtered = all_tx

    if start:
        start_date = datetime.strptime(start, "%Y-%m-%d").date()
        filtered = [t for t in filtered if t["date"] >= start_date]

    if end:
        end_date = datetime.strptime(end, "%Y-%m-%d").date()
        filtered = [t for t in filtered if t["date"] <= end_date]

    period_text = (
        f"{start} to {end}" if start and end
        else f"from {start}" if start
        else f"up to {end}" if end
        else "the entire statement"
    )

    # -------------------------------
    # 1) SUMMARY (ALWAYS FULL STATEMENT)
    # -------------------------------
    if action == "summarize":
        summary = analyze(all_tx)
        data = {
            "type": "summary",
            "total_income": summary["total_income"],
            "total_expense": summary["total_expense"],
            "total_charges": summary["total_charges"],
            "net": summary["net"],
            "transaction_count": summary["transaction_count"],
            "period": "entire statement"
        }

    # -------------------------------
    # 2) MIN / MAX
    # -------------------------------
    elif action in ["min", "max"]:
        category_map = {
            "income": "income",
            "expense": "expense",
            "tcost": "charge"
        }

        values = [t for t in filtered if t["category"] == category_map.get(metric)]

        tx = (
            min(values, key=lambda x: x["amount"])
            if action == "min" and values
            else max(values, key=lambda x: x["amount"])
            if values else None
        )

        data = {
            "type": action,
            "metric": metric,
            "amount": tx["amount"] if tx else 0,
            "date": tx["date"].isoformat() if tx else "N/A",
            "details": tx.get("details", "") if tx else "",
            "transaction_count": len(values),
            "period": period_text
        }

    # -------------------------------
    # 3) TOTALS
    # -------------------------------
    elif action == "totals":
        category_map = {
            "income": "income",
            "expense": "expense",
            "tcost": "charge"
        }

        total = sum(
            t["amount"] for t in filtered
            if t["category"] == category_map.get(metric)
        )

        data = {
            "type": "total",
            "metric": metric,
            "amount": total,
            "transaction_count": len(filtered),
            "period": period_text
        }

    else:
        return jsonify({"ai_explanation": "Invalid action"}), 400

    explanation = explain(data)
    return jsonify({"ai_explanation": explanation})


# -------------------------------------------------
# RUN APP (NO RELOADER BUG)
# -------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
