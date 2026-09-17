# retrieval.py
"""Shared retrieval pipeline: hybrid search + optional rerank + scoped filter.

Accuracy choices:
- MMR vector search (diversity) instead of plain similarity top-k.
- Hybrid vector + BM25 ensemble with configurable weight.
- Scoped (single-document) search uses a metadata filter DICT
  (FAISS-compatible) — the old lambda filter silently matched nothing.
- Cross-encoder rerank is optional and lazy; failure falls back gracefully.
- History-aware reformulation is skipped when there is no history
  (saves an LLM call + avoids mangling first-turn questions).
"""
import logging
from typing import List, Optional

from langchain.retrievers import ContextualCompressionRetriever, EnsembleRetriever
from langchain.retrievers.document_compressors import CrossEncoderReranker
from langchain_core.documents import Document as LCDocument

from config import settings
from state import app_store

log = logging.getLogger("knowledgebase.retrieval")


def all_indexed_docs() -> List[LCDocument]:
    vs = app_store.get("vector_store")
    if not vs:
        return []
    try:
        store = getattr(vs, "docstore", None)
        d = getattr(store, "_dict", None) if store else None
        if isinstance(d, dict):
            return list(d.values())
    except Exception:
        pass
    return []


def unique_sources() -> List[str]:
    return sorted({d.metadata.get("source", "") for d in all_indexed_docs()
                   if d.metadata.get("source")})


def build_base_retriever(filter_source: Optional[str] = None):
    k = int(getattr(settings, "RETRIEVAL_K", 20))
    vs = app_store.get("vector_store")
    if vs is None:
        raise ValueError("Vector store is empty")

    if filter_source:
        # FAISS metadata filter must be a DICT (lambda filters don't apply).
        log.info("Scoped search in %s", filter_source)
        return vs.as_retriever(
            search_type="mmr",
            search_kwargs={"k": min(k, 12), "fetch_k": k,
                           "lambda_mult": 0.5,
                           "filter": {"source": filter_source}},
        )

    vector_retriever = vs.as_retriever(
        search_type="mmr",
        search_kwargs={"k": k, "fetch_k": max(k * 2, 30), "lambda_mult": 0.5},
    )
    bm25 = app_store.get("bm25_retriever")
    if getattr(settings, "ENABLE_HYBRID_SEARCH", True) and bm25 is not None:
        try:
            w = float(getattr(settings, "HYBRID_VECTOR_WEIGHT", 0.5))
            w = min(max(w, 0.0), 1.0)
            # EnsembleRetriever orders retrievers as given; keep [bm25, vector]
            # with complementary weights.
            return EnsembleRetriever(
                retrievers=[bm25, vector_retriever],
                weights=[1.0 - w, w],
            )
        except Exception as e:
            log.warning("Hybrid setup failed, using vector only: %s", e)
    elif bm25 is None:
        log.warning("BM25 unavailable — vector search only")
    return vector_retriever


def with_rerank(base_retriever):
    """Wrap with cross-encoder rerank if enabled and available."""
    if not getattr(settings, "ENABLE_RERANKER", True):
        return base_retriever
    reranker = app_store.get("reranker")
    if reranker is None:
        return base_retriever
    try:
        top_n = int(getattr(settings, "RERANK_TOP_N", 5))
        compressor = CrossEncoderReranker(model=reranker, top_n=top_n)
        return ContextualCompressionRetriever(
            base_compressor=compressor, base_retriever=base_retriever)
    except Exception as e:
        log.warning("Reranker unavailable, using unranked retrieval: %s", e)
        return base_retriever


async def retrieve(retriever, query: str):
    """Version-tolerant async retrieval."""
    if hasattr(retriever, "ainvoke"):
        return await retriever.ainvoke(query)
    if hasattr(retriever, "aget_relevant_documents"):
        return await retriever.aget_relevant_documents(query)
    # sync fallback
    fn = getattr(retriever, "get_relevant_documents", None) or getattr(retriever, "invoke", None)
    if fn is None:
        raise RuntimeError("Retriever has no invoke method")
    return fn(query)
