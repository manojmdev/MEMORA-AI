import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional, List, Set
from uuid import UUID, uuid4
from fastapi import FastAPI, HTTPException, Query, Request
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
from app.agent.models import (
    AgentRunRequest,
    AgentTaskResponse,
    ApprovalActionRequest,
    AgentTask,
    AgentExecutionEvent,
    NoteRecord,
    NoteListResponse,
)
from app.agent.orchestrator import agent_orchestrator
from app.services import note_service
from app.database import init_db_pool, close_db_pool, check_db_health, recover_interrupted_tasks
from app.auth.session_guard import validate_session_id

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Managed background task pool for safe lifecycle shutdown
_managed_tasks: Set[asyncio.Task] = set()

def safe_internal_error(e: Exception, context_msg: str, request: Optional[Request] = None) -> HTTPException:
    """Log full stack trace server-side with correlation ID, and return sanitized error to client."""
    corr_id = getattr(request.state, "correlation_id", "internal") if request and hasattr(request, "state") else "internal"
    logger.error(f"[{corr_id}] {context_msg}: {e}", exc_info=True)
    return HTTPException(
        status_code=500,
        detail=f"An internal error occurred while processing your request. (Reference ID: {corr_id})"
    )

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting MEMORA AI API with Semantic & Hybrid Memory Retrieval Engine...")
    try:
        await init_db_pool()
        # Day 7: Recover tasks interrupted by a prior unexpected server restart
        await recover_interrupted_tasks()
        # Day 7: Track background embedding backfill task for graceful drain on shutdown
        backfill_task = asyncio.create_task(backfill_missing_embeddings())
        _managed_tasks.add(backfill_task)
        backfill_task.add_done_callback(_managed_tasks.discard)
    except Exception as e:
        logger.error(f"Database pool initialization warning: {e}")
    yield
    logger.info("Shutting down MEMORA AI API...")
    # Gracefully drain and cancel any in-flight background tasks before closing database pool
    for task in list(_managed_tasks):
        if not task.done():
            task.cancel()
    if _managed_tasks:
        try:
            await asyncio.wait(_managed_tasks, timeout=5.0)
        except Exception as drain_err:
            logger.warning(f"Error while awaiting background task drain: {drain_err}")
    await close_db_pool()

app = FastAPI(
    title="MEMORA AI API",
    description="Private AI Memory and Agent Intelligence Platform with Semantic & Hybrid Retrieval",
    version="0.3.0",
    lifespan=lifespan
)

@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    """Attach or generate X-Request-ID correlation ID for full request-lifecycle traceability."""
    corr_id = request.headers.get("X-Request-ID") or uuid4().hex
    request.state.correlation_id = corr_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = corr_id
    return response

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
    safe_db = {
        "status": db_health.get("status", "unknown"),
        "connected": db_health.get("connected", False),
        "provider": db_health.get("provider", "Neon Lakebase Postgres"),
    }
    if not is_healthy and "error" in db_health:
        safe_db["error"] = "Database connectivity check failed"
    return {
        "status": "healthy" if is_healthy else "degraded",
        "database": safe_db
    }

@app.post("/api/chat", response_model=ChatResponse)
@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, req: Request):
    valid_sid = validate_session_id(request.session_id)
    try:
        reply, recalled, extracted = await generate_personalized_response(
            message=request.message,
            session_id=valid_sid
        )
        return ChatResponse(
            reply=reply,
            model=settings.NEBIUS_MODEL,
            session_id=valid_sid,
            memories_recalled=[m.model_dump(mode="json") for m in recalled],
            memories_extracted=[c.model_dump(mode="json") for c in extracted]
        )
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, "Chat execution failed", req)

@app.get("/api/memories/search", response_model=List[ScoredMemoryRecord])
async def search_memories(
    req: Request,
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
    valid_sid = validate_session_id(session_id)
    try:
        if mode == "semantic":
            return await default_semantic_retriever.retrieve(
                session_id=valid_sid, query=q, category=category, limit=limit
            )
        elif mode == "keyword":
            records = await keyword_retriever.retrieve(
                session_id=valid_sid, query=q, category=category, limit=limit
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
                session_id=valid_sid, query=q, category=category, limit=limit
            )
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, "Search endpoint error", req)

@app.get("/api/memories", response_model=MemoryListResponse)
async def get_memories(
    req: Request,
    session_id: str = Query(default="default-session", description="Session identifier"),
    category: Optional[str] = Query(default=None, description="Optional category filter")
):
    valid_sid = validate_session_id(session_id)
    try:
        memories = await list_memories(session_id=valid_sid, category=category, is_active=True)
        return MemoryListResponse(
            session_id=valid_sid,
            count=len(memories),
            memories=memories
        )
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, "Failed to fetch memories", req)

@app.get("/api/memories/{memory_id}", response_model=MemoryRecord)
async def get_single_memory(
    memory_id: UUID,
    req: Request,
    session_id: str = Query(default="default-session", description="Session identifier")
):
    valid_sid = validate_session_id(session_id)
    try:
        mem = await get_memory(session_id=valid_sid, memory_id=memory_id)
        if not mem:
            raise HTTPException(status_code=404, detail="Memory not found or does not belong to this session.")
        return mem
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, f"Error fetching memory {memory_id}", req)

@app.delete("/api/memories/{memory_id}", response_model=DeleteResponse)
async def remove_memory(
    memory_id: UUID,
    req: Request,
    session_id: str = Query(default="default-session", description="Session identifier")
):
    valid_sid = validate_session_id(session_id)
    try:
        deleted = await delete_memory(session_id=valid_sid, memory_id=memory_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Memory not found or does not belong to this session.")
        return DeleteResponse(
            session_id=valid_sid,
            message="Memory deleted successfully.",
            deleted_count=1
        )
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, f"Error deleting memory {memory_id}", req)

@app.delete("/api/memories", response_model=DeleteResponse)
async def clear_session_memories(
    req: Request,
    session_id: str = Query(default="default-session", description="Session identifier")
):
    valid_sid = validate_session_id(session_id)
    try:
        count = await delete_all_memories(session_id=valid_sid)
        return DeleteResponse(
            session_id=valid_sid,
            message=f"Cleared {count} memories for session.",
            deleted_count=count
        )
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, "Error clearing memories", req)

@app.post("/api/evaluation/run")
async def run_evaluation_benchmark(req: Request):
    """
    Run the Day 5 quantitative retrieval evaluation benchmark suite.
    Restricted to non-production environments or explicit enablement for security & cost protection.
    """
    if not settings.ENABLE_EVALUATION_ENDPOINT and settings.ENVIRONMENT.lower() == "production":
        raise HTTPException(
            status_code=403,
            detail="Evaluation benchmark endpoint is disabled in production environment."
        )
    from app.evaluation.retrieval_evaluator import run_retrieval_evaluation
    try:
        summary = await run_retrieval_evaluation()
        return summary
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, "Evaluation benchmark failed", req)

# ============================================================================
# DAY 6 — AGENTIC MEMORY & CONTROLLED EXECUTION ENDPOINTS
# ============================================================================

@app.post("/api/agent/run", response_model=AgentTaskResponse)
async def run_agent_task(request: AgentRunRequest, req: Request):
    """
    Run the Day 6 Agentic Orchestrator on a user task request.
    Analyzes intent, plans tasks with registered tools, executes automatic steps,
    and pauses at persistent actions awaiting explicit user approval.
    """
    valid_sid = validate_session_id(request.session_id)
    try:
        return await agent_orchestrator.run_agent_task(
            message=request.message,
            session_id=valid_sid
        )
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, "Agent execution error", req)

@app.get("/api/agent/tasks", response_model=List[AgentTask])
async def list_agent_tasks(
    req: Request,
    session_id: str = Query(default="default-session", description="Session identifier"),
    limit: int = Query(default=20, ge=1, le=100)
):
    """List agent tasks strictly scoped to the requesting session."""
    valid_sid = validate_session_id(session_id)
    try:
        return await agent_orchestrator.list_tasks(session_id=valid_sid, limit=limit)
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, "Failed to list agent tasks", req)

@app.get("/api/agent/tasks/{task_id}", response_model=AgentTask)
async def get_agent_task_detail(
    task_id: UUID,
    req: Request,
    session_id: str = Query(default="default-session", description="Session identifier")
):
    """Fetch task details and current plan status for an agent task."""
    valid_sid = validate_session_id(session_id)
    try:
        task = await agent_orchestrator.get_task(session_id=valid_sid, task_id=task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found or session mismatch.")
        return task
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, "Failed to retrieve agent task", req)

@app.post("/api/agent/tasks/{task_id}/approve", response_model=AgentTaskResponse)
async def approve_agent_task(
    task_id: UUID,
    request: ApprovalActionRequest,
    req: Request
):
    """
    Approve a pending approval step for an agent task using a cryptographically signed token.
    Resumes task execution from the pending step.
    """
    valid_sid = validate_session_id(request.session_id)
    try:
        return await agent_orchestrator.approve_and_resume(
            session_id=valid_sid,
            task_id=task_id,
            approval_token=request.approval_token
        )
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, "Approval resumption failed", req)

@app.post("/api/agent/tasks/{task_id}/reject", response_model=AgentTaskResponse)
async def reject_agent_task(
    task_id: UUID,
    request: ApprovalActionRequest,
    req: Request
):
    """
    Reject a pending approval step for an agent task.
    Safely transitions task to CANCELLED and prevents further execution.
    """
    valid_sid = validate_session_id(request.session_id)
    try:
        return await agent_orchestrator.reject_task(
            session_id=valid_sid,
            task_id=task_id
        )
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, "Rejection handling failed", req)

@app.get("/api/agent/tasks/{task_id}/logs", response_model=List[AgentExecutionEvent])
async def get_agent_task_logs(
    task_id: UUID,
    req: Request,
    session_id: str = Query(default="default-session", description="Session identifier")
):
    """Fetch immutable execution audit logs for an agent task."""
    valid_sid = validate_session_id(session_id)
    try:
        return await agent_orchestrator.get_task_logs(session_id=valid_sid, task_id=task_id)
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, "Failed to fetch execution logs", req)

@app.get("/api/notes", response_model=NoteListResponse)
async def list_user_notes(
    req: Request,
    session_id: str = Query(default="default-session", description="Session identifier"),
    limit: int = Query(default=50, ge=1, le=100)
):
    """Retrieve persistent notes created by agent or user in this session."""
    valid_sid = validate_session_id(session_id)
    try:
        notes = await note_service.list_notes(session_id=valid_sid, limit=limit)
        return NoteListResponse(
            session_id=valid_sid,
            count=len(notes),
            notes=[NoteRecord(**n) for n in notes]
        )
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, "Failed to list notes", req)

@app.delete("/api/notes/{note_id}", response_model=DeleteResponse)
async def delete_user_note(
    note_id: UUID,
    req: Request,
    session_id: str = Query(default="default-session", description="Session identifier")
):
    """Delete a persistent note belonging to this session."""
    valid_sid = validate_session_id(session_id)
    try:
        deleted = await note_service.delete_note(session_id=valid_sid, note_id=note_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Note not found or does not belong to this session.")
        return DeleteResponse(
            session_id=valid_sid,
            message="Note deleted successfully.",
            deleted_count=1
        )
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, "Failed to delete note", req)


