# routers/documents.py
"""Document ingestion / listing / deletion with validation, dedup and locking."""
import logging
import os
import traceback

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from langchain_community.retrievers import BM25Retriever
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import ChatPromptTemplate

from config import settings
from dependencies import get_embeddings, get_llm
from models import DocumentAnalysis, DocumentDetail
from retrieval import all_indexed_docs, unique_sources
from state import app_store, faiss_lock
from utils import process_and_chunk_text, trigger_n8n_webhooks, truncate_for_analysis

log = logging.getLogger("knowledgebase.documents")
router = APIRouter()


def _backup_index() -> None:
    """Copy FAISS files to .bak before destructive ops (best effort)."""
    import shutil
    d = settings.model_dir()
    for name in ("index.faiss", "index.pkl"):
        src = os.path.join(d, name)
        if os.path.exists(src):
            try:
                shutil.copy2(src, src + ".bak")
            except Exception:
                pass


def _rebuild_bm25():
    try:
        docs = all_indexed_docs()
        app_store["bm25_retriever"] = BM25Retriever.from_documents(docs) if docs else None
    except Exception as e:
        log.warning("BM25 rebuild failed: %s", e)
        app_store["bm25_retriever"] = None


@router.get("/api/documents", response_model=list[str])
async def list_documents():
    try:
        if not app_store.get("vector_store"):
            return []
        return unique_sources()
    except Exception as e:
        log.error("list_documents failed: %s\n%s", e, traceback.format_exc())
        return []


@router.get("/api/documents/stats")
async def documents_stats():
    vs = app_store.get("vector_store")
    docs = all_indexed_docs() if vs else []
    return {
        "documents": len(unique_sources()) if vs else 0,
        "chunks": len(docs),
        "document_names": unique_sources() if vs else [],
        "index_loaded": vs is not None,
    }


@router.get("/api/documents/{filename}", response_model=DocumentDetail)
async def document_detail(filename: str):
    if "/" in filename or "\\" in filename or filename in (".", ".."):
        raise HTTPException(status_code=400, detail="Invalid filename.")
    docs = [d for d in all_indexed_docs() if (d.metadata or {}).get("source") == filename]
    if not docs:
        raise HTTPException(status_code=404, detail=f"Document '{filename}' not found.")
    pages = len({(d.metadata or {}).get("page") for d in docs if (d.metadata or {}).get("page")})
    chars = sum(len(d.page_content or "") for d in docs)
    preview = (docs[0].page_content or "")[:600]
    return DocumentDetail(filename=filename, chunks=len(docs), pages=pages, chars=chars, preview=preview)


@router.post("/api/documents/clear")
async def clear_all_documents(confirm: bool = False):
    """Delete the entire index + uploaded files (needed after embedding-model switch)."""
    if not confirm:
        raise HTTPException(status_code=400, detail="Pass ?confirm=true to delete the whole knowledge base.")
    async with faiss_lock:
        _backup_index()
        app_store["vector_store"] = None
        app_store["bm25_retriever"] = None
        import shutil
        d = settings.model_dir()
        for name in ("index.faiss", "index.pkl"):
            try:
                p = os.path.join(d, name)
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass
        try:
            for f in os.listdir(settings.UPLOAD_DIRECTORY):
                fp = os.path.join(settings.UPLOAD_DIRECTORY, f)
                if os.path.isfile(fp):
                    os.remove(fp)
        except Exception:
            pass
        return {"detail": "Knowledge base cleared."}


@router.delete("/api/documents/{filename}")
async def delete_document(filename: str):
    if "/" in filename or "\\" in filename or filename in (".", ".."):
        raise HTTPException(status_code=400, detail="Invalid filename.")
    vector_store = app_store.get("vector_store")
    if not vector_store:
        raise HTTPException(status_code=404, detail="Knowledge Base is empty.")
    async with faiss_lock:
        _backup_index()
        try:
            store = getattr(vector_store, "docstore", None)
            mapping = getattr(store, "_dict", None) if store else None
            if not isinstance(mapping, dict):
                raise HTTPException(status_code=500, detail="Vector store structure is invalid.")
            ids_to_delete = [doc_id for doc_id, doc in mapping.items()
                             if (doc.metadata or {}).get("source") == filename]
            if not ids_to_delete:
                raise HTTPException(status_code=404, detail=f"Document '{filename}' not found.")
            vector_store.delete(ids_to_delete)
            vector_store.save_local(settings.model_dir())
            _rebuild_bm25()
            # remove the uploaded file too (best effort)
            try:
                fp = os.path.join(settings.UPLOAD_DIRECTORY, filename)
                if os.path.exists(fp):
                    os.remove(fp)
            except Exception:
                pass
            log.info("Deleted %d chunks for %s", len(ids_to_delete), filename)
            return {"detail": f"Document '{filename}' deleted successfully.",
                    "chunks_deleted": len(ids_to_delete)}
        except HTTPException:
            raise
        except Exception as e:
            log.error("delete failed: %s\n%s", e, traceback.format_exc())
            raise HTTPException(status_code=500, detail=f"Failed to delete document: {e}")


@router.post("/api/upload-and-process", response_model=DocumentAnalysis)
async def upload_and_process_document(background_tasks: BackgroundTasks,
                                      file: UploadFile = File(...),
                                      llm=Depends(get_llm),
                                      embeddings=Depends(get_embeddings)):
    # --- validation ---
    filename = (file.filename or "").strip()
    if not filename or filename in (".", "..") or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename.")
    # sanitise path traversal
    filename = os.path.basename(filename)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail=f"File '{filename}' is empty.")
    from security import check_file_magic
    check_file_magic(content, filename)

    os.makedirs(settings.UPLOAD_DIRECTORY, exist_ok=True)
    file_path = os.path.join(settings.UPLOAD_DIRECTORY, filename)
    with open(file_path, "wb") as f:
        f.write(content)

    try:
        docs = process_and_chunk_text(content, filename)
    except HTTPException:
        try:
            os.remove(file_path)
        except Exception:
            pass
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process document: {e}")

    # --- LLM analysis (bounded input, tolerant parsing) ---
    try:
        roles = getattr(settings, "ANALYSIS_ROLE_LIST", []) or [
            "Finance Manager", "Customer Manager", "Safety Manager",
            "HR Coordinator", "Legal Counsel", "Rolling Stock Engineer"]
        analysis_text = truncate_for_analysis(docs)
        summary_prompt = ChatPromptTemplate.from_template(
            "Provide a concise, professional summary (100-150 words) of this document:\n\n{document}")
        actions_prompt = ChatPromptTemplate.from_template(
            "Extract the 3-5 most important actionable tasks from this document as a bulleted list "
            "(each line starting with '- '). If none exist, reply exactly 'None'.\n\n{document}")
        role_prompt = ChatPromptTemplate.from_template(
            "Pick the single most relevant role for this document. Reply with ONLY the role name from: "
            f"[{', '.join(roles)}].\n\nDocument:\n{{document}}")
        import asyncio as _asyncio
        summary_result, actions_result, role_result = await _asyncio.gather(
            (summary_prompt | llm).ainvoke({"document": analysis_text}),
            (actions_prompt | llm).ainvoke({"document": analysis_text}),
            (role_prompt | llm).ainvoke({"document": analysis_text}),
        )
        summary = summary_result.content if hasattr(summary_result, "content") else str(summary_result)
        actions_raw = actions_result.content if hasattr(actions_result, "content") else str(actions_result)
        role = role_result.content if hasattr(role_result, "content") else str(role_result)
        action_items = [ln.strip().lstrip("-*• ").strip() for ln in str(actions_raw).splitlines()
                        if ln.strip() and "none" not in ln.strip().lower()][:8]
        analysis = DocumentAnalysis(summary=str(summary).strip(),
                                    action_items=action_items,
                                    assigned_role=str(role).strip().strip("'\""))
    except Exception as e:
        log.error("LLM analysis failed: %s\n%s", e, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"LLM analysis failed: {e}")

    # --- index (replace-then-add = re-upload safe, no duplicates) ---
    async with faiss_lock:
        _backup_index()
        try:
            vector_store = app_store.get("vector_store")
            if vector_store is None:
                app_store["vector_store"] = FAISS.from_documents(docs, embeddings)
            else:
                # remove previous chunks for this filename first
                store = getattr(vector_store, "docstore", None)
                mapping = getattr(store, "_dict", None) if store else None
                if isinstance(mapping, dict):
                    stale = [i for i, d in mapping.items()
                             if (d.metadata or {}).get("source") == filename]
                    if stale:
                        try:
                            vector_store.delete(stale)
                        except Exception as e:
                            log.warning("stale-chunk delete failed: %s", e)
                vector_store.add_documents(docs)
                app_store["vector_store"] = vector_store
            _rebuild_bm25()
            app_store["vector_store"].save_local(settings.model_dir())
        except Exception as e:
            # Embedding-dimension mismatch is the classic cause (model changed after index built).
            log.error("indexing failed: %s\n%s", e, traceback.format_exc())
            msg = str(e)
            if "dimension" in msg.lower():
                msg += (" Hint: the embedding model changed after the index was built. "
                        "Delete vector_store.faiss/ or re-upload with the original embedding model.")
            raise HTTPException(status_code=500, detail=f"Indexing failed: {msg}")

    log.info("Indexed '%s' (%d chunks)", filename, len(docs))
    background_tasks.add_task(trigger_n8n_webhooks, urls=settings.N8N_WEBHOOK_URLS,
                              data={"filename": filename, **analysis.model_dump()})
    return analysis
