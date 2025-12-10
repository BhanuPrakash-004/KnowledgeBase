from typing import List, Optional
from pydantic import BaseModel, Field

class DocumentAnalysis(BaseModel):
    summary: str
    action_items: List[str]
    assigned_role: str

class ChatRequest(BaseModel):
    query: str
    session_id: str = Field(description="A unique identifier for the conversation session.")
    filter_source: Optional[str] = None

class ChatResponse(BaseModel):
    answer: str
    sources: List[str] = []
