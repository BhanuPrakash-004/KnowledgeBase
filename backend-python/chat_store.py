# chat_store.py
"""Persistent chat storage backed by SQLite (stdlib only).

Replaces the previous in-memory `app_store["chat_sessions"]` dict which lost
all history on restart.

Schema:
  sessions(id TEXT PK, created_at TEXT, updated_at TEXT)
  messages(id INTEGER PK, session_id TEXT, role TEXT, content TEXT,
           sources TEXT (json), provider TEXT, model TEXT, created_at TEXT)

Thread-safe via a module-level lock + short-lived connections (WAL mode).
"""
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

_lock = threading.Lock()
_db_path: Optional[str] = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def configure(db_path: str) -> str:
    """Set DB location (resolves relative to backend dir) and init schema."""
    global _db_path
    if os.path.isabs(db_path):
        _db_path = db_path
    else:
        base = os.path.dirname(os.path.abspath(__file__))
        _db_path = os.path.join(base, db_path)
    _init()
    return _db_path


def _connect() -> sqlite3.Connection:
    assert _db_path, "chat_store.configure() must be called first"
    conn = sqlite3.connect(_db_path, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
    except Exception:
        pass
    return conn


def _init() -> None:
    with _lock:
        conn = _connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    sources TEXT DEFAULT '[]',
                    provider TEXT DEFAULT '',
                    model TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);
                """
            )
            conn.commit()
        finally:
            conn.close()


def _check_sid(session_id: str) -> str:
    try:
        from security import validate_session_id
        return validate_session_id(session_id)
    except ImportError:
        return (session_id or "").strip()


def ensure_session(session_id: str) -> None:
    session_id = _check_sid(session_id)
    now = _now()
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO sessions (id, created_at, updated_at) VALUES (?, ?, ?)",
                (session_id, now, now),
            )
            conn.execute("UPDATE sessions SET updated_at=? WHERE id=?", (now, session_id))
            conn.commit()
        finally:
            conn.close()


def save_message(session_id: str, role: str, content: str,
                 sources: Optional[List[str]] = None,
                 provider: str = "", model: str = "") -> None:
    session_id = _check_sid(session_id)
    if role not in ("human", "ai"):
        raise ValueError("role must be 'human' or 'ai'")
    content = (content or "")[:50000]
    ensure_session(session_id)
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO messages (session_id, role, content, sources, provider, model, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (session_id, role, content, json.dumps(sources or []),
                 (provider or "")[:64], (model or "")[:128], _now()),
            )
            conn.execute("UPDATE sessions SET updated_at=? WHERE id=?", (_now(), session_id))
            # Retention cap: prune oldest beyond MAX_MESSAGES_PER_SESSION.
            try:
                from config import settings as _s
                cap = int(getattr(_s, "MAX_MESSAGES_PER_SESSION", 500))
            except Exception:
                cap = 500
            if cap > 0:
                conn.execute(
                    """DELETE FROM messages WHERE session_id=? AND id NOT IN
                       (SELECT id FROM messages WHERE session_id=? ORDER BY id DESC LIMIT ?)""",
                    (session_id, session_id, cap),
                )
            conn.commit()
        finally:
            conn.close()


def get_history_messages(session_id: str, limit: int = 20) -> List[BaseMessage]:
    """Last `limit` messages as LangChain messages (oldest-first)."""
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT role, content FROM messages WHERE session_id=? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        finally:
            conn.close()
    out: List[BaseMessage] = []
    for r in reversed(rows):
        if r["role"] == "human":
            out.append(HumanMessage(content=r["content"]))
        else:
            out.append(AIMessage(content=r["content"]))
    return out


def get_session_transcript(session_id: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    session_id = _check_sid(session_id)
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT id, role, content, sources, provider, model, created_at"
                " FROM messages WHERE session_id=? ORDER BY id ASC LIMIT ? OFFSET ?",
                (session_id, limit, offset),
            ).fetchall()
        finally:
            conn.close()
    result = []
    for r in rows:
        try:
            sources = json.loads(r["sources"] or "[]")
        except Exception:
            sources = []
        result.append({"id": r["id"], "role": r["role"], "content": r["content"],
                       "sources": sources, "provider": r["provider"],
                       "model": r["model"], "created_at": r["created_at"]})
    return result


def list_sessions(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                """SELECT s.id, s.created_at, s.updated_at, COUNT(m.id) AS message_count,
                          MAX(m.content) AS last_preview
                   FROM sessions s LEFT JOIN messages m ON m.session_id = s.id
                   GROUP BY s.id ORDER BY s.updated_at DESC LIMIT ? OFFSET ?""",
                (limit, offset),
            ).fetchall()
        finally:
            conn.close()
    return [{"session_id": r["id"], "created_at": r["created_at"],
             "updated_at": r["updated_at"], "message_count": r["message_count"] or 0,
             "preview": (r["last_preview"] or "")[:160]} for r in rows]


def delete_session(session_id: str) -> bool:
    session_id = _check_sid(session_id)
    with _lock:
        conn = _connect()
        try:
            conn.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
            cur = conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def count_messages() -> int:
    with _lock:
        conn = _connect()
        try:
            row = conn.execute("SELECT COUNT(*) AS c FROM messages").fetchone()
            return int(row["c"] or 0)
        finally:
            conn.close()


def export_transcript_markdown(session_id: str, limit: int = 500) -> str:
    msgs = get_session_transcript(session_id, limit=limit)
    lines = [f"# Chat transcript — {session_id}", ""]
    for m in msgs:
        who = "You" if m["role"] == "human" else f"AI ({m['model'] or m['provider'] or 'assistant'})"
        lines.append(f"## {who} · {m['created_at']}")
        lines.append("")
        lines.append(m["content"] or "")
        if m.get("sources"):
            lines.append("")
            lines.append("Sources: " + "; ".join(m["sources"]))
        lines.append("")
    return "\n".join(lines)
