"""
MEMORA AI - Phase 4: Memory Lifecycle Management Service
Handles memory expiration, archival, user-requested forgetting (with immediate deactivation
and embedding nullification), restoration, superseding, and lifecycle governance audit logging.
"""

import json
import logging
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime

from app.database import get_db_pool
from app.schemas import (
    MemoryRecord,
    LifecycleEventType,
    MemoryLifecycleEventRecord,
    MemoryLifecycleStats,
    RelationshipType,
)
from app.services.memory_service import memory_service

logger = logging.getLogger(__name__)

class MemoryLifecycleService:
    """Service managing memory state transitions, retention, forgetting, and lifecycle audits."""

    async def record_lifecycle_event(
        self,
        session_id: str,
        memory_id: UUID,
        event_type: LifecycleEventType | str,
        reason: Optional[str] = None,
        actor: str = "user",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[UUID]:
        """Record an immutable lifecycle audit event."""
        pool = await get_db_pool()
        if pool is None:
            return None

        event_str = event_type.value if hasattr(event_type, "value") else str(event_type)
        metadata_json = json.dumps(metadata or {})

        query = """
            INSERT INTO memory_lifecycle_events (
                session_id, memory_id, event_type, reason, actor, metadata_json, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, NOW())
            RETURNING id;
        """
        async with pool.acquire() as conn:
            try:
                row = await conn.fetchrow(
                    query, session_id, memory_id, event_str, reason, actor, metadata_json
                )
                return row["id"] if row else None
            except Exception as e:
                logger.error(f"Failed to record memory lifecycle event for memory {memory_id}: {e}")
                return None

    async def archive_memory(
        self,
        session_id: str,
        memory_id: UUID,
        reason: str = "Archived by user",
        actor: str = "user",
    ) -> Optional[MemoryRecord]:
        """
        Archive a memory. Archived memories remain preserved but are excluded
        from default active retrieval unless explicitly requested.
        """
        pool = await get_db_pool()
        if pool is None:
            return None

        query = """
            UPDATE memories
            SET is_archived = TRUE,
                archived_at = NOW(),
                updated_at = NOW()
            WHERE id = $1 AND session_id = $2
            RETURNING *;
        """
        async with pool.acquire() as conn:
            row = await conn.fetchrow(query, memory_id, session_id)
            if not row:
                return None

            record = memory_service.record_from_row(row)
            await self.record_lifecycle_event(
                session_id=session_id,
                memory_id=memory_id,
                event_type=LifecycleEventType.ARCHIVED,
                reason=reason,
                actor=actor,
                metadata={"memory_key": record.memory_key, "category": record.category},
            )
            return record

    async def restore_memory(
        self,
        session_id: str,
        memory_id: UUID,
        reason: str = "Restored by user",
        actor: str = "user",
    ) -> Optional[MemoryRecord]:
        """Restore an archived memory back into active retrieval."""
        pool = await get_db_pool()
        if pool is None:
            return None

        query = """
            UPDATE memories
            SET is_archived = FALSE,
                archived_at = NULL,
                updated_at = NOW()
            WHERE id = $1 AND session_id = $2
            RETURNING *;
        """
        async with pool.acquire() as conn:
            row = await conn.fetchrow(query, memory_id, session_id)
            if not row:
                return None

            record = memory_service.record_from_row(row)
            await self.record_lifecycle_event(
                session_id=session_id,
                memory_id=memory_id,
                event_type=LifecycleEventType.RESTORED,
                reason=reason,
                actor=actor,
                metadata={"memory_key": record.memory_key, "category": record.category},
            )
            return record

    async def forget_memory(
        self,
        session_id: str,
        memory_id: UUID,
        reason: str = "User requested forgetting",
        actor: str = "user",
    ) -> bool:
        """
        Immediately removes memory from active retrieval and completely nullifies
        its embedding vector to ensure zero semantic leakage, while retaining the minimal
        audit lifecycle record required for regulatory governance.
        """
        pool = await get_db_pool()
        if pool is None:
            return False

        query = """
            UPDATE memories
            SET is_active = FALSE,
                memory_status = 'forgotten',
                embedding = NULL,
                updated_at = NOW()
            WHERE id = $1 AND session_id = $2
            RETURNING id, memory_key, category;
        """
        async with pool.acquire() as conn:
            row = await conn.fetchrow(query, memory_id, session_id)
            if not row:
                return False

            # Delete any dangling relationship edges to this forgotten memory
            rel_query = """
                DELETE FROM memory_relationships
                WHERE session_id = $1 AND (source_memory_id = $2 OR target_memory_id = $2);
            """
            await conn.execute(rel_query, session_id, memory_id)

            await self.record_lifecycle_event(
                session_id=session_id,
                memory_id=memory_id,
                event_type=LifecycleEventType.FORGOTTEN,
                reason=reason,
                actor=actor,
                metadata={"memory_key": row["memory_key"], "category": row["category"]},
            )
            logger.info(f"Memory {memory_id} successfully forgotten and embedding vector cleared.")
            return True

    async def supersede_memory(
        self,
        session_id: str,
        old_memory_id: UUID,
        new_memory_id: UUID,
        reason: str = "Superseded by newer memory evolution",
    ) -> bool:
        """
        Mark old memory as superseded and link it with a SUPERSEDES relationship
        from the new memory.
        """
        pool = await get_db_pool()
        if pool is None:
            return False

        async with pool.acquire() as conn:
            async with conn.transaction():
                # 1. Update old memory
                old_row = await conn.fetchrow(
                    """
                    UPDATE memories
                    SET is_active = FALSE,
                        memory_status = 'superseded',
                        updated_at = NOW()
                    WHERE id = $1 AND session_id = $2
                    RETURNING memory_key;
                    """,
                    old_memory_id,
                    session_id,
                )
                if not old_row:
                    return False

                # 2. Create relationship edge: new_memory supersedes old_memory
                await conn.execute(
                    """
                    INSERT INTO memory_relationships (
                        session_id, source_memory_id, target_memory_id, relationship_type, strength, metadata_json, created_at
                    ) VALUES ($1, $2, $3, $4, 1.0, $5::jsonb, NOW())
                    ON CONFLICT (session_id, source_memory_id, target_memory_id, relationship_type) DO NOTHING;
                    """,
                    session_id,
                    new_memory_id,
                    old_memory_id,
                    RelationshipType.SUPERSEDES.value,
                    json.dumps({"reason": reason}),
                )

                # 3. Record lifecycle events
                await conn.execute(
                    """
                    INSERT INTO memory_lifecycle_events (
                        session_id, memory_id, event_type, reason, actor, metadata_json, created_at
                    ) VALUES ($1, $2, 'superseded', $3, 'system', $4::jsonb, NOW());
                    """,
                    session_id,
                    old_memory_id,
                    reason,
                    json.dumps({"superseded_by": str(new_memory_id)}),
                )

            return True

    async def check_and_expire_retention(self, session_id: str) -> List[UUID]:
        """
        Scan and transition memories whose temporal validity has elapsed into 'expired' status.
        Does not delete memories, but deactivates them from active retrieval.
        """
        pool = await get_db_pool()
        if pool is None:
            return []

        query = """
            UPDATE memories
            SET is_active = FALSE,
                memory_status = 'expired',
                updated_at = NOW()
            WHERE session_id = $1 
              AND is_active = TRUE 
              AND valid_until IS NOT NULL 
              AND valid_until < NOW() 
              AND memory_status != 'expired'
            RETURNING id, memory_key;
        """
        expired_ids = []
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, session_id)
            for r in rows:
                mid = r["id"]
                expired_ids.append(mid)
                await self.record_lifecycle_event(
                    session_id=session_id,
                    memory_id=mid,
                    event_type=LifecycleEventType.EXPIRED,
                    reason="Temporal TTL expiration timestamp passed",
                    actor="system",
                    metadata={"memory_key": r["memory_key"]},
                )

        if expired_ids:
            logger.info(f"Expired {len(expired_ids)} memories for session {session_id} based on retention TTL.")
        return expired_ids

    async def get_lifecycle_history(
        self,
        session_id: str,
        memory_id: Optional[UUID] = None,
        limit: int = 50,
    ) -> List[MemoryLifecycleEventRecord]:
        """Retrieve the governance audit trail of lifecycle events."""
        pool = await get_db_pool()
        if pool is None:
            return []

        if memory_id:
            query = """
                SELECT * FROM memory_lifecycle_events
                WHERE session_id = $1 AND memory_id = $2
                ORDER BY created_at DESC
                LIMIT $3;
            """
            params = [session_id, memory_id, limit]
        else:
            query = """
                SELECT * FROM memory_lifecycle_events
                WHERE session_id = $1
                ORDER BY created_at DESC
                LIMIT $2;
            """
            params = [session_id, limit]

        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            events = []
            for r in rows:
                meta = r["metadata_json"]
                if isinstance(meta, str):
                    try:
                        meta = json.loads(meta)
                    except Exception:
                        meta = {}
                elif meta is None:
                    meta = {}

                events.append(
                    MemoryLifecycleEventRecord(
                        id=r["id"],
                        session_id=r["session_id"],
                        memory_id=r["memory_id"],
                        event_type=r["event_type"],
                        reason=r["reason"],
                        actor=r["actor"] or "user",
                        metadata=meta,
                        created_at=r["created_at"],
                    )
                )
            return events

    async def get_lifecycle_stats(self, session_id: str) -> MemoryLifecycleStats:
        """Calculate live aggregated lifecycle stats for a session."""
        pool = await get_db_pool()
        if pool is None:
            return MemoryLifecycleStats(
                session_id=session_id,
                total_memories=0,
                active_memories=0,
                archived_memories=0,
                expired_memories=0,
                superseded_memories=0,
                forgotten_memories=0,
                persistent_count=0,
                temporary_count=0,
            )

        query = """
            SELECT
                COUNT(*)::int AS total_memories,
                COUNT(*) FILTER (WHERE is_active = TRUE AND is_archived = FALSE)::int AS active_memories,
                COUNT(*) FILTER (WHERE is_archived = TRUE)::int AS archived_memories,
                COUNT(*) FILTER (WHERE memory_status = 'expired')::int AS expired_memories,
                COUNT(*) FILTER (WHERE memory_status = 'superseded')::int AS superseded_memories,
                COUNT(*) FILTER (WHERE memory_status = 'forgotten')::int AS forgotten_memories,
                COUNT(*) FILTER (WHERE persistence_type = 'persistent' AND is_active = TRUE)::int AS persistent_count,
                COUNT(*) FILTER (WHERE persistence_type = 'temporary' AND is_active = TRUE)::int AS temporary_count
            FROM memories
            WHERE session_id = $1;
        """
        async with pool.acquire() as conn:
            row = await conn.fetchrow(query, session_id)
            return MemoryLifecycleStats(
                session_id=session_id,
                total_memories=row["total_memories"] or 0,
                active_memories=row["active_memories"] or 0,
                archived_memories=row["archived_memories"] or 0,
                expired_memories=row["expired_memories"] or 0,
                superseded_memories=row["superseded_memories"] or 0,
                forgotten_memories=row["forgotten_memories"] or 0,
                persistent_count=row["persistent_count"] or 0,
                temporary_count=row["temporary_count"] or 0,
            )

lifecycle_service = MemoryLifecycleService()
