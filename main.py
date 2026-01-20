from flask import Flask, render_template, request, redirect, flash, send_file
import os
import io
from pdf_parser import parse_mpesa_pdf
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

app = Flask(__name__)
app.secret_key = "mledger_secret"

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

PDF_PASSWORD = "secure@123"
uploaded_file_path = None

@app.route("/", methods=["GET", "POST"])
def home():
    global uploaded_file_path
    transactions = []
    income = expenses = balance = 0
    selected_filter = request.args.get("filter", "")  # GET parameter for page filter

    if request.method == "POST":
        file = request.files.get("statement")

        if not file or file.filename == "":
            flash("Please upload a PDF file.")
            return redirect("/")

        if not file.filename.lower().endswith(".pdf"):
            flash("Only PDF files are allowed.")
            return redirect("/")

        file_path = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(file_path)
        uploaded_file_path = file_path

        transactions = parse_mpesa_pdf(file_path)
        if not transactions:
            flash("Could not read transactions from this PDF. Please upload an official M-PESA statement.")
            return redirect("/")

        income = sum(t["paid_in"] for t in transactions)
        expenses = sum(t["paid_out"] for t in transactions)
        balance = transactions[-1]["balance"]

    # Filter transactions for display
    filtered_transactions = []
    if transactions:
        if selected_filter == "income":
            filtered_transactions = [t for t in transactions if t["paid_in"] > 0]
        elif selected_filter == "expense":
            filtered_transactions = [t for t in transactions if t["paid_out"] > 0]
        else:
            filtered_transactions = transactions

    return render_template(
        "index.html",
        transactions=filtered_transactions,
        income=income,
        expenses=expenses,
        balance=balance,
        uploaded_file_path=uploaded_file_path,
        selected_filter=selected_filter
    )


@app.route("/download-pdf", methods=["POST"])
def download_pdf():
    global uploaded_file_path
    if not uploaded_file_path:
        flash("No uploaded file found. Please upload a statement first.")
        return redirect("/")

    password = request.form.get("password")
    transaction_type = request.form.get("type", "")  # filter type

    if password != PDF_PASSWORD:
        flash("Incorrect password!")
        return redirect("/")

    transactions = parse_mpesa_pdf(uploaded_file_path)

    # Filter transactions for PDF exactly like the page
    if transaction_type == "income":
        filtered = [t for t in transactions if t["paid_in"] > 0]
        for t in filtered:
            t["paid_out"] = 0
    elif transaction_type == "expense":
        filtered = [t for t in transactions if t["paid_out"] > 0]
        for t in filtered:
            t["paid_in"] = 0
    else:
        filtered = transactions

    if not filtered:
        flash(f"No {transaction_type or 'transactions'} found to export.")
        return redirect("/")

    # Generate PDF
    pdf_buffer = io.BytesIO()
    c = canvas.Canvas(pdf_buffer, pagesize=letter)
    width, height = letter
    y = height - 50

    c.setFont("Helvetica-Bold", 16)
    title = f"{transaction_type.capitalize() if transaction_type else 'All'} Transactions Report"
    c.drawString(50, y, title)
    y -= 30

    c.setFont("Helvetica", 12)
    for t in filtered:
        line = f"{t['date']} | Paid In: {t['paid_in']} | Paid Out: {t['paid_out']} | Balance: {t['balance']}"
        c.drawString(50, y, line)
        y -= 20
        if y < 50:
            c.showPage()
            y = height - 50

    c.save()
    pdf_buffer.seek(0)

    download_name = f"{transaction_type if transaction_type else 'all'}_transactions.pdf"
    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=download_name,
        mimetype="application/pdf"
    )


if __name__ == "__main__":
    app.run(debug=True)
