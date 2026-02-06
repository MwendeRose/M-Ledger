import os
from pdf_parser import extract_text
import rag_engine
from analyzer import parse_transactions
import json

MPESA_DIR = "mpesa_statements"
CACHE_FILE = "data_cache.json"

data = {"transactions":[]}

for f in os.listdir(MPESA_DIR):
    if f.endswith(".pdf"):
        path = os.path.join(MPESA_DIR, f)
        text = extract_text(path)
        if text:
            txs = parse_transactions(text)
            data["transactions"].extend(txs)
            rag_engine.ingest_text(text, f)

with open(CACHE_FILE,"w") as out:
    json.dump(data,out,indent=2)

print("✔ Folder scan complete")
