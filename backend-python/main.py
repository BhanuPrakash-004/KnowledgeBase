# main.py
import logging
import os
import traceback
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from langchain_community.retrievers import BM25Retriever
from langchain_community.vectorstores import FAISS

from config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(levelname)s | %(message)s")
log = logging.getLogger("knowledgebase.main")


def _init_llm():
    import providers as pv
    from state import app_store
    from config import settings as s
    saved = pv._read_json_config()
    try:
        llm = pv.build_chat_model(
            provider=saved.get("llm_provider") or s.LLM_PROVIDER,
            model=saved.get("llm_model") or s.LLM_MODEL,
            api_key=pv._resolve_secret(saved.get("llm_api_key", None), s.LLM_API_KEY),
            base_url=saved.get("llm_base_url") or s.LLM_BASE_URL,
            temperature=s.LLM_TEMPERATURE)
        app_store["llm"] = llm
        log.info("LLM ready: %s / %s",
                 (saved.get("llm_provider") or s.LLM_PROVIDER), (saved.get("llm_model") or s.LLM_MODEL))
    except Exception as e:
        app_store["llm"] = None
        log.warning("LLM not available at startup: %s", e)


def _init_embeddings():
    import providers as pv
    from state import app_store
    from config import settings as s
    saved = pv._read_json_config()
    try:
        emb = pv.build_embeddings(
            provider=saved.get("embedding_provider") or s.EMBEDDING_PROVIDER,
            model=saved.get("embedding_model") or s.EMBEDDING_MODEL,
            api_key=pv._resolve_secret(saved.get("embedding_api_key", None), s.EMBEDDING_API_KEY),
            base_url=saved.get("embedding_base_url") or s.EMBEDDING_BASE_URL)
        app_store["embeddings"] = emb
        log.info("Embeddings ready: %s / %s",
                 (saved.get("embedding_provider") or s.EMBEDDING_PROVIDER),
                 (saved.get("embedding_model") or s.EMBEDDING_MODEL))
    except Exception as e:
        app_store["embeddings"] = None
        log.warning("Embeddings not available at startup: %s", e)


def _init_reranker():
    from state import app_store
    if not getattr(settings, "ENABLE_RERANKER", True):
        app_store["reranker"] = None
        log.info("Reranker disabled by config.")
        return
    # Lazy background load: HuggingFace download (~1GB first run) must not block startup.
    app_store["reranker"] = None
    app_store["reranker_loading"] = True

    def _load():
        try:
            from langchain_community.cross_encoders import HuggingFaceCrossEncoder
            app_store["reranker"] = HuggingFaceCrossEncoder(model_name=settings.RERANKER_MODEL)
            log.info("Reranker ready: %s", settings.RERANKER_MODEL)
        except Exception as e:
            app_store["reranker"] = None
            log.warning("Reranker unavailable (retrieval will skip rerank): %s", e)
        finally:
            app_store["reranker_loading"] = False

    import threading as _th
    _th.Thread(target=_load, daemon=True).start()
    log.info("Reranker loading in background: %s", settings.RERANKER_MODEL)


def _init_vector_store():
    from state import app_store
    index_file = os.path.join(settings.model_dir(), "index.faiss")
    if not os.path.exists(index_file):
        app_store["vector_store"] = None
        app_store["bm25_retriever"] = None
        log.warning("No vector store found. A new one will be created on first upload.")
        return
    try:
        vs = FAISS.load_local(settings.model_dir(), app_store["embeddings"],
                              allow_dangerous_deserialization=True)
        app_store["vector_store"] = vs
        docs = []
        try:
            mapping = getattr(getattr(vs, "docstore", None), "_dict", None)
            if isinstance(mapping, dict):
                docs = list(mapping.values())
        except Exception:
            pass
        app_store["bm25_retriever"] = BM25Retriever.from_documents(docs) if docs else None
        log.info("Vector store loaded: %d chunks.", len(docs))
    except Exception as e:
        # Classic cause: embedding model/dimension changed since the index was built.
        app_store["vector_store"] = None
        app_store["bm25_retriever"] = None
        log.error("Vector store load failed (starting empty): %s\n%s", e, traceback.format_exc())


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting KnowledgeBase API...")
    import chat_store
    from state import app_store
    chat_store.configure(settings.CHAT_DB_PATH)
    _init_llm()
    _init_embeddings()
    _init_reranker()
    if app_store.get("embeddings") is None:
        log.warning("Embeddings missing — vector store load skipped until embeddings are configured.")
        app_store["vector_store"] = None
        app_store["bm25_retriever"] = None
    else:
        _init_vector_store()
    yield
    log.info("Shutting down.")
    app_store.clear()


app = FastAPI(title="KnowledgeBase API", version="2.0", lifespan=lifespan)

# CORS: "*" + credentials is rejected by browsers; use explicit origins when possible.
_cors_origins = settings.CORS_ORIGIN_LIST
_allow_creds = not (_cors_origins == ["*"])
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_allow_creds,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs(settings.UPLOAD_DIRECTORY, exist_ok=True)
if getattr(settings, "SERVE_FILES", True) and os.path.isdir(settings.UPLOAD_DIRECTORY):
    app.mount("/files", StaticFiles(directory=settings.UPLOAD_DIRECTORY), name="files")


@app.middleware("http")
async def request_id_and_rate_limit(request: Request, call_next):
    from security import check_rate_limit, new_request_id
    rid = new_request_id()
    request.state.request_id = rid
    path = request.url.path
    client_ip = request.client.host if request.client else "unknown"
    limited: tuple[str, int] | None = None
    if path == "/api/chat" and request.method == "POST":
        limited = ("chat", int(getattr(settings, "RATE_LIMIT_CHAT_PER_MIN", 30)))
    elif path == "/api/upload-and-process" and request.method == "POST":
        limited = ("upload", int(getattr(settings, "RATE_LIMIT_UPLOAD_PER_MIN", 10)))
    elif path == "/api/provider/test" and request.method == "POST":
        limited = ("provider-test", int(getattr(settings, "RATE_LIMIT_TEST_PER_MIN", 10)))
    if limited and limited[1] > 0 and not check_rate_limit(client_ip, limited[0], limited[1]):
        return JSONResponse(status_code=429,
                            content={"detail": f"Rate limit exceeded for {limited[0]} ({limited[1]}/min)."},
                            headers={"X-Request-ID": rid})
    try:
        response = await call_next(request)
    except Exception:
        raise
    response.headers["X-Request-ID"] = rid
    return response


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    if "HTTPException" in type(exc).__name__:
        raise exc
    rid = getattr(getattr(request, "state", None), "request_id", "-")
    log.error("Unhandled %s %s rid=%s: %s\n%s", request.method, request.url.path, rid, exc, traceback.format_exc())
    if getattr(settings, "DEBUG_ERRORS", False):
        return JSONResponse(status_code=500, content={"detail": f"Internal error: {exc}"})
    return JSONResponse(status_code=500, content={"detail": "Internal error. Check server logs."})


@app.get("/api/health")
async def health():
    from state import app_store
    import providers as pv
    prov = pv.get_active_provider_config()
    prov.pop("supported_providers", None)
    vs = app_store.get("vector_store")
    n_chunks = 0
    try:
        mapping = getattr(getattr(vs, "docstore", None), "_dict", None)
        if isinstance(mapping, dict):
            n_chunks = len(mapping)
    except Exception:
        pass
    ok = app_store.get("llm") is not None and app_store.get("embeddings") is not None
    return {"status": "ok" if ok else "degraded",
            "llm_ready": app_store.get("llm") is not None,
            "embeddings_ready": app_store.get("embeddings") is not None,
            "reranker_ready": app_store.get("reranker") is not None,
            "reranker_loading": bool(app_store.get("reranker_loading", False)),
            "index_loaded": vs is not None, "chunks": n_chunks,
            "provider": prov}


@app.get("/api/stats")
async def stats():
    from state import app_store
    import chat_store as cs
    from retrieval import unique_sources
    vs = app_store.get("vector_store")
    try:
        n_sessions = len(cs.list_sessions(limit=1000))
        n_messages = cs.count_messages()
    except Exception:
        n_sessions, n_messages = 0, 0
    return {"documents": len(unique_sources()) if vs else 0,
            "index_loaded": vs is not None,
            "chat_messages": n_messages,
            "sessions": n_sessions}


from routers import chat as chat_router, documents as documents_router, provider as provider_router  # noqa: E402
app.include_router(documents_router.router, tags=["documents"])
app.include_router(chat_router.router, tags=["chat"])
app.include_router(provider_router.router, tags=["provider"])


if __name__ == '__main__':
    uvicorn.run(app, host="0.0.0.0", port=8000)
