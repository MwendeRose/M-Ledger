import os
import datetime
from PyPDF2 import PdfReader
from pymongo import MongoClient

PDF_FOLDER = r"C:\Users\user\OneDrive\Desktop\M-Ledger\mpesa_statements"
PASSWORD_FOLDER = r"C:\Users\user\OneDrive\Desktop\M-Ledger\passwords"

# Load passwords
passwords = []
for file in os.listdir(PASSWORD_FOLDER):
    if file.lower().endswith(".txt"):
        with open(os.path.join(PASSWORD_FOLDER, file), "r", encoding="utf-8") as f:
            passwords.extend([line.strip() for line in f if line.strip()])

print(f"Loaded {len(passwords)} passwords")

# MongoDB setup
client = MongoClient("mongodb://localhost:27017")
db = client["ml_ledger"]
collection = db["statements"]

# Process PDFs
for pdf_file in os.listdir(PDF_FOLDER):
    if not pdf_file.lower().endswith(".pdf"):
        continue

    pdf_path = os.path.join(PDF_FOLDER, pdf_file)
    print(f"\n  Processing: {pdf_file}")

    success = False
    for pwd in passwords:
        try:
            reader = PdfReader(pdf_path)
            if reader.is_encrypted:
                reader.decrypt(pwd)

            last_page = reader.pages[-1]
            text = last_page.extract_text()
            if not text:
                continue

            print(f"  Success with password: {pwd}")

            # Store in MongoDB
            collection.update_one(
                {"pdf_name": pdf_file},
                {"$set": {
                    "last_statement": text,
                    "last_processed": datetime.datetime.now()
                }},
                upsert=True
            )

            success = True
            break
        except Exception as e:
            print(f" Failed with password {pwd}: {e}")

    if not success:
        print(f"  No password worked for {pdf_file}")
# convert_mpesa_pdf.py

def convert_mpesa_pdf(pdf_path):
    # Your PDF extraction logic here
    return "PDF processed"
