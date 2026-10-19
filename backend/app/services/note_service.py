"""
MEMORA AI — Dedicated Persistent Note Storage Service
Provides session-isolated CRUD operations for persistent user notes in Neon PostgreSQL.
"""
import logging
from typing import List, Optional, Dict, Any
from uuid import UUID
import asyncpg
from app.database import get_db_pool

logger = logging.getLogger(__name__)

async def find_note_by_idempotency_key(session_id: str, idempotency_key: str) -> Optional[Dict[str, Any]]:
    """Look up an existing note by stable idempotency key for downstream reconciliation."""
    pool = await get_db_pool()
    if pool is None or not idempotency_key:
        return None
    clean_session = session_id.strip()
    clean_key = idempotency_key.strip()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, session_id, title, content, idempotency_key, created_at, updated_at
            FROM notes
            WHERE session_id = $1 AND idempotency_key = $2
            LIMIT 1
            """,
            clean_session,
            clean_key
        )
        return dict(row) if row else None

async def create_note(session_id: str, title: str, content: str, idempotency_key: Optional[str] = None) -> Dict[str, Any]:
    """
    Create a persistent note belonging to a specific session with idempotency key support.
    Guarantees parameterized SQL insertion and strict session isolation.
    """
    pool = await get_db_pool()
    if pool is None:
        raise RuntimeError("Database pool is unavailable.")

    clean_session = session_id.strip()
    clean_title = title.strip()
    clean_content = content.strip()

    # If idempotency key provided, check for previous execution match
    if idempotency_key:
        existing = await find_note_by_idempotency_key(clean_session, idempotency_key)
        if existing:
            logger.info(f"Idempotent match via idempotency_key '{idempotency_key}' for session '{clean_session}'.")
            return existing

    async with pool.acquire() as conn:
        # Atomic insert with ON CONFLICT DO NOTHING to prevent duplicate race conditions
        row = await conn.fetchrow(
            """
            INSERT INTO notes (session_id, title, content, idempotency_key)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (session_id, md5(title), md5(content)) DO NOTHING
            RETURNING id, session_id, title, content, idempotency_key, created_at, updated_at
            """,
            clean_session,
            clean_title,
            clean_content,
            idempotency_key
        )
        if row:
            logger.info(f"Created persistent note '{row['id']}' for session '{clean_session}'.")
            return dict(row)

        # If row is None, ON CONFLICT triggered because the note already exists; retrieve existing
        existing = await conn.fetchrow(
            """
            SELECT id, session_id, title, content, idempotency_key, created_at, updated_at
            FROM notes
            WHERE session_id = $1 AND title = $2 AND content = $3
            ORDER BY created_at ASC
            LIMIT 1
            """,
            clean_session,
            clean_title,
            clean_content,
        )
        if existing:
            logger.info(f"Idempotent match: note already exists for session '{clean_session}'.")
            return dict(existing)
        raise RuntimeError("Failed to create or retrieve persistent note.")

async def get_note(session_id: str, note_id: UUID) -> Optional[Dict[str, Any]]:
    """Retrieve a note by ID, strictly enforcing session isolation."""
    pool = await get_db_pool()
    if pool is None:
        raise RuntimeError("Database pool is unavailable.")

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, session_id, title, content, created_at, updated_at
            FROM notes
            WHERE id = $1 AND session_id = $2
            """,
            note_id,
            session_id.strip(),
        )
        return dict(row) if row else None

async def list_notes(session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """List all notes belonging to the current session."""
    pool = await get_db_pool()
    if pool is None:
        raise RuntimeError("Database pool is unavailable.")

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, session_id, title, content, created_at, updated_at
            FROM notes
            WHERE session_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            session_id.strip(),
            limit,
        )
        return [dict(r) for r in rows]

async def delete_note(session_id: str, note_id: UUID) -> bool:
    """Delete a note within the owning session."""
    pool = await get_db_pool()
    if pool is None:
        raise RuntimeError("Database pool is unavailable.")

    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            DELETE FROM notes
            WHERE id = $1 AND session_id = $2
            """,
            note_id,
            session_id.strip(),
        )
        return result.endswith("1")

async def delete_all_notes(session_id: str) -> int:
    """Clear all notes for a specific session."""
    pool = await get_db_pool()
    if pool is None:
        raise RuntimeError("Database pool is unavailable.")

    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM notes WHERE session_id = $1",
            session_id.strip(),
        )
        try:
            return int(result.split()[-1])
        except (ValueError, IndexError):
            return 0
