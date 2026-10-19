"""
MEMORA AI — Context-Aware Retrieval 2.0 Engine (Sprint 2 / Phase 3)
Advanced multi-factor retrieval combining:
1. Dense vector semantic similarity (pgvector cosine similarity).
2. Sparse token/keyword matching (exact match & query terms).
3. Long-term utility importance score weighting.
4. Confidence calibration.
5. Calibrated recency time-decay (exponential decay with half-life; never blindly favors trivia).
6. Temporal validity evaluation (active vs expired/future).
7. Graph-assisted relationship boost (1-hop connected memories receive topological proximity score).
8. Full explainable score breakdown with zero chain-of-thought exposure.
"""
import asyncio
import logging
import math
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Set
from uuid import UUID

from app.config import settings
from app.database import get_db_pool
from app.schemas import (
    ScoredMemoryRecord,
    RetrievalMethod,
    MemoryRecord
)
from app.services.memory_retriever import default_retriever as keyword_retriever
from app.services.semantic_retriever import default_semantic_retriever as semantic_retriever

logger = logging.getLogger(__name__)

class ContextAwareRetriever:
    """
    Context-Aware Retrieval 2.0 Engine.
    Blends vector semantics, keyword lexical matching, relationship graph proximity,
    importance weighting, and asymptotic recency decay into an explainable scored record.
    """

    def compute_recency_factor(self, updated_at: Optional[datetime], now_utc: datetime) -> float:
        """
        Calibrated recency factor:
        Uses an exponential decay function S_rec = 0.5 + 0.5 * exp(- delta_t / 30_days).
        - Brand new memories score 1.0.
        - Memories 30 days old score ~0.68.
        - Long-standing memories asymptotically approach 0.50 (never zeroed out or discarded).
        """
        if not updated_at:
            return 0.85

        delta = (now_utc - updated_at).total_seconds()
        days_elapsed = max(0.0, delta / 86400.0)
        # Decay rate lambda = 1.0 / 30.0 (half-life ~20.8 days, decay constant 30 days)
        decay = math.exp(-days_elapsed / 30.0)
        return round(0.5 + 0.5 * decay, 4)

    async def retrieve(
        self,
        session_id: str,
        query: str,
        category: Optional[str] = None,
        limit: int = 5,
        include_inactive: bool = False,
        include_archived: bool = False,
        debug_scores: bool = True,
        semantic_weight: Optional[float] = None,
        keyword_weight: Optional[float] = None
    ) -> List[ScoredMemoryRecord]:
        """
        Execute Context-Aware Retrieval 2.0.
        """
        session_id = session_id.strip() if session_id else ""
        if not session_id or not query or not query.strip():
            return []

        w_sem = semantic_weight if semantic_weight is not None else settings.SEMANTIC_WEIGHT
        w_key = keyword_weight if keyword_weight is not None else settings.KEYWORD_WEIGHT
        now_utc = datetime.now(timezone.utc)

        # 1. Concurrently run Semantic and Keyword retrieval passes
        tasks = [
            semantic_retriever.retrieve(
                session_id=session_id,
                query=query,
                category=category,
                limit=limit * 2
            ),
            keyword_retriever.retrieve(
                session_id=session_id,
                query=query,
                category=category,
                limit=limit * 2
            )
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        semantic_matches: List[ScoredMemoryRecord] = []
        if isinstance(results[0], list):
            semantic_matches = results[0]
        else:
            logger.warning(f"Semantic retrieval pass encountered an issue: {results[0]}")

        keyword_matches: List[MemoryRecord] = []
        if isinstance(results[1], list):
            keyword_matches = results[1]
        else:
            logger.warning(f"Keyword retrieval pass encountered an issue: {results[1]}")

        if not semantic_matches and not keyword_matches:
            return []

        # 2. Build candidate map
        candidate_map: Dict[UUID, Dict[str, Any]] = {}

        for idx, s_item in enumerate(semantic_matches):
            candidate_map[s_item.id] = {
                "record": s_item,
                "is_semantic": True,
                "is_keyword": False,
                "sem_score": s_item.similarity_score,
                "key_score": 0.0,
                "graph_boost": 0.0,
                "connected_via": None
            }

        for idx, k_item in enumerate(keyword_matches):
            if k_item.id in candidate_map:
                candidate_map[k_item.id]["is_keyword"] = True
                candidate_map[k_item.id]["key_score"] = 1.0
            else:
                candidate_map[k_item.id] = {
                    "record": k_item,
                    "is_semantic": False,
                    "is_keyword": True,
                    "sem_score": 0.0,
                    "key_score": 1.0,
                    "graph_boost": 0.0,
                    "connected_via": None
                }

        # 3. Relationship Graph Proximity Expansion (Phase 1 Integration)
        # Find memories connected to top-scoring seeds (semantic >= 0.65 or keyword match)
        top_seed_ids = [
            cid for cid, cdata in candidate_map.items()
            if cdata["sem_score"] >= 0.60 or cdata["key_score"] >= 1.0
        ]

        pool = await get_db_pool()
        if pool is not None and top_seed_ids:
            try:
                async with pool.acquire() as conn:
                    graph_rows = await conn.fetch(
                        """
                        SELECT r.target_memory_id as connected_id, r.relationship_type, r.strength,
                               m.id as m_id, m.session_id as m_sid, m.category, m.memory_type,
                               m.memory_key, m.content, m.confidence_score, m.importance_score,
                               m.information_source, m.persistence_type, m.memory_status,
                               m.reason_for_storage, m.valid_from, m.valid_until, m.last_confirmed_at,
                               m.source_message, m.is_active, m.is_archived, m.archived_at,
                               m.access_count, m.last_accessed_at, m.created_at as m_created_at,
                               m.updated_at as m_updated_at, (m.embedding IS NOT NULL) as has_embedding
                        FROM memory_relationships r
                        JOIN memories m ON r.target_memory_id = m.id
                        WHERE r.session_id = $1 AND r.source_memory_id = ANY($2::uuid[])
                          AND r.relationship_type IN ('uses', 'belongs_to', 'applied_in', 'depends_on', 'relates_to')
                          AND ($3 = TRUE OR (m.is_active = TRUE AND m.is_archived = FALSE))
                        LIMIT 5
                        """,
                        session_id,
                        top_seed_ids[:3],
                        include_inactive
                    )

                    for gr in graph_rows:
                        conn_id = gr["connected_id"]
                        rel_type = gr["relationship_type"]
                        rel_strength = float(gr["strength"])
                        boost = round(0.12 * rel_strength, 4)

                        if conn_id in candidate_map:
                            candidate_map[conn_id]["graph_boost"] = max(candidate_map[conn_id]["graph_boost"], boost)
                            candidate_map[conn_id]["connected_via"] = rel_type
                        else:
                            # Add connected neighbor as a graph-assisted candidate
                            mem_rec = MemoryRecord(
                                id=gr["m_id"],
                                session_id=gr["m_sid"],
                                category=gr["category"],
                                memory_type=gr["memory_type"] or "general_fact",
                                memory_key=gr["memory_key"],
                                content=gr["content"],
                                confidence_score=gr["confidence_score"],
                                importance_score=float(gr["importance_score"] if gr["importance_score"] is not None else 0.70),
                                information_source=gr["information_source"] or "explicit_statement",
                                persistence_type=gr["persistence_type"] or "persistent",
                                memory_status=gr["memory_status"] or "active",
                                reason_for_storage=gr["reason_for_storage"],
                                valid_from=gr["valid_from"],
                                valid_until=gr["valid_until"],
                                last_confirmed_at=gr["last_confirmed_at"],
                                source_message=gr["source_message"],
                                is_active=gr["is_active"],
                                is_archived=bool(gr["is_archived"]),
                                archived_at=gr["archived_at"],
                                access_count=int(gr["access_count"] or 0),
                                last_accessed_at=gr["last_accessed_at"],
                                has_embedding=bool(gr["has_embedding"]),
                                created_at=gr["m_created_at"],
                                updated_at=gr["m_updated_at"]
                            )
                            candidate_map[conn_id] = {
                                "record": mem_rec,
                                "is_semantic": False,
                                "is_keyword": False,
                                "sem_score": 0.50, # baseline graph assumption
                                "key_score": 0.0,
                                "graph_boost": boost,
                                "connected_via": rel_type
                            }
            except Exception as e:
                logger.warning(f"Graph proximity expansion skipped due to query error: {e}")

        # 4. Multi-Factor Scoring & Explainability Breakdown
        scored_candidates: List[ScoredMemoryRecord] = []

        for entry in candidate_map.values():
            rec = entry["record"]
            is_sem = entry["is_semantic"]
            is_key = entry["is_keyword"]
            sem_val = entry["sem_score"]
            key_val = entry["key_score"]
            graph_b = entry["graph_boost"]
            conn_via = entry["connected_via"]

            # Filter out inactive/superseded/expired unless explicitly requested
            if not include_inactive:
                if not rec.is_active or rec.is_archived or rec.memory_status in ("superseded", "expired", "forgotten"):
                    continue
                if rec.valid_until and rec.valid_until <= now_utc:
                    continue

            conf_score = float(rec.confidence_score)
            imp_score = float(getattr(rec, "importance_score", 0.70) or 0.70)
            recency_factor = self.compute_recency_factor(rec.updated_at, now_utc)

            # Determine retrieval method & reason
            if is_sem and is_key:
                method = RetrievalMethod.HYBRID.value
                sim_pct = int(sem_val * 100)
                reason = f"Hybrid match: strong semantic concept ({sim_pct}%) with exact query keywords."
                raw_match = (w_sem * sem_val) + (w_key * 1.0)
            elif is_sem:
                method = RetrievalMethod.SEMANTIC.value
                sim_pct = int(sem_val * 100)
                reason = f"Semantic concept match ({sim_pct}%) with query meaning."
                raw_match = w_sem * sem_val
            elif is_key:
                method = RetrievalMethod.KEYWORD.value
                reason = "Exact keyword and token lexical match."
                raw_match = w_key * 0.90
            else:
                method = RetrievalMethod.GRAPH_ASSISTED.value
                reason = f"Graph-assisted retrieval linked via '{conn_via}' relationship."
                raw_match = 0.45

            if graph_b > 0 and method != RetrievalMethod.GRAPH_ASSISTED.value:
                reason += f" Graph proximity boost (+{graph_b}) via '{conn_via}' relationship."

            # Multi-factor composite calculation
            # Quality multiplier combines confidence (0.8-1.0) and importance (0.7-1.0)
            quality_multiplier = 0.70 + (0.15 * conf_score) + (0.15 * imp_score)
            # Final relevance combines raw match, graph boost, quality, and calibrated recency
            final_relevance = round(min(1.0, (raw_match + graph_b) * quality_multiplier * (0.85 + 0.15 * recency_factor)), 4)

            score_breakdown = {
                "semantic": round(sem_val, 4),
                "semantic_similarity": round(sem_val, 4),
                "keyword": round(key_val, 4),
                "keyword_match": round(key_val, 4),
                "graph_boost": round(graph_b, 4),
                "confidence": round(conf_score, 4),
                "importance": round(imp_score, 4),
                "recency": round(recency_factor, 4),
                "recency_factor": round(recency_factor, 4),
                "final_score": final_relevance
            }

            scored_item = ScoredMemoryRecord(
                id=rec.id,
                session_id=rec.session_id,
                category=rec.category,
                memory_type=getattr(rec, "memory_type", "general_fact"),
                memory_key=rec.memory_key,
                content=rec.content,
                confidence_score=conf_score,
                importance_score=imp_score,
                information_source=getattr(rec, "information_source", "explicit_statement"),
                persistence_type=getattr(rec, "persistence_type", "persistent"),
                memory_status=getattr(rec, "memory_status", "active"),
                reason_for_storage=getattr(rec, "reason_for_storage", None),
                valid_from=getattr(rec, "valid_from", None),
                valid_until=getattr(rec, "valid_until", None),
                last_confirmed_at=getattr(rec, "last_confirmed_at", None),
                source_message=rec.source_message,
                is_active=rec.is_active,
                is_archived=getattr(rec, "is_archived", False),
                created_at=rec.created_at,
                updated_at=rec.updated_at,
                retrieval_method=method,
                similarity_score=round(sem_val if sem_val > 0 else 0.85, 4),
                relevance_score=final_relevance,
                retrieval_reason=reason,
                graph_boost=graph_b,
                recency_score=recency_factor,
                score_breakdown=score_breakdown
            )
            scored_candidates.append(scored_item)

        # 5. Sort by relevance_score descending, then updated_at
        scored_candidates.sort(key=lambda x: (x.relevance_score, x.updated_at), reverse=True)
        top_results = scored_candidates[:limit]

        # 6. Asynchronously update access count and last_accessed_at in Neon DB
        if pool is not None and top_results:
            recalled_ids = [m.id for m in top_results]
            asyncio.create_task(self._touch_access_counts(pool, recalled_ids))

        logger.info(f"Context-Aware Retrieval 2.0 selected {len(top_results)} memories for session '{session_id}'.")
        return top_results

    async def _touch_access_counts(self, pool, memory_ids: List[UUID]) -> None:
        """Asynchronously increment access_count and touch last_accessed_at."""
        try:
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE memories
                    SET access_count = access_count + 1,
                        last_accessed_at = NOW()
                    WHERE id = ANY($1::uuid[])
                    """,
                    memory_ids
                )
        except Exception as e:
            logger.debug(f"Failed to update access count: {e}")

    retrieve_context_aware = retrieve

default_context_retriever = ContextAwareRetriever()
context_retriever = default_context_retriever

async def retrieve_context_aware_memories(
    session_id: str,
    query: str,
    category: Optional[str] = None,
    limit: int = 5,
    include_inactive: bool = False,
    include_archived: bool = False,
    debug_scores: bool = True
) -> List[ScoredMemoryRecord]:
    """Helper entry point for Context-Aware Retrieval 2.0."""
    return await default_context_retriever.retrieve(
        session_id=session_id,
        query=query,
        category=category,
        limit=limit,
        include_inactive=include_inactive,
        include_archived=include_archived,
        debug_scores=debug_scores
    )
