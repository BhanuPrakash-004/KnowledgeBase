import traceback
from operator import itemgetter
from fastapi import APIRouter, HTTPException, Depends
from langchain.retrievers import EnsembleRetriever, ContextualCompressionRetriever
from langchain.retrievers.document_compressors import CrossEncoderReranker
from langchain.chains import create_retrieval_chain, create_history_aware_retriever
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnablePassthrough
from langchain_core.messages import HumanMessage, AIMessage
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
        print(f"🔍 Performing Scoped Search in: {request.filter_source}")
        
        source_filter = lambda metadata: metadata.get("source") == request.filter_source
        
        # Increase initial retrieval to 30 to improve recall
        base_retriever = app_store["vector_store"].as_retriever(
            search_kwargs={"k": 30, "filter": source_filter}
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

    # Reranking and Context Compression
    # Increase top_n to 6 to give the LLM more context
    compressor = CrossEncoderReranker(model=reranker, top_n=6)
    compression_retriever = ContextualCompressionRetriever(
        base_compressor=compressor, base_retriever=base_retriever
    )

    # --- 3. CREATE HISTORY-AWARE RETRIEVER ---
    # This chain reformulates the user's query into a standalone question if history exists
    contextualize_q_system_prompt = (
        "Given a chat history and the latest user question "
        "which might reference context in the chat history, "
        "formulate a standalone question which can be understood "
        "without the chat history. Do NOT answer the question, "
        "just reformulate it if needed and otherwise return it as is."
    )
    
    contextualize_q_prompt = ChatPromptTemplate.from_messages([
        ("system", contextualize_q_system_prompt),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ])
    
    # This retriever will use the "standalone question" to search
    history_aware_retriever = create_history_aware_retriever(
        llm, compression_retriever, contextualize_q_prompt
    )

    # --- 4. DEFINE THE ANSWER GENERATION CHAIN ---
    qa_system_prompt = (
        "You are a precise and helpful assistant. Use the following pieces of retrieved context to answer the user's question. "
        "If the answer is not in the context, strictly state 'I cannot find the answer in the provided documents'. "
        "Do not make up information. Keep the answer concise and accurate.\n\n"
        "Context:\n{context}"
    )
    
    qa_prompt = ChatPromptTemplate.from_messages([
        ("system", qa_system_prompt),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ])

    question_answer_chain = create_stuff_documents_chain(llm, qa_prompt)
    
    # The final RAG chain
    rag_chain = create_retrieval_chain(history_aware_retriever, question_answer_chain)

    try:
        # Load conversation history for the prompt
        chat_history_obj = memory.load_memory_variables({})["chat_history"]
        
        # --- 5. INVOKE THE CHAIN AND MANAGE MEMORY ---
        print(f"❓ Asking: {request.query}")
        
        # Invoke the chain
        response_dict = await rag_chain.ainvoke({
            "input": request.query,
            "chat_history": chat_history_obj
        })
        
        response = response_dict["answer"]
        
        print(f"💬 LLM Response: {response}")

        # Save the current interaction to memory
        memory.save_context({"input": request.query}, {"answer": response})

        # Extract sources from the retrieved context (from response_dict["context"])
        retrieved_docs = response_dict.get("context", [])
        sources = sorted(list(set(f"{doc.metadata.get('source', 'N/A')}" + (f" (Page {doc.metadata['page']})" if 'page' in doc.metadata else "") for doc in retrieved_docs)))
        
        print(f"📚 Sources Found: {sources}")

        return ChatResponse(answer=response, sources=sources)
    except Exception as e:
        print(f"❌ Chat Error: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error during chat retrieval: {e}")
