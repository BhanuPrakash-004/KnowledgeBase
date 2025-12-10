from fastapi import HTTPException
from state import app_store

def get_llm(): return app_store["llm"]
def get_embeddings(): return app_store["embeddings"]
def get_reranker(): return app_store["reranker"]

def get_retrievers():
    if not app_store.get("vector_store"):
        raise HTTPException(status_code=404, detail="Knowledge Base is empty. Please upload a document.")
    
    return {
        "vector": app_store["vector_store"].as_retriever(search_kwargs={"k": 10}),
        "keyword": app_store.get("bm25_retriever")
    }
