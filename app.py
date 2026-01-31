from flask import Flask, render_template, request, jsonify, send_file
import os
import io
import re
import pdfplumber
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'


STATEMENTS_DIR = 'mpesa_statements'
PASSWORD_DIR = 'passwords'
os.makedirs(STATEMENTS_DIR, exist_ok=True)
os.makedirs(PASSWORD_DIR, exist_ok=True)


@app.template_filter('format_number')
def format_number(value):
    try:
        if isinstance(value, (int, float)):
            return f"{value:,.2f}"
        return value
    except:
        return value


def parse_pdf(file_path, password=None):
    transactions = []
    total_income = 0
    total_expense = 0
    total_charges = 0

    try:
        with pdfplumber.open(file_path, password=password) as pdf:
            text = ""
            for page in pdf.pages:
                txt = page.extract_text()
                if txt:
                    text += txt + "\n"

        lines = text.splitlines()
        for line in lines:
            line = line.strip()
            if not line:
                continue

        
            pattern = r'(\d{1,2}/\d{1,2}/\d{4}).*?(?:KES\s*([\d,]+\.?\d*))'
            match = re.search(pattern, line)
            if match:
                date_str = match.group(1)
                amount = float(match.group(2).replace(',', ''))

            
                lc = line.lower()
                if 'received' in lc or 'deposit' in lc:
                    category = 'income'
                    total_income += amount
                elif 'sent' in lc or 'withdraw' in lc:
                    category = 'expense'
                    total_expense += amount
                elif 'charge' in lc or 'fee' in lc:
                    category = 'charge'
                    total_charges += amount
                else:
                    category = 'other'

                transactions.append({
                    'date': date_str,
                    'details': line[:100],
                    'amount': amount,
                    'category': category,
                    'balance': None
                })
    except Exception as e:
        raise e

    balance = total_income - total_expense - total_charges
    
    running_balance = 0
    for t in transactions:
        if t['category'] == 'income':
            running_balance += t['amount']
        elif t['category'] == 'expense' or t['category'] == 'charge':
            running_balance -= t['amount']
        t['balance'] = running_balance

    return {
        'transactions': transactions,
        'total_income': total_income,
        'total_expense': total_expense,
        'total_charges': total_charges,
        'balance': balance
    }

def try_passwords(file_path):
    
    try:
        return parse_pdf(file_path), None
    except Exception as e:
        if 'password' not in str(e).lower():
            raise e

    
    for pw_file in os.listdir(PASSWORD_DIR):
        if pw_file.lower().endswith('.txt'):
            with open(os.path.join(PASSWORD_DIR, pw_file), 'r', encoding='utf-8') as f:
                pw = f.read().strip()
            try:
                return parse_pdf(file_path, password=pw), pw
            except:
                continue
    raise ValueError("PDF is password protected and no valid password found.")


def auto_load_statements():
    statements = []
    for fname in os.listdir(STATEMENTS_DIR):
        if not fname.lower().endswith('.pdf'):
            continue
        fpath = os.path.join(STATEMENTS_DIR, fname)
        try:
            result, used_pw = try_passwords(fpath)
            statements.append({
                'filename': fname,
                'transactions': result['transactions'],
                'income': result['total_income'],
                'expenses': result['total_expense'],
                'charges': result['total_charges'],
                'balance': result['balance'],
                'password_used': used_pw
            })
        except Exception as e:
            statements.append({
                'filename': fname,
                'error': str(e)
            })
    return statements


@app.route('/', methods=['GET'])
def index():
    statements = auto_load_statements()

    
    all_tx = []
    for s in statements:
        if 'transactions' in s:
            all_tx.extend(s['transactions'])

    total_income = sum(t['amount'] for t in all_tx if t['category']=='income')
    total_expense = sum(t['amount'] for t in all_tx if t['category']=='expense')
    total_charges = sum(t['amount'] for t in all_tx if t['category']=='charge')
    total_balance = total_income - total_expense - total_charges

    return render_template(
        'index.html',
        transactions=all_tx,
        income=total_income,
        expenses=total_expense,
        charges=total_charges,
        balance=total_balance
    )


@app.route('/ai_chat', methods=['POST'])
def ai_chat():
    data = request.get_json()
    question = data.get('question', '')

    statements = auto_load_statements()
    all_tx = []
    for s in statements:
        if 'transactions' in s:
            all_tx.extend(s['transactions'])

    if not all_tx:
        return jsonify({'success': False, 'answer': 'No statements available.'})

    q = question.lower()
    if 'income' in q:
        total = sum(t['amount'] for t in all_tx if t['category']=='income')
        answer = f"Total income: KES {total:,.2f}"
    elif 'expense' in q or 'spend' in q:
        total = sum(t['amount'] for t in all_tx if t['category']=='expense')
        answer = f"Total expenses: KES {total:,.2f}"
    elif 'balance' in q:
        total_income = sum(t['amount'] for t in all_tx if t['category']=='income')
        total_expense = sum(t['amount'] for t in all_tx if t['category']=='expense')
        total_charges = sum(t['amount'] for t in all_tx if t['category']=='charge')
        balance = total_income - total_expense - total_charges
        answer = f"Current balance: KES {balance:,.2f}"
    else:
        answer = "Ask about income, expenses, balance, or charges."

    return jsonify({'success': True, 'answer': answer})


@app.route('/download_pdf')
def download_pdf():
    try:
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)
        c.drawString(100, 750, "M-Ledger AI Financial Report")
        c.drawString(100, 730, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        c.drawString(100, 710, "---")
        c.drawString(100, 690, "Thank you for using M-Ledger AI!")
        c.save()
        buffer.seek(0)
        return send_file(buffer, as_attachment=True, download_name='M-Ledger_Report.pdf', mimetype='application/pdf')
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000)
