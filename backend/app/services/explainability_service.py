"""
MEMORA AI - Phase 5: Memory Explainability Service
Generates concise, evidence-based explanations for extraction, retention, retrieval,
consolidation, exclusion, and lineage without exposing raw internal model chain-of-thought.
"""

import json
import logging
from typing import Optional, Dict, Any, List
from uuid import UUID

from app.database import get_db_pool
from app.schemas import MemoryExplanationResponse, ScoredMemoryRecord
from app.services.relationship_service import relationship_service
from app.services.lifecycle_service import lifecycle_service

logger = logging.getLogger(__name__)

class MemoryExplainabilityService:
    """Service providing transparent, structured explainability for all memory decisions."""

    async def explain_memory(
        self,
        session_id: str,
        memory_id: UUID,
    ) -> Optional[MemoryExplanationResponse]:
        """
        Generate a comprehensive, evidence-based explanation for a specific memory record.
        """
        pool = await get_db_pool()
        if pool is None:
            return None

        query = "SELECT * FROM memories WHERE id = $1 AND session_id = $2;"
        async with pool.acquire() as conn:
            row = await conn.fetchrow(query, memory_id, session_id)
            if not row:
                return None

        meta = row.get("metadata_json") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        elif not isinstance(meta, dict):
            meta = {}

        lineage = row.get("lineage_json") or {}
        if isinstance(lineage, str):
            try:
                lineage = json.loads(lineage)
            except Exception:
                lineage = {}
        elif not isinstance(lineage, dict):
            lineage = {}

        if row.get("superseded_by"):
            lineage["superseded_by"] = str(row.get("superseded_by"))
            lineage["superseded_reason"] = row.get("superseded_reason")

        # 1. Determine extraction origin (Inferred vs Explicit)
        source_msg = row.get("source_message") or ""
        info_source = row.get("information_source") or ""
        is_inferred = (
            bool(meta.get("is_inferred", False))
            or info_source.lower() == "inferred"
            or ("infer" in source_msg.lower())
        )
        
        if source_msg:
            why_extracted = (
                f"Directly extracted from user message: \"{source_msg[:120]}...\""
                if not is_inferred
                else f"Inferred from context in user interaction: \"{source_msg[:120]}...\""
            )
        else:
            why_extracted = f"Extracted during session onboarding for key '{row['memory_key']}'."

        # 2. Determine retention rationale
        imp = float(row.get("importance_score") if row.get("importance_score") is not None else 0.70)
        conf = float(row.get("confidence_score") if row.get("confidence_score") is not None else 1.0)
        temp_type = row.get("persistence_type") or "persistent"
        is_active = bool(row.get("is_active", True))
        is_archived = bool(row.get("is_archived", False))
        status = row.get("memory_status") or "active"

        if not is_active:
            why_retained = f"Inactive in memory store with status '{status}' (retained for governance audit)."
        elif is_archived:
            archived_date = row.get("archived_at")
            why_retained = f"Archived by user on {archived_date}. Preserved in cold storage, excluded from active search."
        else:
            accessed = row.get("access_count") or 0
            why_retained = (
                f"Active {temp_type} memory retained with importance {imp:.2f} and confidence {conf:.2f}. "
                f"Accessed {accessed} times."
            )

        # 3. Retrieve connected relationship edges
        connected_nodes = await relationship_service.get_connected_memories(
            session_id=session_id, memory_id=memory_id, depth=1
        )
        connected_summary = [
            {
                "connected_memory_id": str(n.memory.id),
                "relationship_type": getattr(n, "relationship_type", None) or n.relationship.relationship_type,
                "connected_key": n.memory.memory_key,
                "content": n.memory.content,
                "strength": getattr(n, "strength", None) if getattr(n, "strength", None) is not None else n.relationship.strength,
            }
            for n in connected_nodes
        ]

        # 4. Retrieve lifecycle event trail
        events = await lifecycle_service.get_lifecycle_history(
            session_id=session_id, memory_id=memory_id, limit=10
        )
        lifecycle_summary = [
            {
                "event_type": e.event_type,
                "actor": e.actor,
                "reason": e.reason,
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ]

        return MemoryExplanationResponse(
            memory_id=row["id"],
            session_id=row["session_id"],
            memory_key=row["memory_key"],
            content=row["content"],
            category=row["category"],
            memory_status=status,
            why_extracted=why_extracted,
            why_retained=why_retained,
            is_inferred=is_inferred,
            source_message=source_msg or None,
            lineage=lineage,
            connected_relationships=connected_summary,
            lifecycle_events=lifecycle_summary,
        )

    def explain_retrieval(self, query: str, scored: ScoredMemoryRecord) -> str:
        """
        Explain why a memory was retrieved for a given query based on score breakdown.
        """
        breakdown = scored.score_breakdown or {}
        sem = breakdown.get("semantic_similarity", scored.similarity_score)
        kw = breakdown.get("keyword_match", 0.0)
        rec = breakdown.get("recency_factor", scored.recency_score)
        graph = breakdown.get("graph_boost", scored.graph_boost)
        total = scored.similarity_score

        reasons = []
        if sem >= 0.70:
            reasons.append(f"strong semantic match ({sem:.2f})")
        elif sem >= 0.50:
            reasons.append(f"moderate semantic similarity ({sem:.2f})")

        if kw > 0.30:
            reasons.append(f"exact keyword matches ({kw:.2f})")

        if graph > 0.0:
            reasons.append(f"relationship graph association (+{graph:.2f})")

        if rec >= 0.85:
            reasons.append("recent interaction recency")

        summary = ", ".join(reasons) if reasons else "composite relevance threshold match"
        return f"Retrieved with combined score {total:.2f} due to: {summary}."

    def explain_exclusion(self, memory_row: Dict[str, Any], query_similarity: Optional[float] = None) -> str:
        """
        Explain why a memory was excluded from retrieval results.
        """
        if not memory_row.get("is_active", True):
            status = memory_row.get("memory_status", "inactive")
            return f"Excluded because memory is inactive with status '{status}'."

        if memory_row.get("is_archived", False):
            return "Excluded because memory has been archived by the user."

        status = memory_row.get("memory_status")
        if status in ("expired", "superseded", "forgotten"):
            return f"Excluded because memory status is '{status}'."

        if query_similarity is not None and query_similarity < 0.40:
            return f"Excluded because semantic similarity ({query_similarity:.2f}) fell below the retrieval threshold."

        return "Excluded because combined relevance score fell below retrieval top-k cutoff."

explainability_service = MemoryExplainabilityService()
