import os
import io
import asyncio
import httpx
from typing import List
from PIL import Image
import pytesseract
from PyPDF2 import PdfReader
from fastapi import HTTPException
from langchain.docstore.document import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter

def process_and_chunk_text(file_content: bytes, filename: str) -> List[Document]:
    docs = []
    file_extension = os.path.splitext(filename)[1].lower()
    if file_extension == ".pdf":
        pdf_file = io.BytesIO(file_content)
        pdf_reader = PdfReader(pdf_file)
        for i, page in enumerate(pdf_reader.pages):
            page_text = page.extract_text() or ""
            if page_text.strip():
                docs.append(Document(page_content=page_text, metadata={"source": filename, "page": i + 1}))
    elif file_extension in [".txt", ".md"]:
        text = file_content.decode("utf-8", errors="ignore")
        docs.append(Document(page_content=text, metadata={"source": filename}))
    elif file_extension in [".png", ".jpg", ".jpeg"]:
         image = Image.open(io.BytesIO(file_content))
         text = pytesseract.image_to_string(image)
         if text.strip():
             docs.append(Document(page_content=text, metadata={"source": filename}))
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_extension}")

    if not docs:
        raise HTTPException(status_code=400, detail=f"Could not extract any text from '{filename}'.")

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
    return text_splitter.split_documents(docs)

async def trigger_n8n_webhooks(urls: List[str], data: dict):
    if not urls: return
    async with httpx.AsyncClient() as client:
        tasks = [client.post(url, json=data, timeout=10) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                print(f"❌ Error triggering n8n webhook {urls[i]}: {res}")
            else:
                print(f"✅ n8n webhook triggered successfully: {urls[i]}")

def format_docs(docs: List[Document]) -> str:
    return "\n\n".join(doc.page_content for doc in docs)
