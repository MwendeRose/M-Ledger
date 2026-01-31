from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.pdfencrypt import StandardEncryption
from datetime import datetime

def generate_mpesa_pdf(transactions, password: str):
    file_name = "M-Ledger-AI_Statement.pdf"
    encrypt = StandardEncryption(userPassword=password, ownerPassword="ledger-admin", canPrint=1)
    doc = SimpleDocTemplate(file_name, pagesize=A4, encrypt=encrypt)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("<b>M-Ledger AI</b>", styles["Title"]))
    elements.append(Paragraph("Agentic M-PESA Statement", styles["Heading2"]))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"<b>Generated On:</b> {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles["Normal"]))
    elements.append(Spacer(1, 14))

    table_data = [["Date", "Type", "Details", "Amount", "Balance"]]
    for t in transactions:
        table_data.append([str(t["date"]), t["category"], t["details"], f"KES {t['amount']:,.2f}", f"KES {t['balance']:,.2f}"])

    table = Table(table_data, colWidths=[70, 80, 200, 80, 80])
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 1, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (-2, 1), (-1, -1), "RIGHT"),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 16))
    elements.append(Paragraph("This statement was generated offline by M-Ledger AI.", styles["Normal"]))

    doc.build(elements)
    return file_name
