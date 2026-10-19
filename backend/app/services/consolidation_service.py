"""
MEMORA AI — Intelligent Memory Consolidation Service (Sprint 2 / Phase 2)
Discovers semantically overlapping and duplicate memories within a session.
Proposes structured, contradiction-aware consolidations with human-in-the-loop preview.
Applies atomic, idempotent consolidations while preserving source facts and lineage.
"""
import asyncio
import json
import logging
import uuid
from typing import List, Dict, Any, Optional, Set
from uuid import UUID
from openai import AsyncOpenAI

from app.config import settings
from app.database import get_db_pool
from app.schemas import (
    MemoryRecord,
    ConsolidationCandidateGroup,
    ConsolidationPreviewResponse,
    ApplyConsolidationRequest,
    ApplyConsolidationResponse,
    MemoryCandidate,
    MemoryType,
    InformationSource,
    PersistenceType,
    MemoryStatus,
    RelationshipType
)
from app.services.memory_service import list_memories, record_from_row, add_memory
from app.services.embedding_service import generate_embedding, vector_to_sql_str
from app.services.relationship_service import create_relationship

logger = logging.getLogger(__name__)

llm_client = AsyncOpenAI(
    api_key=settings.NEBIUS_API_KEY,
    base_url=settings.NEBIUS_BASE_URL,
    timeout=60.0,
    max_retries=1
)

CONSOLIDATION_PROMPT = """You are the Memory Consolidation Architect for MEMORA AI.
Your objective is to analyze a cluster of semantically related user memories and propose a clean, coherent, unified consolidation.

CRITICAL INSTRUCTIONS:
1. Synthesize the core facts from the source memories into a single concise, durable factual statement.
2. DO NOT lose specific important details (e.g. library names, framework choices, specific metrics, project names).
3. Check for CONTRADICTIONS:
   - If the source memories contain mutually exclusive or directly conflicting claims (e.g. "User prefers Python" vs "User prefers Java exclusively"), mark is_contradictory: true, explain the contradiction, and DO NOT merge conflicting statements into false unity.
4. Propose a normalized snake_case key (e.g. "core_development_stack").
5. Return ONLY a valid JSON object matching this schema:
{
  "topic": "Concise cluster topic name",
  "proposed_content": "Consolidated factual summary sentence.",
  "proposed_key": "normalized_snake_case_key",
  "proposed_category": "preferences | skills | projects | goals | personal_context | learning_style | general",
  "rationale": "Clear explanation of why these memories were combined and how facts were preserved.",
  "preserved_facts": ["Specific fact 1", "Specific fact 2"],
  "confidence_score": 0.95,
  "is_contradictory": false
}
"""

async def preview_consolidation(
    session_id: str,
    similarity_threshold: float = 0.70
) -> ConsolidationPreviewResponse:
    """
    Scan active memories in a session to identify semantically related or duplicate clusters.
    Generates structured consolidation proposals using NVIDIA Nemotron.
    Does NOT modify database state (read-only preview).
    """
    session_id = session_id.strip() if session_id else ""
    if not session_id:
        return ConsolidationPreviewResponse(session_id="", total_active_memories=0, proposed_clusters=[])

    active_memories = await list_memories(session_id=session_id, is_active=True)
    if len(active_memories) < 2:
        return ConsolidationPreviewResponse(
            session_id=session_id,
            total_active_memories=len(active_memories),
            proposed_clusters=[]
        )

    # 1. Cluster active memories by semantic similarity using pgvector cosine distance
    pool = await get_db_pool()
    if pool is None:
        return ConsolidationPreviewResponse(
            session_id=session_id,
            total_active_memories=len(active_memories),
            proposed_clusters=[]
        )

    candidate_clusters: List[List[MemoryRecord]] = []
    mem_map = {m.id: m for m in active_memories}
    grouped_ids: Set[UUID] = set()
    max_dist = max(0.05, min(0.50, 1.0 - float(similarity_threshold)))

    async with pool.acquire() as conn:
        for mem in active_memories:
            if mem.id in grouped_ids:
                continue

            # Find neighboring memories within cosine distance threshold
            rows = await conn.fetch(
                """
                SELECT id, (1.0 - (embedding <=> (SELECT embedding FROM memories WHERE id = $1))) as sim
                FROM memories
                WHERE session_id = $2 AND is_active = TRUE AND id != $1 AND embedding IS NOT NULL
                  AND (embedding <=> (SELECT embedding FROM memories WHERE id = $1)) <= $3
                ORDER BY sim DESC
                LIMIT 4
                """,
                mem.id,
                session_id,
                max_dist,
            )

            similar_ids = [r["id"] for r in rows if r["id"] in mem_map and r["id"] not in grouped_ids]
            if similar_ids:
                cluster = [mem] + [mem_map[mid] for mid in similar_ids]
                candidate_clusters.append(cluster)
                for c_item in cluster:
                    grouped_ids.add(c_item.id)

    # 2. For each identified cluster, generate Nemotron structured consolidation proposal
    proposed_clusters: List[ConsolidationCandidateGroup] = []

    for idx, cluster in enumerate(candidate_clusters[:5]): # Bound preview clusters
        cluster_texts = [f"[{m.category}] {m.memory_key}: {m.content}" for m in cluster]
        user_prompt = "SOURCE MEMORIES TO CONSOLIDATE:\n" + "\n".join(f"- {t}" for t in cluster_texts)

        try:
            response = await llm_client.chat.completions.create(
                model=settings.NEBIUS_MODEL,
                messages=[
                    {"role": "system", "content": CONSOLIDATION_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2,
            )
            raw_reply = response.choices[0].message.content or ""
            # Strip markdown fences if present
            clean_reply = raw_reply.strip()
            if "```" in clean_reply:
                import re
                m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean_reply)
                if m:
                    clean_reply = m.group(1).strip()

            proposal = json.loads(clean_reply)

            group = ConsolidationCandidateGroup(
                cluster_id=f"cluster_{session_id[:6]}_{idx+1}_{uuid.uuid4().hex[:4]}",
                topic=proposal.get("topic") or f"Consolidation of {cluster[0].memory_key}",
                source_memory_ids=[m.id for m in cluster],
                source_memories=cluster,
                proposed_content=proposal.get("proposed_content") or cluster[0].content,
                proposed_key=proposal.get("proposed_key") or f"consolidated_{cluster[0].memory_key}",
                proposed_category=proposal.get("proposed_category") or cluster[0].category,
                rationale=proposal.get("rationale") or "Synthesized semantically related observations into a unified record.",
                preserved_facts=proposal.get("preserved_facts") or [m.content for m in cluster],
                confidence_score=float(proposal.get("confidence_score") or 0.90),
                is_contradictory=bool(proposal.get("is_contradictory", False))
            )
            proposed_clusters.append(group)

        except Exception as e:
            logger.warning(f"Consolidation LLM synthesis failed for cluster {idx}: {e}")
            # Fallback proposal without LLM synthesis
            combined_content = " | ".join(m.content for m in cluster)
            group = ConsolidationCandidateGroup(
                cluster_id=f"cluster_{session_id[:6]}_{idx+1}_{uuid.uuid4().hex[:4]}",
                topic=f"Unified {cluster[0].category} context",
                source_memory_ids=[m.id for m in cluster],
                source_memories=cluster,
                proposed_content=combined_content,
                proposed_key=f"unified_{cluster[0].memory_key}",
                proposed_category=cluster[0].category,
                rationale="Heuristic consolidation of overlapping session memories.",
                preserved_facts=[m.content for m in cluster],
                confidence_score=0.85,
                is_contradictory=False
            )
            proposed_clusters.append(group)

    return ConsolidationPreviewResponse(
        session_id=session_id,
        total_active_memories=len(active_memories),
        proposed_clusters=proposed_clusters
    )

async def apply_consolidation(
    session_id: str,
    request: Optional[ApplyConsolidationRequest] = None,
    source_memory_ids: Optional[List[UUID]] = None,
    consolidated_content: Optional[str] = None,
    cluster_topic: Optional[str] = None,
    rationale: Optional[str] = None,
    consolidated_key: Optional[str] = None,
    consolidated_category: Optional[str] = None
) -> ApplyConsolidationResponse:
    """
    Atomically and idempotently apply a memory consolidation:
    1. Validates all source memories exist, belong to session, and are currently active.
    2. Inserts new consolidated MemoryRecord with pre-generated embedding.
    3. Retires source memories: is_active = FALSE, memory_status = 'consolidated', superseded_by = new_id.
    4. Automatically creates bidirectional relationship graph edges:
       - Each source memory has 'CONSOLIDATED_INTO' -> new_memory.
       - The new memory has 'DERIVED_FROM' -> each source memory.
    5. Records entry in memory_consolidations table for permanent governance history.
    """
    session_id = session_id.strip() if session_id else ""
    if not session_id:
        raise ValueError("session_id is required.")

    if request is None:
        if not source_memory_ids or not consolidated_content:
            raise ValueError("source_memory_ids and consolidated_content are required.")
        request = ApplyConsolidationRequest(
            session_id=session_id,
            source_memory_ids=source_memory_ids,
            consolidated_content=consolidated_content,
            cluster_topic=cluster_topic,
            rationale=rationale or "",
            consolidated_key=consolidated_key,
            consolidated_category=consolidated_category,
        )

    if not request.source_memory_ids or len(request.source_memory_ids) < 2:
        raise ValueError("Consolidation requires at least two source memories.")

    pool = await get_db_pool()
    if pool is None:
        raise RuntimeError("Database connection pool is not available.")

    new_memory_id = uuid.uuid4()
    consolidation_id = uuid.uuid4()

    # Pre-generate embedding for the consolidated content
    vector_sql = None
    try:
        emb = await generate_embedding(request.consolidated_content)
        if emb:
            vector_sql = vector_to_sql_str(emb)
    except Exception as e:
        logger.warning(f"Could not generate embedding for consolidated memory: {e}")

    async with pool.acquire() as conn:
        async with conn.transaction():
            # Verify all source memories belong to this session and are active
            source_rows = await conn.fetch(
                """
                SELECT * FROM memories
                WHERE id = ANY($1::uuid[]) AND session_id = $2
                FOR UPDATE
                """,
                request.source_memory_ids,
                session_id,
            )

            if len(source_rows) != len(request.source_memory_ids):
                found_ids = {r["id"] for r in source_rows}
                missing = [mid for mid in request.source_memory_ids if mid not in found_ids]
                raise PermissionError(f"Some source memories not found or do not belong to session: {missing}")

            for r in source_rows:
                if not r["is_active"]:
                    raise ValueError(f"Source memory '{r['id']}' is not active (status: {r['memory_status']}); cannot consolidate.")

            # Compute highest importance and confidence among sources
            highest_conf = max(r["confidence_score"] for r in source_rows)
            highest_imp = max(float(r["importance_score"] if r["importance_score"] is not None else 0.70) for r in source_rows)

            target_key = request.consolidated_key or f"consolidated_{source_rows[0]['memory_key']}"
            target_cat = request.consolidated_category or source_rows[0]["category"]
            rationale_text = request.rationale or f"Consolidated {len(source_rows)} memories into unified record."

            # 1. Insert new consolidated memory
            new_row = await conn.fetchrow(
                """
                INSERT INTO memories (
                    id, session_id, category, memory_type, memory_key, content,
                    confidence_score, importance_score, information_source,
                    persistence_type, memory_status, reason_for_storage,
                    valid_from, last_confirmed_at, is_active, embedding, created_at, updated_at
                )
                VALUES (
                    $1, $2, $3, 'consolidated_fact', $4, $5,
                    $6, $7, 'consolidated',
                    'persistent', 'active', $8,
                    NOW(), NOW(), TRUE, $9::vector, NOW(), NOW()
                )
                RETURNING *
                """,
                new_memory_id,
                session_id,
                target_cat,
                target_key,
                request.consolidated_content,
                highest_conf,
                highest_imp,
                rationale_text,
                vector_sql,
            )

            # 2. Retire source memories (never silently delete!)
            await conn.execute(
                """
                UPDATE memories
                SET is_active = FALSE,
                    memory_status = 'consolidated',
                    superseded_by = $1,
                    superseded_reason = $2,
                    updated_at = NOW()
                WHERE id = ANY($3::uuid[]) AND session_id = $4
                """,
                new_memory_id,
                f"Consolidated into {new_memory_id} ({target_key})",
                request.source_memory_ids,
                session_id,
            )

            # 3. Create bidirectional graph relationships
            for s_id in request.source_memory_ids:
                # Source -> CONSOLIDATED_INTO -> Target
                await conn.execute(
                    """
                    INSERT INTO memory_relationships (
                        id, session_id, source_memory_id, target_memory_id,
                        relationship_type, strength, metadata_json, created_at
                    )
                    VALUES (gen_random_uuid(), $1, $2, $3, $4, 1.0, $5::jsonb, NOW())
                    ON CONFLICT (session_id, source_memory_id, target_memory_id, relationship_type) DO NOTHING
                    """,
                    session_id,
                    s_id,
                    new_memory_id,
                    RelationshipType.CONSOLIDATED_INTO.value,
                    json.dumps({"consolidation_id": str(consolidation_id)})
                )

                # Target -> DERIVED_FROM -> Source
                await conn.execute(
                    """
                    INSERT INTO memory_relationships (
                        id, session_id, source_memory_id, target_memory_id,
                        relationship_type, strength, metadata_json, created_at
                    )
                    VALUES (gen_random_uuid(), $1, $2, $3, $4, 1.0, $5::jsonb, NOW())
                    ON CONFLICT (session_id, source_memory_id, target_memory_id, relationship_type) DO NOTHING
                    """,
                    session_id,
                    new_memory_id,
                    s_id,
                    RelationshipType.DERIVED_FROM.value,
                    json.dumps({"consolidation_id": str(consolidation_id)})
                )

            # 4. Record entry in memory_consolidations table
            await conn.execute(
                """
                INSERT INTO memory_consolidations (
                    id, session_id, consolidated_memory_id, source_memory_ids,
                    rationale, cluster_topic, status, created_at
                )
                VALUES ($1, $2, $3, $4::uuid[], $5, $6, 'applied', NOW())
                """,
                consolidation_id,
                session_id,
                new_memory_id,
                request.source_memory_ids,
                rationale_text,
                target_key,
            )

            # 5. Log lifecycle events
            for s_id in request.source_memory_ids:
                await conn.execute(
                    """
                    INSERT INTO memory_lifecycle_events (id, session_id, memory_id, event_type, reason, metadata_json)
                    VALUES (gen_random_uuid(), $1, $2, 'consolidated', $3, $4::jsonb)
                    """,
                    session_id,
                    s_id,
                    f"Consolidated into {new_memory_id}",
                    json.dumps({"consolidated_into": str(new_memory_id)})
                )

            await conn.execute(
                """
                INSERT INTO memory_lifecycle_events (id, session_id, memory_id, event_type, reason, metadata_json)
                VALUES (gen_random_uuid(), $1, $2, 'created', $3, $4::jsonb)
                """,
                session_id,
                new_memory_id,
                f"Created from consolidation of {len(request.source_memory_ids)} source memories",
                json.dumps({"source_ids": [str(sid) for sid in request.source_memory_ids]})
            )

    logger.info(f"Successfully consolidated {len(request.source_memory_ids)} memories into {new_memory_id} for session '{session_id}'.")
    return ApplyConsolidationResponse(
        session_id=session_id,
        consolidation_id=consolidation_id,
        new_memory=record_from_row(new_row),
        consolidated_memory_ids=request.source_memory_ids,
        message=f"Successfully consolidated {len(request.source_memory_ids)} memories into unified record '{target_key}'."
    )

class MemoryConsolidationService:
    preview_consolidation = staticmethod(preview_consolidation)
    apply_consolidation = staticmethod(apply_consolidation)

consolidation_service = MemoryConsolidationService()
