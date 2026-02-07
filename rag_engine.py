import os, re
from langchain_community.vectorstores import FAISS
from langchain_ollama import OllamaLLM, OllamaEmbeddings
from langchain_core.documents import Document

DB_PATH = "vector_db"
vectorstore = None

llm = OllamaLLM(model="llama3")
embeddings = OllamaEmbeddings(model="llama3")

def ingest_text(text, source):
    """
    Save the uploaded statement into FAISS vectorstore for retrieval.
    """
    global vectorstore
    docs = [Document(page_content=text, metadata={"source": source})]

    if os.path.exists(DB_PATH):
        vectorstore = FAISS.load_local(DB_PATH, embeddings, allow_dangerous_deserialization=True)
        vectorstore.add_documents(docs)
    else:
        vectorstore = FAISS.from_documents(docs, embeddings)

    vectorstore.save_local(DB_PATH)
    print(f"[RAG] Ingested {source}")

def ask(question):
    """
    Query the ingested statements. Returns a plain string safe for JSON.
    """
    global vectorstore

    # Load vectorstore if needed
    if vectorstore is None:
        if not os.path.exists(DB_PATH):
            return "No statements uploaded yet. Please upload an M-Pesa statement first."
        vectorstore = FAISS.load_local(DB_PATH, embeddings, allow_dangerous_deserialization=True)

    # Get top 3 relevant documents
    docs = vectorstore.similarity_search(question, k=3)
    if not docs:
        return "No relevant information found in your uploaded statements."

    context = "\n".join(d.page_content for d in docs)

    # Build prompt
    prompt = f"""
You are an AI assistant that answers questions ONLY based on the user's uploaded M-Pesa statements.

Context:
{context}

Question: {question}
Answer clearly using ONLY the context above. If the answer is not in the statements, say "I could not find that information in your uploaded statements."
"""

    # Get response
    response = llm.invoke(prompt)

    # Ensure plain string
    if isinstance(response, (list, tuple)):
        response = " ".join(str(r) for r in response)
    else:
        response = str(response)

    # Clean up prompts and extra whitespace
    response = response.replace(">>>", "").strip()
    response = re.sub(r'\n+', '\n', response)

    return response
