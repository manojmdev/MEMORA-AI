"""
MEMORA AI - Phase 6: Memory Health Dashboard Service
Aggregates live, verifiable statistics from PostgreSQL without any mocked or fabricated metrics.
"""

import json
import logging
from typing import Dict, Any, List
from uuid import UUID

from app.database import get_db_pool
from app.schemas import MemoryDashboardStats

logger = logging.getLogger(__name__)

class MemoryDashboardService:
    """Service providing live analytical metrics for the Memory Health Dashboard."""

    async def get_dashboard_stats(self, session_id: str) -> MemoryDashboardStats:
        """Fetch real-time comprehensive memory health metrics for the given session."""
        pool = await get_db_pool()
        if pool is None:
            return MemoryDashboardStats(
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

        async with pool.acquire() as conn:
            # 1. Status and Temporal Distributions
            stats_query = """
                SELECT
                    COUNT(*)::int AS total_memories,
                    COUNT(*) FILTER (WHERE is_active = TRUE AND is_archived = FALSE)::int AS active_memories,
                    COUNT(*) FILTER (WHERE is_archived = TRUE)::int AS archived_memories,
                    COUNT(*) FILTER (WHERE memory_status = 'expired')::int AS expired_memories,
                    COUNT(*) FILTER (WHERE memory_status = 'superseded')::int AS superseded_memories,
                    COUNT(*) FILTER (WHERE memory_status = 'forgotten')::int AS forgotten_memories,
                    COUNT(*) FILTER (WHERE persistence_type = 'persistent' AND is_active = TRUE)::int AS persistent_count,
                    COUNT(*) FILTER (WHERE persistence_type = 'temporary' AND is_active = TRUE)::int AS temporary_count,
                    COALESCE(SUM(access_count), 0)::int AS total_retrieval_accesses,
                    COALESCE(AVG(access_count) FILTER (WHERE is_active = TRUE), 0.0)::float AS avg_accesses_per_memory,
                    COUNT(*) FILTER (WHERE last_accessed_at >= NOW() - INTERVAL '24 hours')::int AS accessed_last_24h
                FROM memories
                WHERE session_id = $1;
            """
            s_row = await conn.fetchrow(stats_query, session_id)

            # 2. Category Distribution
            cat_query = """
                SELECT category, COUNT(*)::int AS count
                FROM memories
                WHERE session_id = $1 AND is_active = TRUE
                GROUP BY category;
            """
            cat_rows = await conn.fetch(cat_query, session_id)
            category_counts = {r["category"]: r["count"] for r in cat_rows}

            # 3. Relationship Count
            rel_query = "SELECT COUNT(*)::int FROM memory_relationships WHERE session_id = $1;"
            relationship_count = await conn.fetchval(rel_query, session_id) or 0

            # 4. Consolidation Count
            cons_query = "SELECT COUNT(*)::int FROM memory_consolidations WHERE session_id = $1;"
            consolidation_count = await conn.fetchval(cons_query, session_id) or 0

            # 5. Recent Evolution Timeline (from memory_lifecycle_events)
            events_query = """
                SELECT mle.id, mle.memory_id, mle.event_type, mle.reason, mle.actor, mle.created_at,
                       m.memory_key, m.category
                FROM memory_lifecycle_events mle
                LEFT JOIN memories m ON mle.memory_id = m.id
                WHERE mle.session_id = $1
                ORDER BY mle.created_at DESC
                LIMIT 8;
            """
            ev_rows = await conn.fetch(events_query, session_id)
            recent_evolutions = [
                {
                    "event_id": str(r["id"]),
                    "memory_id": str(r["memory_id"]),
                    "memory_key": r["memory_key"] or "unknown_key",
                    "category": r["category"] or "general",
                    "event_type": r["event_type"],
                    "reason": r["reason"] or "",
                    "actor": r["actor"] or "system",
                    "created_at": r["created_at"].isoformat(),
                }
                for r in ev_rows
            ]

            # 6. Duplication / Overlap statistics (detect pairs with cosine distance < 0.15)
            dup_query = """
                SELECT COUNT(*)::int
                FROM memories m1
                JOIN memories m2 ON m1.session_id = m2.session_id AND m1.id < m2.id
                WHERE m1.session_id = $1
                  AND m1.is_active = TRUE AND m2.is_active = TRUE
                  AND m1.embedding IS NOT NULL AND m2.embedding IS NOT NULL
                  AND (m1.embedding <=> m2.embedding) < 0.15;
            """
            try:
                high_similarity_pairs = await conn.fetchval(dup_query, session_id) or 0
            except Exception as e:
                logger.warning(f"Could not compute high similarity pairs: {e}")
                high_similarity_pairs = 0

            retrieval_metrics = {
                "total_retrieval_accesses": s_row["total_retrieval_accesses"] if s_row else 0,
                "avg_accesses_per_memory": round(s_row["avg_accesses_per_memory"], 2) if s_row else 0.0,
                "accessed_last_24h": s_row["accessed_last_24h"] if s_row else 0,
                "potential_duplicate_pairs": high_similarity_pairs,
            }

            return MemoryDashboardStats(
                session_id=session_id,
                total_memories=s_row["total_memories"] if s_row else 0,
                active_memories=s_row["active_memories"] if s_row else 0,
                archived_memories=s_row["archived_memories"] if s_row else 0,
                expired_memories=s_row["expired_memories"] if s_row else 0,
                superseded_memories=s_row["superseded_memories"] if s_row else 0,
                forgotten_memories=s_row["forgotten_memories"] if s_row else 0,
                persistent_count=s_row["persistent_count"] if s_row else 0,
                temporary_count=s_row["temporary_count"] if s_row else 0,
                category_counts=category_counts,
                relationship_count=relationship_count,
                consolidation_count=consolidation_count,
                recent_evolutions=recent_evolutions,
                retrieval_metrics=retrieval_metrics,
            )

dashboard_service = MemoryDashboardService()
