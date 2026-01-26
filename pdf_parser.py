import pdfplumber
import re
import io
from datetime import datetime
from pypdf import PdfReader, PdfWriter


# ----------------------------------------------------
# Unlock encrypted PDFs safely
# ----------------------------------------------------
def unlock_pdf(pdf_path, password):
    reader = PdfReader(pdf_path)

    if not reader.is_encrypted:
        return pdf_path

    if not reader.decrypt(password):
        raise ValueError("Incorrect PDF password")

    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    buffer = io.BytesIO()
    writer.write(buffer)
    buffer.seek(0)
    return buffer


# ----------------------------------------------------
# Parse M-PESA PDF into structured transactions
# ----------------------------------------------------
def parse_mpesa_pdf(pdf_path, password=None):
    pdf_source = unlock_pdf(pdf_path, password) if password else pdf_path

    # -------- Extract all text lines --------
    with pdfplumber.open(pdf_source) as pdf:
        lines = []
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                lines.extend(text.splitlines())

    # -------- Phase 1: Extract raw rows --------
    raw = []
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        match = re.match(
            r"^([A-Z0-9]{8,})\s+(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})\s+(.*)",
            line
        )

        if not match:
            i += 1
            continue

        receipt, date_str, time_str, rest = match.groups()
        tx_date = datetime.strptime(date_str, "%Y-%m-%d").date()

        details_lines = [rest]
        i += 1

        while i < len(lines) and not re.match(
            r"^[A-Z0-9]{8,}\s+\d{4}-\d{2}-\d{2}",
            lines[i]
        ):
            details_lines.append(lines[i].strip())
            i += 1

        blob = " ".join(details_lines)

        numbers = re.findall(r"-?[\d,]+\.\d{2}", blob)
        if len(numbers) < 2:
            continue

        numbers = [float(n.replace(",", "")) for n in numbers]

        # -------- Detect transaction layout --------
        if len(numbers) >= 3 and numbers[-3] >= 0 and numbers[-2] >= 0:
            paid_in = numbers[-3]
            paid_out = numbers[-2]
            balance = numbers[-1]
        else:
            amt = numbers[-2]
            balance = numbers[-1]
            paid_in = amt if amt > 0 else 0.0
            paid_out = abs(amt) if amt < 0 else 0.0

        raw.append({
            "receipt": receipt,
            "date": tx_date,          # ✅ DATE OBJECT (IMPORTANT)
            "time": time_str,
            "details": blob,
            "paid_in": paid_in,
            "paid_out": paid_out,
            "balance": balance
        })

    # -------- Phase 2: Group by receipt --------
    grouped = {}
    for r in raw:
        grouped.setdefault(r["receipt"], []).append(r)

    # -------- Phase 3: Classify transactions & link charges --------
    final = []

    charge_patterns = {
        "customer_transfer_charge": r"Transfer of Funds Charge",
        "paybill_charge": r"Pay Bill Charge",
        "withdrawal_charge": r"Withdrawal Charge"
    }

    for receipt, rows in grouped.items():
        main_tx = None
        charge_rows = []

        for r in rows:
            if any(re.search(p, r["details"], re.IGNORECASE) for p in charge_patterns.values()):
                charge_rows.append(r)
            else:
                main_tx = r

        # Case: charge-only transaction
        if not main_tx and charge_rows:
            for c in charge_rows:
                final.append({
                    "receipt": c["receipt"],
                    "parent_receipt": None,
                    "date": c["date"],
                    "time": c["time"],
                    "details": c["details"],
                    "category": "charge",
                    "subcategory": None,
                    "amount": c["paid_out"],
                    "balance": c["balance"]
                })
            continue

        # Main transaction
        if main_tx:
            if main_tx["paid_in"] > 0:
                category = "income"
                amount = main_tx["paid_in"]
            else:
                category = "expense"
                amount = main_tx["paid_out"]

            final.append({
                "receipt": main_tx["receipt"],
                "parent_receipt": None,
                "date": main_tx["date"],
                "time": main_tx["time"],
                "details": main_tx["details"],
                "category": category,
                "subcategory": None,
                "amount": amount,
                "balance": main_tx["balance"]
            })

        # Linked charges
        for c in charge_rows:
            subcat = None
            for name, pat in charge_patterns.items():
                if re.search(pat, c["details"], re.IGNORECASE):
                    subcat = name
                    break

            final.append({
                "receipt": c["receipt"],
                "parent_receipt": main_tx["receipt"] if main_tx else None,
                "date": c["date"],
                "time": c["time"],
                "details": c["details"],
                "category": "charge",
                "subcategory": subcat,
                "amount": c["paid_out"],
                "balance": c["balance"]
            })

    # -------- Final sort (chronological) --------
    return sorted(final, key=lambda x: (x["date"], x["time"]))
