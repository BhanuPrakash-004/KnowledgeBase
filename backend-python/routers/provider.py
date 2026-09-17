# routers/provider.py
"""BYOK toggle API: inspect / switch / smoke-test the active LLM + embeddings."""
import logging

from fastapi import APIRouter, HTTPException

from models import ProviderTestRequest, ProviderUpdate
from providers import (SUPPORTED_PROVIDERS, build_embeddings, get_active_provider_config,
                       normalize_provider, test_llm_connection, update_active_provider_config)
from state import app_store

log = logging.getLogger("knowledgebase.provider")
router = APIRouter()


@router.get("/api/providers")
async def list_providers():
    """Catalogue for the frontend toggle (no secrets)."""
    cfg = get_active_provider_config()
    return {"active": {k: v for k, v in cfg.items() if k != "supported_providers"},
            "providers": cfg["supported_providers"]}


@router.get("/api/provider")
async def get_provider():
    cfg = get_active_provider_config()
    cfg.pop("supported_providers", None)
    return cfg


@router.put("/api/provider")
async def set_provider(update: ProviderUpdate):
    """Switch provider/model/keys at runtime and hot-reload the LLM + embeddings.

    Notes:
    - Keys are stored in provider_config.json (local file, git-ignored).
      Send "" to clear a stored key.
    - Changing the EMBEDDING model after documents are indexed will cause a
      dimension mismatch on next upload — the upload endpoint errors clearly.
      Delete vector_store.faiss/ to start a fresh index with the new model.
    """
    data = update.model_dump(exclude_unset=True)
    from security import sanitize_model_name, validate_base_url
    for f in ("llm_base_url", "embedding_base_url"):
        if data.get(f):
            try:
                data[f] = validate_base_url(data[f])
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Invalid {f}: {e}")
    for f in ("llm_model", "embedding_model"):
        if data.get(f):
            try:
                data[f] = sanitize_model_name(data[f], "")
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Invalid {f}: {e}")
    if "llm_provider" in data and data["llm_provider"] is not None:
        p = normalize_provider(data["llm_provider"])
        if p not in SUPPORTED_PROVIDERS:
            raise HTTPException(status_code=400,
                                detail=f"Unknown provider '{data['llm_provider']}'. Options: {sorted(SUPPORTED_PROVIDERS)}")
        data["llm_provider"] = p
        if SUPPORTED_PROVIDERS[p]["needs_key"] and not (data.get("llm_api_key") or get_active_provider_config()["has_llm_key"]):
            # allow switching first, testing later — just warn via response
            pass
    if "embedding_provider" in data and data["embedding_provider"] is not None:
        p = normalize_provider(data["embedding_provider"])
        if p not in ("ollama", "openai", "google", "groq", "mistral", "openrouter", "openai_compatible"):
            raise HTTPException(status_code=400, detail=f"Unsupported embedding provider '{p}'.")
        if p == "anthropic":
            raise HTTPException(status_code=400, detail="Anthropic has no embeddings API — use ollama/openai/google.")
        data["embedding_provider"] = p

    cfg = update_active_provider_config(**{k: v for k, v in data.items()
                                           if k in ("llm_provider", "llm_model", "llm_api_key", "llm_base_url",
                                                    "embedding_provider", "embedding_model",
                                                    "embedding_api_key", "embedding_base_url")})
    # Hot-reload: rebuild handles so subsequent requests use the new config.
    errors: dict = {}
    import providers as _pv
    from config import settings as _s
    saved = _pv._read_json_config()

    def _secret(which):
        v = saved.get(which, None)
        return v if v is not None else ""

    try:
        from providers import _resolve_secret
        app_store["llm"] = _pv.build_chat_model(
            provider=cfg["llm_provider"], model=cfg["llm_model"],
            api_key=_resolve_secret(saved.get("llm_api_key", None), _s.LLM_API_KEY),
            base_url=saved.get("llm_base_url") or _s.LLM_BASE_URL,
            temperature=_s.LLM_TEMPERATURE)
    except Exception as e:
        app_store["llm"] = None
        errors["llm"] = str(e)[:500]
        log.warning("LLM reload failed: %s", e)
    try:
        app_store["embeddings"] = build_embeddings(
            provider=cfg["embedding_provider"], model=cfg["embedding_model"],
            api_key=_resolve_secret(saved.get("embedding_api_key", None), _s.EMBEDDING_API_KEY),
            base_url=saved.get("embedding_base_url") or _s.EMBEDDING_BASE_URL)
    except Exception as e:
        # Keep old embeddings if the new ones fail (index compatibility).
        errors["embeddings"] = str(e)[:500]
        log.warning("Embeddings reload failed (kept previous): %s", e)

    out = dict(cfg)
    out.pop("supported_providers", None)
    if errors:
        out["warnings"] = errors
    return out


@router.post("/api/provider/test")
async def test_provider(req: ProviderTestRequest):
    """Smoke-test any provider+model+key without changing global config."""
    from security import sanitize_model_name, validate_base_url
    provider = normalize_provider(req.provider)
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown provider '{req.provider}'.")
    try:
        if req.base_url:
            validate_base_url(req.base_url)
        sanitize_model_name(req.model, "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        result = await test_llm_connection(provider, req.model, req.api_key or "", req.base_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not result.get("ok"):
        raise HTTPException(status_code=502, detail=result.get("error", "Connection failed"))
    return result
