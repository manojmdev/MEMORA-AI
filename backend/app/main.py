import logging
from contextlib import asynccontextmanager
from typing import Optional
from uuid import UUID
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.schemas import (
    ChatRequest,
    ChatResponse,
    MemoryListResponse,
    MemoryRecord,
    DeleteResponse
)
from app.services.memory_context import generate_personalized_response
from app.services.memory_service import (
    list_memories,
    get_memory,
    delete_memory,
    delete_all_memories
)
from app.database import init_db_pool, close_db_pool, check_db_health

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting MEMORA AI API with Memory Evolution Engine...")
    try:
        await init_db_pool()
    except Exception as e:
        logger.error(f"Database pool initialization warning: {e}")
    yield
    logger.info("Shutting down MEMORA AI API...")
    await close_db_pool()

app = FastAPI(
    title="MEMORA AI API",
    description="Private AI Memory and Agent Intelligence Platform with Memory Evolution Engine",
    version="0.2.0",
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
