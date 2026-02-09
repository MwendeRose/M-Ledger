import os
import pytesseract
from pdf2image import convert_from_path
from PIL import Image
import re
from datetime import datetime

PASSWORD_DIR = "passwords"

POPPLER_PATH = r"C:\flutter\bin\poppler-25.12.0\Library\bin"

from pathlib import Path

def load_passwords(passwords_dir="passwords"):
    passwords = [None]  # try without password first
    dir_path = Path(passwords_dir)
    if dir_path.exists():
        for txt_file in dir_path.glob("*.txt"):
            with open(txt_file, "r") as f:
                passwords.extend([line.strip() for line in f if line.strip()])
    print(f"Loaded {len(passwords)} passwords")
    return passwords



def extract_text_from_image_pdf(pdf_path):
    print("Running OCR on image-based PDF...")

    passwords = load_passwords()

    for pw in passwords:
        try:
            print(f"Trying password: {pw}")

            pages = convert_from_path(
                pdf_path,
                poppler_path=POPPLER_PATH,
                userpw=pw
            )

            full_text = ""
            for page in pages:
                text = pytesseract.image_to_string(page)
                full_text += text + "\n"

            print("Password SUCCESS")
            return full_text

        except Exception as e:
            print(f"Password failed: {pw}")

    raise Exception("All passwords failed. Could not open PDF.")


def parse_mpesa_transactions(text):
    transactions = []
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    for line in lines:
        m = re.search(r'(\d{4}-\d{2}-\d{2}).*?(-?\d+\.\d+)', line)
        if m:
            date_str = m.group(1)
            amount = float(m.group(2))
            dt = datetime.strptime(date_str, "%Y-%m-%d")

            category = "income" if amount > 0 else "expense"

            transactions.append({
                "datetime": dt,
                "description": line,
                "amount": abs(amount),
                "category": category
            })

    return transactions
