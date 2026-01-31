import os
from pdf_parser import parse_mpesa_pdf

def load_statements(statements_folder="mpesa_statements", passwords_folder="passwords"):
    """
    Load all PDF statements and parse transactions.
    Automatically detects and applies passwords from the passwords folder.
    """
    statements = []

    # Load all passwords into a dict
    pw_dict = {}
    for pw_file in os.listdir(passwords_folder):
        if pw_file.endswith(".txt"):
            base_name = os.path.splitext(pw_file)[0]
            with open(os.path.join(passwords_folder, pw_file), "r", encoding="utf-8") as f:
                pw_dict[base_name] = f.read().strip()  # remove whitespace/newlines

    # Process each PDF
    for pdf_file in os.listdir(statements_folder):
        if not pdf_file.lower().endswith(".pdf"):
            continue

        pdf_path = os.path.join(statements_folder, pdf_file)
        base_name = os.path.splitext(pdf_file)[0]

        # Automatically detect password
        password = pw_dict.get(base_name, None)

        try:
            transactions = parse_mpesa_pdf(pdf_path, password=password)
        except ValueError as e:
            # PDF still not readable
            msg = str(e).lower()
            if "password protected" in msg:
                print(f"PDF {pdf_file} is password protected but password not found. Skipping.")
            else:
                print(f"Error parsing {pdf_file}: {str(e)}")
            transactions = []

        statements.append({
            "filename": pdf_file,
            "transactions": transactions
        })

    return statements


def answer_question(transactions, question):
    """
    Basic RAG replacement: returns simple stats based on user's question
    """
    question = question.lower()
    category = None

    if "income" in question:
        category = "income"
    elif "expenditure" in question or "expense" in question:
        category = "expense"
    elif "charge" in question or "transaction cost" in question:
        category = "charge"

    numbers = [tx["amount"] for tx in transactions if tx["category"] == category] if category else []

    if "sum" in question or "total" in question or "totals" in question:
        return f"Total {category}: KES {sum(numbers):,.2f}" if numbers else "No data"
    if "min" in question:
        return f"Minimum {category}: KES {min(numbers):,.2f}" if numbers else "No data"
    if "max" in question:
        return f"Maximum {category}: KES {max(numbers):,.2f}" if numbers else "No data"

    return "Sorry, I cannot answer that question."
