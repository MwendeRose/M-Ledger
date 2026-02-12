import os
from pathlib import Path
import tempfile
import re
from datetime import datetime

import pytesseract
from pdf2image import convert_from_path
from PIL import Image, ImageFilter
import pikepdf

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

PASSWORD_DIR = "passwords"
POPPLER_PATH = r"C:\flutter\bin\poppler-25.12.0\Library\bin"

def extract_text_from_image_pdf(pdf_path, passwords_dir=PASSWORD_DIR, poppler_path=POPPLER_PATH):
    passwords = []
    for txt_file in Path(passwords_dir).glob("*.txt"):
        with open(txt_file, "r") as f:
            passwords.extend([line.strip() for line in f if line.strip()])

    if not passwords:
        raise ValueError("No passwords found")

    decrypted_path = None

    for pw in passwords:
        try:
            with pikepdf.open(pdf_path, password=pw) as pdf:
                decrypted_path = tempfile.mktemp(suffix=".pdf")
                pdf.save(decrypted_path)

            pages = convert_from_path(decrypted_path, poppler_path=poppler_path, dpi=400)
            full_text = ""

            for page in pages:
                # Preprocess page for better OCR
                preprocessed_page = page.convert("L").filter(ImageFilter.MedianFilter())
                # Extract text
                page_text = pytesseract.image_to_string(preprocessed_page, config='--oem 3 --psm 6')
                full_text += page_text + "\n"

            if decrypted_path and os.path.exists(decrypted_path):
                os.remove(decrypted_path)

            return full_text

        except pikepdf.PasswordError:
            continue
        except Exception:
            if decrypted_path and os.path.exists(decrypted_path):
                os.remove(decrypted_path)
            continue

    raise Exception("All passwords failed. Could not open PDF.")

def parse_mpesa_transactions(text):
    transactions = []

    # Flexible pattern to capture Sent/Received/Charges/Fees
    pattern = (
        r"(\d{2}/\d{2}/\d{4})\s+"        # Date
        r"(\d{2}:\d{2})\s+"              # Time
        r"(.+?)\s+"                      # Details
        r"(Sent|Received|Charge|Withdrawal Fee)?\s*"  # Type
        r"Ksh\s*([\d,]+)\s+"             # Amount
        r"(?:Balance[:\s]+Ksh\s*([\d,]+))?"  # Optional Balance
    )

    matches = re.findall(pattern, text, re.IGNORECASE)

    for m in matches:
        date_str, time_str, details, t_type, amount_str, balance_str = m
        t_type = t_type.lower() if t_type else "charge"

        # Classify transaction category
        if t_type in ["received"]:
            category = "income"
        elif t_type in ["sent"]:
            category = "expense"
        else:
            category = "charge"

        transactions.append({
            "date": datetime.strptime(date_str, "%d/%m/%Y").date().isoformat(),
            "time": time_str,
            "details": details.strip(),
            "type": t_type,
            "category": category,
            "amount": float(amount_str.replace(",", "")),
            "balance": float(balance_str.replace(",", "")) if balance_str else None
        })

    return transactions

