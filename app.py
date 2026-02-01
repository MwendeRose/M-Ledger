import os
import io
import json
import traceback
import sys
from datetime import datetime
import pdfplumber
import re
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

app = Flask(__name__, static_folder='static')
CORS(app)

# ----------------- CONFIG -----------------
BASE_DIR = Path(__file__).parent.absolute()
PDF_DIR = BASE_DIR / "mpesa_statements"
PASSWORD_DIR = BASE_DIR / "passwords"
CACHE_FILE = BASE_DIR / "data_cache.json"

# Create directories if they don't exist
PDF_DIR.mkdir(exist_ok=True)
PASSWORD_DIR.mkdir(exist_ok=True)

# Allow large uploads
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
app.config['SECRET_KEY'] = 'm-ledger-secret-key-change-in-production'

# Global state
transactions_cache = []
processed_files = set()
scan_results = []
app_start_time = datetime.now()

CATEGORY_MAP = {
    "paid_in": "income",
    "paid_out": "expense",
    "transaction_cost": "charge",
    "charge": "charge",
    "income": "income",
    "expense": "expense",
    "reversal": "income",
    "deposit": "income",
    "withdrawal": "expense",
    "sent": "expense",
    "received": "income",
    "payment": "expense",
    "transfer": "expense"
}

# ----------------- PDF PROCESSING FUNCTIONS -----------------
def extract_text_from_pdf(pdf_path, password=None):
    """Extract text from PDF using pdfplumber"""
    try:
        print(f"  📄 Extracting text from: {pdf_path.name}")
        
        # Try to open with password if provided
        try:
            if password:
                pdf = pdfplumber.open(pdf_path, password=password)
            else:
                pdf = pdfplumber.open(pdf_path)
        except Exception as e:
            error_msg = str(e).lower()
            if "password" in error_msg or "encrypted" in error_msg:
                print(f"  🔐 PDF requires password: {pdf_path.name}")
                return None, "Password required"
            else:
                raise
        
        text = ""
        for i, page in enumerate(pdf.pages):
            try:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
                    print(f"    Page {i+1}: {len(page_text)} chars")
            except Exception as e:
                print(f"    Page {i+1} error: {e}")
                continue
        
        pdf.close()
        
        if not text.strip():
            return None, "No text extracted (PDF might be image-based)"
        
        print(f"  ✅ Extracted {len(text)} characters total")
        return text, None
        
    except Exception as e:
        return None, f"Failed to open PDF: {str(e)}"

def parse_transactions_from_text(text, filename):
    """Parse transactions from extracted PDF text"""
    transactions = []
    
    # Common MPesa patterns
    patterns = [
        # Pattern: 01/01/2024 KES 1,000.00 details
        r'(\d{2}/\d{2}/\d{4}).*?(KES\s*[\d,]+\.\d{2})',
        # Pattern: 2024-01-01 KES 1,000.00 details
        r'(\d{4}-\d{2}-\d{2}).*?(KES\s*[\d,]+\.\d{2})',
        # Pattern: Date: 01/01/2024 Amount: 1,000.00
        r'Date[:\s]+(\d{2}/\d{2}/\d{4}).*?Amount[:\s]+([\d,]+\.\d{2})',
    ]
    
    lines = text.split('\n')
    print(f"  📊 Parsing {len(lines)} lines for transactions")
    
    for line in lines:
        line = line.strip()
        if not line or len(line) < 20:
            continue
        
        # Try each pattern
        for pattern in patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                try:
                    date_str = match.group(1).strip()
                    amount_str = match.group(2).replace('KES', '').replace(',', '').strip()
                    
                    # Parse amount
                    amount = float(amount_str)
                    
                    # Categorize based on keywords
                    line_lower = line.lower()
                    
                    if any(word in line_lower for word in ['received', 'deposit', 'reversal', 'from', 'credit']):
                        category = 'income'
                    elif any(word in line_lower for word in ['sent', 'paid', 'to', 'withdrawal', 'payment', 'transfer', 'buy']):
                        category = 'expense'
                    elif any(word in line_lower for word in ['charge', 'fee', 'commission', 'service']):
                        category = 'charge'
                    else:
                        # Default based on amount sign (if we can detect)
                        if ' -' in line or '- ' in line:
                            category = 'expense'
                        elif ' +' in line or '+ ' in line:
                            category = 'income'
                        else:
                            category = 'expense'  # Default
                    
                    # Format date
                    try:
                        if '/' in date_str:
                            date_obj = datetime.strptime(date_str, '%d/%m/%Y')
                        elif '-' in date_str:
                            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                        formatted_date = date_obj.strftime('%Y-%m-%d')
                    except:
                        formatted_date = date_str
                    
                    transaction = {
                        'date': formatted_date,
                        'amount': amount,
                        'category': category,
                        'details': line[:100],  # First 100 chars
                        'filename': filename,
                        'raw_line': line[:200],
                        'processed_at': datetime.now().isoformat()
                    }
                    
                    transactions.append(transaction)
                    print(f"    ✅ Found: {formatted_date} - {category} - KES {amount:,.2f}")
                    break  # Found with this pattern, move to next line
                    
                except Exception as e:
                    print(f"    ⚠️  Error parsing line: {line[:50]}... - {e}")
                    continue
    
    return transactions

def process_pdf_file(pdf_path, password=None):
    """Process a single PDF file and extract transactions"""
    print(f"\n{'='*60}")
    print(f"🔍 PROCESSING: {pdf_path.name}")
    print(f"{'='*60}")
    
    # Extract text from PDF
    text, error = extract_text_from_pdf(pdf_path, password)
    
    if error:
        print(f"❌ Failed: {error}")
        return None, error
    
    # Parse transactions from text
    transactions = parse_transactions_from_text(text, pdf_path.name)
    
    if not transactions:
        print("⚠️  No transactions found in PDF")
        # Try alternative parsing
        transactions = fallback_parsing(text, pdf_path.name)
    
    print(f"📊 Found {len(transactions)} transactions")
    print(f"{'='*60}")
    
    return transactions, None

def fallback_parsing(text, filename):
    """Fallback method if regex patterns don't work"""
    transactions = []
    lines = text.split('\n')
    
    # Look for any lines with amounts
    amount_pattern = r'(\d{1,3}(?:,\d{3})*\.\d{2})|(KES\s*\d+(?:,\d+)*\.\d{2})'
    
    for line in lines:
        line = line.strip()
        if len(line) < 10:
            continue
        
        # Look for amounts
        amount_match = re.search(amount_pattern, line)
        if amount_match:
            try:
                # Extract amount
                amount_str = amount_match.group(0).replace('KES', '').replace(',', '').strip()
                amount = float(amount_str)
                
                # Look for date (various formats)
                date_match = re.search(r'(\d{2}[/\-]\d{2}[/\-]\d{4})|(\d{4}[/\-]\d{2}[/\-]\d{2})', line)
                date_str = date_match.group(0) if date_match else datetime.now().strftime('%Y-%m-%d')
                
                # Categorize
                line_lower = line.lower()
                if 'received' in line_lower or 'from' in line_lower:
                    category = 'income'
                elif 'sent' in line_lower or 'to' in line_lower:
                    category = 'expense'
                elif 'charge' in line_lower or 'fee' in line_lower:
                    category = 'charge'
                else:
                    category = 'unknown'
                
                transaction = {
                    'date': date_str,
                    'amount': amount,
                    'category': category,
                    'details': line[:80],
                    'filename': filename,
                    'raw_line': line[:150],
                    'processed_at': datetime.now().isoformat()
                }
                
                transactions.append(transaction)
                
            except Exception as e:
                continue
    
    return transactions

def auto_scan_all_pdfs():
    """Automatically scan and process all PDFs in the statements folder"""
    global transactions_cache, processed_files, scan_results
    
    print(f"\n{'#'*70}")
    print(f"🚀 M-LEDGER AI - STARTING AUTOMATIC PDF SCAN")
    print(f"{'#'*70}")
    print(f"📁 PDF Directory: {PDF_DIR}")
    print(f"📊 Cache File: {CACHE_FILE}")
    print(f"{'#'*70}\n")
    
    # Load existing cache
    load_cache()
    
    # Check if directory exists
    if not PDF_DIR.exists():
        print(f"❌ PDF directory not found: {PDF_DIR}")
        print(f"✅ Created directory: {PDF_DIR}")
        return
    
    # Find all PDF files
    pdf_files = list(PDF_DIR.glob("*.pdf"))
    pdf_files.extend(PDF_DIR.glob("*.PDF"))  # Uppercase extension
    
    if not pdf_files:
        print("📭 No PDF files found in directory")
        print("💡 Place your M-Pesa statement PDFs in the 'mpesa_statements' folder")
        return
    
    print(f"📄 Found {len(pdf_files)} PDF file(s):")
    for pdf in pdf_files:
        print(f"   • {pdf.name}")
    
    print(f"\n🔄 Processing PDFs...")
    
    # Process each PDF
    for pdf_path in pdf_files:
        filename = pdf_path.name
        
        # Skip if already processed (check cache)
        if filename in processed_files:
            print(f"\n⏭️  Already processed: {filename}")
            continue
        
        print(f"\n{'='*50}")
        print(f"🔄 Processing: {filename}")
        print(f"{'='*50}")
        
        try:
            # Try without password first
            transactions, error = process_pdf_file(pdf_path)
            
            if error and "password" in error.lower():
                # Try with common passwords
                passwords_to_try = get_passwords_to_try()
                processed = False
                
                for pwd in passwords_to_try:
                    print(f"  🔐 Trying password: {pwd[:10]}...")
                    transactions, error = process_pdf_file(pdf_path, pwd)
                    if not error:
                        processed = True
                        break
                
                if not processed:
                    error = "Password required and none worked"
            
            if error:
                print(f"❌ Failed: {error}")
                scan_results.append({
                    'file': filename,
                    'status': 'failed',
                    'message': error,
                    'timestamp': datetime.now().isoformat()
                })
                continue
            
            # Add to cache
            for tx in transactions:
                # Map category
                tx['category'] = CATEGORY_MAP.get(tx['category'].lower(), tx['category'])
                transactions_cache.append(tx)
            
            processed_files.add(filename)
            
            # Add to scan results
            scan_results.append({
                'file': filename,
                'status': 'success',
                'message': f'Processed {len(transactions)} transactions',
                'transactions': len(transactions),
                'timestamp': datetime.now().isoformat()
            })
            
            print(f"✅ Successfully processed {filename}")
            print(f"   📊 Added {len(transactions)} transactions")
            
        except Exception as e:
            error_msg = str(e)
            print(f"❌ Error processing {filename}: {error_msg}")
            traceback.print_exc()
            
            scan_results.append({
                'file': filename,
                'status': 'failed',
                'message': error_msg,
                'timestamp': datetime.now().isoformat()
            })
    
    # Calculate running balances
    calculate_running_balances()
    
    # Save cache
    save_cache()
    
    print(f"\n{'#'*70}")
    print(f"📊 SCAN COMPLETE - SUMMARY")
    print(f"{'#'*70}")
    print(f"✅ Total PDFs processed: {len(processed_files)}")
    print(f"✅ Total transactions: {len(transactions_cache)}")
    print(f"✅ Successful scans: {len([r for r in scan_results if r['status'] == 'success'])}")
    print(f"❌ Failed scans: {len([r for r in scan_results if r['status'] == 'failed'])}")
    
    # Show summary
    summary = calculate_summary()
    print(f"\n💰 FINANCIAL SUMMARY:")
    print(f"   • Total Income: KES {summary['income']:,.2f}")
    print(f"   • Total Expenses: KES {summary['expenses']:,.2f}")
    print(f"   • Total Charges: KES {summary['charges']:,.2f}")
    print(f"   • Net Balance: KES {summary['balance']:,.2f}")
    print(f"{'#'*70}\n")

def get_passwords_to_try():
    """Get passwords to try from passwords directory"""
    passwords = []
    
    if PASSWORD_DIR.exists():
        # Look for password files
        for pwd_file in PASSWORD_DIR.glob("*.txt"):
            try:
                with open(pwd_file, 'r') as f:
                    pwd = f.read().strip()
                    if pwd:
                        passwords.append(pwd)
            except:
                pass
    
    # Add common/default passwords
    default_passwords = ['1234', '0000', 'mpesa', 'password', '123456']
    passwords.extend(default_passwords)
    
    return passwords

def calculate_running_balances():
    """Calculate running balance for each transaction"""
    if not transactions_cache:
        return
    
    # Sort by date
    sorted_transactions = sorted(
        transactions_cache,
        key=lambda x: datetime.strptime(x['date'], '%Y-%m-%d') if '-' in x['date'] else datetime.now()
    )
    
    running_balance = 0
    
    for tx in sorted_transactions:
        if tx['category'] == 'income':
            running_balance += tx['amount']
        elif tx['category'] in ['expense', 'charge']:
            running_balance -= tx['amount']
        
        tx['balance'] = round(running_balance, 2)

def calculate_summary():
    """Calculate financial summary"""
    income = sum(tx['amount'] for tx in transactions_cache if tx['category'] == 'income')
    expenses = sum(tx['amount'] for tx in transactions_cache if tx['category'] == 'expense')
    charges = sum(tx['amount'] for tx in transactions_cache if tx['category'] == 'charge')
    balance = income - expenses - charges
    
    return {
        'income': income,
        'expenses': expenses,
        'charges': charges,
        'balance': balance
    }

def load_cache():
    """Load transactions from cache file"""
    global transactions_cache, processed_files, scan_results
    
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, 'r') as f:
                data = json.load(f)
                transactions_cache = data.get('transactions', [])
                processed_files = set(data.get('processed_files', []))
                scan_results = data.get('scan_results', [])
                print(f"📂 Loaded cache: {len(transactions_cache)} transactions")
        except Exception as e:
            print(f"⚠️ Error loading cache: {e}")
            transactions_cache = []
            processed_files = set()
            scan_results = []

def save_cache():
    """Save transactions to cache file"""
    try:
        data = {
            'transactions': transactions_cache,
            'processed_files': list(processed_files),
            'scan_results': scan_results[-20:],  # Keep last 20 scans
            'last_updated': datetime.now().isoformat(),
            'total_transactions': len(transactions_cache)
        }
        
        with open(CACHE_FILE, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        
        print(f"💾 Cache saved: {len(transactions_cache)} transactions")
    except Exception as e:
        print(f"❌ Error saving cache: {e}")

# ----------------- ROUTES -----------------
@app.route("/", methods=["GET", "POST"])
def index():
    """Main page"""
    upload_message = ""
    upload_success = False
    
    if request.method == "POST":
        uploaded_file = request.files.get("statement")
        
        if uploaded_file and uploaded_file.filename:
            filename = uploaded_file.filename
            
            if not filename.lower().endswith(".pdf"):
                upload_message = "❌ Only PDF files are allowed."
            else:
                # Save the file
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_name = f"{timestamp}_{filename}"
                save_path = PDF_DIR / safe_name
                
                try:
                    uploaded_file.save(save_path)
                    print(f"📤 File uploaded: {safe_name}")
                    
                    # Process immediately
                    transactions, error = process_pdf_file(save_path)
                    
                    if error:
                        upload_message = f"❌ Processing failed: {error}"
                    else:
                        # Add to cache
                        for tx in transactions:
                            tx['category'] = CATEGORY_MAP.get(tx['category'].lower(), tx['category'])
                            tx['filename'] = safe_name
                            transactions_cache.append(tx)
                        
                        processed_files.add(safe_name)
                        calculate_running_balances()
                        save_cache()
                        
                        upload_success = True
                        upload_message = f"✅ '{filename}' processed successfully! Found {len(transactions)} transactions."
                        
                except Exception as e:
                    upload_message = f"❌ Upload failed: {str(e)}"
        else:
            upload_message = "⚠️ Please select a PDF file."
    
    # Calculate summary
    summary = calculate_summary()
    
    # Sort transactions by date (newest first)
    sorted_transactions = sorted(
        transactions_cache,
        key=lambda x: datetime.strptime(x['date'], '%Y-%m-%d') if '-' in x['date'] and len(x['date']) == 10 else datetime.now(),
        reverse=True
    )
    
    return render_template(
        "index.html",
        income=summary['income'],
        expenses=summary['expenses'],
        charges=summary['charges'],
        balance=summary['balance'],
        transactions=sorted_transactions,
        scan_results=scan_results[-10:],  # Show last 10 scans
        upload_success=upload_success,
        upload_message=upload_message,
        total_transactions=len(transactions_cache),
        app_uptime=str(datetime.now() - app_start_time).split('.')[0]
    )

@app.route("/filter_transactions", methods=["POST"])
def filter_transactions():
    """Filter transactions API"""
    try:
        data = request.get_json()
        ttype = data.get("type_filter", "all")
        start_date = data.get("start_date")
        end_date = data.get("end_date")
        
        filtered = transactions_cache.copy()
        
        # Filter by type
        if ttype != "all":
            filtered = [t for t in filtered if t.get("category") == ttype]
        
        # Filter by date
        if start_date:
            try:
                start = datetime.strptime(start_date, '%Y-%m-%d')
                filtered = [t for t in filtered 
                          if datetime.strptime(t['date'], '%Y-%m-%d') >= start]
            except:
                pass
        
        if end_date:
            try:
                end = datetime.strptime(end_date, '%Y-%m-%d')
                filtered = [t for t in filtered 
                          if datetime.strptime(t['date'], '%Y-%m-%d') <= end]
            except:
                pass
        
        # Sort by date
        filtered.sort(key=lambda x: datetime.strptime(x['date'], '%Y-%m-%d'), reverse=True)
        
        return jsonify({
            "transactions": filtered,
            "count": len(filtered)
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/ai_chat", methods=["POST"])
def ai_chat():
    """AI Chat endpoint"""
    try:
        question = request.form.get("question", "").strip()
        
        if not question:
            return jsonify({"answer": "Please enter a question."})
        
        if not transactions_cache:
            return jsonify({"answer": "No transactions available. Please upload or scan PDFs first."})
        
        # Simple AI responses (you can integrate Claude API here)
        answer = generate_ai_response(question)
        return jsonify({"answer": answer})
        
    except Exception as e:
        return jsonify({"answer": f"Error: {str(e)}"}), 500

def generate_ai_response(question):
    """Generate AI response based on transactions"""
    question_lower = question.lower()
    summary = calculate_summary()
    
    if 'total' in question_lower and 'income' in question_lower:
        return f"📈 Total Income: KES {summary['income']:,.2f}"
    
    elif 'total' in question_lower and ('expense' in question_lower or 'spent' in question_lower):
        return f"📉 Total Expenses: KES {summary['expenses']:,.2f}"
    
    elif 'balance' in question_lower:
        return f"💰 Current Balance: KES {summary['balance']:,.2f}"
    
    elif 'transaction' in question_lower and 'many' in question_lower:
        return f"📊 Total Transactions: {len(transactions_cache)}"
    
    elif 'category' in question_lower:
        # Count by category
        categories = {}
        for tx in transactions_cache:
            cat = tx['category']
            categories[cat] = categories.get(cat, 0) + 1
        
        response = "📋 Transaction Categories:\n"
        for cat, count in categories.items():
            response += f"• {cat.title()}: {count} transactions\n"
        return response
    
    elif 'recent' in question_lower or 'last' in question_lower:
        recent = transactions_cache[:5]
        response = "🕒 Recent Transactions:\n"
        for tx in recent:
            response += f"• {tx['date']} - {tx['category']} - KES {tx['amount']:,.2f}\n"
        return response
    
    else:
        return f"🤖 I found {len(transactions_cache)} transactions totaling KES {summary['income']:,.2f} in income and KES {summary['expenses']:,.2f} in expenses. Current balance is KES {summary['balance']:,.2f}. How else can I help you?"

@app.route("/download_pdf")
def download_pdf():
    """Download PDF report"""
    try:
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)
        
        # Header
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, 780, "M-Ledger AI - Financial Report")
        c.setFont("Helvetica", 10)
        c.drawString(50, 760, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        c.drawString(50, 745, f"Total Transactions: {len(transactions_cache)}")
        
        # Summary
        summary = calculate_summary()
        c.drawString(50, 725, f"Income: KES {summary['income']:,.2f}")
        c.drawString(200, 725, f"Expenses: KES {summary['expenses']:,.2f}")
        c.drawString(350, 725, f"Charges: KES {summary['charges']:,.2f}")
        c.drawString(500, 725, f"Balance: KES {summary['balance']:,.2f}")
        
        # Table header
        c.setFont("Helvetica-Bold", 10)
        c.drawString(50, 700, "Date")
        c.drawString(120, 700, "Type")
        c.drawString(170, 700, "Details")
        c.drawString(400, 700, "Amount")
        c.drawString(480, 700, "Balance")
        
        # Transactions
        c.setFont("Helvetica", 9)
        y = 680
        
        for t in transactions_cache[:100]:  # Limit to 100 for readability
            if y < 50:
                c.showPage()
                y = 750
                c.setFont("Helvetica", 9)
            
            c.drawString(50, y, str(t.get('date', ''))[:10])
            c.drawString(120, y, str(t.get('category', ''))[:10])
            c.drawString(170, y, str(t.get('details', ''))[:40])
            c.drawString(400, y, f"KES {t.get('amount', 0):,.2f}")
            c.drawString(480, y, f"KES {t.get('balance', 0):,.2f}" if t.get('balance') else '-')
            y -= 12
        
        c.save()
        buffer.seek(0)
        
        filename = f"M-Ledger_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        return send_file(buffer, as_attachment=True, download_name=filename, mimetype="application/pdf")
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/rescan")
def rescan():
    """Force rescan all PDFs"""
    try:
        global processed_files
        processed_files.clear()
        auto_scan_all_pdfs()
        return jsonify({
            "status": "success",
            "message": f"Rescanned {len(processed_files)} files",
            "total_transactions": len(transactions_cache)
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/status")
def api_status():
    """API status endpoint"""
    return jsonify({
        "status": "running",
        "transactions": len(transactions_cache),
        "processed_files": len(processed_files),
        "pdf_directory": str(PDF_DIR),
        "uptime": str(datetime.now() - app_start_time).split('.')[0],
        "last_update": datetime.now().isoformat()
    })

@app.route("/api/transactions")
def api_transactions():
    """Get all transactions as JSON"""
    return jsonify({
        "transactions": transactions_cache,
        "total": len(transactions_cache),
        "summary": calculate_summary()
    })

@app.template_filter("format_number")
def format_number(value):
    """Format number with commas"""
    try:
        return "{:,.2f}".format(float(value))
    except:
        return str(value)

# ----------------- INITIALIZATION -----------------
if __name__ == "__main__":
    print("\n" + "="*70)
    print("🚀 M-LEDGER AI - FINANCIAL STATEMENT ANALYZER")
    print("="*70)
    print(f"📁 Working Directory: {BASE_DIR}")
    print(f"📄 PDF Statements: {PDF_DIR}")
    print(f"🔑 Passwords: {PASSWORD_DIR}")
    print("="*70)
    
    # Perform automatic scan on startup
    auto_scan_all_pdfs()
    
    # Run the Flask app
    print(f"\n🌐 Starting web server on http://localhost:5000")
    print("="*70)
    
    app.run(debug=True, host='0.0.0.0', port=5000)