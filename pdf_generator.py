from reportlab.platypus import SimpleDocTemplate, Table

def generate_pdf(txs, out):
    rows=[["Date","Details","Amount","Type"]]
    for t in txs:
        rows.append([t["date"],t["details"],t["amount"],t["category"]])

    pdf=SimpleDocTemplate(out)
    pdf.build([Table(rows)])
