import traceback
from operator import itemgetter
from fastapi import APIRouter, HTTPException, Depends
from langchain.retrievers import EnsembleRetriever, ContextualCompressionRetriever
from langchain.retrievers.document_compressors import CrossEncoderReranker
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnablePassthrough
from langchain.memory import ConversationBufferMemory

from models import ChatRequest, ChatResponse
from state import app_store
from dependencies import get_llm, get_reranker, get_retrievers
from utils import format_docs

router = APIRouter()

@router.post("/api/chat", response_model=ChatResponse)
async def chat_with_knowledge_base(request: ChatRequest, llm=Depends(get_llm), reranker=Depends(get_reranker), retrievers=Depends(get_retrievers)):
    # --- 1. SET UP CONVERSATIONAL MEMORY ---
    if request.session_id not in app_store["chat_sessions"]:
        app_store["chat_sessions"][request.session_id] = ConversationBufferMemory(
            memory_key="chat_history", return_messages=True, output_key='answer'
        )
    memory = app_store["chat_sessions"][request.session_id]

    # --- 2. CREATE THE RETRIEVAL PIPELINE (CONDITIONAL) ---
    if request.filter_source:
        # SCOPED SEARCH: Search only within the specific document using Metadata Filtering
        # Note: We rely on Vector Search here as BM25Retriever in LangChain doesn't easily support dynamic metadata filtering without rebuilding.
        print(f"🔍 Performing Scoped Search in: {request.filter_source}")
        
        # FAISS in LangChain requires a callable for filtering when using the standard docstore
        source_filter = lambda metadata: metadata.get("source") == request.filter_source
        
        base_retriever = app_store["vector_store"].as_retriever(
            search_kwargs={"k": 10, "filter": source_filter}
        )
    else:
        # GLOBAL SEARCH: Hybrid Search (Vector + Keyword) across all docs
        print("🔍 Performing Global Search")
        
        if retrievers["keyword"]:
            base_retriever = EnsembleRetriever(
                retrievers=[retrievers["keyword"], retrievers["vector"]],
                weights=[0.5, 0.5]
            )
        else:
            print("⚠️ Warning: BM25 Retriever is not available. Falling back to Vector Search only.")
            base_retriever = retrievers["vector"]

    # Reranking and Context Compression (Applied to whichever retriever is selected)
    compressor = CrossEncoderReranker(model=reranker, top_n=4)
    compression_retriever = ContextualCompressionRetriever(
        base_compressor=compressor, base_retriever=base_retriever
    )

    # --- 3. DEFINE THE CONVERSATIONAL RAG CHAIN ---
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an intelligent assistant. Answer the user's question based on the provided context. If you don't know the answer from the context, say so. After the answer, list the sources you used.\n\nContext:\n{context}"),
        MessagesPlaceholder(variable_name="chat_history"),
        ("user", "{input}"),
    ])

    document_chain = create_stuff_documents_chain(llm, prompt)

    # Load conversation history
    def load_history(inputs):
        return memory.load_memory_variables(inputs)["chat_history"]

    # The final chain that combines retrieval, history, and generation
    conversational_rag_chain = (
        RunnablePassthrough.assign(chat_history=load_history)
        | {
            "context": itemgetter("input") | compression_retriever,
            "input": itemgetter("input"),
            "chat_history": itemgetter("chat_history")
          }
        | document_chain
    )

    try:
        # --- 4. INVOKE THE CHAIN AND MANAGE MEMORY ---
        print(f"❓ Asking: {request.query}")
        response = await conversational_rag_chain.ainvoke({"input": request.query})
        
        print(f"💬 LLM Response Raw: {response}")
        print(f"💬 LLM Response Type: {type(response)}")

        # Save the current interaction to memory
        memory.save_context({"input": request.query}, {"answer": response})

        # Extract sources from the retrieved context
        retrieved_docs = compression_retriever.get_relevant_documents(request.query)
        sources = sorted(list(set(f"{doc.metadata.get('source', 'N/A')}" + (f" (Page {doc.metadata['page']})" if 'page' in doc.metadata else "") for doc in retrieved_docs)))
        
        print(f"📚 Sources Found: {sources}")

        return ChatResponse(answer=response, sources=sources)
    except Exception as e:
        print(f"❌ Chat Error: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error during chat retrieval: {e}")
