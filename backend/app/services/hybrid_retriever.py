import asyncio
import logging
from typing import List, Optional, Dict
from uuid import UUID
from app.config import settings
from app.schemas import ScoredMemoryRecord, RetrievalMethod, MemoryRecord
from app.services.memory_retriever import default_retriever as keyword_retriever, BaseMemoryRetriever
from app.services.semantic_retriever import default_semantic_retriever as semantic_retriever

logger = logging.getLogger(__name__)

class HybridMemoryRetriever(BaseMemoryRetriever):
    """
    Blended hybrid retrieval system combining semantic vector search (pgvector)
    and exact keyword retrieval. Deduplicates records, blends ranking scores,
    and preserves full explainability and provenance.
    """

    async def retrieve(
        self,
        session_id: str,
        query: str,
        category: Optional[str] = None,
        limit: int = 5,
        semantic_weight: Optional[float] = None,
        keyword_weight: Optional[float] = None
    ) -> List[ScoredMemoryRecord]:
        session_id = session_id.strip() if session_id else ""
        if not session_id or not query or not query.strip():
            return []

        w_sem = semantic_weight if semantic_weight is not None else settings.SEMANTIC_WEIGHT
        w_key = keyword_weight if keyword_weight is not None else settings.KEYWORD_WEIGHT

        # Run semantic and keyword retrievers concurrently
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
            logger.warning(f"Semantic retrieval failed during hybrid execution: {results[0]}")

        keyword_matches: List[MemoryRecord] = []
        if isinstance(results[1], list):
            keyword_matches = results[1]
        else:
            logger.warning(f"Keyword retrieval failed during hybrid execution: {results[1]}")

        # If both returned empty, early exit
        if not semantic_matches and not keyword_matches:
            return []

        # Merge candidates by Memory ID
        merged_map: Dict[UUID, Dict] = {}

        # 1. Process Semantic candidates
        for idx, sem_rec in enumerate(semantic_matches):
            merged_map[sem_rec.id] = {
                "record": sem_rec,
                "is_semantic": True,
                "is_keyword": False,
                "semantic_score": sem_rec.similarity_score,
                "keyword_score": 0.0,
                "semantic_rank": idx + 1,
                "keyword_rank": 999
            }

        # 2. Process Keyword candidates
        for idx, key_rec in enumerate(keyword_matches):
            if key_rec.id in merged_map:
                merged_map[key_rec.id]["is_keyword"] = True
                merged_map[key_rec.id]["keyword_rank"] = idx + 1
                merged_map[key_rec.id]["keyword_score"] = 1.0  # matched keywords
            else:
                merged_map[key_rec.id] = {
                    "record": key_rec,
                    "is_semantic": False,
                    "is_keyword": True,
                    "semantic_score": 0.0,
                    "keyword_score": 1.0,
                    "semantic_rank": 999,
                    "keyword_rank": idx + 1
                }

        # 3. Compute hybrid scores and build ScoredMemoryRecords
        final_list: List[ScoredMemoryRecord] = []
        for entry in merged_map.values():
            rec = entry["record"]
            is_sem = entry["is_semantic"]
            is_key = entry["is_keyword"]
            sem_score = entry["semantic_score"]
            key_score = entry["keyword_score"]
            conf = rec.confidence_score

            if is_sem and is_key:
                # Hybrid match (both matched)
                method = RetrievalMethod.HYBRID.value
                sim_pct = int(sem_score * 100)
                reason = f"Hybrid match: strong semantic similarity ({sim_pct}%) with exact query keywords."
                # Blend with boost for dual match
                score = round((w_sem * sem_score + w_key * 1.0) * (0.8 + 0.2 * conf), 4)
                similarity = sem_score

            elif is_sem:
                # Semantic match only
                method = RetrievalMethod.SEMANTIC.value
                sim_pct = int(sem_score * 100)
                reason = f"Semantic concept match ({sim_pct}%) with query meaning."
                score = round((w_sem * sem_score) * (0.8 + 0.2 * conf), 4)
                similarity = sem_score

            else:
                # Keyword match only
                method = RetrievalMethod.KEYWORD.value
                reason = "Exact keyword and token match on query terms."
                score = round((w_key * 0.9) * (0.8 + 0.2 * conf), 4)
                similarity = 0.85

            scored_item = ScoredMemoryRecord(
                id=rec.id,
                session_id=rec.session_id,
                category=rec.category,
                memory_type=getattr(rec, "memory_type", "general_fact"),
                memory_key=rec.memory_key,
                content=rec.content,
                confidence_score=rec.confidence_score,
                importance_score=getattr(rec, "importance_score", 0.70),
                information_source=getattr(rec, "information_source", "explicit_statement"),
                persistence_type=getattr(rec, "persistence_type", "persistent"),
                memory_status=getattr(rec, "memory_status", "active"),
                reason_for_storage=getattr(rec, "reason_for_storage", None),
                valid_from=getattr(rec, "valid_from", None),
                valid_until=getattr(rec, "valid_until", None),
                last_confirmed_at=getattr(rec, "last_confirmed_at", None),
                source_message=rec.source_message,
                is_active=rec.is_active,
                created_at=rec.created_at,
                updated_at=rec.updated_at,
                retrieval_method=method,
                similarity_score=round(similarity, 4),
                relevance_score=score,
                retrieval_reason=reason
            )
            final_list.append(scored_item)

        # 4. Rank by hybrid relevance score descending
        final_list.sort(key=lambda item: (item.relevance_score, item.updated_at), reverse=True)
        top_results = final_list[:limit]

        logger.info(
            f"Hybrid retriever blended {len(final_list)} candidates down to {len(top_results)} for session '{session_id}'."
        )
        return top_results

default_hybrid_retriever = HybridMemoryRetriever()

async def retrieve_hybrid_memories(
    session_id: str,
    query: str,
    category: Optional[str] = None,
    limit: int = 5
) -> List[ScoredMemoryRecord]:
    """Helper entry point for retrieving hybrid memories."""
    return await default_hybrid_retriever.retrieve(
        session_id=session_id,
        query=query,
        category=category,
        limit=limit
    )
