import logging
from typing import List, Optional
from app.config import settings
from app.database import get_db_pool
from app.schemas import ScoredMemoryRecord, RetrievalMethod
from app.services.embedding_service import generate_embedding, vector_to_sql_str
from app.services.memory_retriever import BaseMemoryRetriever

logger = logging.getLogger(__name__)

class SemanticMemoryRetriever(BaseMemoryRetriever):
    """
    Dedicated semantic memory retrieval service using pgvector cosine similarity.
    Guarantees strict session isolation, active-only retrieval, and parameterized execution.
    """

    async def retrieve(
        self,
        session_id: str,
        query: str,
        category: Optional[str] = None,
        limit: int = 5,
        threshold: Optional[float] = None
    ) -> List[ScoredMemoryRecord]:
        pool = await get_db_pool()
        if pool is None:
            logger.warning("Database pool is unavailable for semantic retrieval.")
            return []

        session_id = session_id.strip() if session_id else ""
        if not session_id or not query or not query.strip():
            return []

        # 1. Generate embedding for query
        query_vec = await generate_embedding(query, is_query=True)
        if not query_vec:
            logger.info("Semantic retriever: query embedding could not be generated; returning empty.")
            return []

        query_sql_vec = vector_to_sql_str(query_vec)
        min_threshold = threshold if threshold is not None else settings.SIMILARITY_THRESHOLD

        try:
            async with pool.acquire() as conn:
                # 2. Search active memory embeddings with session isolation & expiration filtering
                if category:
                    rows = await conn.fetch(
                        """
                        SELECT 
                            id, session_id, category, memory_type, memory_key, content, 
                            confidence_score, importance_score, information_source, persistence_type,
                            memory_status, reason_for_storage, valid_from, valid_until, last_confirmed_at,
                            source_message, is_active, created_at, updated_at,
                            (1.0 - (embedding <=> $1::vector)) AS similarity_score
                        FROM memories
                        WHERE session_id = $2 
                          AND is_active = TRUE 
                          AND (valid_until IS NULL OR valid_until > NOW())
                          AND embedding IS NOT NULL
                          AND category = $3
                          AND (1.0 - (embedding <=> $1::vector)) >= $4
                        ORDER BY (embedding <=> $1::vector) ASC
                        LIMIT $5
                        """,
                        query_sql_vec,
                        session_id,
                        category.strip().lower(),
                        min_threshold,
                        limit
                    )
                else:
                    rows = await conn.fetch(
                        """
                        SELECT 
                            id, session_id, category, memory_type, memory_key, content, 
                            confidence_score, importance_score, information_source, persistence_type,
                            memory_status, reason_for_storage, valid_from, valid_until, last_confirmed_at,
                            source_message, is_active, created_at, updated_at,
                            (1.0 - (embedding <=> $1::vector)) AS similarity_score
                        FROM memories
                        WHERE session_id = $2 
                          AND is_active = TRUE 
                          AND (valid_until IS NULL OR valid_until > NOW())
                          AND embedding IS NOT NULL
                          AND (1.0 - (embedding <=> $1::vector)) >= $3
                        ORDER BY (embedding <=> $1::vector) ASC
                        LIMIT $4
                        """,
                        query_sql_vec,
                        session_id,
                        min_threshold,
                        limit
                    )

                results: List[ScoredMemoryRecord] = []
                for row in rows:
                    raw_sim = float(row["similarity_score"])
                    conf = float(row["confidence_score"])
                    # Combine semantic similarity with confidence
                    relevance = round(raw_sim * (0.8 + 0.2 * conf), 4)
                    sim_pct = max(0, min(100, int(raw_sim * 100)))

                    record = ScoredMemoryRecord(
                        id=row["id"],
                        session_id=row["session_id"],
                        category=row["category"],
                        memory_type=row.get("memory_type") or "general_fact",
                        memory_key=row["memory_key"],
                        content=row["content"],
                        confidence_score=conf,
                        importance_score=float(row.get("importance_score") if row.get("importance_score") is not None else 0.70),
                        information_source=row.get("information_source") or "explicit_statement",
                        persistence_type=row.get("persistence_type") or "persistent",
                        memory_status=row.get("memory_status") or "active",
                        reason_for_storage=row.get("reason_for_storage"),
                        valid_from=row.get("valid_from"),
                        valid_until=row.get("valid_until"),
                        last_confirmed_at=row.get("last_confirmed_at"),
                        source_message=row["source_message"],
                        is_active=row["is_active"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                        retrieval_method=RetrievalMethod.SEMANTIC.value,
                        similarity_score=round(raw_sim, 4),
                        relevance_score=relevance,
                        retrieval_reason=f"Semantic concept match ({sim_pct}%) with query meaning."
                    )
                    results.append(record)

                logger.info(
                    f"Semantic retriever found {len(results)} matches for session '{session_id}' "
                    f"(min_threshold={min_threshold})."
                )
                return results

        except Exception as e:
            logger.error(f"Semantic retrieval database execution failed: {e.__class__.__name__}")
            return []

default_semantic_retriever = SemanticMemoryRetriever()
