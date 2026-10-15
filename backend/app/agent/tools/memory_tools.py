"""
MEMORA AI — Memory Tools for Agent Execution
Exposes read-only hybrid semantic search and memory listing with strict session isolation.
"""
from typing import Dict, Any, Optional, List
from app.agent.models import ToolPermission
from app.agent.tools.base import BaseTool
from app.services.hybrid_retriever import retrieve_hybrid_memories
from app.services.memory_service import list_memories

class SearchMemoriesTool(BaseTool):
    name = "search_memories"
    description = (
        "Retrieve relevant user memories using hybrid (semantic pgvector + exact keyword) search. "
        "Arguments: 'query' (string, required), 'category' (string, optional), 'limit' (int, optional, default 5)."
    )
    permission = ToolPermission.AUTOMATIC

    async def execute(self, session_id: str, **kwargs) -> Dict[str, Any]:
        query = kwargs.get("query")
        if not query or not isinstance(query, str) or not query.strip():
            raise ValueError("search_memories requires a non-empty 'query' string.")

        category = kwargs.get("category")
        limit = kwargs.get("limit", 5)
        try:
            limit = int(limit)
            limit = max(1, min(limit, 10))
        except (ValueError, TypeError):
            limit = 5

        memories = await retrieve_hybrid_memories(
            session_id=session_id,
            query=query.strip(),
            category=category,
            limit=limit
        )

        formatted = [
            {
                "id": str(m.id),
                "category": m.category,
                "memory_key": m.memory_key,
                "content": m.content,
                "confidence_score": m.confidence_score,
                "similarity_score": m.similarity_score,
                "relevance_score": m.relevance_score,
                "retrieval_method": m.retrieval_method,
                "retrieval_reason": m.retrieval_reason,
            }
            for m in memories
        ]

        return {
            "query": query,
            "count": len(formatted),
            "memories": formatted
        }

class ListMemoriesTool(BaseTool):
    name = "list_memories"
    description = (
        "List all active persistent memories stored for the current user session. "
        "Arguments: 'category' (string, optional - e.g. 'skills', 'preferences', 'projects', 'goals')."
    )
    permission = ToolPermission.AUTOMATIC

    async def execute(self, session_id: str, **kwargs) -> Dict[str, Any]:
        category = kwargs.get("category")
        memories = await list_memories(
            session_id=session_id,
            category=category,
            is_active=True
        )

        formatted = [
            {
                "id": str(m.id),
                "category": m.category,
                "memory_type": m.memory_type,
                "memory_key": m.memory_key,
                "content": m.content,
                "confidence_score": m.confidence_score,
                "persistence_type": m.persistence_type,
                "reason_for_storage": m.reason_for_storage,
            }
            for m in memories
        ]

        return {
            "session_id": session_id,
            "count": len(formatted),
            "memories": formatted
        }
