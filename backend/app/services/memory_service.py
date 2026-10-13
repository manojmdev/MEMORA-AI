import asyncio
import logging
import zlib
from typing import List, Optional
from uuid import UUID
import asyncpg
from app.database import get_db_pool
from app.schemas import MemoryCandidate, MemoryRecord

logger = logging.getLogger(__name__)

def record_from_row(row: asyncpg.Record) -> MemoryRecord:
    """Convert an asyncpg database record into a validated Pydantic MemoryRecord."""
    return MemoryRecord(
        id=row["id"],
        session_id=row["session_id"],
        category=row["category"],
        memory_key=row["memory_key"],
        content=row["content"],
        confidence_score=row["confidence_score"],
        source_message=row["source_message"],
        is_active=row["is_active"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )

async def _add_memory_tx(session_id: str, candidate: MemoryCandidate, pool: asyncpg.Pool) -> MemoryRecord:
    """Internal transaction execution for adding or evolving a memory."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Transaction-scoped advisory lock on (session_id, memory_key)
            # perfectly serializes concurrent updates for the same memory key
            lock_id = zlib.crc32(f"{session_id}:{candidate.memory_key}".encode("utf-8"))
            await conn.execute("SELECT pg_advisory_xact_lock($1)", lock_id)

            # Check for existing active memory with identical key in this session
            existing = await conn.fetchrow(
                """
                SELECT * FROM memories 
                WHERE session_id = $1 AND memory_key = $2 AND is_active = TRUE
                """,
                session_id,
                candidate.memory_key,
            )

            if existing:
                existing_content = existing["content"].strip().lower()
                new_content = candidate.content.strip().lower()

                # Deduplication: equivalent fact
                if existing_content == new_content:
                    higher_confidence = max(existing["confidence_score"], candidate.confidence_score)
                    updated_row = await conn.fetchrow(
                        """
                        UPDATE memories 
                        SET confidence_score = $1, 
                            source_message = COALESCE($2, source_message),
                            updated_at = NOW()
                        WHERE id = $3
                        RETURNING *
                        """,
                        higher_confidence,
                        candidate.source_message,
                        existing["id"],
                    )
                    logger.info(f"Deduplicated existing memory key '{candidate.memory_key}' for session '{session_id}'.")
                    return record_from_row(updated_row)

                # Evolution/Superseding: fact has changed or was corrected
                logger.info(f"Superseding memory key '{candidate.memory_key}' for session '{session_id}'.")
                await conn.execute(
                    """
                    UPDATE memories 
                    SET is_active = FALSE, updated_at = NOW()
                    WHERE id = $1
                    """,
                    existing["id"],
                )

            # Insert new active memory
            inserted_row = await conn.fetchrow(
                """
                INSERT INTO memories (session_id, category, memory_key, content, confidence_score, source_message, is_active)
                VALUES ($1, $2, $3, $4, $5, $6, TRUE)
                RETURNING *
                """,
                session_id,
                candidate.category,
                candidate.memory_key,
                candidate.content,
                candidate.confidence_score,
                candidate.source_message,
            )
            return record_from_row(inserted_row)

async def add_memory(session_id: str, candidate: MemoryCandidate, max_retries: int = 3) -> MemoryRecord:
    """
    Add or evolve a memory record within a session.
    - If equivalent fact exists: updates confidence and timestamp (deduplication).
    - If conflicting/new fact exists for the key: supersedes old active memory in a transaction.
    - If new key: inserts fresh active memory.
    - Includes automatic retry handling for concurrent insert race conditions.
    """
    pool = await get_db_pool()
    if pool is None:
        raise RuntimeError("Database connection pool is not available.")

    session_id = session_id.strip()

    for attempt in range(max_retries):
        try:
            return await _add_memory_tx(session_id, candidate, pool)
        except asyncpg.exceptions.UniqueViolationError:
            if attempt == max_retries - 1:
                logger.error(f"Concurrency resolution exceeded max retries for key '{candidate.memory_key}'.")
                raise
            await asyncio.sleep(0.04 * (attempt + 1))

async def supersede_memory(session_id: str, existing_key: str, new_candidate: MemoryCandidate) -> MemoryRecord:
    """Explicitly supersede an existing active memory with a new fact in a transaction."""
    new_candidate.memory_key = existing_key
    return await add_memory(session_id, new_candidate)

async def list_memories(
    session_id: str,
    category: Optional[str] = None,
    is_active: bool = True
) -> List[MemoryRecord]:
    """List memories belonging to a session, optionally filtered by category and active status."""
    pool = await get_db_pool()
    if pool is None:
        raise RuntimeError("Database connection pool is not available.")

    session_id = session_id.strip()

    async with pool.acquire() as conn:
        if category:
            rows = await conn.fetch(
                """
                SELECT * FROM memories 
                WHERE session_id = $1 AND category = $2 AND is_active = $3
                ORDER BY updated_at DESC
                """,
                session_id,
                category.strip().lower(),
                is_active,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT * FROM memories 
                WHERE session_id = $1 AND is_active = $2
                ORDER BY updated_at DESC
                """,
                session_id,
                is_active,
            )

        return [record_from_row(r) for r in rows]

async def get_memory(session_id: str, memory_id: UUID) -> Optional[MemoryRecord]:
    """Retrieve a single memory by ID, strictly enforcing session isolation."""
    pool = await get_db_pool()
    if pool is None:
        raise RuntimeError("Database connection pool is not available.")

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT * FROM memories 
            WHERE id = $1 AND session_id = $2
            """,
            memory_id,
            session_id.strip(),
        )
        return record_from_row(row) if row else None

async def update_memory(
    session_id: str,
    memory_id: UUID,
    content: Optional[str] = None,
    confidence_score: Optional[float] = None,
    category: Optional[str] = None,
    is_active: Optional[bool] = None
) -> Optional[MemoryRecord]:
    """Update fields on a specific memory record, enforcing session scope."""
    pool = await get_db_pool()
    if pool is None:
        raise RuntimeError("Database connection pool is not available.")

    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT * FROM memories WHERE id = $1 AND session_id = $2",
            memory_id,
            session_id.strip(),
        )
        if not existing:
            return None

        new_content = content if content is not None else existing["content"]
        new_confidence = confidence_score if confidence_score is not None else existing["confidence_score"]
        new_category = category if category is not None else existing["category"]
        new_active = is_active if is_active is not None else existing["is_active"]

        row = await conn.fetchrow(
            """
            UPDATE memories 
            SET content = $1, confidence_score = $2, category = $3, is_active = $4, updated_at = NOW()
            WHERE id = $5 AND session_id = $6
            RETURNING *
            """,
            new_content,
            new_confidence,
            new_category,
            new_active,
            memory_id,
            session_id.strip(),
        )
        return record_from_row(row) if row else None

async def delete_memory(session_id: str, memory_id: UUID) -> bool:
    """Delete a specific memory by ID within the user's session."""
    pool = await get_db_pool()
    if pool is None:
        raise RuntimeError("Database connection pool is not available.")

    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            DELETE FROM memories 
            WHERE id = $1 AND session_id = $2
            """,
            memory_id,
            session_id.strip(),
        )
        deleted = result.endswith("1")
        if deleted:
            logger.info(f"Memory {memory_id} deleted for session '{session_id}'.")
        return deleted

async def delete_all_memories(session_id: str) -> int:
    """Clear all memories associated with a given session ID."""
    pool = await get_db_pool()
    if pool is None:
        raise RuntimeError("Database connection pool is not available.")

    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            DELETE FROM memories 
            WHERE session_id = $1
            """,
            session_id.strip(),
        )
        try:
            count = int(result.split()[-1])
        except (ValueError, IndexError):
            count = 0
        logger.info(f"Deleted {count} memories for session '{session_id}'.")
        return count
