# security.py
"""Backend hardening helpers: SSRF guard, file checks, rate limiting, IDs.

Stdlib only — no new dependencies.
"""
import ipaddress
import os
import re
import threading
import time
import uuid
from collections import defaultdict, deque
from typing import Deque, Dict, Tuple
from urllib.parse import urlparse

_SESSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-:]{0,127}$")

# Cloud metadata + loopback-trick addresses that must never be a BYOK target.
_BLOCKED_HOSTS = {"169.254.169.254", "0.0.0.0", "::", "0000::1"}
_BLOCKED_NETS = [ipaddress.ip_network("169.254.0.0/16")]


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


def validate_session_id(sid: str) -> str:
    sid = (sid or "").strip()
    if not sid or len(sid) > 128 or not _SESSION_RE.match(sid):
        raise ValueError("Invalid session_id (use letters/numbers/.-_:, max 128).")
    return sid


def validate_base_url(base_url: str | None, *, allow_private: bool = True) -> str | None:
    """SSRF guard for user-supplied provider base URLs.

    - Requires http(s) scheme, no credentials in URL.
    - Blocks cloud metadata IP 169.254.169.254 (exact + resolved literals).
    - Private LAN (localhost/10/8, 192.168/16, 172.16/12) is ALLOWED by default
      because local gateways (Ollama, LM Studio, vLLM) legitimately live there.
      Pass allow_private=False to force public-only.
    """
    if not base_url:
        return None
    url = base_url.strip()
    if len(url) > 500:
        raise ValueError("base_url too long.")
    try:
        p = urlparse(url)
    except Exception:
        raise ValueError("base_url is not a valid URL.")
    if p.scheme not in ("http", "https"):
        raise ValueError("base_url must start with http:// or https://")
    if p.username or p.password or "@" in (p.netloc or ""):
        raise ValueError("base_url must not contain credentials.")
    host = (p.hostname or "").lower()
    if not host:
        raise ValueError("base_url needs a host.")
    if host in _BLOCKED_HOSTS:
        raise ValueError("base_url host is blocked.")
    # Literal-IP checks (DNS resolution intentionally NOT performed here to keep
    # this dependency-free; exact metadata net is still blocked).
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
        for net in _BLOCKED_NETS:
            if ip in net:
                raise ValueError("base_url resolves to blocked link-local range.")
        if not allow_private and (ip.is_private or ip.is_loopback):
            raise ValueError("base_url must be a public address.")
    except ValueError as e:
        if "blocked" in str(e).lower() or "public" in str(e).lower():
            raise
        # not an IP literal — hostname, fine
    return url.rstrip("/")


def sanitize_model_name(model: str | None, default: str = "") -> str:
    m = (model or default or "").strip()
    if len(m) > 128:
        raise ValueError("model name too long (max 128).")
    if m and not re.match(r"^[\w][\w.:/\-@+]{0,127}$", m):
        raise ValueError("model name contains invalid characters.")
    return m


def check_file_magic(content: bytes, filename: str) -> None:
    """Best-effort content-vs-extension check. Raises 400 on clear mismatch."""
    from fastapi import HTTPException
    if not content or len(content) < 8:
        return
    ext = os.path.splitext(filename)[1].lower()
    head = content[:8]
    if ext == ".pdf" and not content[:5] == b"%PDF-":
        raise HTTPException(status_code=400, detail=f"'{filename}' has .pdf extension but is not a PDF file.")
    if ext == ".docx" and not head[:2] == b"PK":
        raise HTTPException(status_code=400, detail=f"'{filename}' has .docx extension but is not a valid DOCX (zip) file.")
    if ext in (".png",) and not head.startswith(b"\x89PNG"):
        raise HTTPException(status_code=400, detail=f"'{filename}' is not a valid PNG file.")
    if ext in (".jpg", ".jpeg") and not head.startswith(b"\xff\xd8\xff"):
        raise HTTPException(status_code=400, detail=f"'{filename}' is not a valid JPEG file.")


def chmod_private(path: str) -> None:
    try:
        if os.name == "posix":
            os.chmod(path, 0o600)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Tiny in-memory sliding-window rate limiter (per IP + bucket, process-local)
# ---------------------------------------------------------------------------
_hits: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)
_rl_lock = threading.Lock()


def check_rate_limit(ip: str, bucket: str, max_hits: int, window_s: int = 60) -> bool:
    """Return True if allowed; False if over limit."""
    now = time.monotonic()
    key = (ip or "unknown", bucket)
    with _rl_lock:
        q = _hits[key]
        while q and now - q[0] > window_s:
            q.popleft()
        if len(q) >= max_hits:
            return False
        q.append(now)
        # bound memory: drop idle buckets occasionally
        if len(_hits) > 5000:
            _hits.clear()
        return True
