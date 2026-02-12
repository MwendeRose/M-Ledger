from pymongo import MongoClient
from langchain_ollama import OllamaLLM

# MongoDB (SAME DB AS APP)
client = MongoClient("mongodb://localhost:27017/")
db = client["Mledger"]
collection = db["statements"]

# Initialize Ollama with timeout
try:
    llm = OllamaLLM(model="llama3", base_url="http://localhost:11434")
except Exception as e:
    print(f"Error initializing Ollama: {e}")
    llm = None

def build_statement_context(statement_doc):
    tx_lines = []
    for t in statement_doc.get("transactions", []):
        line = f"{t.get('date','')} | {t.get('description','')} | {t.get('amount',0)} | {t.get('category','')} | balance {t.get('balance',0)}"
        tx_lines.append(line)

    totals = statement_doc.get("totals", {})
    totals_text = f"""
TOTALS:
Income: {totals.get('income',0)}
Expenses: {totals.get('expenses',0)}
Charges: {totals.get('charges',0)}
Balance: {totals.get('balance',0)}
"""
    return "\n".join(tx_lines) + "\n" + totals_text

def ask_latest_statement(question: str):
    if llm is None:
        return "AI service is not available. Please ensure Ollama is running with llama3 model."
    
    stmt = collection.find_one({}, sort=[("uploaded_at", -1)])

    if not stmt:
        return "No statement found. Please upload a statement first."

    context = build_statement_context(stmt)

    prompt = f"""
You are an assistant that answers questions ONLY from this M-Pesa statement.

STATEMENT:
{context}

Question: {question}

Rules:
- Use ONLY the data above
- If not found, say: "I could not find that information in the statement."
- Be concise
"""

    try:
        response = llm.invoke(prompt)
        return str(response)
    except Exception as e:
        return f"Error getting AI response: {str(e)}"