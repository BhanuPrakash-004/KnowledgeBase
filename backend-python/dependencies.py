# dependencies.py
"""FastAPI dependencies with graceful degradation (no hard crash if Ollama is down)."""
from fastapi import HTTPException, Request

from state import app_store


def _unavailable(name: str) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail=f"{name} is not available. If using Ollama, run `ollama serve` and "
               f"`ollama pull <model>`. If using BYOK, set the provider + API key via /api/provider.",
    )


def get_llm(request: Request = None):
    # Per-request BYOK override via headers (frontend toggle can use body OR headers):
    #   x-llm-provider, x-llm-model, x-llm-api-key, x-llm-base-url
    if request is not None:
        try:
            override = {
                "provider": request.headers.get("x-llm-provider"),
                "model": request.headers.get("x-llm-model"),
                "api_key": request.headers.get("x-llm-api-key"),
                "base_url": request.headers.get("x-llm-base-url"),
            }
            if any(override.values()):
                from providers import resolve_active_llm_kwargs, build_chat_model
                kwargs = resolve_active_llm_kwargs({k: v for k, v in override.items() if v})
                return build_chat_model(**kwargs)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid LLM override: {e}")
    llm = app_store.get("llm")
    if llm is None:
        raise _unavailable("LLM")
    return llm


def get_embeddings():
    emb = app_store.get("embeddings")
    if emb is None:
        raise _unavailable("Embeddings")
    return emb


def get_reranker():
    # Reranker is optional — retrieval falls back to unranked results.
    return app_store.get("reranker")


def get_retrievers():
    if not app_store.get("vector_store"):
        raise HTTPException(status_code=404, detail="Knowledge Base is empty. Please upload a document.")
    return {
        "vector": app_store["vector_store"].as_retriever(
            search_kwargs={"k": _k()}),
        "keyword": app_store.get("bm25_retriever"),
    }


def _k() -> int:
    try:
        from config import settings
        return int(getattr(settings, "RETRIEVAL_K", 20))
    except Exception:
        return 20
