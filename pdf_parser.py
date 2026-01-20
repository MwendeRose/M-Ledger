import pdfplumber
import re

def parse_mpesa_pdf(pdf_path):
    full_text = ""

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"

    if not full_text.strip():
        return []

    pattern = re.compile(
        r"([A-Z0-9]{8,})\s+"
        r"(\d{4}-\d{2}-\d{2})\s+"
        r"(\d{2}:\d{2}:\d{2})\s+"
        r"(.*?)"
        r"COMPLETED\s+"
        r"([\d,]+\.\d{2})\s+"
        r"([\d,]+\.\d{2})\s+"
        r"([\d,]+\.\d{2})",
        re.DOTALL
    )

    transactions = []

    for m in pattern.finditer(full_text):
        transactions.append({
            "receipt": m.group(1),
            "date": m.group(2),
            "time": m.group(3),
            "details": " ".join(m.group(4).split()),
            "paid_in": float(m.group(5).replace(",", "")),
            "paid_out": float(m.group(6).replace(",", "")),
            "balance": float(m.group(7).replace(",", ""))
        })

    return transactions
