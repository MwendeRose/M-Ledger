from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.llms import Ollama
from langchain_core.documents import Document

import os

DB_PATH = "vector_db"
vectorstore = None

llm = Ollama(model="llama3")
embeddings = OllamaEmbeddings(model="llama3")

def ingest_text(text, source):
    global vectorstore
    docs = [Document(page_content=text, metadata={"source": source})]

    if os.path.exists(DB_PATH):
        vectorstore = FAISS.load_local(DB_PATH, embeddings)
        vectorstore.add_documents(docs)
    else:
        vectorstore = FAISS.from_documents(docs, embeddings)

    vectorstore.save_local(DB_PATH)


def ask(question):
    global vectorstore

    if vectorstore is None:
        vectorstore = FAISS.load_local(DB_PATH, embeddings)

    docs = vectorstore.similarity_search(question, k=3)
    context = "\n".join(d.page_content for d in docs)

    prompt = f"""
You are an AI that understands M-Pesa statements.

Context:
{context}

Question: {question}
"""
    return llm(prompt)
