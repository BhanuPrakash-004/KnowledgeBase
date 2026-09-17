# models.py
from typing import List, Optional
from pydantic import BaseModel, Field


class DocumentAnalysis(BaseModel):
    summary: str
    action_items: List[str]
    assigned_role: str


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000, description="User question")
    session_id: str = Field(default="default", min_length=1, max_length=128,
                            pattern=r"^[A-Za-z0-9][A-Za-z0-9._\-:]{0,127}$",
                            description="Conversation id (persisted in SQLite)")
    filter_source: Optional[str] = Field(default=None, max_length=256, description="Restrict search to one file")
    # --- Per-request BYOK override (takes precedence over global toggle) ---
    provider: Optional[str] = Field(default=None, max_length=32, description="e.g. ollama|openai|anthropic|google|groq|mistral|openrouter|openai_compatible")
    model: Optional[str] = Field(default=None, max_length=128, description="Model name for the provider")
    api_key: Optional[str] = Field(default=None, max_length=500, description="BYOK key for this request only (never stored)")
    base_url: Optional[str] = Field(default=None, max_length=500, description="Custom gateway base URL")
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)


class SourceChunk(BaseModel):
    source: str
    page: Optional[int] = None
    preview: str = ""


class ChatResponse(BaseModel):
    answer: str
    sources: List[str] = []
    provider: str = "ollama"
    model: str = ""
    latency_ms: int = 0
    context_chars: int = 0
    docs_used: int = 0


class DocumentDetail(BaseModel):
    filename: str
    chunks: int
    pages: int = 0
    chars: int = 0
    preview: str = ""


class ProviderUpdate(BaseModel):
    llm_provider: Optional[str] = Field(default=None, max_length=32)
    llm_model: Optional[str] = Field(default=None, max_length=128)
    llm_api_key: Optional[str] = Field(default=None, max_length=500)  # empty string clears
    llm_base_url: Optional[str] = Field(default=None, max_length=500)
    embedding_provider: Optional[str] = Field(default=None, max_length=32)
    embedding_model: Optional[str] = Field(default=None, max_length=128)
    embedding_api_key: Optional[str] = Field(default=None, max_length=500)
    embedding_base_url: Optional[str] = Field(default=None, max_length=500)


class ProviderTestRequest(BaseModel):
    provider: str = Field(max_length=32)
    model: str = Field(max_length=128)
    api_key: Optional[str] = Field(default="", max_length=500)
    base_url: Optional[str] = Field(default=None, max_length=500)


class ChatMessageOut(BaseModel):
    id: int
    role: str
    content: str
    sources: List[str] = []
    provider: str = ""
    model: str = ""
    created_at: str = ""


class ChatSessionOut(BaseModel):
    session_id: str
    created_at: str = ""
    updated_at: str = ""
    message_count: int = 0
    preview: str = ""
