"""
MEMORA AI — Graph & Context Retrieval Tools for Agent Execution
Exposes read-only access to Sprint 2 Memory Relationship Graph and Context-Aware Retrieval 2.0.
"""
from typing import Dict, Any, Optional, List
from uuid import UUID
from pydantic import BaseModel, Field

from app.agent.models import ToolPermission
from app.agent.tools.base import BaseTool
from app.services.relationship_service import relationship_service
from app.services.context_retriever import context_retriever

class InspectMemoryGraphArgs(BaseModel):
    memory_id: Optional[str] = Field(default=None, description="Optional center memory UUID to inspect connected nodes")
    depth: Optional[int] = Field(default=1, ge=1, le=3, description="Graph traversal hop depth")

class InspectMemoryGraphTool(BaseTool):
    name = "inspect_memory_graph"
    description = (
        "Inspect the relationship graph between memories in the active session. "
        "Arguments: 'memory_id' (string UUID, optional), 'depth' (int 1-3, optional)."
    )
    permission = ToolPermission.AUTOMATIC
    is_idempotent = True
    category = "knowledge_graph"
    risk_level = "safe_readonly"
    args_schema = InspectMemoryGraphArgs

    async def execute(self, session_id: str, **kwargs) -> Dict[str, Any]:
        mem_id_str = kwargs.get("memory_id")
        depth = int(kwargs.get("depth", 1))

        if mem_id_str:
            try:
                mem_uuid = UUID(mem_id_str)
                connected = await relationship_service.get_connected_memories(
                    session_id=session_id,
                    memory_id=mem_uuid,
                    depth=depth
                )
                formatted = [
                    {
                        "connected_memory_id": str(node.memory.id),
                        "memory_key": node.memory.memory_key,
                        "content": node.memory.content,
                        "relationship_type": node.relationship.relationship_type,
                        "strength": node.relationship.strength,
                        "direction": node.direction
                    }
                    for node in connected
                ]
                return {
                    "session_id": session_id,
                    "target_memory_id": mem_id_str,
                    "depth": depth,
                    "count": len(formatted),
                    "connected_memories": formatted
                }
            except Exception as e:
                raise ValueError(f"Failed to inspect connected memories for '{mem_id_str}': {e}")

        # Full session graph topology
        graph = await relationship_service.get_session_graph(session_id=session_id)
        return {
            "session_id": session_id,
            "node_count": len(graph.nodes),
            "edge_count": len(graph.edges),
            "nodes": graph.nodes[:50],
            "edges": graph.edges[:50]
        }

class RetrieveContextV2Args(BaseModel):
    query: str = Field(..., min_length=1, max_length=500, description="Search query string")
    limit: Optional[int] = Field(default=5, ge=1, le=20, description="Max memories to return")

class RetrieveContextV2Tool(BaseTool):
    name = "retrieve_context_v2"
    description = (
        "Retrieve relevant facts using Context-Aware Retrieval 2.0 with multi-factor scoring and graph boosting. "
        "Arguments: 'query' (string, required), 'limit' (int, optional, default 5)."
    )
    permission = ToolPermission.AUTOMATIC
    is_idempotent = True
    category = "memory"
    risk_level = "safe_readonly"
    args_schema = RetrieveContextV2Args

    async def execute(self, session_id: str, **kwargs) -> Dict[str, Any]:
        query = kwargs.get("query")
        if not query or not isinstance(query, str) or not query.strip():
            raise ValueError("retrieve_context_v2 requires a non-empty 'query' string.")

        limit = int(kwargs.get("limit", 5))
        scored_memories = await context_retriever.retrieve(
            session_id=session_id,
            query=query.strip(),
            limit=limit
        )

        formatted = [
            {
                "id": str(m.id),
                "category": m.category,
                "memory_key": m.memory_key,
                "content": m.content,
                "total_score": m.similarity_score,
                "score_breakdown": m.score_breakdown,
                "retrieval_reason": m.retrieval_reason,
            }
            for m in scored_memories
        ]

        return {
            "query": query,
            "count": len(formatted),
            "results": formatted
        }
