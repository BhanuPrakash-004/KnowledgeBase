import os
import traceback
import asyncio
from typing import List
from fastapi import APIRouter, File, UploadFile, HTTPException, Depends, BackgroundTasks
from langchain_community.vectorstores import FAISS
from langchain_community.retrievers import BM25Retriever
from langchain_core.prompts import ChatPromptTemplate

from config import settings
from models import DocumentAnalysis
from state import app_store
from dependencies import get_llm, get_embeddings
from utils import process_and_chunk_text, trigger_n8n_webhooks

router = APIRouter()

@router.get("/api/documents", response_model=List[str])
async def list_documents():
    """Returns a list of all unique document names in the knowledge base."""
    vector_store = app_store.get("vector_store")
    if not vector_store:
        print("⚠️ Debug: vector_store is None in app_store")
        return []
    
    try:
        # Debugging FAISS Internal Structure
        print(f"⚠️ Debug: vector_store type: {type(vector_store)}")
        if hasattr(vector_store, "docstore"):
             print(f"⚠️ Debug: docstore type: {type(vector_store.docstore)}")
             if hasattr(vector_store.docstore, "_dict"):
                 print(f"⚠️ Debug: docstore count: {len(vector_store.docstore._dict)}")
             else:
                 print("⚠️ Debug: docstore has no _dict attribute")
        else:
             print("⚠️ Debug: vector_store has no docstore attribute")

        # Access the underlying docstore to find unique sources
        unique_sources = set()
        
        # Safe access to docstore
        if hasattr(vector_store, "docstore") and hasattr(vector_store.docstore, "_dict"):
            for doc_id, doc in vector_store.docstore._dict.items():
                # Debug first few docs
                if len(unique_sources) == 0:
                    print(f"⚠️ Debug: Sample Doc Metadata: {doc.metadata}")
                
                if "source" in doc.metadata:
                    unique_sources.add(doc.metadata["source"])
        
        doc_list = sorted(list(unique_sources))
        print(f"✅ Debug: Found {len(doc_list)} unique documents: {doc_list}")
        return doc_list
    except Exception as e:
        print(f"❌ Error listing documents: {e}")
        print(traceback.format_exc())
        return []

@router.post("/api/upload-and-process", response_model=DocumentAnalysis)
async def upload_and_process_document(background_tasks: BackgroundTasks, file: UploadFile = File(...), llm=Depends(get_llm), embeddings=Depends(get_embeddings)):
    file_path = os.path.join(settings.UPLOAD_DIRECTORY, file.filename)
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    try:
        docs = process_and_chunk_text(content, file.filename)
        # Use the first few chunks for a quicker analysis
        analysis_text = " ".join([doc.page_content for doc in docs[:4]])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process document: {e}")

    # LLM analysis for summary, actions, role
    try:
        summary_prompt = ChatPromptTemplate.from_template(
            "Provide a concise, professional summary (around 100-150 words) of the following document content: \n\n{document}"
        )
        actions_prompt = ChatPromptTemplate.from_template(
            "Extract the 3 to 5 most important, actionable tasks from the following document. Present them as a bulleted list. If no clear action items exist, respond with 'None'. \n\n{document}"
        )
        role_prompt = ChatPromptTemplate.from_template(
            "Read the document and determine the single most relevant employee role to handle it. Choose ONLY from this list: [Finance Manager, Customer Manager, Safety Manager, HR Coordinator, Legal Counsel, Rolling Stock Engineer]. Respond with ONLY the role name. Document: \n\n{document}"
        )

        # Create chains by piping prompts into the LLM
        summary_chain = summary_prompt | llm
        actions_chain = actions_prompt | llm
        role_chain = role_prompt | llm

        # Asynchronously run all analysis chains
        summary_result, actions_result, role_result = await asyncio.gather(
            summary_chain.ainvoke({"document": analysis_text}),
            actions_chain.ainvoke({"document": analysis_text}),
            role_chain.ainvoke({"document": analysis_text})
        )

        # Process the action items string into a clean list
        action_items_list = [
            line.strip().lstrip('-* ').strip() for line in actions_result.split('\n') 
            if line.strip() and "none" not in line.lower()
        ]
        
        # Create the final analysis object with real data
        analysis = DocumentAnalysis(
            summary=summary_result.strip(),
            action_items=action_items_list,
            assigned_role=role_result.strip().replace("'", "").replace('"', '')
        )
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"LLM analysis failed: {e}")

    # --- ADVANCED INGESTION PIPELINE ---
    vector_store = app_store.get("vector_store")
    if vector_store is None:
        app_store["vector_store"] = FAISS.from_documents(docs, embeddings)
    else:
        vector_store.add_documents(docs)

    # For BM25, we rebuild it with all documents from the vector store's docstore
    all_docs = list(app_store["vector_store"].docstore._dict.values())
    app_store["bm25_retriever"] = BM25Retriever.from_documents(all_docs)

    app_store["vector_store"].save_local(settings.FAISS_PATH)
    print(f"✅ Successfully processed, embedded, and indexed '{file.filename}'.")

    background_tasks.add_task(trigger_n8n_webhooks, urls=settings.N8N_WEBHOOK_URLS, data=analysis.model_dump())
    return analysis
