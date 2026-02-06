import pdfplumber
import os

PASSWORD_DIR = "passwords"

def extract_text(pdf_path):
    passwords = []

    for fname in os.listdir(PASSWORD_DIR):
        with open(os.path.join(PASSWORD_DIR, fname)) as f:
            passwords += [line.strip() for line in f if line.strip()]

    # Try without password first
    try:
        with pdfplumber.open(pdf_path) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    except:
        pass

    # Try passwords
    for pw in passwords:
        try:
            with pdfplumber.open(pdf_path, password=pw) as pdf:
                return "\n".join(page.extract_text() or "" for page in pdf.pages)
        except:
            continue

    return None
