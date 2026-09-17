# routers/chat.py
"""Conversational RAG with persistent SQLite history + BYOK override."""
import logging
import time
import traceback

from fastapi import APIRouter, HTTPException
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

import chat_store
from models import ChatRequest, ChatResponse, ChatMessageOut, ChatSessionOut
from providers import build_chat_model, resolve_active_llm_kwargs
from retrieval import build_base_retriever, retrieve, with_rerank
from state import app_store
from utils import format_docs

log = logging.getLogger("knowledgebase.chat")
router = APIRouter()

REFORMULATE_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "Given a chat history and the latest user question which might reference "
     "context in the chat history, formulate a standalone question which can be "
     "understood without the chat history. Do NOT answer the question, just "
     "reformulate it if needed and otherwise return it as is."),
    MessagesPlaceholder("chat_history"),
    ("human", "{input}"),
])

QA_SYSTEM = (
    "You are a precise assistant answering ONLY from the retrieved context below.\n"
    "Rules:\n"
    "1. If the answer is in the context, answer concisely and quote the key facts.\n"
    "2. End factual claims with the document tag shown in brackets, e.g. [Source: report.pdf, Page 2].\n"
    "3. If the context does not contain the answer, say exactly: "
    "'I cannot find the answer in the provided documents.' and suggest what to upload.\n"
    "4. Never invent names, numbers, dates, or page numbers.\n"
    "5. Keep answers focused; use short paragraphs or bullets.\n\n"
    "Context:\n{context}"
)
QA_PROMPT = ChatPromptTemplate.from_messages([
    ("system", QA_SYSTEM),
    MessagesPlaceholder("chat_history"),
    ("human", "{input}"),
])


def _sources(docs) -> list[str]:
    out = []
    for d in docs or []:
        src = (d.metadata or {}).get("source", "N/A")
        page = (d.metadata or {}).get("page")
        label = f"{src}" + (f" (Page {page})" if page else "")
        if label not in out:
            out.append(label)
    return sorted(out)


async def _maybe_reformulate(llm, query: str, history):
    if not history:
        return query
    try:
        chain = REFORMULATE_PROMPT | llm
        res = await chain.ainvoke({"input": query, "chat_history": history})
        text = res.content if hasattr(res, "content") else str(res)
        text = (text or "").strip()
        return text or query
    except Exception as e:
        log.warning("Query reformulation failed, using raw query: %s", e)
        return query


FALLBACK_NO_CONTEXT = "I cannot find the answer in the provided documents."


async def _answer_with_retry(llm, payload: dict, tries: int = 2):
    last: Exception | None = None
    for _ in range(max(1, tries)):
        try:
            return await (QA_PROMPT | llm).ainvoke(payload)
        except Exception as e:
            last = e
    raise last  # type: ignore[misc]


@router.post("/api/chat", response_model=ChatResponse)
async def chat_with_knowledge_base(request: ChatRequest):
    from security import validate_session_id
    t0 = time.perf_counter()
    query = (request.query or "").strip()
    if not query:
        raise HTTPException(status_code=422, detail="Query must not be empty.")
    try:
        session_id = validate_session_id(request.session_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if not app_store.get("vector_store"):
        raise HTTPException(status_code=404, detail="Knowledge Base is empty. Please upload a document.")

    # Resolve LLM: per-request BYOK override wins, else global toggle/active config.
    llm_kwargs = resolve_active_llm_kwargs({
        "provider": request.provider, "model": request.model,
        "api_key": request.api_key, "base_url": request.base_url,
        "temperature": request.temperature if request.temperature is not None else None,
    })
    # drop None temperature so factory falls back to settings default
    if llm_kwargs.get("temperature") is None:
        from config import settings as _s
        llm_kwargs["temperature"] = _s.LLM_TEMPERATURE
    try:
        # Reuse the preloaded global LLM when the request matches the active config
        # (avoids rebuilding Ollama clients on every turn).
        from providers import resolve_active_llm_kwargs as _resolve
        active = _resolve({})
        wants_override = bool(request.provider or request.model or request.api_key or request.base_url
                              or request.temperature is not None)
        if not wants_override and app_store.get("llm") is not None and llm_kwargs == active:
            llm = app_store["llm"]
        else:
            llm = build_chat_model(**llm_kwargs)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"LLM unavailable ({llm_kwargs['provider']}/{llm_kwargs['model']}): {e}")

    # Scoped-search guard: unknown filename -> 404 with helpful message.
    if request.filter_source:
        from retrieval import unique_sources
        if request.filter_source not in unique_sources():
            raise HTTPException(status_code=404,
                                detail=f"Document '{request.filter_source}' not found in the knowledge base.")

    try:
        history = chat_store.get_history_messages(session_id, limit=20)
        standalone = await _maybe_reformulate(llm, query, history)

        base = build_base_retriever(request.filter_source)
        retriever = with_rerank(base)
        docs = await retrieve(retriever, standalone)
        # Safety cap: reranker misconfig could return many docs; bound LLM input.
        from config import settings as _s
        docs = list(docs or [])[: max(int(getattr(_s, "RERANK_TOP_N", 5)) * 2, 5)]

        context = format_docs(docs) if docs else "(no relevant passages retrieved)"
        res = await _answer_with_retry(llm, {"input": query, "chat_history": history, "context": context})
        answer = res.content if hasattr(res, "content") else str(res)
        answer = (answer or "").strip() or FALLBACK_NO_CONTEXT
        # Anti-hallucination guard: empty retrieval must not produce a factual answer.
        if not docs and answer.strip() != FALLBACK_NO_CONTEXT:
            log.warning("Empty retrieval but LLM answered; forcing fallback (session=%s)", session_id)
            answer = (FALLBACK_NO_CONTEXT +
                      " Try rephrasing, or upload a document that contains the answer.")

        sources = _sources(docs)
        latency_ms = int((time.perf_counter() - t0) * 1000)

        # Persist both turns (best-effort; chat must succeed even if DB write fails).
        try:
            chat_store.save_message(session_id, "human", query,
                                    provider=llm_kwargs["provider"], model=str(llm_kwargs["model"]))
            chat_store.save_message(session_id, "ai", answer, sources=sources,
                                    provider=llm_kwargs["provider"], model=str(llm_kwargs["model"]))
        except Exception as e:
            log.warning("chat_store save failed: %s", e)

        log.info("chat session=%s provider=%s model=%s docs=%d ms=%d",
                 session_id, llm_kwargs["provider"], llm_kwargs["model"], len(docs), latency_ms)
        return ChatResponse(answer=answer, sources=sources,
                            provider=llm_kwargs["provider"], model=str(llm_kwargs["model"]),
                            latency_ms=latency_ms,
                            context_chars=len(context), docs_used=len(docs))
    except HTTPException:
        raise
    except Exception as e:
        log.error("Chat error: %s\n%s", e, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error during chat retrieval: {e}")


# --- Persistent history endpoints (used by the frontend chat panel) ---
@router.get("/api/chat/sessions", response_model=list[ChatSessionOut])
async def list_chat_sessions(limit: int = 50, offset: int = 0):
    return [ChatSessionOut(**s) for s in chat_store.list_sessions(
        limit=min(max(limit, 1), 200), offset=max(offset, 0))]


@router.get("/api/chat/sessions/{session_id}", response_model=list[ChatMessageOut])
async def get_chat_session(session_id: str, limit: int = 100, offset: int = 0):
    from security import validate_session_id
    try:
        session_id = validate_session_id(session_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return [ChatMessageOut(**m) for m in chat_store.get_session_transcript(
        session_id, limit=min(max(limit, 1), 500), offset=max(offset, 0))]


@router.get("/api/chat/sessions/{session_id}/export")
async def export_chat_session(session_id: str):
    from fastapi.responses import PlainTextResponse
    from security import validate_session_id
    try:
        session_id = validate_session_id(session_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    md = chat_store.export_transcript_markdown(session_id)
    return PlainTextResponse(md, media_type="text/markdown",
                             headers={"Content-Disposition": f"attachment; filename=chat-{session_id}.md"})


@router.delete("/api/chat/sessions/{session_id}")
async def delete_chat_session(session_id: str):
    from security import validate_session_id
    try:
        session_id = validate_session_id(session_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    ok = chat_store.delete_session(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return {"detail": f"Session '{session_id}' deleted."}
