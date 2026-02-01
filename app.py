import os
from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
from rag_engine import ingest_statement, answer_question
from datetime import datetime
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import json
import pdfplumber

app = Flask(__name__)
CORS(app)

PDF_DIR = "mpesa_statements"
PASSWORD_DIR = "passwords"

transactions_cache = []
scan_results = []  # Track each PDF processing result


# ---------------- FILTER ----------------
@app.template_filter("format_number")
def format_number(value):
    try:
        return "{:,.2f}".format(float(value))
    except:
        return value


# ---------------- AUTO PASSWORD TESTER ----------------
def get_all_passwords():
    """Get all passwords from password directory"""
    passwords = []
    
    if not os.path.exists(PASSWORD_DIR):
        os.makedirs(PASSWORD_DIR, exist_ok=True)
        return passwords
    
    for file in os.listdir(PASSWORD_DIR):
        if file.endswith(".txt") and file != "password_mapping.json":
            try:
                with open(os.path.join(PASSWORD_DIR, file)) as f:
                    password = f.read().strip()
                    if password:  # Only add non-empty passwords
                        passwords.append({
                            'password': password,
                            'source': file
                        })
            except Exception as e:
                print(f"Warning: Could not read {file}: {e}")
    
    return passwords


def try_all_passwords(pdf_path):
    """
    Try to open a PDF with all available passwords.
    Returns the working password or None.
    """
    filename = os.path.basename(pdf_path)
    
    # Get all available passwords
    all_passwords = get_all_passwords()
    
    print(f"\n🔑 Auto-testing passwords for: {filename}")
    print(f"   Found {len(all_passwords)} password(s) to try")
    
    # First try without password
    try:
        with pdfplumber.open(pdf_path, password=None) as pdf:
            pages = len(pdf.pages)
            print(f"   ✓ PDF opened WITHOUT password ({pages} pages)")
            return None
    except:
        pass
    
    # Try each password
    for i, pwd_info in enumerate(all_passwords, 1):
        pwd = pwd_info['password']
        source = pwd_info['source']
        
        try:
            with pdfplumber.open(pdf_path, password=pwd) as pdf:
                pages = len(pdf.pages)
                print(f"   ✓ SUCCESS! Password from '{source}' works ({pages} pages)")
                return pwd
        except:
            pass
    
    print(f" None of the {len(all_passwords)} passwords worked!")
    return None


def get_password(filename):
    """Smart password matching"""
    base = os.path.splitext(filename)[0]
    
  
    exact_match = base + ".txt"
    exact_path = os.path.join(PASSWORD_DIR, exact_match)
    if os.path.exists(exact_path):
        with open(exact_path) as f:
            return f.read().strip()
    

    mapping_file = os.path.join(PASSWORD_DIR, "password_mapping.json")
    if os.path.exists(mapping_file):
        try:
            with open(mapping_file) as f:
                mapping = json.load(f)
            
            for pattern, pwd_file in mapping.items():
                if pattern.lower() in base.lower():
                    pwd_path = os.path.join(PASSWORD_DIR, pwd_file)
                    if os.path.exists(pwd_path):
                        with open(pwd_path) as f:
                            return f.read().strip()
        except:
            pass
    
    
    default_path = os.path.join(PASSWORD_DIR, "default.txt")
    if os.path.exists(default_path):
        with open(default_path) as f:
            return f.read().strip()
    
    return None

def auto_scan_pdfs():
    global transactions_cache, scan_results
    transactions_cache = []
    scan_results = []

    os.makedirs(PDF_DIR, exist_ok=True)
    os.makedirs(PASSWORD_DIR, exist_ok=True)

    print("\n" + "="*60)
    print("STARTING PDF SCAN WITH AUTO-PASSWORD DETECTION")
    print("="*60)

    for file in os.listdir(PDF_DIR):
        if not file.lower().endswith(".pdf"):
            continue

        path = os.path.join(PDF_DIR, file)

        try:
            print(f"\n Processing: {file}")
            
            # First try matched password
            password = get_password(file)
            
            # If no match, auto-test all passwords
            if not password:
                print(f"   No matched password - auto-testing all available passwords...")
                password = try_all_passwords(path)
            
            if password:
                print(f" Using password: {'*' * len(password)}")
            else:
                print(f" No password needed/found")
            
            # Ingest the statement
            result = ingest_statement(path, password=password)
            
            # Handle different return types
            if isinstance(result, list):
                tx = result
            elif isinstance(result, dict):
                tx = result.get('transactions', [])
            else:
                tx = [result] if result else []
            
            transactions_cache.extend(tx)

            scan_results.append({
                "file": file,
                "status": "success",
                "message": f"{len(tx)} transactions processed",
                "password_used": "yes" if password else "no",
                "transactions": tx
            })
            print(f" SUCCESS: {len(tx)} transactions extracted")

        except Exception as e:
            import traceback
            error_msg = str(e) if str(e) else f"Unknown error ({type(e).__name__})"
            
            print(f" FAILED: {error_msg}")
            
            scan_results.append({
                "file": file,
                "status": "failed",
                "message": error_msg,
                "error_trace": traceback.format_exc(),
                "transactions": []
            })

    print("\n" + "="*60)
    print(f"SCAN COMPLETE: {len(transactions_cache)} total transactions")
    print("="*60 + "\n")


@app.route("/", methods=["GET", "POST"])
def index():
    global transactions_cache, scan_results
    
    if request.method == "POST":
      
        uploaded_file = request.files.get("statement")
        pdf_password = request.form.get("pdf_password", "").strip()
        
        if uploaded_file:
            filename = uploaded_file.filename
            save_path = os.path.join(PDF_DIR, filename)
            uploaded_file.save(save_path)
            
            try:
               
                if not pdf_password:
                    print(f"\n Auto-detecting password for {filename}...")
                    pdf_password = try_all_passwords(save_path)
                
                result = ingest_statement(save_path, password=pdf_password)
                
                if isinstance(result, list):
                    tx = result
                elif isinstance(result, dict):
                    tx = result.get('transactions', [])
                else:
                    tx = [result] if result else []
                
                transactions_cache.extend(tx)
                
                scan_results.append({
                    "file": filename,
                    "status": "success",
                    "message": f"{len(tx)} transactions processed",
                    "password_used": "yes" if pdf_password else "no",
                    "transactions": tx
                })
                
            except Exception as e:
                import traceback
                scan_results.append({
                    "file": filename,
                    "status": "failed",
                    "message": str(e),
                    "error_trace": traceback.format_exc(),
                    "transactions": []
                })

    income = sum(t.get("amount", 0) for t in transactions_cache if t.get("category") == "income")
    expenses = sum(t.get("amount", 0) for t in transactions_cache if t.get("category") == "expense")
    charges = sum(t.get("amount", 0) for t in transactions_cache if t.get("category") == "charge")
    balance = income - expenses - charges

    return render_template(
        "index.html",
        income=income,
        expenses=expenses,
        charges=charges,
        balance=balance,
        transactions=transactions_cache,
        scan_results=scan_results
    )

@app.route("/filter_transactions", methods=["POST"])
def filter_transactions():
    data = request.get_json()
    type_filter = data.get("type_filter", "all")
    amount_filter = data.get("amount_filter", "none")
    start_date = data.get("start_date")
    end_date = data.get("end_date")

    filtered = transactions_cache.copy()

    if type_filter != "all":
        filtered = [t for t in filtered if t.get("category") == type_filter]

    if start_date:
        filtered = [t for t in filtered if t.get("date", "") >= start_date]
    if end_date:
        filtered = [t for t in filtered if t.get("date", "") <= end_date]

    if amount_filter == "max" and filtered:
        max_amount = max(t.get("amount", 0) for t in filtered)
        filtered = [t for t in filtered if t.get("amount", 0) == max_amount]
    elif amount_filter == "min" and filtered:
        min_amount = min(t.get("amount", 0) for t in filtered)
        filtered = [t for t in filtered if t.get("amount", 0) == min_amount]

    return jsonify({"transactions": filtered})


@app.route("/ai_chat", methods=["POST"])
def ai_chat():
    question = request.form.get("question")
    answer = answer_question(transactions_cache, question)
    return jsonify({"answer": answer})


@app.route("/download_pdf")
def download_pdf():
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    textobject = c.beginText(40, 750)
    textobject.setFont("Helvetica", 12)

    for t in transactions_cache:
        line = f"{t.get('date', 'N/A')} | {t.get('category', 'N/A')} | {t.get('amount', 0)} | Balance: {t.get('balance', 0)} | {t.get('details', '')[:50]}"
        textobject.textLine(line)

    c.drawText(textobject)
    c.showPage()
    c.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name="M-Ledger_Report.pdf", mimetype="application/pdf")


@app.route("/test_passwords")
def test_passwords():
    """Test endpoint to verify password matching"""
    results = []
    for file in os.listdir(PDF_DIR):
        if file.lower().endswith(".pdf"):
            path = os.path.join(PDF_DIR, file)
            working_password = try_all_passwords(path)
            
            results.append({
                "pdf": file,
                "working_password_found": working_password is not None,
                "status": "✓ Working" if working_password else "✗ No working password"
            })
    return jsonify(results)


@app.route("/rescan")
def rescan():
    """Endpoint to trigger a rescan of PDFs"""
    auto_scan_pdfs()
    return jsonify({
        "status": "success",
        "total_transactions": len(transactions_cache),
        "scan_results": scan_results
    })



if __name__ == "__main__":
    print("\n" + "="*60)
    print(" STARTING M-LEDGER WITH AUTO-PASSWORD DETECTION")
    print("="*60)
    print(f" Server: http://127.0.0.1:5000")
    print(f" PDF Directory: {PDF_DIR}")
    print(f" Password Directory: {PASSWORD_DIR}")
    print("="*60 + "\n")
    
    auto_scan_pdfs()
    
    app.run(debug=True)