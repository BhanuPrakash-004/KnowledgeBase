# providers.py
"""LLM / embedding provider abstraction with Local-vs-BYOK toggle.

Design goals:
- Zero hard dependency on hosted-provider SDKs. Ollama works out of the box
  (langchain-ollama, already required). Every OpenAI-compatible provider
  (OpenAI, Groq, Mistral, OpenRouter, Together, DeepSeek, xAI, any custom
  gateway) works through a small httpx-based client below.
- If the optional langchain_* partner packages ARE installed
  (langchain-openai, langchain-anthropic, ...), we prefer them for maximum
  feature parity; otherwise we fall back to the generic HTTP clients.
- Request-level BYOK override: chat / test endpoints may pass
  provider+model+api_key+base_url per request without changing global config.
- Global toggle persisted in provider_config.json (keys stored locally only,
  never returned in full by the API).
"""
import hashlib
import json
import os
from typing import Any, Dict, List, Optional, Sequence

import httpx
from pydantic import Field, PrivateAttr

from langchain_core.callbacks import CallbackManagerForLLMRun, AsyncCallbackManagerForLLMRun
from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from config import settings


# ---------------------------------------------------------------------------
# Provider catalogue (used by frontend toggle + validation)
# ---------------------------------------------------------------------------
SUPPORTED_PROVIDERS: Dict[str, Dict[str, Any]] = {
    "ollama": {
        "label": "Local / Own model (Ollama)",
        "needs_key": False,
        "openai_compatible": False,
        "default_model": "llama3",
        "default_base_url": "http://localhost:11434",
        "description": "Runs on your machine. Private, free, no API key.",
    },
    "openai": {
        "label": "OpenAI (BYOK)",
        "needs_key": True,
        "openai_compatible": True,
        "default_model": "gpt-4o-mini",
        "default_base_url": "https://api.openai.com/v1",
        "description": "GPT-4o / GPT-4o-mini / o-series via your OpenAI key.",
    },
    "anthropic": {
        "label": "Anthropic Claude (BYOK)",
        "needs_key": True,
        "openai_compatible": False,
        "default_model": "claude-3-5-sonnet-latest",
        "default_base_url": "https://api.anthropic.com",
        "description": "Claude Sonnet / Haiku / Opus via your Anthropic key.",
    },
    "google": {
        "label": "Google Gemini (BYOK)",
        "needs_key": True,
        "openai_compatible": False,
        "default_model": "gemini-1.5-flash",
        "default_base_url": "https://generativelanguage.googleapis.com",
        "description": "Gemini Flash / Pro via your Google AI Studio key.",
    },
    "groq": {
        "label": "Groq (BYOK)",
        "needs_key": True,
        "openai_compatible": True,
        "default_model": "llama-3.3-70b-versatile",
        "default_base_url": "https://api.groq.com/openai/v1",
        "description": "Ultra-fast Llama / Mixtral hosting via your Groq key.",
    },
    "mistral": {
        "label": "Mistral (BYOK)",
        "needs_key": True,
        "openai_compatible": True,
        "default_model": "mistral-small-latest",
        "default_base_url": "https://api.mistral.ai/v1",
        "description": "Mistral models via your Mistral key.",
    },
    "openrouter": {
        "label": "OpenRouter (BYOK)",
        "needs_key": True,
        "openai_compatible": True,
        "default_model": "meta-llama/llama-3.3-70b-instruct:free",
        "default_base_url": "https://openrouter.ai/api/v1",
        "description": "100+ models behind one OpenAI-compatible key.",
    },
    "openai_compatible": {
        "label": "Custom OpenAI-compatible (BYOK)",
        "needs_key": True,
        "openai_compatible": True,
        "default_model": "",
        "default_base_url": "",
        "description": "Any gateway exposing /chat/completions (Together, DeepSeek, xAI, vLLM, LM Studio...).",
    },
}

OPENAI_COMPATIBLE_PROVIDERS = {k for k, v in SUPPORTED_PROVIDERS.items() if v.get("openai_compatible")}

CANONICAL_ALIASES = {
    "local": "ollama", "own": "ollama", "ollama": "ollama",
    "openai": "openai", "gpt": "openai",
    "anthropic": "anthropic", "claude": "anthropic",
    "google": "google", "gemini": "google",
    "groq": "groq",
    "mistral": "mistral",
    "openrouter": "openrouter",
    "custom": "openai_compatible", "openai_compatible": "openai_compatible",
    "compatible": "openai_compatible", "together": "openai_compatible",
    "deepseek": "openai_compatible", "xai": "openai_compatible",
}


def normalize_provider(name: Optional[str]) -> str:
    if not name:
        return "ollama"
    key = str(name).strip().lower()
    if key in SUPPORTED_PROVIDERS:
        return key
    return CANONICAL_ALIASES.get(key, key)


def default_base_url(provider: str) -> Optional[str]:
    return (SUPPORTED_PROVIDERS.get(provider) or {}).get("default_base_url") or None


def default_model(provider: str) -> str:
    return (SUPPORTED_PROVIDERS.get(provider) or {}).get("default_model") or ""


# ---------------------------------------------------------------------------
# Message helpers
# ---------------------------------------------------------------------------
def _to_openai_messages(messages: Sequence[BaseMessage]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for m in messages:
        if isinstance(m, SystemMessage):
            role = "system"
        elif isinstance(m, HumanMessage):
            role = "user"
        elif isinstance(m, AIMessage):
            role = "assistant"
        else:
            role = getattr(m, "type", "user")
            if role == "human":
                role = "user"
            elif role == "ai":
                role = "assistant"
            elif role not in ("system", "user", "assistant"):
                role = "user"
        content = m.content if isinstance(m.content, str) else str(m.content)
        out.append({"role": role, "content": content})
    return out


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict):
                if b.get("type") == "text":
                    parts.append(b.get("text", ""))
                elif "text" in b:
                    parts.append(str(b["text"]))
            else:
                parts.append(str(b))
        return "".join(parts)
    return str(content)


# ---------------------------------------------------------------------------
# Generic HTTP chat models (no extra SDK needed)
# ---------------------------------------------------------------------------
class OpenAICompatibleChat(BaseChatModel):
    """Minimal OpenAI-compatible chat model (OpenAI, Groq, OpenRouter, ...)."""

    model: str = Field(default="gpt-4o-mini")
    api_key: str = Field(default="")
    base_url: str = Field(default="https://api.openai.com/v1")
    temperature: float = Field(default=0.2)
    timeout: float = Field(default=60.0)
    extra_headers: Dict[str, str] = Field(default_factory=dict)

    _client: Optional[httpx.Client] = PrivateAttr(default=None)
    _aclient: Optional[httpx.AsyncClient] = PrivateAttr(default=None)

    @property
    def _llm_type(self) -> str:
        return "openai-compatible-chat"

    def _url(self) -> str:
        return self.base_url.rstrip("/") + "/chat/completions"

    def _headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        h.update(self.extra_headers or {})
        return h

    def _payload(self, messages: List[BaseMessage]) -> Dict[str, Any]:
        return {
            "model": self.model,
            "messages": _to_openai_messages(messages),
            "temperature": self.temperature,
        }

    def _parse(self, data: Dict[str, Any]) -> str:
        try:
            return data["choices"][0]["message"]["content"] or ""
        except Exception as e:
            raise RuntimeError(f"Unexpected chat-completions response: {data!r:.500}") from e

    def _generate(self, messages: List[BaseMessage], stop=None,
                  run_manager: Optional[CallbackManagerForLLMRun] = None, **kwargs) -> ChatResult:
        payload = self._payload(messages)
        if stop:
            payload["stop"] = stop
        try:
            with httpx.Client(timeout=self.timeout) as client:
                r = client.post(self._url(), headers=self._headers(), json=payload)
                r.raise_for_status()
                text = self._parse(r.json())
        except httpx.HTTPStatusError as e:
            body = e.response.text[:800] if e.response is not None else ""
            raise RuntimeError(f"LLM provider error {e.response.status_code if e.response is not None else '?'}: {body}") from e
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

    async def _agenerate(self, messages: List[BaseMessage], stop=None,
                         run_manager: Optional[AsyncCallbackManagerForLLMRun] = None, **kwargs) -> ChatResult:
        payload = self._payload(messages)
        if stop:
            payload["stop"] = stop
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(self._url(), headers=self._headers(), json=payload)
                r.raise_for_status()
                text = self._parse(r.json())
        except httpx.HTTPStatusError as e:
            body = e.response.text[:800] if e.response is not None else ""
            raise RuntimeError(f"LLM provider error {e.response.status_code if e.response is not None else '?'}: {body}") from e
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])


class AnthropicChat(BaseChatModel):
    """Minimal Anthropic Messages API client (fallback when langchain-anthropic is absent)."""

    model: str = Field(default="claude-3-5-sonnet-latest")
    api_key: str = Field(default="")
    base_url: str = Field(default="https://api.anthropic.com")
    temperature: float = Field(default=0.2)
    timeout: float = Field(default=60.0)
    max_tokens: int = Field(default=1024)

    @property
    def _llm_type(self) -> str:
        return "anthropic-chat"

    def _split(self, messages: Sequence[BaseMessage]):
        system_parts, convo = [], []
        for m in messages:
            text = m.content if isinstance(m.content, str) else str(m.content)
            if isinstance(m, SystemMessage):
                system_parts.append(text)
            elif isinstance(m, AIMessage):
                convo.append({"role": "assistant", "content": text})
            else:
                convo.append({"role": "user", "content": text})
        return ("\n".join(system_parts), convo)

    def _payload(self, messages: List[BaseMessage]) -> Dict[str, Any]:
        system, convo = self._split(messages)
        p: Dict[str, Any] = {"model": self.model, "max_tokens": self.max_tokens,
                             "temperature": self.temperature, "messages": convo}
        if system:
            p["system"] = system
        return p

    def _headers(self) -> Dict[str, str]:
        return {"Content-Type": "application/json", "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01"}

    def _parse(self, data: Dict[str, Any]) -> str:
        try:
            return "".join(b.get("text", "") for b in data.get("content", []) if isinstance(b, dict))
        except Exception as e:
            raise RuntimeError(f"Unexpected Anthropic response: {data!r:.500}") from e

    def _generate(self, messages: List[BaseMessage], stop=None,
                  run_manager: Optional[CallbackManagerForLLMRun] = None, **kwargs) -> ChatResult:
        payload = self._payload(messages)
        if stop:
            payload["stop_sequences"] = stop
        with httpx.Client(timeout=self.timeout) as client:
            r = client.post(self.base_url.rstrip("/") + "/v1/messages", headers=self._headers(), json=payload)
            r.raise_for_status()
            text = self._parse(r.json())
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

    async def _agenerate(self, messages: List[BaseMessage], stop=None,
                         run_manager: Optional[AsyncCallbackManagerForLLMRun] = None, **kwargs) -> ChatResult:
        payload = self._payload(messages)
        if stop:
            payload["stop_sequences"] = stop
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(self.base_url.rstrip("/") + "/v1/messages", headers=self._headers(), json=payload)
            r.raise_for_status()
            text = self._parse(r.json())
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])


class GoogleChat(BaseChatModel):
    """Minimal Google Generative Language client (fallback when langchain-google-genai is absent)."""

    model: str = Field(default="gemini-1.5-flash")
    api_key: str = Field(default="")
    base_url: str = Field(default="https://generativelanguage.googleapis.com")
    temperature: float = Field(default=0.2)
    timeout: float = Field(default=60.0)

    @property
    def _llm_type(self) -> str:
        return "google-chat"

    def _payload(self, messages: List[BaseMessage]) -> Dict[str, Any]:
        system_parts, contents = [], []
        for m in messages:
            text = m.content if isinstance(m.content, str) else str(m.content)
            if isinstance(m, SystemMessage):
                system_parts.append(text)
            else:
                role = "model" if isinstance(m, AIMessage) else "user"
                contents.append({"role": role, "parts": [{"text": text}]})
        p: Dict[str, Any] = {"contents": contents,
                             "generationConfig": {"temperature": self.temperature}}
        if system_parts:
            p["systemInstruction"] = {"parts": [{"text": "\n".join(system_parts)}]}
        return p

    def _url(self) -> str:
        return f"{self.base_url.rstrip('/')}/v1beta/models/{self.model}:generateContent?key={self.api_key}"

    def _parse(self, data: Dict[str, Any]) -> str:
        try:
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts if isinstance(p, dict))
        except Exception as e:
            raise RuntimeError(f"Unexpected Google response: {data!r:.500}") from e

    def _generate(self, messages: List[BaseMessage], stop=None,
                  run_manager: Optional[CallbackManagerForLLMRun] = None, **kwargs) -> ChatResult:
        with httpx.Client(timeout=self.timeout) as client:
            r = client.post(self._url(), json=self._payload(messages))
            r.raise_for_status()
            text = self._parse(r.json())
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

    async def _agenerate(self, messages: List[BaseMessage], stop=None,
                         run_manager: Optional[AsyncCallbackManagerForLLMRun] = None, **kwargs) -> ChatResult:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(self._url(), json=self._payload(messages))
            r.raise_for_status()
            text = self._parse(r.json())
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])


# ---------------------------------------------------------------------------
# Generic HTTP embeddings (OpenAI-compatible + Google)
# ---------------------------------------------------------------------------
class OpenAICompatibleEmbeddings(Embeddings):
    model: str = Field(default="text-embedding-3-small")
    api_key: str = Field(default="")
    base_url: str = Field(default="https://api.openai.com/v1")
    timeout: float = Field(default=60.0)

    def _headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _embed(self, texts: List[str]) -> List[List[float]]:
        url = self.base_url.rstrip("/") + "/embeddings"
        with httpx.Client(timeout=self.timeout) as client:
            r = client.post(url, headers=self._headers(),
                            json={"model": self.model, "input": texts})
            r.raise_for_status()
            data = r.json()
        return [d["embedding"] for d in sorted(data["data"], key=lambda x: x["index"])]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        out: List[List[float]] = []
        for i in range(0, len(texts), 96):
            out.extend(self._embed(texts[i:i + 96]))
        return out

    def embed_query(self, text: str) -> List[float]:
        return self._embed([text])[0]


class GoogleEmbeddings(Embeddings):
    model: str = Field(default="text-embedding-004")
    api_key: str = Field(default="")
    base_url: str = Field(default="https://generativelanguage.googleapis.com")
    timeout: float = Field(default=60.0)

    def _embed_one(self, client: httpx.Client, text: str) -> List[float]:
        url = (f"{self.base_url.rstrip('/')}/v1beta/models/{self.model}"
               f":embedContent?key={self.api_key}")
        r = client.post(url, json={"content": {"parts": [{"text": text}]}})
        r.raise_for_status()
        return r.json()["embedding"]["values"]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        with httpx.Client(timeout=self.timeout) as client:
            return [self._embed_one(client, t) for t in texts]

    def embed_query(self, text: str) -> List[float]:
        with httpx.Client(timeout=self.timeout) as client:
            return self._embed_one(client, text)


# ---------------------------------------------------------------------------
# Factories (prefer official partner packages when installed)
# ---------------------------------------------------------------------------
def build_chat_model(provider: Optional[str] = None, model: Optional[str] = None,
                     api_key: Optional[str] = None, base_url: Optional[str] = None,
                     temperature: Optional[float] = None):
    from security import sanitize_model_name, validate_base_url
    provider = normalize_provider(provider or settings.LLM_PROVIDER)
    _default = default_model(provider)
    model = sanitize_model_name(model or getattr(settings, "LLM_MODEL", None) or _default, _default) or _default
    temperature = settings.LLM_TEMPERATURE if temperature is None else float(temperature)
    api_key = (api_key if api_key is not None else (settings.LLM_API_KEY or "")).strip() if isinstance((api_key if api_key is not None else settings.LLM_API_KEY), str) else (api_key or settings.LLM_API_KEY or "")
    raw_base = (base_url or settings.LLM_BASE_URL or default_base_url(provider) or "").strip()
    try:
        base_url = validate_base_url(raw_base) if raw_base else ""
    except ValueError as e:
        raise ValueError(f"Invalid LLM base_url: {e}")

    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Unsupported LLM provider '{provider}'. Choose from: {sorted(SUPPORTED_PROVIDERS)}")

    if provider == "ollama":
        try:
            from langchain_ollama import ChatOllama
            return ChatOllama(model=model, temperature=temperature,
                              base_url=getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434"))
        except ImportError:
            try:
                from langchain_ollama import OllamaLLM as _OllamaLLM
                return _OllamaLLM(model=model, temperature=temperature,
                                  base_url=getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434"))
            except ImportError:
                from langchain_community.llms import Ollama as _OldOllama
                return _OldOllama(model=model, temperature=temperature)

    if provider in OPENAI_COMPATIBLE_PROVIDERS:
        if not api_key:
            raise ValueError(f"Provider '{provider}' needs an API key (BYOK). Pass api_key or set LLM_API_KEY.")
        if not base_url:
            raise ValueError(f"Provider '{provider}' needs a base_url (e.g. {default_base_url(provider)}).")
        if not model:
            raise ValueError(f"Provider '{provider}' needs a model name.")
        # Prefer official SDK when present (better retries / tool support)
        try:
            from langchain_openai import ChatOpenAI
            extra = {}
            if provider == "openrouter":
                extra = {"default_headers": {"HTTP-Referer": "http://localhost:5173", "X-Title": "KnowledgeBase"}}
            return ChatOpenAI(model=model, api_key=api_key, base_url=base_url,
                              temperature=temperature, timeout=60, max_retries=2, **extra)
        except ImportError:
            extra_headers = {}
            if provider == "openrouter":
                extra_headers = {"HTTP-Referer": "http://localhost:5173", "X-Title": "KnowledgeBase"}
            return OpenAICompatibleChat(model=model, api_key=api_key, base_url=base_url,
                                        temperature=temperature, extra_headers=extra_headers)

    if provider == "anthropic":
        if not api_key:
            raise ValueError("Anthropic needs an API key (BYOK).")
        try:
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(model=model or default_model("anthropic"), api_key=api_key,
                                 temperature=temperature, timeout=60, max_retries=2)
        except ImportError:
            return AnthropicChat(model=model or default_model("anthropic"), api_key=api_key,
                                 base_url=base_url or "https://api.anthropic.com", temperature=temperature)

    if provider == "google":
        if not api_key:
            raise ValueError("Google Gemini needs an API key (BYOK).")
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(model=model or default_model("google"),
                                          google_api_key=api_key, temperature=temperature)
        except ImportError:
            return GoogleChat(model=model or default_model("google"), api_key=api_key,
                              base_url=base_url or "https://generativelanguage.googleapis.com",
                              temperature=temperature)

    raise ValueError(f"Unsupported provider '{provider}'")


def build_embeddings(provider: Optional[str] = None, model: Optional[str] = None,
                     api_key: Optional[str] = None, base_url: Optional[str] = None):
    from security import sanitize_model_name, validate_base_url
    provider = normalize_provider(provider or settings.EMBEDDING_PROVIDER)
    model = sanitize_model_name(model or getattr(settings, "EMBEDDING_MODEL", None) or "", "") or (getattr(settings, "EMBEDDING_MODEL", None) or "").strip()
    api_key = (api_key if api_key is not None else (settings.EMBEDDING_API_KEY or ""))
    if isinstance(api_key, str):
        api_key = api_key.strip()
    raw_base = (base_url or settings.EMBEDDING_BASE_URL or default_base_url(provider) or "").strip()
    try:
        base_url = validate_base_url(raw_base) if raw_base else ""
    except ValueError as e:
        raise ValueError(f"Invalid embedding base_url: {e}")

    if provider == "ollama":
        from langchain_ollama import OllamaEmbeddings
        return OllamaEmbeddings(
            model=model or "mxbai-embed-large:335m",
            base_url=getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434"))

    if provider in OPENAI_COMPATIBLE_PROVIDERS:
        if not api_key:
            raise ValueError(f"Embedding provider '{provider}' needs an API key.")
        if not base_url:
            raise ValueError(f"Embedding provider '{provider}' needs a base_url.")
        try:
            from langchain_openai import OpenAIEmbeddings
            return OpenAIEmbeddings(model=model or "text-embedding-3-small",
                                    api_key=api_key, base_url=base_url)
        except ImportError:
            return OpenAICompatibleEmbeddings(model=model or "text-embedding-3-small",
                                              api_key=api_key, base_url=base_url)

    if provider == "google":
        if not api_key:
            raise ValueError("Google embeddings need an API key.")
        try:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
            return GoogleGenerativeAIEmbeddings(model=model or "models/text-embedding-004",
                                                google_api_key=api_key)
        except ImportError:
            return GoogleEmbeddings(model=model or "text-embedding-004",
                                    api_key=api_key, base_url=base_url or default_base_url("google"))

    if provider == "anthropic":
        raise ValueError("Anthropic has no embeddings API — use ollama / openai / google for embeddings.")

    raise ValueError(f"Unsupported embedding provider '{provider}'")


# ---------------------------------------------------------------------------
# Runtime toggle persistence (provider_config.json)
# ---------------------------------------------------------------------------
def _config_path() -> str:
    p = getattr(settings, "PROVIDER_CONFIG_PATH", "provider_config.json")
    if os.path.isabs(p):
        return p
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, p)


def _read_json_config() -> Dict[str, Any]:
    try:
        with open(_config_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def _write_json_config(data: Dict[str, Any]) -> None:
    path = _config_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    try:
        from security import chmod_private
        chmod_private(path)
    except Exception:
        pass


def _mask(key: Optional[str]) -> str:
    if not key:
        return ""
    k = str(key)
    if len(k) <= 8:
        return "****"
    return k[:3] + "****" + k[-3:]


def get_active_provider_config() -> Dict[str, Any]:
    """Merged view: JSON overrides > env settings. Secrets are masked."""
    saved = _read_json_config()
    llm_provider = normalize_provider(saved.get("llm_provider") or settings.LLM_PROVIDER)
    emb_provider = normalize_provider(saved.get("embedding_provider") or settings.EMBEDDING_PROVIDER)
    llm_key = saved.get("llm_api_key", None)
    if llm_key is None:
        llm_key = settings.LLM_API_KEY or ""
    emb_key = saved.get("embedding_api_key", None)
    if emb_key is None:
        emb_key = settings.EMBEDDING_API_KEY or ""
    return {
        "llm_provider": llm_provider,
        "llm_model": saved.get("llm_model") or settings.LLM_MODEL,
        "llm_base_url": saved.get("llm_base_url") or settings.LLM_BASE_URL or default_base_url(llm_provider),
        "llm_api_key_masked": _mask(llm_key),
        "has_llm_key": bool(llm_key),
        "embedding_provider": emb_provider,
        "embedding_model": saved.get("embedding_model") or settings.EMBEDDING_MODEL,
        "embedding_base_url": saved.get("embedding_base_url") or settings.EMBEDDING_BASE_URL or default_base_url(emb_provider),
        "has_embedding_key": bool(emb_key),
        "supported_providers": [
            {"id": pid, **info} for pid, info in SUPPORTED_PROVIDERS.items()
        ],
    }


def _resolve_secret(saved_key: Any, settings_key: Optional[str]) -> str:
    if saved_key is not None and str(saved_key) != "":
        return str(saved_key)
    return (settings_key or "")


def resolve_active_llm_kwargs(overrides: Optional[Dict[str, Any]] = None):
    """Final kwargs for build_chat_model: request override > saved JSON > env."""
    overrides = overrides or {}
    saved = _read_json_config()
    provider = normalize_provider(overrides.get("provider") or saved.get("llm_provider") or settings.LLM_PROVIDER)
    model = overrides.get("model") or saved.get("llm_model") or settings.LLM_MODEL
    base_url = overrides.get("base_url") or saved.get("llm_base_url") or settings.LLM_BASE_URL or default_base_url(provider)
    if "api_key" in overrides and overrides["api_key"] not in (None, ""):
        api_key = overrides["api_key"]
    else:
        api_key = _resolve_secret(saved.get("llm_api_key", None), settings.LLM_API_KEY)
    temperature = overrides.get("temperature", settings.LLM_TEMPERATURE)
    return {"provider": provider, "model": model, "api_key": api_key,
            "base_url": base_url, "temperature": temperature}


def update_active_provider_config(llm_provider=None, llm_model=None, llm_api_key=None,
                                  llm_base_url=None, embedding_provider=None,
                                  embedding_model=None, embedding_api_key=None,
                                  embedding_base_url=None) -> Dict[str, Any]:
    saved = _read_json_config()
    if llm_provider is not None:
        saved["llm_provider"] = normalize_provider(llm_provider)
    if llm_model is not None:
        saved["llm_model"] = llm_model
    if llm_api_key is not None:  # empty string clears the key
        saved["llm_api_key"] = llm_api_key
    if llm_base_url is not None:
        saved["llm_base_url"] = llm_base_url
    if embedding_provider is not None:
        saved["embedding_provider"] = normalize_provider(embedding_provider)
    if embedding_model is not None:
        saved["embedding_model"] = embedding_model
    if embedding_api_key is not None:
        saved["embedding_api_key"] = embedding_api_key
    if embedding_base_url is not None:
        saved["embedding_base_url"] = embedding_base_url
    _write_json_config(saved)
    return get_active_provider_config()


def fingerprint(*parts: Any) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(str(p if p is not None else "").encode("utf-8", errors="ignore"))
        h.update(b"|")
    return h.hexdigest()[:16]


async def test_llm_connection(provider: str, model: str, api_key: str = "",
                              base_url: Optional[str] = None) -> Dict[str, Any]:
    """Smoke-test a provider config with a tiny chat call."""
    from langchain_core.messages import HumanMessage
    from security import sanitize_model_name, validate_base_url
    provider = normalize_provider(provider)
    model = sanitize_model_name(model, "")
    if base_url:
        base_url = validate_base_url(base_url)
    llm = build_chat_model(provider=provider, model=model, api_key=api_key,
                           base_url=base_url, temperature=0)
    try:
        msg = await llm.ainvoke([HumanMessage(content="Reply with exactly: ok")])
        text = msg.content if isinstance(msg.content, str) else str(msg.content)
        return {"ok": True, "provider": normalize_provider(provider),
                "model": model, "sample": text[:300]}
    except Exception as e:
        return {"ok": False, "provider": normalize_provider(provider),
                "model": model, "error": str(e)[:800]}
