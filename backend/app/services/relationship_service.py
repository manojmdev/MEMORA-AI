"""
MEMORA AI — Memory Relationship Graph Service (Sprint 2 / Phase 1)
Manages typed, directed relationships between memories within isolated sessions.
Enforces session boundaries, prevents self-referential relationships, and enables
relational graph traversal using PostgreSQL without requiring an external graph database.
"""
import logging
import uuid
from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID
import asyncpg
from app.database import get_db_pool
from app.schemas import (
    MemoryRelationshipRecord,
    CreateRelationshipRequest,
    ConnectedMemoryNode,
    MemoryGraphResponse,
    RelationshipType,
    MemoryRecord
)
from app.services.memory_service import record_from_row

logger = logging.getLogger(__name__)

def relationship_from_row(row: asyncpg.Record) -> MemoryRelationshipRecord:
    """Convert an asyncpg database record into a validated Pydantic MemoryRelationshipRecord."""
    metadata = row.get("metadata_json") or {}
    if isinstance(metadata, str):
        import json
        try:
            metadata = json.loads(metadata)
        except Exception:
            metadata = {}

    return MemoryRelationshipRecord(
        id=row["id"],
        session_id=row["session_id"],
        source_memory_id=row["source_memory_id"],
        target_memory_id=row["target_memory_id"],
        relationship_type=row["relationship_type"],
        strength=float(row.get("strength", 1.0)),
        metadata=metadata,
        created_at=row["created_at"],
    )

async def create_relationship(
    session_id: str,
    source_memory_id: UUID,
    target_memory_id: UUID,
    relationship_type: str,
    strength: float = 1.0,
    metadata: Optional[Dict[str, Any]] = None
) -> MemoryRelationshipRecord:
    """
    Establish a typed, weighted relationship between two memories in a session.
    - Validates that source and target are distinct.
    - Validates that both memories exist and belong to the requesting session.
    - Idempotently updates strength/metadata if relationship already exists.
    """
    session_id = session_id.strip() if session_id else ""
    if not session_id:
        raise ValueError("session_id is required.")

    if source_memory_id == target_memory_id:
        raise ValueError("Self-referential memory relationships are prohibited (source_memory_id cannot equal target_memory_id).")

    pool = await get_db_pool()
    if pool is None:
        raise RuntimeError("Database connection pool is not available.")

    rel_type = relationship_type.strip().lower()
    clean_strength = max(0.0, min(1.0, float(strength)))
    metadata_dict = metadata or {}
    import json
    metadata_json = json.dumps(metadata_dict)

    async with pool.acquire() as conn:
        # Verify that both memories exist and belong strictly to this session
        rows = await conn.fetch(
            """
            SELECT id FROM memories
            WHERE id IN ($1, $2) AND session_id = $3
            """,
            source_memory_id,
            target_memory_id,
            session_id,
        )
        found_ids = {r["id"] for r in rows}
        if source_memory_id not in found_ids:
            raise PermissionError(f"Source memory '{source_memory_id}' not found or does not belong to session '{session_id}'.")
        if target_memory_id not in found_ids:
            raise PermissionError(f"Target memory '{target_memory_id}' not found or does not belong to session '{session_id}'.")

        # Insert or update relationship idempotently
        row = await conn.fetchrow(
            """
            INSERT INTO memory_relationships (
                id, session_id, source_memory_id, target_memory_id, 
                relationship_type, strength, metadata_json, created_at
            )
            VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, $6::jsonb, NOW())
            ON CONFLICT (session_id, source_memory_id, target_memory_id, relationship_type)
            DO UPDATE SET 
                strength = EXCLUDED.strength,
                metadata_json = EXCLUDED.metadata_json
            RETURNING *
            """,
            session_id,
            source_memory_id,
            target_memory_id,
            rel_type,
            clean_strength,
            metadata_json,
        )

        # Log relationship lifecycle audit events
        await conn.execute(
            """
            INSERT INTO memory_lifecycle_events (id, session_id, memory_id, event_type, reason, metadata_json)
            VALUES 
                (gen_random_uuid(), $1, $2, 'relationship_linked', $4, $5::jsonb),
                (gen_random_uuid(), $1, $3, 'relationship_linked', $4, $5::jsonb)
            """,
            session_id,
            source_memory_id,
            target_memory_id,
            f"Linked via relationship '{rel_type}'",
            metadata_json,
        )

        logger.info(f"Created/updated relationship [{source_memory_id}] --({rel_type}, {clean_strength})--> [{target_memory_id}] for session '{session_id}'.")
        return relationship_from_row(row)

async def delete_relationship(session_id: str, relationship_id: UUID) -> bool:
    """Delete a memory relationship by ID within the user's session."""
    pool = await get_db_pool()
    if pool is None:
        raise RuntimeError("Database connection pool is not available.")

    session_id = session_id.strip() if session_id else ""
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            DELETE FROM memory_relationships
            WHERE id = $1 AND session_id = $2
            """,
            relationship_id,
            session_id,
        )
        deleted = result.endswith("1")
        if deleted:
            logger.info(f"Deleted relationship {relationship_id} for session '{session_id}'.")
        return deleted

async def list_relationships(
    session_id: str,
    memory_id: Optional[UUID] = None,
    source_id: Optional[UUID] = None,
    target_id: Optional[UUID] = None,
    relationship_type: Optional[str] = None
) -> List[MemoryRelationshipRecord]:
    """List relationships for a session, optionally filtered by source, target, focal memory or type."""
    pool = await get_db_pool()
    if pool is None:
        raise RuntimeError("Database connection pool is not available.")

    session_id = session_id.strip() if session_id else ""

    async with pool.acquire() as conn:
        query = "SELECT * FROM memory_relationships WHERE session_id = $1"
        params: List[Any] = [session_id]

        if source_id:
            params.append(source_id)
            query += f" AND source_memory_id = ${len(params)}"

        if target_id:
            params.append(target_id)
            query += f" AND target_memory_id = ${len(params)}"

        if memory_id and not source_id and not target_id:
            params.append(memory_id)
            query += f" AND (source_memory_id = ${len(params)} OR target_memory_id = ${len(params)})"

        if relationship_type:
            params.append(relationship_type.strip().lower())
            query += f" AND relationship_type = ${len(params)}"

        query += " ORDER BY created_at DESC"
        rows = await conn.fetch(query, *params)
        return [relationship_from_row(r) for r in rows]

async def get_connected_memories(
    session_id: str,
    memory_id: UUID,
    max_hops: int = 1,
    min_strength: float = 0.0,
    depth: Optional[int] = None
) -> List[ConnectedMemoryNode]:
    """
    Retrieve memories connected to a focal memory via the relationship graph.
    Supports 1-hop and multi-hop traversal with strength thresholds.
    """
    if depth is not None:
        max_hops = depth

    pool = await get_db_pool()
    if pool is None:
        raise RuntimeError("Database connection pool is not available.")

    session_id = session_id.strip() if session_id else ""

    async with pool.acquire() as conn:
        # Check focal memory ownership
        focal_exists = await conn.fetchval(
            "SELECT 1 FROM memories WHERE id = $1 AND session_id = $2",
            memory_id,
            session_id,
        )
        if not focal_exists:
            return []

        # Outgoing connections (memory_id is source)
        out_rows = await conn.fetch(
            """
            SELECT r.*, m.id as m_id, m.session_id as m_sid, m.category, m.memory_type,
                   m.memory_key, m.content, m.confidence_score, m.importance_score,
                   m.information_source, m.persistence_type, m.memory_status,
                   m.reason_for_storage, m.valid_from, m.valid_until, m.last_confirmed_at,
                   m.source_message, m.is_active, m.is_archived, m.archived_at,
                   m.access_count, m.last_accessed_at, m.created_at as m_created_at,
                   m.updated_at as m_updated_at, (m.embedding IS NOT NULL) as has_embedding
            FROM memory_relationships r
            JOIN memories m ON r.target_memory_id = m.id
            WHERE r.session_id = $1 AND r.source_memory_id = $2 AND r.strength >= $3
            ORDER BY r.strength DESC
            """,
            session_id,
            memory_id,
            min_strength,
        )

        # Incoming connections (memory_id is target)
        in_rows = await conn.fetch(
            """
            SELECT r.*, m.id as m_id, m.session_id as m_sid, m.category, m.memory_type,
                   m.memory_key, m.content, m.confidence_score, m.importance_score,
                   m.information_source, m.persistence_type, m.memory_status,
                   m.reason_for_storage, m.valid_from, m.valid_until, m.last_confirmed_at,
                   m.source_message, m.is_active, m.is_archived, m.archived_at,
                   m.access_count, m.last_accessed_at, m.created_at as m_created_at,
                   m.updated_at as m_updated_at, (m.embedding IS NOT NULL) as has_embedding
            FROM memory_relationships r
            JOIN memories m ON r.source_memory_id = m.id
            WHERE r.session_id = $1 AND r.target_memory_id = $2 AND r.strength >= $3
            ORDER BY r.strength DESC
            """,
            session_id,
            memory_id,
            min_strength,
        )

        results: List[ConnectedMemoryNode] = []
        seen_memory_ids = set()

        for r in out_rows:
            target_id = r["m_id"]
            if target_id not in seen_memory_ids:
                seen_memory_ids.add(target_id)
                mem_rec = MemoryRecord(
                    id=r["m_id"],
                    session_id=r["m_sid"],
                    category=r["category"],
                    memory_type=r["memory_type"] or "general_fact",
                    memory_key=r["memory_key"],
                    content=r["content"],
                    confidence_score=r["confidence_score"],
                    importance_score=float(r["importance_score"] if r["importance_score"] is not None else 0.70),
                    information_source=r["information_source"] or "explicit_statement",
                    persistence_type=r["persistence_type"] or "persistent",
                    memory_status=r["memory_status"] or "active",
                    reason_for_storage=r["reason_for_storage"],
                    valid_from=r["valid_from"],
                    valid_until=r["valid_until"],
                    last_confirmed_at=r["last_confirmed_at"],
                    source_message=r["source_message"],
                    is_active=r["is_active"],
                    is_archived=bool(r["is_archived"]),
                    archived_at=r["archived_at"],
                    access_count=int(r["access_count"] or 0),
                    last_accessed_at=r["last_accessed_at"],
                    has_embedding=bool(r["has_embedding"]),
                    created_at=r["m_created_at"],
                    updated_at=r["m_updated_at"]
                )
                rel_rec = relationship_from_row(r)
                results.append(ConnectedMemoryNode(memory=mem_rec, relationship=rel_rec, direction="outgoing"))

        for r in in_rows:
            source_id = r["m_id"]
            if source_id not in seen_memory_ids:
                seen_memory_ids.add(source_id)
                mem_rec = MemoryRecord(
                    id=r["m_id"],
                    session_id=r["m_sid"],
                    category=r["category"],
                    memory_type=r["memory_type"] or "general_fact",
                    memory_key=r["memory_key"],
                    content=r["content"],
                    confidence_score=r["confidence_score"],
                    importance_score=float(r["importance_score"] if r["importance_score"] is not None else 0.70),
                    information_source=r["information_source"] or "explicit_statement",
                    persistence_type=r["persistence_type"] or "persistent",
                    memory_status=r["memory_status"] or "active",
                    reason_for_storage=r["reason_for_storage"],
                    valid_from=r["valid_from"],
                    valid_until=r["valid_until"],
                    last_confirmed_at=r["last_confirmed_at"],
                    source_message=r["source_message"],
                    is_active=r["is_active"],
                    is_archived=bool(r["is_archived"]),
                    archived_at=r["archived_at"],
                    access_count=int(r["access_count"] or 0),
                    last_accessed_at=r["last_accessed_at"],
                    has_embedding=bool(r["has_embedding"]),
                    created_at=r["m_created_at"],
                    updated_at=r["m_updated_at"]
                )
                rel_rec = relationship_from_row(r)
                results.append(ConnectedMemoryNode(memory=mem_rec, relationship=rel_rec, direction="incoming"))

        return results

async def get_session_graph(session_id: str, include_inactive: bool = False) -> MemoryGraphResponse:
    """
    Export the full memory relationship graph for visualization in the Health Dashboard.
    Returns nodes and edges formatted for React graph components.
    """
    pool = await get_db_pool()
    if pool is None:
        raise RuntimeError("Database connection pool is not available.")

    session_id = session_id.strip() if session_id else ""

    async with pool.acquire() as conn:
        # Fetch memories for nodes
        if include_inactive:
            mem_rows = await conn.fetch(
                """
                SELECT id, category, memory_type, memory_key, content, confidence_score,
                       importance_score, memory_status, is_active, is_archived, created_at
                FROM memories
                WHERE session_id = $1
                ORDER BY created_at ASC
                """,
                session_id,
            )
        else:
            mem_rows = await conn.fetch(
                """
                SELECT id, category, memory_type, memory_key, content, confidence_score,
                       importance_score, memory_status, is_active, is_archived, created_at
                FROM memories
                WHERE session_id = $1 AND is_active = TRUE AND is_archived = FALSE
                ORDER BY created_at ASC
                """,
                session_id,
            )

        nodes = [
            {
                "id": str(r["id"]),
                "key": r["memory_key"],
                "content": r["content"],
                "category": r["category"],
                "memory_type": r["memory_type"] or "general_fact",
                "confidence": r["confidence_score"],
                "importance": float(r["importance_score"] if r["importance_score"] is not None else 0.70),
                "status": r["memory_status"] or ("active" if r["is_active"] else "inactive"),
                "is_active": r["is_active"],
                "is_archived": r["is_archived"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None
            }
            for r in mem_rows
        ]

        active_node_ids = {n["id"] for n in nodes}

        # Fetch relationships for edges
        rel_rows = await conn.fetch(
            """
            SELECT id, source_memory_id, target_memory_id, relationship_type, strength, metadata_json, created_at
            FROM memory_relationships
            WHERE session_id = $1
            """,
            session_id,
        )

        edges = []
        for r in rel_rows:
            s_id = str(r["source_memory_id"])
            t_id = str(r["target_memory_id"])
            # Only include edge if both nodes are present
            if s_id in active_node_ids and t_id in active_node_ids:
                edges.append({
                    "id": str(r["id"]),
                    "source": s_id,
                    "target": t_id,
                    "relationship_type": r["relationship_type"],
                    "strength": float(r["strength"]),
                    "created_at": r["created_at"].isoformat() if r["created_at"] else None
                })

        return MemoryGraphResponse(session_id=session_id, nodes=nodes, edges=edges)

class MemoryRelationshipService:
    create_relationship = staticmethod(create_relationship)
    delete_relationship = staticmethod(delete_relationship)
    list_relationships = staticmethod(list_relationships)
    get_connected_memories = staticmethod(get_connected_memories)
    get_session_graph = staticmethod(get_session_graph)

relationship_service = MemoryRelationshipService()
