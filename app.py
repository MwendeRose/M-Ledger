from flask import Flask, render_template, request, jsonify, send_file, Response
from werkzeug.utils import secure_filename
import os
import json
from datetime import datetime
import pandas as pd
import io
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import re

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = 'uploads'
app.secret_key = 'your-secret-key-here'

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Custom Jinja2 filter for formatting numbers
@app.template_filter('format_number')
def format_number(value):
    try:
        if isinstance(value, (int, float)):
            return f"{value:,.2f}"
        return value
    except:
        return value

def parse_mpesa_statement(file_path, password=None):
    """Parse M-Pesa statement and extract transactions"""
    transactions = []
    total_income = 0
    total_expenses = 0
    total_charges = 0
    
    try:
        # Check file extension
        if file_path.lower().endswith('.csv'):
            # Parse CSV file
            df = pd.read_csv(file_path)
            
            # Adjust these column names based on your M-Pesa statement format
            for _, row in df.iterrows():
                try:
                    date = str(row.get('Completion Time', row.get('Date', ''))).strip()
                    details = str(row.get('Details', row.get('Transaction Details', ''))).strip()
                    amount = float(row.get('Paid In', 0) or row.get('Withdrawn', 0) or row.get('Amount', 0))
                    balance = float(row.get('Balance', 0))
                    
                    # Categorize transaction
                    if 'paid in' in str(row).lower() or amount > 0:
                        category = "income"
                        total_income += amount
                    elif 'withdrawn' in str(row).lower() or amount < 0:
                        category = "expense"
                        total_expenses += abs(amount)
                        amount = abs(amount)
                    elif 'charge' in str(row).lower() or 'fee' in str(row).lower():
                        category = "charge"
                        total_charges += amount
                    else:
                        # Try to categorize based on description
                        details_lower = details.lower()
                        if any(word in details_lower for word in ['sent', 'withdraw', 'payment', 'pay bill']):
                            category = "expense"
                            total_expenses += amount
                        elif any(word in details_lower for word in ['received', 'deposit']):
                            category = "income"
                            total_income += amount
                        else:
                            category = "other"
                    
                    transactions.append({
                        'date': date,
                        'details': details,
                        'amount': amount,
                        'category': category,
                        'balance': balance
                    })
                except Exception as e:
                    print(f"Error parsing row: {e}")
                    continue
        
        elif file_path.lower().endswith('.txt'):
            # Parse text file (common M-Pesa format)
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # M-Pesa text format patterns
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Try to extract transaction data using regex
                # This pattern might need adjustment based on your statement format
                pattern = r'(\d{1,2}/\d{1,2}/\d{4}).*?(?:KES\s*([\d,]+\.?\d*)).*?(?:Bal\s*([\d,]+\.?\d*))?'
                match = re.search(pattern, line)
                
                if match:
                    date = match.group(1)
                    amount_match = re.search(r'([\d,]+\.?\d*)', match.group(2) if match.group(2) else '0')
                    amount = float(amount_match.group(1).replace(',', '')) if amount_match else 0
                    
                    # Determine category from description
                    if 'sent' in line.lower() or 'withdraw' in line.lower():
                        category = "expense"
                        total_expenses += amount
                    elif 'received' in line.lower() or 'deposit' in line.lower():
                        category = "income"
                        total_income += amount
                    elif 'charge' in line.lower() or 'fee' in line.lower():
                        category = "charge"
                        total_charges += amount
                    else:
                        category = "other"
                    
                    transactions.append({
                        'date': date,
                        'details': line[:100],  # First 100 chars as details
                        'amount': amount,
                        'category': category,
                        'balance': None
                    })
        
        else:
            # For PDF files, you would need PyPDF2 or pdfplumber
            # For simplicity, we'll return empty for now
            print(f"Unsupported file format: {file_path}")
    
    except Exception as e:
        print(f"Error parsing statement: {e}")
    
    # Calculate current balance (last transaction's balance or sum)
    current_balance = 0
    if transactions:
        try:
            # Try to get last balance
            last_tx = [t for t in transactions if t.get('balance')][-1]
            current_balance = last_tx.get('balance', 0)
        except:
            # Calculate balance from transactions
            current_balance = total_income - total_expenses - total_charges
    
    return {
        'transactions': transactions,
        'total_income': total_income,
        'total_expenses': total_expenses,
        'total_charges': total_charges,
        'current_balance': current_balance
    }

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # Check if file was uploaded
        if 'statement' not in request.files:
            return render_template('index.html', 
                                 income=0, 
                                 expenses=0, 
                                 charges=0, 
                                 balance=0, 
                                 transactions=[],
                                 error="No file selected")
        
        file = request.files['statement']
        
        if file.filename == '':
            return render_template('index.html', 
                                 income=0, 
                                 expenses=0, 
                                 charges=0, 
                                 balance=0, 
                                 transactions=[],
                                 error="No file selected")
        
        if file:
            # Save uploaded file
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            
            # Get password if provided
            password = request.form.get('pdf_password', None)
            
            # Parse the statement
            try:
                result = parse_mpesa_statement(file_path, password)
                
                # Clean up uploaded file
                if os.path.exists(file_path):
                    os.remove(file_path)
                
                return render_template('index.html',
                                     income=result['total_income'],
                                     expenses=result['total_expenses'],
                                     charges=result['total_charges'],
                                     balance=result['current_balance'],
                                     transactions=result['transactions'])
            
            except Exception as e:
                # Clean up on error
                if os.path.exists(file_path):
                    os.remove(file_path)
                
                return render_template('index.html',
                                     income=0,
                                     expenses=0,
                                     charges=0,
                                     balance=0,
                                     transactions=[],
                                     error=f"Error parsing statement: {str(e)}")
    
    # GET request or initial load
    return render_template('index.html',
                         income=0,
                         expenses=0,
                         charges=0,
                         balance=0,
                         transactions=[])

@app.route('/filter_transactions', methods=['POST'])
def filter_transactions():
    try:
        data = request.get_json()
        
        # Get filter parameters
        type_filter = data.get('type_filter', 'all')
        amount_filter = data.get('amount_filter', 'none')
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        # In a real app, you would filter from database
        # For now, return sample filtered data
        filtered_transactions = []
        
        # Sample transaction structure
        sample_transactions = [
            {
                'date': '2024-01-15',
                'details': 'Payment received from John',
                'amount': 5000.00,
                'category': 'income',
                'balance': 15000.00
            },
            {
                'date': '2024-01-16',
                'details': 'Supermarket purchase',
                'amount': 2500.00,
                'category': 'expense',
                'balance': 12500.00
            },
            {
                'date': '2024-01-17',
                'details': 'Transaction fee',
                'amount': 10.00,
                'category': 'charge',
                'balance': 12490.00
            }
        ]
        
        # Apply filters (simplified)
        for tx in sample_transactions:
            if type_filter == 'all' or tx['category'] == type_filter:
                filtered_transactions.append(tx)
        
        return jsonify({
            'success': True,
            'transactions': filtered_transactions,
            'count': len(filtered_transactions)
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/ai_chat', methods=['POST'])
def ai_chat():
    try:
        data = request.get_json()
        question = data.get('question', '')
        
        # Simple AI response based on keywords
        responses = {
            'income': "Your total income is KES {{income}}. This includes all money received.",
            'expense': "Your total expenses are KES {{expenses}}. Consider reviewing your spending habits.",
            'balance': "Your current balance is KES {{balance}}. Make sure to maintain a positive balance.",
            'save': "Based on your spending, you could save more by reducing unnecessary expenses.",
            'help': "I can help you analyze your finances. Ask about income, expenses, or savings tips."
        }
        
        answer = "I've analyzed your statement. "
        
        # Check for keywords
        question_lower = question.lower()
        if 'income' in question_lower:
            answer += responses['income']
        elif 'expense' in question_lower or 'spend' in question_lower:
            answer += responses['expense']
        elif 'balance' in question_lower:
            answer += responses['balance']
        elif 'save' in question_lower:
            answer += responses['save']
        else:
            answer += responses['help']
        
        return jsonify({
            'success': True,
            'answer': answer
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/download_pdf')
def download_pdf():
    """Generate PDF report"""
    try:
        # Create PDF in memory
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)
        
        # Add content to PDF
        c.drawString(100, 750, "M-Ledger AI Financial Report")
        c.drawString(100, 730, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        c.drawString(100, 710, "---")
        
        # You can add more detailed report here
        c.drawString(100, 690, "Thank you for using M-Ledger AI!")
        
        c.save()
        buffer.seek(0)
        
        return send_file(buffer, 
                        as_attachment=True, 
                        download_name='M-Ledger_Report.pdf',
                        mimetype='application/pdf')
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)