# watcher.py
import os
import time
from pdf_parser import parse_mpesa_pdf

STATEMENTS_DIR = "mpesa_statements"
PASSWORDS_DIR = "passwords"

processed = set()
ALL_TRANSACTIONS = []

def check_new_statements():
    global ALL_TRANSACTIONS

    for pdf in os.listdir(STATEMENTS_DIR):
        if not pdf.endswith(".pdf"):
            continue

        pdf_path = os.path.join(STATEMENTS_DIR, pdf)
        if pdf_path in processed:
            continue

        password_path = os.path.join(
            PASSWORDS_DIR, pdf.replace(".pdf", ".txt")
        )

        password = None
        if os.path.exists(password_path):
            with open(password_path) as f:
                password = f.read().strip()

        try:
            txs = parse_mpesa_pdf(pdf_path, password)
            ALL_TRANSACTIONS.extend(txs)
            processed.add(pdf_path)
            print(f"✔ Parsed {pdf}")
        except Exception as e:
            print(f"✖ Skipped {pdf}: {e}")

    return ALL_TRANSACTIONS


def start_watcher():
    while True:
        check_new_statements()
        time.sleep(300)  # 5 minutes
