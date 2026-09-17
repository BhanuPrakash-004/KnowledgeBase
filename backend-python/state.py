# state.py
"""Global application state (process-local handles; chat history is in SQLite)."""
import asyncio

app_store = {}

# Serialises FAISS read-modify-write cycles (upload/delete) to avoid corruption.
faiss_lock = asyncio.Lock()
