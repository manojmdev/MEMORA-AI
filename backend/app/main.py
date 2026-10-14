import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional, List
from uuid import UUID
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.schemas import (
    ChatRequest,
    ChatResponse,
    MemoryListResponse,
    MemoryRecord,
    ScoredMemoryRecord,
    DeleteResponse
)
from app.services.memory_context import generate_personalized_response
from app.services.memory_service import (
    list_memories,
    get_memory,
    delete_memory,
    delete_all_memories,
    backfill_missing_embeddings
)
from app.services.hybrid_retriever import retrieve_hybrid_memories
from app.services.semantic_retriever import default_semantic_retriever
from app.services.memory_retriever import default_retriever as keyword_retriever
from app.database import init_db_pool, close_db_pool, check_db_health

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting MEMORA AI API with Semantic & Hybrid Memory Retrieval Engine...")
    try:
        await init_db_pool()
        # Non-blocking backfill of missing embeddings
        asyncio.create_task(backfill_missing_embeddings())
    except Exception as e:
        logger.error(f"Database pool initialization warning: {e}")
    yield
    logger.info("Shutting down MEMORA AI API...")
    await close_db_pool()

app = FastAPI(
    title="MEMORA AI API",
    description="Private AI Memory and Agent Intelligence Platform with Semantic & Hybrid Retrieval",
    version="0.3.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN, "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {
        "message": "Welcome to MEMORA AI API",
        "status": "running",
        "engine": "Memory Evolution Engine v1"
    }

@app.get("/health")
async def health():
    db_health = await check_db_health()
    is_healthy = db_health.get("status") == "healthy"
    return {
        "status": "healthy" if is_healthy else "degraded",
        "database": db_health
    }

@app.post("/api/chat", response_model=ChatResponse)
@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        reply, recalled, extracted = await generate_personalized_response(
            message=request.message,
            session_id=request.session_id
        )
        return ChatResponse(
            reply=reply,
            model=settings.NEBIUS_MODEL,
            session_id=request.session_id,
            memories_recalled=[m.model_dump(mode="json") for m in recalled],
            memories_extracted=[c.model_dump(mode="json") for c in extracted]
        )
    except Exception as e:
        logger.error(f"Chat execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/memories/search", response_model=List[ScoredMemoryRecord])
async def search_memories(
    q: str = Query(..., min_length=1, description="Search query string"),
    session_id: str = Query(default="default-session", description="Session identifier"),
    category: Optional[str] = Query(default=None, description="Optional category filter"),
    mode: str = Query(default="hybrid", description="Search mode: 'hybrid', 'semantic', or 'keyword'"),
    limit: int = Query(default=5, ge=1, le=20)
):
    """
    Search active memories for a session using hybrid (semantic + keyword),
    semantic-only (pgvector), or keyword-only retrieval.
    """
    try:
        if mode == "semantic":
            return await default_semantic_retriever.retrieve(
                session_id=session_id, query=q, category=category, limit=limit
            )
        elif mode == "keyword":
            records = await keyword_retriever.retrieve(
                session_id=session_id, query=q, category=category, limit=limit
            )
            return [
                ScoredMemoryRecord(
                    id=r.id,
                    session_id=r.session_id,
                    category=r.category,
                    memory_type=r.memory_type,
                    memory_key=r.memory_key,
                    content=r.content,
                    confidence_score=r.confidence_score,
                    importance_score=r.importance_score,
                    information_source=r.information_source,
                    persistence_type=r.persistence_type,
                    memory_status=r.memory_status,
                    reason_for_storage=r.reason_for_storage,
                    valid_from=r.valid_from,
                    valid_until=r.valid_until,
                    last_confirmed_at=r.last_confirmed_at,
                    source_message=r.source_message,
                    is_active=r.is_active,
                    created_at=r.created_at,
                    updated_at=r.updated_at,
                    retrieval_method="keyword",
                    similarity_score=1.0,
                    relevance_score=r.confidence_score,
                    retrieval_reason="Exact keyword and token match on query terms."
                )
                for r in records
            ]
        else:
            return await retrieve_hybrid_memories(
                session_id=session_id, query=q, category=category, limit=limit
            )
    except Exception as e:
        logger.error(f"Search endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/memories", response_model=MemoryListResponse)
async def get_memories(
    session_id: str = Query(default="default-session", description="Session identifier"),
    category: Optional[str] = Query(default=None, description="Optional category filter")
):
    try:
        memories = await list_memories(session_id=session_id, category=category, is_active=True)
        return MemoryListResponse(
            session_id=session_id,
            count=len(memories),
            memories=memories
        )
    except Exception as e:
        logger.error(f"Failed to fetch memories: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/memories/{memory_id}", response_model=MemoryRecord)
async def get_single_memory(
    memory_id: UUID,
    session_id: str = Query(default="default-session", description="Session identifier")
):
    try:
        mem = await get_memory(session_id=session_id, memory_id=memory_id)
        if not mem:
            raise HTTPException(status_code=404, detail="Memory not found or does not belong to this session.")
        return mem
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching memory {memory_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/memories/{memory_id}", response_model=DeleteResponse)
async def remove_memory(
    memory_id: UUID,
    session_id: str = Query(default="default-session", description="Session identifier")
):
    try:
        deleted = await delete_memory(session_id=session_id, memory_id=memory_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Memory not found or does not belong to this session.")
        return DeleteResponse(
            session_id=session_id,
            message="Memory deleted successfully.",
            deleted_count=1
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting memory {memory_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/memories", response_model=DeleteResponse)
async def clear_session_memories(
    session_id: str = Query(default="default-session", description="Session identifier")
):
    try:
        count = await delete_all_memories(session_id=session_id)
        return DeleteResponse(
            session_id=session_id,
            message=f"Cleared {count} memories for session.",
            deleted_count=count
        )
    except Exception as e:
        logger.error(f"Error clearing memories: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/evaluation/run")
async def run_evaluation_benchmark():
    """Run the Day 5 quantitative retrieval evaluation benchmark suite."""
    from app.evaluation.retrieval_evaluator import run_retrieval_evaluation
    try:
        summary = await run_retrieval_evaluation()
        return summary
    except Exception as e:
        logger.error(f"Evaluation benchmark failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

