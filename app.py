import os
import io
import json
import traceback
import sys
from datetime import datetime
import pdfplumber
import re
import fitz  # PyMuPDF for better PDF handling
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for
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
failed_files = {}  # Track failed files and their errors
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
    "transfer": "expense",
    "payment to": "expense",
    "received from": "income",
    "withdrawn": "expense",
    "withdraw": "expense",
    "withdrawal to": "expense",
    "deposited": "income",
    "paid": "expense",
    "paid to": "expense",
    "mpesa": "charge",
    "transaction fee": "charge",
    "service charge": "charge"
}

# ----------------- PDF PROCESSING FUNCTIONS -----------------
def get_all_passwords():
    """Get all passwords from password directory txt files"""
    passwords = []
    
    if not PASSWORD_DIR.exists():
        return passwords
    
    # Look for all .txt files in passwords directory
    for pwd_file in PASSWORD_DIR.glob("*.txt"):
        try:
            with open(pwd_file, 'r', encoding='utf-8') as f:
                password = f.read().strip()
                if password:
                    passwords.append(password)
                    print(f"  🔑 Loaded password from: {pwd_file.name}")
        except Exception as e:
            print(f"  ⚠️ Error reading password file {pwd_file}: {e}")
            continue
    
    # Also check for password_mapping.json for pattern-based passwords
    mapping_file = PASSWORD_DIR / "password_mapping.json"
    if mapping_file.exists():
        try:
            with open(mapping_file, 'r') as f:
                mapping = json.load(f)
                for pattern, pwd_file_name in mapping.items():
                    pwd_file = PASSWORD_DIR / pwd_file_name
                    if pwd_file.exists():
                        try:
                            with open(pwd_file, 'r') as pf:
                                password = pf.read().strip()
                                if password:
                                    passwords.append(password)
                                    print(f"  🔑 Loaded password from mapping: {pwd_file_name}")
                        except Exception as e:
                            print(f"  ⚠️ Error reading mapped password file {pwd_file_name}: {e}")
        except Exception as e:
            print(f"  ⚠️ Error reading password mapping: {e}")
    
    # Remove duplicates but preserve order
    unique_passwords = []
    for pwd in passwords:
        if pwd not in unique_passwords:
            unique_passwords.append(pwd)
    
    print(f"  📋 Loaded {len(unique_passwords)} unique passwords from password directory")
    return unique_passwords

def get_password_for_file(filename):
    """Get password for specific filename from password directory"""
    base_name = Path(filename).stem  # Get filename without extension
    
    # 1. Try exact filename match: filename.txt
    exact_match = PASSWORD_DIR / f"{base_name}.txt"
    if exact_match.exists():
        try:
            with open(exact_match, 'r', encoding='utf-8') as f:
                password = f.read().strip()
                if password:
                    print(f"  🔑 Found exact password match for {filename}: {exact_match.name}")
                    return password
        except Exception as e:
            print(f"  ⚠️ Error reading password file {exact_match}: {e}")
    
    # 2. Try pattern matching from password_mapping.json
    mapping_file = PASSWORD_DIR / "password_mapping.json"
    if mapping_file.exists():
        try:
            with open(mapping_file, 'r') as f:
                mapping = json.load(f)
                for pattern, pwd_file_name in mapping.items():
                    if pattern.lower() in filename.lower():
                        pwd_file = PASSWORD_DIR / pwd_file_name
                        if pwd_file.exists():
                            try:
                                with open(pwd_file, 'r') as pf:
                                    password = pf.read().strip()
                                    if password:
                                        print(f"  🔑 Found pattern match for {filename}: pattern '{pattern}' -> {pwd_file_name}")
                                        return password
                            except Exception as e:
                                print(f"  ⚠️ Error reading mapped password file {pwd_file_name}: {e}")
        except Exception as e:
            print(f"  ⚠️ Error reading password mapping: {e}")
    
    # 3. Try default password file
    default_file = PASSWORD_DIR / "default.txt"
    if default_file.exists():
        try:
            with open(default_file, 'r', encoding='utf-8') as f:
                password = f.read().strip()
                if password:
                    print(f"  🔑 Using default password for {filename}")
                    return password
        except Exception as e:
            print(f"  ⚠️ Error reading default password file: {e}")
    
    return None

def extract_text_with_pymupdf(pdf_path, password=None):
    """Try extracting text using PyMuPDF (fitz) as backup"""
    try:
        doc = fitz.open(pdf_path)
        
        # Try password if provided
        if password:
            if doc.authenticate(password):
                print(f"  🔐 PyMuPDF: Authentication successful with password")
            else:
                doc.close()
                return None, "Incorrect password"
        
        text = ""
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            page_text = page.get_text()
            if page_text:
                text += page_text + "\n"
        
        doc.close()
        
        if not text.strip():
            return None, "No text extracted (PDF might be image-based)"
        
        print(f"  ✅ PyMuPDF: Successfully extracted text ({len(text)} chars)")
        return text, None
        
    except Exception as e:
        error_msg = str(e).lower()
        if "password" in error_msg or "encrypted" in error_msg or "decrypt" in error_msg:
            return None, "Password required"
        elif "invalid" in error_msg or "corrupt" in error_msg:
            return None, "Invalid or corrupted PDF file"
        else:
            return None, f"PyMuPDF error: {str(e)}"

def extract_text_from_pdf(pdf_path, password=None):
    """Extract text from PDF using pdfplumber with fallback to PyMuPDF"""
    filename = pdf_path.name
    
    # First try pdfplumber
    try:
        print(f"  📄 Trying pdfplumber for {filename}...")
        if password:
            print(f"  🔐 Trying to open with password...")
            pdf = pdfplumber.open(pdf_path, password=password)
        else:
            pdf = pdfplumber.open(pdf_path)
        
        text = ""
        for i, page in enumerate(pdf.pages):
            try:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            except Exception as e:
                print(f"    Page {i+1} error: {e}")
                continue
        pdf.close()
        
        if not text.strip():
            print(f"  ⚠️ pdfplumber: No text extracted, trying PyMuPDF...")
            return extract_text_with_pymupdf(pdf_path, password)
        
        print(f"  ✅ pdfplumber: Successfully extracted text ({len(text)} chars)")
        return text, None
        
    except Exception as e:
        error_msg = str(e).lower()
        print(f"  ⚠️ pdfplumber failed: {error_msg}")
        
        if "password" in error_msg or "encrypted" in error_msg or "decrypt" in error_msg:
            print(f"  🔐 Password required, trying PyMuPDF...")
            return extract_text_with_pymupdf(pdf_path, password)
        elif "invalid" in error_msg or "corrupt" in error_msg:
            print(f"  ⚠️ Invalid PDF, trying PyMuPDF...")
            return extract_text_with_pymupdf(pdf_path, password)
        else:
            print(f"  🔄 Trying PyMuPDF as fallback...")
            return extract_text_with_pymupdf(pdf_path, password)

def try_passwords_for_pdf(pdf_path, manual_password=None):
    """Try passwords to open a protected PDF"""
    filename = pdf_path.name
    print(f"  🔐 Trying passwords for protected PDF: {filename}")
    
    # First, try manual password from frontend
    if manual_password:
        print(f"  🔑 Trying manual password from frontend")
        text, error = extract_text_from_pdf(pdf_path, manual_password)
        if not error:
            print(f"  ✅ Success with manual password")
            return text, manual_password
    
    # Second, try specific password for this file from password directory
    specific_password = get_password_for_file(filename)
    if specific_password:
        print(f"  🔑 Trying specific password for {filename}")
        text, error = extract_text_from_pdf(pdf_path, specific_password)
        if not error:
            print(f"  ✅ Success with specific password for {filename}")
            return text, specific_password
    
    # Third, try all passwords from password directory
    all_passwords = get_all_passwords()
    
    # Skip passwords we already tried
    if manual_password and manual_password in all_passwords:
        all_passwords = [pwd for pwd in all_passwords if pwd != manual_password]
    if specific_password and specific_password in all_passwords:
        all_passwords = [pwd for pwd in all_passwords if pwd != specific_password]
    
    print(f"  🔑 Trying {len(all_passwords)} passwords from password directory")
    
    for password in all_passwords:
        print(f"  🔑 Trying password: {password[:10]}..." if len(password) > 10 else f"  🔑 Trying password: {password}")
        text, error = extract_text_from_pdf(pdf_path, password)
        if not error:
            print(f"  ✅ Success with password: {password[:10]}..." if len(password) > 10 else f"  ✅ Success with password: {password}")
            return text, password
    
    return None, "No password worked for this PDF. Try entering password manually or check if PDF is corrupted."

def parse_transactions_from_text(text, filename):
    """Parse transactions from extracted PDF text"""
    transactions = []
    lines = text.split('\n')
    
    # Common patterns for M-Pesa statements
    patterns = [
        # Pattern: DD/MM/YYYY HH:MM Description Amount Balance
        r'(\d{2}/\d{2}/\d{4})\s+\d{2}:\d{2}\s+(.*?)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})',
        # Pattern: DD/MM/YYYY Description Amount
        r'(\d{2}/\d{2}/\d{4})\s+(.*?)\s+([\d,]+\.\d{2})',
        # Pattern with KES: DD/MM/YYYY KES X,XXX.XX Description
        r'(\d{2}/\d{2}/\d{4})\s+KES\s+([\d,]+\.\d{2})\s+(.*)',
    ]
    
    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if len(line) < 10:  # Skip very short lines
            continue
        
        # Clean the line
        line = re.sub(r'\s+', ' ', line)
        
        transaction_found = False
        for pattern in patterns:
            match = re.search(pattern, line)
            if match:
                try:
                    if len(match.groups()) >= 3:
                        date_str = match.group(1)
                        
                        # Get amount based on pattern
                        if 'KES' in line.upper():
                            amount_str = match.group(2).replace(',', '')
                            details = match.group(3) if len(match.groups()) > 2 else line
                        else:
                            # Check which group is amount (usually the last number before balance)
                            groups = match.groups()
                            amount_str = groups[-2] if len(groups) >= 3 else groups[-1]
                            amount_str = amount_str.replace(',', '')
                            details = ' '.join(groups[1:-2]) if len(groups) > 3 else groups[1]
                        
                        try:
                            amount = float(amount_str)
                        except ValueError:
                            continue
                        
                        # Determine transaction type
                        line_lower = line.lower()
                        details_lower = details.lower()
                        
                        # Check for charges first
                        if any(word in line_lower or word in details_lower for word in 
                              ['charge', 'fee', 'commission', 'service fee', 'transaction charge']):
                            category = 'charge'
                            transaction_type = 'Charge'
                        
                        # Check for income
                        elif any(word in line_lower or word in details_lower for word in 
                                ['received', 'from', 'deposit', 'reversal', 'credit', 'paid in', 'cash in']):
                            category = 'income'
                            transaction_type = 'Paid In'
                        
                        # Check for expenses
                        elif any(word in line_lower or word in details_lower for word in 
                                ['sent', 'to', 'payment', 'withdrawal', 'transfer', 'buy', 'paid to', 'paid out', 'airtime']):
                            category = 'expense'
                            transaction_type = 'Paid Out'
                        
                        # Default based on context
                        else:
                            # Look for negative indicators
                            if '-' in line or ' dr ' in line_lower or 'debit' in line_lower:
                                category = 'expense'
                                transaction_type = 'Paid Out'
                            elif '+' in line or ' cr ' in line_lower or 'credit' in line_lower:
                                category = 'income'
                                transaction_type = 'Paid In'
                            else:
                                # If uncertain, check amount position in statement
                                # Usually expenses are listed as deductions
                                category = 'expense'
                                transaction_type = 'Paid Out'
                        
                        # Format date
                        try:
                            date_obj = datetime.strptime(date_str, '%d/%m/%Y')
                            formatted_date = date_obj.strftime('%Y-%m-%d')
                        except:
                            formatted_date = date_str
                        
                        # Clean up details
                        clean_details = extract_transaction_details(details)
                        
                        transaction = {
                            'date': formatted_date,
                            'amount': amount,
                            'category': category,
                            'transaction_type': transaction_type,
                            'details': clean_details,
                            'raw_details': line[:150],
                            'filename': filename,
                            'line_number': line_num,
                            'processed_at': datetime.now().isoformat()
                        }
                        
                        transactions.append(transaction)
                        print(f"    ✅ {formatted_date} - {transaction_type} - KES {amount:,.2f}")
                        transaction_found = True
                        break
                        
                except Exception as e:
                    print(f"    ⚠️ Error parsing line {line_num}: {e}")
                    continue
        
        # Fallback: Look for any amount and date in the line
        if not transaction_found:
            # Look for amount
            amount_match = re.search(r'(\d{1,3}(?:,\d{3})*\.\d{2})', line)
            if amount_match:
                try:
                    amount = float(amount_match.group(1).replace(',', ''))
                    
                    # Look for date
                    date_match = re.search(r'(\d{2}/\d{2}/\d{4})', line)
                    date_str = date_match.group(1) if date_match else datetime.now().strftime('%Y-%m-%d')
                    
                    # Determine category from line content
                    line_lower = line.lower()
                    if any(word in line_lower for word in ['received', 'from', 'deposit']):
                        category = 'income'
                        transaction_type = 'Paid In'
                    elif any(word in line_lower for word in ['sent', 'to', 'payment', 'withdrawal']):
                        category = 'expense'
                        transaction_type = 'Paid Out'
                    elif any(word in line_lower for word in ['charge', 'fee']):
                        category = 'charge'
                        transaction_type = 'Charge'
                    else:
                        category = 'expense'  # Default
                        transaction_type = 'Paid Out'
                    
                    transaction = {
                        'date': date_str,
                        'amount': amount,
                        'category': category,
                        'transaction_type': transaction_type,
                        'details': extract_transaction_details(line),
                        'raw_details': line[:150],
                        'filename': filename,
                        'line_number': line_num,
                        'processed_at': datetime.now().isoformat()
                    }
                    
                    transactions.append(transaction)
                    print(f"    ✅ (Fallback) {date_str} - {transaction_type} - KES {amount:,.2f}")
                    
                except Exception as e:
                    continue
    
    return transactions

def extract_transaction_details(details):
    """Extract meaningful details from transaction line"""
    if not details:
        return "Transaction"
    
    details_lower = details.lower()
    
    # Extract receiver/sender info
    if 'to' in details_lower:
        parts = details_lower.split('to')
        if len(parts) > 1:
            recipient = parts[1].split(' on ')[0].split(' from ')[0].split(' sent ')[0].strip()
            if recipient and len(recipient) > 2:
                return f"To: {recipient.title()}"
    
    if 'from' in details_lower:
        parts = details_lower.split('from')
        if len(parts) > 1:
            sender = parts[1].split(' on ')[0].split(' to ')[0].strip()
            if sender and len(sender) > 2:
                return f"From: {sender.title()}"
    
    # Return first meaningful part of details
    words = details.split()
    if len(words) > 2:
        # Skip date/amount if at beginning
        if re.match(r'\d+[/\-\.]\d+[/\-\.]\d+', words[0]):
            return ' '.join(words[2:5])[:50]
        elif words[0].replace(',', '').replace('.', '').isdigit():
            return ' '.join(words[1:4])[:50]
    
    return details[:50]

def check_file_exists(filename):
    """Check if a PDF file still exists in the folder"""
    pdf_path = PDF_DIR / filename
    return pdf_path.exists()

def process_pdf_file(pdf_path, manual_password=None):
    """Process a single PDF file and extract transactions"""
    filename = pdf_path.name
    
    # Check if file exists before processing
    if not pdf_path.exists():
        return None, f"File not found: {filename}"
    
    print(f"\n{'='*60}")
    print(f"🔍 PROCESSING: {filename}")
    print(f"{'='*60}")
    
    # Check file size
    file_size = pdf_path.stat().st_size
    print(f"  📊 File size: {file_size:,} bytes")
    
    if file_size == 0:
        return None, "PDF file is empty (0 bytes)"
    
    # First try without password
    text, error = extract_text_from_pdf(pdf_path, manual_password)
    
    # If password required, try all password sources
    if error and "password" in error.lower():
        print(f"  🔐 PDF is password protected")
        text, used_password = try_passwords_for_pdf(pdf_path, manual_password)
        if not text:
            return None, "Password required. Add password to passwords folder or enter manually."
    
    elif error:
        return None, error
    
    # Parse transactions
    transactions = parse_transactions_from_text(text, filename)
    
    if not transactions:
        return None, "No transactions found in PDF (might be image-based or different format)"
    
    # Categorize transactions properly
    categorized = []
    for tx in transactions:
        # Ensure every transaction has proper category
        if tx['category'] not in ['income', 'expense', 'charge']:
            # Re-categorize based on details
            details_lower = tx.get('details', '').lower()
            if any(word in details_lower for word in ['charge', 'fee']):
                tx['category'] = 'charge'
                tx['transaction_type'] = 'Charge'
            elif any(word in details_lower for word in ['received', 'from', 'deposit']):
                tx['category'] = 'income'
                tx['transaction_type'] = 'Paid In'
            else:
                tx['category'] = 'expense'
                tx['transaction_type'] = 'Paid Out'
        categorized.append(tx)
    
    print(f"📊 Found {len(categorized)} transactions")
    print(f"{'='*60}")
    
    return categorized, None

def auto_scan_all_pdfs():
    """Automatically scan and process all PDFs in the statements folder"""
    global transactions_cache, processed_files, scan_results, failed_files
    
    print(f"\n{'#'*70}")
    print(f"🚀 M-LEDGER AI - STARTING AUTOMATIC PDF SCAN")
    print(f"{'#'*70}")
    print(f"📁 PDF Directory: {PDF_DIR}")
    print(f"🔑 Password Directory: {PASSWORD_DIR}")
    print(f"{'#'*70}\n")
    
    # Check password directory setup
    if PASSWORD_DIR.exists():
        password_files = list(PASSWORD_DIR.glob("*.txt"))
        print(f"📋 Found {len(password_files)} password files in password directory")
        for pwd_file in password_files:
            print(f"   • {pwd_file.name}")
    else:
        print(f"⚠️  Password directory not found: {PASSWORD_DIR}")
        print(f"✅ Created password directory")
    
    # Load existing cache
    load_cache()
    
    # Check if PDF directory exists
    if not PDF_DIR.exists():
        print(f"❌ PDF directory not found: {PDF_DIR}")
        print(f"✅ Created directory: {PDF_DIR}")
        return
    
    # Find all PDF files
    pdf_files = list(PDF_DIR.glob("*.pdf"))
    pdf_files.extend(PDF_DIR.glob("*.PDF"))
    
    if not pdf_files:
        print("📭 No PDF files found in directory")
        print("💡 Place your M-Pesa statement PDFs in the 'mpesa_statements' folder")
        return
    
    print(f"📄 Found {len(pdf_files)} PDF file(s):")
    for pdf in pdf_files:
        file_size = pdf.stat().st_size
        print(f"   • {pdf.name} ({file_size:,} bytes)")
    
    print(f"\n🔄 Processing PDFs...")
    
    # Process each PDF
    for pdf_path in pdf_files:
        filename = pdf_path.name
        
        # Skip if already processed and file still exists
        if filename in processed_files and check_file_exists(filename):
            print(f"\n⏭️  Already processed: {filename}")
            continue
        
        print(f"\n{'='*50}")
        print(f"🔄 Processing: {filename}")
        print(f"{'='*50}")
        
        try:
            # Try processing without manual password first (will use password directory passwords)
            transactions, error = process_pdf_file(pdf_path, None)
            
            if error:
                print(f"❌ Failed: {error}")
                scan_results.append({
                    'file': filename,
                    'status': 'failed',
                    'message': error,
                    'timestamp': datetime.now().isoformat()
                })
                failed_files[filename] = error
                continue
            
            # Add to cache with proper categorization
            for tx in transactions:
                # Ensure proper category mapping
                tx['category'] = CATEGORY_MAP.get(tx['category'].lower(), tx['category'])
                transactions_cache.append(tx)
            
            processed_files.add(filename)
            
            # Count categories
            income_count = sum(1 for t in transactions if t['category'] == 'income')
            expense_count = sum(1 for t in transactions if t['category'] == 'expense')
            charge_count = sum(1 for t in transactions if t['category'] == 'charge')
            
            scan_results.append({
                'file': filename,
                'status': 'success',
                'message': f'Processed {len(transactions)} transactions ({income_count} income, {expense_count} expense, {charge_count} charge)',
                'transactions': len(transactions),
                'timestamp': datetime.now().isoformat()
            })
            
            print(f"✅ Successfully processed {filename}")
            print(f"   📊 {income_count} income, {expense_count} expense, {charge_count} charge")
            
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
            failed_files[filename] = error_msg
    
    # Clean up cache - remove transactions from files that no longer exist
    cleanup_cache()
    
    # Format transactions for display
    format_transactions_for_display()
    
    # Save cache
    save_cache()
    
    print(f"\n{'#'*70}")
    print(f"📊 SCAN COMPLETE - SUMMARY")
    print(f"{'#'*70}")
    print(f"✅ Processed files: {len(processed_files)}")
    print(f"✅ Total transactions: {len(transactions_cache)}")
    print(f"❌ Failed files: {len(failed_files)}")
    
    if failed_files:
        print(f"\n⚠️  FILES NEEDING ATTENTION:")
        for filename, error in failed_files.items():
            print(f"   • {filename}: {error}")
        print(f"\n💡 Troubleshooting steps:")
        print(f"   1. Check if PDF files are valid (try opening in a PDF viewer)")
        print(f"   2. Ensure PDFs are not corrupted")
        print(f"   3. Try uploading PDFs through the web interface with manual password")
        print(f"   4. Check password files contain correct passwords")
    
    summary = calculate_summary()
    print(f"\n💰 FINANCIAL SUMMARY:")
    print(f"   • Income: KES {summary['income']:,.2f}")
    print(f"   • Expenses: KES {summary['expenses']:,.2f}")
    print(f"   • Charges: KES {summary['charges']:,.2f}")
    print(f"   • Balance: KES {summary['balance']:,.2f}")
    print(f"{'#'*70}\n")

def cleanup_cache():
    """Remove transactions from files that no longer exist"""
    global transactions_cache, processed_files
    
    # Get list of files that currently exist
    existing_files = {f.name for f in PDF_DIR.glob("*.pdf")} | {f.name for f in PDF_DIR.glob("*.PDF")}
    
    # Filter transactions
    new_transactions = []
    for tx in transactions_cache:
        if tx['filename'] in existing_files:
            new_transactions.append(tx)
    
    # Update processed files
    processed_files = processed_files.intersection(existing_files)
    
    removed_count = len(transactions_cache) - len(new_transactions)
    if removed_count > 0:
        print(f"🧹 Cleaned up {removed_count} transactions from removed files")
        transactions_cache = new_transactions

def format_transactions_for_display():
    """Format transactions for display in table"""
    if not transactions_cache:
        return
    
    # Sort by date
    sorted_transactions = sorted(
        transactions_cache,
        key=lambda x: datetime.strptime(x['date'], '%Y-%m-%d') if '-' in x['date'] else datetime.now()
    )
    
    running_balance = 0
    
    for tx in sorted_transactions:
        # Set display values based on category
        if tx['category'] == 'income':
            tx['display_type'] = 'Paid In'
            tx['paid_in'] = tx['amount']
            tx['paid_out'] = 0
            tx['charge'] = 0
            running_balance += tx['amount']
        elif tx['category'] == 'expense':
            tx['display_type'] = 'Paid Out'
            tx['paid_in'] = 0
            tx['paid_out'] = tx['amount']
            tx['charge'] = 0
            running_balance -= tx['amount']
        elif tx['category'] == 'charge':
            tx['display_type'] = 'Charge'
            tx['paid_in'] = 0
            tx['paid_out'] = 0
            tx['charge'] = tx['amount']
            running_balance -= tx['amount']
        
        tx['balance'] = round(running_balance, 2)
        tx['formatted_amount'] = format_number(tx['amount'])
        tx['formatted_paid_in'] = format_number(tx['paid_in']) if tx['paid_in'] > 0 else ''
        tx['formatted_paid_out'] = format_number(tx['paid_out']) if tx['paid_out'] > 0 else ''
        tx['formatted_charge'] = format_number(tx['charge']) if tx['charge'] > 0 else ''
        tx['formatted_balance'] = format_number(tx['balance'])
        
        # CSS classes
        if tx['category'] == 'income':
            tx['row_class'] = 'income-row'
            tx['type_class'] = 'type-income'
        elif tx['category'] == 'expense':
            tx['row_class'] = 'expense-row'
            tx['type_class'] = 'type-expense'
        elif tx['category'] == 'charge':
            tx['row_class'] = 'charge-row'
            tx['type_class'] = 'type-charge'

def calculate_summary(transactions=None):
    """Calculate financial summary"""
    if transactions is None:
        transactions = transactions_cache
    
    income = sum(tx['amount'] for tx in transactions if tx['category'] == 'income')
    expenses = sum(tx['amount'] for tx in transactions if tx['category'] == 'expense')
    charges = sum(tx['amount'] for tx in transactions if tx['category'] == 'charge')
    balance = income - expenses - charges
    
    return {
        'income': income,
        'expenses': expenses,
        'charges': charges,
        'balance': balance
    }

# ----------------- ROUTES -----------------
@app.route("/", methods=["GET", "POST"])
def index():
    """Main page - handles uploads and displays transactions with pagination"""
    upload_message = ""
    upload_success = False
    
    # Get filter parameters
    type_filter = request.args.get('type_filter', 'all')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    statement_filter = request.args.get('statement_filter', 'all')
    page = request.args.get('page', 1, type=int)
    
    # Format transactions for display
    format_transactions_for_display()
    
    # Get all unique filenames for statement filter dropdown
    all_filenames = sorted(set(tx['filename'] for tx in transactions_cache if 'filename' in tx))
    
    # Filter transactions
    filtered = transactions_cache.copy()
    
    # Apply filters
    if type_filter != 'all':
        filtered = [t for t in filtered if t['category'] == type_filter]
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
    if statement_filter != 'all':
        filtered = [t for t in filtered if t['filename'] == statement_filter]
    
    # Sort filtered by date (newest first)
    filtered.sort(key=lambda x: datetime.strptime(x['date'], '%Y-%m-%d'), reverse=True)
    
    # Handle file upload
    if request.method == "POST" and 'statement' in request.files:
        uploaded_file = request.files.get("statement")
        pdf_password = request.form.get("pdf_password", "").strip()
        
        if uploaded_file and uploaded_file.filename:
            filename = uploaded_file.filename
            
            if not filename.lower().endswith(".pdf"):
                upload_message = "❌ Only PDF files are allowed."
            else:
                # Save file
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_name = f"{timestamp}_{filename}"
                save_path = PDF_DIR / safe_name
                
                try:
                    uploaded_file.save(save_path)
                    print(f"📤 File uploaded: {safe_name}")
                    print(f"🔑 Using password: {'Yes' if pdf_password else 'No (will try auto passwords)'}")
                    
                    # Process with optional password
                    password_to_use = pdf_password if pdf_password else None
                    transactions, error = process_pdf_file(save_path, password_to_use)
                    
                    if error:
                        upload_message = f"❌ {error}"
                    else:
                        # Add to cache with statement tracking
                        for tx in transactions:
                            tx['filename'] = safe_name
                            tx['statement_name'] = filename  # Original name
                            transactions_cache.append(tx)
                        
                        processed_files.add(safe_name)
                        format_transactions_for_display()
                        save_cache()
                        
                        # Update all_filenames list
                        all_filenames = sorted(set(tx['filename'] for tx in transactions_cache if 'filename' in tx))
                        
                        upload_success = True
                        upload_message = f"✅ Processed {len(transactions)} transactions from {filename}"
                        
                except Exception as e:
                    upload_message = f"❌ Upload failed: {str(e)}"
    
    # Pagination logic - 5 transactions per page
    transactions_per_page = 5
    total_transactions = len(filtered)
    total_pages = (total_transactions + transactions_per_page - 1) // transactions_per_page
    
    # Ensure page is within valid range
    page = max(1, min(page, total_pages))
    
    # Calculate start and end indices
    start_idx = (page - 1) * transactions_per_page
    end_idx = min(start_idx + transactions_per_page, total_transactions)
    
    # Get transactions for current page
    paginated_transactions = filtered[start_idx:end_idx]
    
    # Add statement name display to each transaction
    for tx in paginated_transactions:
        if 'statement_name' not in tx:
            # Extract original filename from timestamp_filename format
            filename = tx.get('filename', '')
            if '_' in filename:
                tx['statement_name'] = '_'.join(filename.split('_')[2:]) if len(filename.split('_')) > 2 else filename
            else:
                tx['statement_name'] = filename
    
    # Calculate summary for filtered transactions
    summary = calculate_summary(filtered)
    
    return render_template(
        "index.html",
        income=summary['income'],
        expenses=summary['expenses'],
        charges=summary['charges'],
        balance=summary['balance'],
        transactions=paginated_transactions,
        all_statements=all_filenames,
        scan_results=scan_results[-10:],
        upload_success=upload_success,
        upload_message=upload_message,
        total_transactions=total_transactions,
        type_filter=type_filter,
        start_date=start_date,
        end_date=end_date,
        statement_filter=statement_filter,
        current_page=page,
        total_pages=total_pages,
        has_prev=page > 1,
        has_next=page < total_pages,
        prev_page=page - 1,
        next_page=page + 1,
        page_numbers=[i for i in range(max(1, page-2), min(total_pages, page+3)+1)]
    )

@app.route("/filter_transactions", methods=["GET"])
def filter_transactions():
    """Filter transactions endpoint"""
    type_filter = request.args.get('type_filter', 'all')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    statement_filter = request.args.get('statement_filter', 'all')
    page = request.args.get('page', 1, type=int)
    
    # Build redirect URL with filters
    params = []
    if type_filter != 'all':
        params.append(f"type_filter={type_filter}")
    if start_date:
        params.append(f"start_date={start_date}")
    if end_date:
        params.append(f"end_date={end_date}")
    if statement_filter != 'all':
        params.append(f"statement_filter={statement_filter}")
    if page > 1:
        params.append(f"page={page}")
    
    redirect_url = "/"
    if params:
        redirect_url += "?" + "&".join(params)
    
    return redirect(redirect_url)

@app.route("/clear_cache", methods=["POST"])
def clear_cache():
    """Clear all cached data"""
    global transactions_cache, processed_files, scan_results
    
    transactions_cache = []
    processed_files = set()
    scan_results = []
    
    # Delete cache file
    if CACHE_FILE.exists():
        CACHE_FILE.unlink()
    
    return jsonify({
        "success": True,
        "message": "Cache cleared successfully"
    })

@app.route("/refresh_scan", methods=["POST"])
def refresh_scan():
    """Rescan all PDFs in directory"""
    auto_scan_all_pdfs()
    
    return jsonify({
        "success": True,
        "message": f"Rescan completed. Found {len(transactions_cache)} transactions."
    })

@app.route("/export_csv", methods=["GET"])
def export_csv():
    """Export transactions as CSV"""
    import csv
    
    # Get filters from request
    type_filter = request.args.get('type_filter', 'all')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    statement_filter = request.args.get('statement_filter', 'all')
    
    # Filter transactions
    filtered = transactions_cache.copy()
    
    if type_filter != 'all':
        filtered = [t for t in filtered if t['category'] == type_filter]
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
    if statement_filter != 'all':
        filtered = [t for t in filtered if t['filename'] == statement_filter]
    
    # Sort by date
    filtered.sort(key=lambda x: datetime.strptime(x['date'], '%Y-%m-%d'), reverse=True)
    
    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'Date', 'Transaction Type', 'Details', 
        'Paid In', 'Paid Out', 'Charge', 'Balance',
        'Statement File', 'Original File Name'
    ])
    
    # Write data
    running_balance = 0
    for tx in filtered:
        # Calculate running balance
        if tx['category'] == 'income':
            paid_in = tx['amount']
            paid_out = 0
            charge = 0
            running_balance += tx['amount']
        elif tx['category'] == 'expense':
            paid_in = 0
            paid_out = tx['amount']
            charge = 0
            running_balance -= tx['amount']
        else:  # charge
            paid_in = 0
            paid_out = 0
            charge = tx['amount']
            running_balance -= tx['amount']
        
        # Get statement name
        statement_name = tx.get('statement_name', tx.get('filename', ''))
        
        writer.writerow([
            tx['date'],
            tx.get('transaction_type', ''),
            tx.get('details', ''),
            paid_in,
            paid_out,
            charge,
            running_balance,
            tx.get('filename', ''),
            statement_name
        ])
    
    # Prepare response
    output.seek(0)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f"mpesa_transactions_{timestamp}.csv"
    )

@app.route("/download_pdf", methods=["GET"])
def download_pdf():
    """Generate and download PDF report"""
    # Get filters from request
    type_filter = request.args.get('type_filter', 'all')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    statement_filter = request.args.get('statement_filter', 'all')
    
    # Filter transactions
    filtered = transactions_cache.copy()
    
    if type_filter != 'all':
        filtered = [t for t in filtered if t['category'] == type_filter]
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
    if statement_filter != 'all':
        filtered = [t for t in filtered if t['filename'] == statement_filter]
    
    # Sort by date
    filtered.sort(key=lambda x: datetime.strptime(x['date'], '%Y-%m-%d'))
    
    # Create PDF
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    # Title
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, height - 50, "M-Pesa Transactions Report")
    
    # Date range
    c.setFont("Helvetica", 10)
    report_date = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.drawString(50, height - 70, f"Generated: {report_date}")
    
    if start_date or end_date:
        date_range = f"Date range: {start_date if start_date else 'Start'} to {end_date if end_date else 'End'}"
        c.drawString(50, height - 85, date_range)
    
    # Summary
    summary = calculate_summary(filtered)
    c.drawString(50, height - 105, f"Total Income: KES {summary['income']:,.2f}")
    c.drawString(50, height - 120, f"Total Expenses: KES {summary['expenses']:,.2f}")
    c.drawString(50, height - 135, f"Total Charges: KES {summary['charges']:,.2f}")
    c.drawString(50, height - 150, f"Net Balance: KES {summary['balance']:,.2f}")
    
    # Table headers
    y_position = height - 180
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y_position, "Date")
    c.drawString(100, y_position, "Type")
    c.drawString(150, y_position, "Details")
    c.drawString(300, y_position, "Amount")
    c.drawString(400, y_position, "Statement")
    
    # Table rows
    c.setFont("Helvetica", 9)
    y_position -= 20
    
    running_balance = 0
    for tx in filtered:
        if y_position < 50:
            c.showPage()
            y_position = height - 50
            c.setFont("Helvetica", 9)
        
        # Calculate amount display
        if tx['category'] == 'income':
            amount_display = f"+{tx['amount']:,.2f}"
            running_balance += tx['amount']
        elif tx['category'] == 'expense':
            amount_display = f"-{tx['amount']:,.2f}"
            running_balance -= tx['amount']
        else:
            amount_display = f"-{tx['amount']:,.2f} (Charge)"
            running_balance -= tx['amount']
        
        # Get statement name
        statement_name = tx.get('statement_name', tx.get('filename', ''))
        if len(statement_name) > 20:
            statement_name = statement_name[:17] + "..."
        
        c.drawString(50, y_position, tx['date'])
        c.drawString(100, y_position, tx.get('transaction_type', ''))
        
        # Truncate details if too long
        details = tx.get('details', '')
        if len(details) > 30:
            details = details[:27] + "..."
        c.drawString(150, y_position, details)
        
        c.drawString(300, y_position, amount_display)
        c.drawString(400, y_position, statement_name)
        
        y_position -= 15
    
    # Final balance
    y_position -= 10
    c.setFont("Helvetica-Bold", 10)
    c.drawString(300, y_position, f"Final Balance: KES {running_balance:,.2f}")
    
    c.save()
    buffer.seek(0)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"mpesa_report_{timestamp}.pdf"
    )

@app.route("/process_with_password", methods=["POST"])
def process_with_password():
    """Process a specific PDF with a manually entered password"""
    try:
        data = request.get_json()
        filename = data.get("filename")
        password = data.get("password", "").strip()
        
        if not filename:
            return jsonify({
                "success": False,
                "message": "Filename is required"
            })
        
        pdf_path = PDF_DIR / filename
        
        if not pdf_path.exists():
            return jsonify({
                "success": False,
                "message": f"File not found: {filename}"
            })
        
        print(f"\n{'='*50}")
        print(f"🔐 Processing with manual password: {filename}")
        print(f"{'='*50}")
        
        # Process with manual password
        transactions, error = process_pdf_file(pdf_path, password)
        
        if error:
            return jsonify({
                "success": False,
                "message": error
            })
        
        # Add to cache with statement tracking
        for tx in transactions:
            tx['filename'] = filename
            tx['statement_name'] = filename
            transactions_cache.append(tx)
        
        processed_files.add(filename)
        format_transactions_for_display()
        save_cache()
        
        # Remove from failed files if it was there
        if filename in failed_files:
            failed_files.pop(filename)
        
        return jsonify({
            "success": True,
            "message": f"Successfully processed {len(transactions)} transactions",
            "transactions_count": len(transactions)
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error: {str(e)}"
        })

@app.route("/ai_chat", methods=["POST"])
def ai_chat():
    """Simple AI chat endpoint for transaction queries"""
    try:
        data = request.get_json()
        query = data.get("query", "").lower()
        
        if not query:
            return jsonify({"response": "Please enter a question."})
        
        # Simple keyword-based responses
        if "total" in query and "income" in query:
            summary = calculate_summary()
            return jsonify({
                "response": f"Total Income: KES {summary['income']:,.2f}"
            })
        
        elif "total" in query and ("expense" in query or "expenses" in query):
            summary = calculate_summary()
            return jsonify({
                "response": f"Total Expenses: KES {summary['expenses']:,.2f}"
            })
        
        elif "total" in query and "charge" in query:
            summary = calculate_summary()
            return jsonify({
                "response": f"Total Charges: KES {summary['charges']:,.2f}"
            })
        
        elif "balance" in query or "net" in query:
            summary = calculate_summary()
            return jsonify({
                "response": f"Net Balance: KES {summary['balance']:,.2f}"
            })
        
        elif "how many" in query and "transaction" in query:
            return jsonify({
                "response": f"Total transactions: {len(transactions_cache)}"
            })
        
        elif "recent" in query or "latest" in query:
            recent = sorted(transactions_cache, 
                          key=lambda x: datetime.strptime(x['date'], '%Y-%m-%d'), 
                          reverse=True)[:5]
            response = "Recent transactions:\n"
            for tx in recent:
                response += f"{tx['date']}: {tx.get('details', 'Transaction')} - KES {tx['amount']:,.2f}\n"
            return jsonify({"response": response})
        
        elif "statement" in query or "file" in query:
            # Count transactions per statement
            statement_counts = {}
            for tx in transactions_cache:
                filename = tx.get('filename', 'Unknown')
                statement_counts[filename] = statement_counts.get(filename, 0) + 1
            
            response = "Transactions per statement:\n"
            for filename, count in statement_counts.items():
                # Extract original name
                if '_' in filename:
                    display_name = '_'.join(filename.split('_')[2:]) if len(filename.split('_')) > 2 else filename
                else:
                    display_name = filename
                response += f"• {display_name}: {count} transactions\n"
            
            return jsonify({"response": response})
        
        else:
            return jsonify({
                "response": f"I can help you with:\n• Total income/expenses/charges\n• Net balance\n• Number of transactions\n• Recent transactions\n• Statement summaries\n\nAsk me about your M-Pesa transactions!"
            })
            
    except Exception as e:
        return jsonify({"response": f"Error: {str(e)}"})

# ----------------- TEMPLATE FILTERS -----------------
@app.template_filter("format_number")
def format_number(value):
    """Format number with commas"""
    try:
        return "{:,.2f}".format(float(value))
    except:
        return str(value)

@app.template_filter("truncate_filename")
def truncate_filename(filename, length=30):
    """Truncate filename for display"""
    if len(filename) <= length:
        return filename
    
    # Try to extract original name from timestamp_filename
    if '_' in filename:
        parts = filename.split('_')
        if len(parts) >= 3:
            original = '_'.join(parts[2:])
            if len(original) <= length:
                return original
    
    return filename[:length-3] + "..."

# ----------------- HELPER FUNCTIONS -----------------
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
            'scan_results': scan_results[-20:],
            'last_updated': datetime.now().isoformat(),
            'total_transactions': len(transactions_cache)
        }
        
        with open(CACHE_FILE, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        
        print(f"💾 Cache saved: {len(transactions_cache)} transactions")
    except Exception as e:
        print(f"❌ Error saving cache: {e}")

# ----------------- INITIALIZATION -----------------
if __name__ == "__main__":
    print("\n" + "="*70)
    print("🚀 M-LEDGER AI - FINANCIAL STATEMENT ANALYZER")
    print("="*70)
    print(f"📁 Working Directory: {BASE_DIR}")
    print(f"📄 PDF Statements: {PDF_DIR}")
    print(f"🔑 Passwords: {PASSWORD_DIR}")
    print("="*70)
    
    # Initial scan
    auto_scan_all_pdfs()
    
    print(f"\n🌐 Starting web server on http://localhost:5000")
    print("="*70)
    
    app.run(debug=True, host='0.0.0.0', port=5000)