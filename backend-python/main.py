# main.py
import os
from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from langchain_community.llms import Ollama
from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.retrievers import BM25Retriever
from langchain_community.cross_encoders import HuggingFaceCrossEncoder

# --- CONFIGURATION ---
from config import settings

# --- STATE ---
from state import app_store

# --- ROUTERS ---
from routers import documents, chat

# --- FastAPI Lifespan Manager (for Startup and Shutdown) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting up application...")
    app_store["llm"] = Ollama(model=settings.LLM_MODEL, temperature=0.2)
    app_store["embeddings"] = OllamaEmbeddings(model=settings.EMBEDDING_MODEL)
    app_store["reranker"] = HuggingFaceCrossEncoder(model_name=settings.RERANKER_MODEL)
    app_store["chat_sessions"] = {} # To store memory for each session

    # Load existing vector store and create retrievers
    index_file = os.path.join(settings.FAISS_PATH, "index.faiss")
    if os.path.exists(index_file):
        print(f"Loading existing vector store from {settings.FAISS_PATH}...")
        vector_store = FAISS.load_local(
            settings.FAISS_PATH,
            app_store["embeddings"],
            allow_dangerous_deserialization=True
        )
        app_store["vector_store"] = vector_store
        
        # Ensure we convert to list for BM25
        if hasattr(vector_store, "docstore") and hasattr(vector_store.docstore, "_dict"):
             docs_from_vectorstore = list(vector_store.docstore._dict.values())
             if docs_from_vectorstore:
                 app_store["bm25_retriever"] = BM25Retriever.from_documents(docs_from_vectorstore)
                 print(f"✅ Retrievers are ready. Loaded {len(docs_from_vectorstore)} documents.")
             else:
                 app_store["bm25_retriever"] = None
                 print("⚠️ Vector store loaded but appears empty (no documents in docstore).")
        else:
             app_store["bm25_retriever"] = None
             print("⚠️ Vector store loaded but docstore is missing or invalid.")
    else:
        app_store["vector_store"] = None
        app_store["bm25_retriever"] = None
        print("⚠️ No vector store found. A new one will be created on first upload.")

    yield

    print("Shutting down application...")
    app_store.clear()

# --- FASTAPI APP INITIALIZATION ---
app = FastAPI(title="Advanced RAG API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
os.makedirs(settings.UPLOAD_DIRECTORY, exist_ok=True)
app.mount("/files", StaticFiles(directory=settings.UPLOAD_DIRECTORY), name="files")

# --- INCLUDE ROUTERS ---
app.include_router(documents.router)
app.include_router(chat.router)

# --- MAIN EXECUTION ---
if __name__ == '__main__':
    uvicorn.run(app, host="0.0.0.0", port=8000)
