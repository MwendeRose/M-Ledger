import re

def parse_transactions(text):
    txs=[]
    for line in text.splitlines():
        m=re.search(r"(\d{2}/\d{2}/\d{4}).+?KES\s([\d,]+\.\d{2})",line)
        if m:
            amt=float(m.group(2).replace(",",""))
            cat="expense"
            if "received" in line.lower(): cat="income"
            if "charge" in line.lower(): cat="charge"

            txs.append({
                "date":m.group(1),
                "details":line.strip(),
                "amount":amt,
                "category":cat,
                "balance":None
            })
    return txs
