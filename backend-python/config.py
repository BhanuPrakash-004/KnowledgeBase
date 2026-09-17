# config.py
"""Central application configuration.

Supports two LLM modes:
  1. Local / own model  -> LLM_PROVIDER=ollama (default, no API key needed)
  2. BYOK (bring your own key) -> LLM_PROVIDER=openai|anthropic|google|groq|mistral|openrouter|openai_compatible

Embedding provider can be chosen independently so you can keep cheap local
embeddings (Ollama) while using a hosted chat model, or vice-versa.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional
import json
import os


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    # ---- LLM (chat generation) ----
    LLM_PROVIDER: str = "ollama"
    LLM_MODEL: str = "llama3"
    LLM_API_KEY: Optional[str] = None
    LLM_BASE_URL: Optional[str] = None  # for openai_compatible / openrouter / custom gateway
    LLM_TEMPERATURE: float = 0.2
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # ---- Embeddings ----
    EMBEDDING_PROVIDER: str = "ollama"
    EMBEDDING_MODEL: str = "mxbai-embed-large:335m"
    EMBEDDING_API_KEY: Optional[str] = None
    EMBEDDING_BASE_URL: Optional[str] = None

    # ---- Reranker / retrieval accuracy tuning ----
    RERANKER_MODEL: str = "BAAI/bge-reranker-base"
    ENABLE_RERANKER: bool = True
    ENABLE_HYBRID_SEARCH: bool = True
    RETRIEVAL_K: int = 20            # candidates from vector store (before rerank)
    RERANK_TOP_N: int = 5            # final passages given to the LLM
    HYBRID_VECTOR_WEIGHT: float = 0.5  # 0..1, remainder goes to BM25
    CHUNK_SIZE: int = 900
    CHUNK_OVERLAP: int = 150
    MAX_CONTEXT_CHARS: int = 12000   # cap analysis input to bound LLM cost

    # ---- Application paths ----
    FAISS_PATH: str = "vector_store.faiss"
    UPLOAD_DIRECTORY: str = "uploaded_files"
    CHAT_DB_PATH: str = "chat_history.db"
    PROVIDER_CONFIG_PATH: str = "provider_config.json"

    # ---- Upload limits ----
    MAX_FILE_MB: int = 25
    ALLOWED_EXTENSIONS: str = ".pdf,.txt,.md,.csv,.docx,.png,.jpg,.jpeg"

    # ---- Serving / errors ----
    SERVE_FILES: bool = True  # set false to disable public /files static mount
    DEBUG_ERRORS: bool = False  # true -> raw exception text in 500s (dev only)

    # ---- Chat history retention ----
    MAX_MESSAGES_PER_SESSION: int = 500  # auto-prune oldest beyond this

    # ---- Rate limits (per IP / minute, 0 = disabled) ----
    RATE_LIMIT_CHAT_PER_MIN: int = 30
    RATE_LIMIT_UPLOAD_PER_MIN: int = 10
    RATE_LIMIT_TEST_PER_MIN: int = 10

    # ---- Document analysis roles (comma-separated, configurable) ----
    ANALYSIS_ROLES: str = "Finance Manager,Customer Manager,Safety Manager,HR Coordinator,Legal Counsel,Rolling Stock Engineer"

    # ---- CORS ----
    # Comma-separated list. Use "*" only for dev without credentials.
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173"

    # ---- n8n Integration ----
    N8N_WEBHOOK_URLS_JSON: Optional[str] = '[]'

    @property
    def N8N_WEBHOOK_URLS(self) -> List[str]:
        try:
            return json.loads(self.N8N_WEBHOOK_URLS_JSON or '[]')
        except Exception:
            return []

    @property
    def CORS_ORIGIN_LIST(self) -> List[str]:
        raw = (self.CORS_ORIGINS or "").strip()
        if raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]

    @property
    def ALLOWED_EXT_SET(self) -> set:
        return {e.strip().lower() for e in (self.ALLOWED_EXTENSIONS or "").split(",") if e.strip()}

    @property
    def ANALYSIS_ROLE_LIST(self) -> list:
        return [r.strip() for r in (self.ANALYSIS_ROLES or "").split(",") if r.strip()]

    def model_dir(self) -> str:
        # Resolve FAISS dir relative to this file so cwd doesn't matter.
        base = os.path.dirname(os.path.abspath(__file__))
        p = self.FAISS_PATH
        return p if os.path.isabs(p) else os.path.join(base, p)


settings = Settings()
