import asyncio
import logging
import uuid
import zlib
from typing import List, Optional
from uuid import UUID
import asyncpg
from app.database import get_db_pool
from app.schemas import (
    MemoryCandidate,
    MemoryRecord,
    MemoryType,
    InformationSource,
    PersistenceType,
    MemoryStatus
)
from app.services.embedding_service import generate_embedding, vector_to_sql_str

logger = logging.getLogger(__name__)

def record_from_row(row: asyncpg.Record) -> MemoryRecord:
    """Convert an asyncpg database record into a validated Pydantic MemoryRecord."""
    has_emb = False
    if "embedding" in row:
        has_emb = row["embedding"] is not None

    return MemoryRecord(
        id=row["id"],
        session_id=row["session_id"],
        category=row["category"],
        memory_type=row.get("memory_type") or MemoryType.GENERAL_FACT.value,
        memory_key=row["memory_key"],
        content=row["content"],
        confidence_score=row["confidence_score"],
        importance_score=float(row.get("importance_score") if row.get("importance_score") is not None else 0.70),
        information_source=row.get("information_source") or InformationSource.EXPLICIT_STATEMENT.value,
        persistence_type=row.get("persistence_type") or PersistenceType.PERSISTENT.value,
        memory_status=row.get("memory_status") or MemoryStatus.ACTIVE.value,
        reason_for_storage=row.get("reason_for_storage"),
        valid_from=row.get("valid_from"),
        valid_until=row.get("valid_until"),
        last_confirmed_at=row.get("last_confirmed_at"),
        superseded_by=row.get("superseded_by"),
        superseded_reason=row.get("superseded_reason"),
        source_message=row["source_message"],
        is_active=row["is_active"],
        is_archived=bool(row.get("is_archived", False)),
        archived_at=row.get("archived_at"),
        access_count=int(row.get("access_count") or 0),
        last_accessed_at=row.get("last_accessed_at"),
        has_embedding=has_emb,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )

async def _add_memory_tx(
    session_id: str,
    candidate: MemoryCandidate,
    pool: asyncpg.Pool,
    vector_sql: Optional[str] = None
) -> MemoryRecord:
    """Internal transaction execution for adding or evolving a memory with its embedding."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Automatically expire past-due temporary memories for this session
            await conn.execute(
                """
                UPDATE memories
                SET is_active = FALSE, memory_status = 'expired', updated_at = NOW()
                WHERE session_id = $1 AND is_active = TRUE AND valid_until IS NOT NULL AND valid_until <= NOW()
                """,
                session_id,
            )

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

            new_id = uuid.uuid4()

            if existing:
                existing_content = existing["content"].strip().lower()
                new_content = candidate.content.strip().lower()

                # Deduplication: equivalent fact
                if existing_content == new_content:
                    higher_confidence = max(existing["confidence_score"], candidate.confidence_score)
                    higher_importance = max(
                        float(existing["importance_score"] if existing["importance_score"] is not None else 0.70),
                        candidate.importance_score
                    )
                    updated_row = await conn.fetchrow(
                        """
                        UPDATE memories 
                        SET confidence_score = $1, 
                            importance_score = $2,
                            source_message = COALESCE($3, source_message),
                            embedding = COALESCE(embedding, $4::vector),
                            last_confirmed_at = NOW(),
                            updated_at = NOW()
                        WHERE id = $5
                        RETURNING *
                        """,
                        higher_confidence,
                        higher_importance,
                        candidate.source_message,
                        vector_sql,
                        existing["id"],
                    )
                    try:
                        await conn.execute(
                            """
                            INSERT INTO memory_lifecycle_events (session_id, memory_id, event_type, reason, actor)
                            VALUES ($1, $2, 'confirmed', 'Memory reinforced and confirmed by subsequent statement.', 'system')
                            """,
                            session_id,
                            existing["id"],
                        )
                    except Exception:
                        pass
                    logger.info(f"Deduplicated existing memory key '{candidate.memory_key}' for session '{session_id}'.")
                    return record_from_row(updated_row)

                # Evolution/Superseding: fact has changed or was corrected
                logger.info(f"Superseding memory key '{candidate.memory_key}' for session '{session_id}'.")
                superseded_reason = (
                    f"Superseded by update: {candidate.content[:120]}"
                    if candidate.information_source == InformationSource.EXPLICIT_STATEMENT.value
                    else "Superseded by new contextual observation."
                )
                await conn.execute(
                    """
                    UPDATE memories 
                    SET is_active = FALSE,
                        memory_status = 'superseded',
                        superseded_by = $1,
                        superseded_reason = $2,
                        updated_at = NOW()
                    WHERE id = $3
                    """,
                    new_id,
                    superseded_reason,
                    existing["id"],
                )
                try:
                    await conn.execute(
                        """
                        INSERT INTO memory_lifecycle_events (session_id, memory_id, event_type, reason, actor)
                        VALUES ($1, $2, 'superseded', $3, 'system')
                        """,
                        session_id,
                        existing["id"],
                        superseded_reason,
                    )
                except Exception:
                    pass

            # Insert new active memory with embedding vector and intelligence metadata
            inserted_row = await conn.fetchrow(
                """
                INSERT INTO memories (
                    id, session_id, category, memory_type, memory_key, content, 
                    confidence_score, importance_score, information_source,
                    persistence_type, memory_status, reason_for_storage,
                    valid_from, valid_until, last_confirmed_at,
                    source_message, is_active, embedding
                )
                VALUES (
                    $1, $2, $3, $4, $5, $6, 
                    $7, $8, $9, 
                    $10, $11, $12, 
                    NOW(), $13, NOW(),
                    $14, TRUE, $15::vector
                )
                RETURNING *
                """,
                new_id,
                session_id,
                candidate.category,
                candidate.memory_type,
                candidate.memory_key,
                candidate.content,
                candidate.confidence_score,
                candidate.importance_score,
                candidate.information_source,
                candidate.persistence_type,
                MemoryStatus.ACTIVE.value,
                candidate.reason_for_storage,
                candidate.valid_until,
                candidate.source_message,
                vector_sql,
            )

            try:
                await conn.execute(
                    """
                    INSERT INTO memory_lifecycle_events (session_id, memory_id, event_type, reason, actor)
                    VALUES ($1, $2, 'created', 'Initial memory extraction and storage.', 'system')
                    """,
                    session_id,
                    new_id,
                )
            except Exception:
                pass

            return record_from_row(inserted_row)

async def add_memory(session_id: str, candidate: MemoryCandidate, max_retries: int = 3) -> MemoryRecord:
    """
    Add or evolve a memory record within a session.
    - Generates vector embedding for candidate content.
    - If equivalent fact exists: updates confidence and timestamp (deduplication).
    - If conflicting/new fact exists for the key: supersedes old active memory in a transaction.
    - If new key: inserts fresh active memory with embedding vector.
    - Includes automatic retry handling for concurrent insert race conditions.
    """
    pool = await get_db_pool()
    if pool is None:
        raise RuntimeError("Database connection pool is not available.")

    session_id = session_id.strip()

    # Pre-generate embedding vector for the memory content
    vector_sql: Optional[str] = None
    try:
        emb = await generate_embedding(candidate.content)
        if emb:
            vector_sql = vector_to_sql_str(emb)
    except Exception as e:
        logger.warning(f"Could not generate embedding for memory key '{candidate.memory_key}': {e}")

    for attempt in range(max_retries):
        try:
            return await _add_memory_tx(session_id, candidate, pool, vector_sql)
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
        # If querying active memories, auto-expire any past-due temporary memories
        if is_active:
            await conn.execute(
                """
                UPDATE memories
                SET is_active = FALSE, memory_status = 'expired', updated_at = NOW()
                WHERE session_id = $1 AND is_active = TRUE AND valid_until IS NOT NULL AND valid_until <= NOW()
                """,
                session_id,
            )

        if category:
            rows = await conn.fetch(
                """
                SELECT * FROM memories 
                WHERE session_id = $1 AND category = $2 AND is_active = $3
                  AND ($3 = FALSE OR valid_until IS NULL OR valid_until > NOW())
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
                  AND ($2 = FALSE OR valid_until IS NULL OR valid_until > NOW())
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

        # Regenerate embedding if content changed
        vector_sql = None
        if content is not None and content.strip() != existing["content"].strip():
            try:
                emb = await generate_embedding(new_content)
                if emb:
                    vector_sql = vector_to_sql_str(emb)
            except Exception as e:
                logger.warning(f"Failed to regenerate embedding on memory update: {e}")

        row = await conn.fetchrow(
            """
            UPDATE memories 
            SET content = $1, 
                confidence_score = $2, 
                category = $3, 
                is_active = $4, 
                embedding = COALESCE($5::vector, embedding),
                updated_at = NOW()
            WHERE id = $6 AND session_id = $7
            RETURNING *
            """,
            new_content,
            new_confidence,
            new_category,
            new_active,
            vector_sql,
            memory_id,
            session_id.strip(),
        )
        return record_from_row(row) if row else None

async def backfill_missing_embeddings(session_id: Optional[str] = None) -> int:
    """Backfill vector embeddings for any active memories currently lacking one."""
    pool = await get_db_pool()
    if pool is None:
        return 0

    async with pool.acquire() as conn:
        if session_id:
            rows = await conn.fetch(
                "SELECT id, content FROM memories WHERE session_id = $1 AND is_active = TRUE AND embedding IS NULL",
                session_id.strip(),
            )
        else:
            rows = await conn.fetch(
                "SELECT id, content FROM memories WHERE is_active = TRUE AND embedding IS NULL"
            )

        updated_count = 0
        for r in rows:
            emb = await generate_embedding(r["content"])
            if emb:
                await conn.execute(
                    "UPDATE memories SET embedding = $1::vector, updated_at = NOW() WHERE id = $2",
                    vector_to_sql_str(emb),
                    r["id"],
                )
                updated_count += 1

        if updated_count > 0:
            logger.info(f"Backfilled {updated_count} missing memory embeddings.")
        return updated_count

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

class MemoryService:
    record_from_row = staticmethod(record_from_row)
    add_memory = staticmethod(add_memory)
    list_memories = staticmethod(list_memories)
    get_memory = staticmethod(get_memory)
    delete_memory = staticmethod(delete_memory)
    delete_all_memories = staticmethod(delete_all_memories)
    backfill_missing_embeddings = staticmethod(backfill_missing_embeddings)

memory_service = MemoryService()
