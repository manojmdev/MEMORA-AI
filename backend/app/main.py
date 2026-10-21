import asyncio
import logging
from contextvars import ContextVar
from contextlib import asynccontextmanager
from typing import Optional, List, Set
from uuid import UUID, uuid4
import httpx
from openai import APITimeoutError, APIConnectionError, RateLimitError, APIError
from fastapi import FastAPI, HTTPException, Query, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.schemas import (
    ChatRequest,
    ChatResponse,
    MemoryListResponse,
    MemoryRecord,
    ScoredMemoryRecord,
    DeleteResponse,
    CreateRelationshipRequest,
    MemoryRelationshipRecord,
    ConnectedMemoryNode,
    MemoryGraphResponse,
    ConsolidationPreviewResponse,
    ApplyConsolidationRequest,
    ApplyConsolidationResponse,
    MemoryLifecycleEventRecord,
    MemoryLifecycleStats,
    MemoryExplanationResponse,
    MemoryDashboardStats,
    UpdateMemoryRequest,
)
from app.services.memory_context import generate_personalized_response
from app.services.memory_service import (
    list_memories,
    get_memory,
    update_memory,
    delete_memory,
    delete_all_memories,
    backfill_missing_embeddings
)
from app.services.hybrid_retriever import retrieve_hybrid_memories
from app.services.semantic_retriever import default_semantic_retriever
from app.services.memory_retriever import default_retriever as keyword_retriever
from app.services.relationship_service import relationship_service
from app.services.consolidation_service import consolidation_service
from app.services.context_retriever import context_retriever
from app.services.lifecycle_service import lifecycle_service
from app.services.explainability_service import explainability_service
from app.services.dashboard_service import dashboard_service
from app.agent.models import (
    AgentRunRequest,
    AgentTaskResponse,
    ApprovalActionRequest,
    ClarificationActionRequest,
    AgentTask,
    AgentTaskCheckpoint,
    AgentExecutionEvent,
    NoteRecord,
    NoteListResponse,
)
from app.agent.orchestrator import agent_orchestrator
from app.agent.checkpoint_manager import checkpoint_manager
from app.agent.worker_identity import WorkerIdentity
from app.services import note_service
from app.database import init_db_pool, close_db_pool, check_db_health, recover_interrupted_tasks
from app.auth.session_guard import validate_session_id, get_current_principal, UserPrincipal

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="system")

def get_current_correlation_id() -> str:
    return correlation_id_var.get()

class CorrelationIdFilter(logging.Filter):
    def filter(self, record):
        record.correlation_id = correlation_id_var.get()
        return True

corr_filter = CorrelationIdFilter()
log_handler = logging.StreamHandler()
log_handler.addFilter(corr_filter)
log_handler.setFormatter(logging.Formatter("[%(asctime)s] [%(correlation_id)s] [%(levelname)s] [%(name)s]: %(message)s"))
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.handlers = [log_handler]

logger = logging.getLogger(__name__)

# Managed background task pool for safe lifecycle shutdown
_managed_tasks: Set[asyncio.Task] = set()

def safe_internal_error(e: Exception, context_msg: str, request: Optional[Request] = None) -> HTTPException:
    """Log full stack trace server-side with correlation ID, and return sanitized error to client."""
    corr_id = getattr(request.state, "correlation_id", "internal") if request and hasattr(request, "state") else get_current_correlation_id()
    logger.error(f"[{corr_id}] {context_msg}: {e}", exc_info=True)

    if isinstance(e, (APITimeoutError, asyncio.TimeoutError, httpx.TimeoutException)):
        return HTTPException(
            status_code=504,
            detail=f"The AI service provider timed out while processing your request. Please try again. (Reference ID: {corr_id})"
        )
    if isinstance(e, (APIConnectionError, httpx.ConnectError)):
        return HTTPException(
            status_code=503,
            detail=f"AI service provider is temporarily unreachable. Please retry. (Reference ID: {corr_id})"
        )
    if isinstance(e, RateLimitError):
        return HTTPException(
            status_code=429,
            detail=f"AI service rate limit exceeded. Please try again later. (Reference ID: {corr_id})"
        )
    return HTTPException(
        status_code=500,
        detail=f"An internal error occurred while processing your request. (Reference ID: {corr_id})"
    )

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting MEMORA AI API with Semantic & Hybrid Memory Retrieval Engine...")
    try:
        await init_db_pool()
        # Recover tasks interrupted by a prior unexpected server restart
        await recover_interrupted_tasks()
        # Track background embedding backfill task if explicitly enabled (disabled by default on serverless)
        if settings.ENABLE_BACKGROUND_EMBEDDING_BACKFILL:
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
    token = correlation_id_var.set(corr_id)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = corr_id
        return response
    finally:
        correlation_id_var.reset(token)

cors_origins = [
    settings.FRONTEND_ORIGIN,
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://localhost:4173",
]
if settings.FRONTEND_ORIGIN and "," in settings.FRONTEND_ORIGIN:
    cors_origins.extend([o.strip() for o in settings.FRONTEND_ORIGIN.split(",") if o.strip()])

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(dict.fromkeys(cors_origins)),
    allow_origin_regex=r"^https:\/\/.*\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {
        "message": "Welcome to MEMORA AI API",
        "status": "running",
        "engine": "Memory Evolution Engine v1"
    }

@app.get("/api/system/info")
async def get_system_info():
    """Return verified system, model, and environment telemetry without leaking secrets."""
    db_health = await check_db_health()
    return {
        "app_name": "MEMORA AI",
        "version": "2.0.0",
        "environment": settings.ENVIRONMENT,
        "llm_model": settings.NEBIUS_MODEL,
        "embedding_model": settings.NEBIUS_EMBEDDING_MODEL or settings.EMBEDDING_MODEL,
        "embedding_dim": settings.EMBEDDING_DIM or settings.EMBEDDING_DIMENSION,
        "database_provider": "Neon Lakebase Postgres (pgvector)",
        "database_connected": db_health.get("connected", False),
        "database_pool_size": db_health.get("pool_size", 0),
        "database_free_connections": db_health.get("free_connections", 0),
        "auth_mode": "Strict HMAC Bearer" if settings.ENVIRONMENT.lower() == "production" else "Development / Demo Session",
        "worker_id": WorkerIdentity.get_worker_id(),
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
async def chat(
    request: ChatRequest,
    req: Request,
    principal: UserPrincipal = Depends(get_current_principal)
):
    valid_sid = validate_session_id(request.session_id, principal)
    try:
        reply, recalled, extracted, p_status, p_error = await generate_personalized_response(
            message=request.message,
            session_id=valid_sid
        )
        return ChatResponse(
            reply=reply,
            model=settings.NEBIUS_MODEL,
            session_id=valid_sid,
            memories_recalled=[m.model_dump(mode="json") for m in recalled],
            memories_extracted=[c.model_dump(mode="json") for c in extracted],
            memory_persistence_status=p_status,
            memory_persistence_error=p_error
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
    limit: int = Query(default=5, ge=1, le=20),
    principal: UserPrincipal = Depends(get_current_principal)
):
    """
    Search active memories for a session using hybrid (semantic + keyword),
    semantic-only (pgvector), or keyword-only retrieval.
    """
    valid_sid = validate_session_id(session_id, principal)
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
    category: Optional[str] = Query(default=None, description="Optional category filter"),
    is_active: Optional[bool] = Query(default=True, description="Filter by active status"),
    principal: UserPrincipal = Depends(get_current_principal)
):
    valid_sid = validate_session_id(session_id, principal)
    try:
        memories = await list_memories(session_id=valid_sid, category=category, is_active=is_active if is_active is not None else True)
        return MemoryListResponse(
            session_id=valid_sid,
            count=len(memories),
            memories=memories
        )
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, "Failed to fetch memories", req)

@app.delete("/api/memories", response_model=DeleteResponse)
async def clear_session_memories(
    req: Request,
    session_id: str = Query(default="default-session", description="Session identifier"),
    principal: UserPrincipal = Depends(get_current_principal)
):
    valid_sid = validate_session_id(session_id, principal)
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

@app.post("/api/agent/tasks", response_model=AgentTaskResponse)
async def create_agent_task(
    request: AgentRunRequest,
    req: Request,
    principal: UserPrincipal = Depends(get_current_principal)
):
    """
    Initialize and persist an agent task and its plan in PostgreSQL.
    Returns durable task ID and plan without executing long-running steps.
    """
    valid_sid = validate_session_id(request.session_id, principal)
    try:
        resp, _ = await agent_orchestrator.create_task(
            session_id=valid_sid,
            user_request=request.effective_instruction,
            require_approval=request.require_approval,
            max_steps=request.max_steps
        )
        return resp
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, "Agent task creation error", req)

@app.post("/api/agent/tasks/{task_id}/step", response_model=AgentTaskResponse)
async def step_agent_task(
    task_id: UUID,
    req: Request,
    session_id: str = Query(default="default-session", description="Session identifier"),
    principal: UserPrincipal = Depends(get_current_principal)
):
    """
    Execute a bounded execution slice of an agent task in a serverless environment.
    Claims database lease with fencing generation, runs ready step(s), updates checkpoints,
    and returns current state.
    """
    valid_sid = validate_session_id(session_id, principal)
    try:
        return await agent_orchestrator.execute_task_slice(
            session_id=valid_sid,
            task_id=task_id,
            max_duration_seconds=20.0,
            max_steps=1
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, "Agent task step execution failed", req)

@app.post("/api/agent/recovery")
async def recover_tasks_endpoint(
    req: Request,
    principal: UserPrincipal = Depends(get_current_principal)
):
    """Manually trigger stale interrupted task recovery for the system."""
    try:
        count = await recover_interrupted_tasks()
        return {"status": "ok", "recovered_count": count}
    except Exception as e:
        raise safe_internal_error(e, "Task recovery sweep failed", req)

@app.get("/api/agent/cron/recover")
async def cron_recover_tasks(req: Request):
    """
    Vercel Cron endpoint to recover stale tasks with expired worker leases.
    Authorized via CRON_SECRET header in production environment.
    """
    auth_header = req.headers.get("Authorization")
    if settings.ENVIRONMENT.lower() == "production":
        if not settings.CRON_SECRET:
            raise HTTPException(status_code=500, detail="CRON_SECRET is not configured in production.")
        expected = f"Bearer {settings.CRON_SECRET}"
        if auth_header != expected:
            raise HTTPException(status_code=401, detail="Unauthorized cron invocation.")
    try:
        count = await recover_interrupted_tasks()
        return {"status": "ok", "recovered_count": count}
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, "Cron recovery sweep failed", req)

@app.post("/api/agent/run", response_model=AgentTaskResponse)
async def run_agent_task(
    request: AgentRunRequest,
    req: Request,
    principal: UserPrincipal = Depends(get_current_principal)
):
    """
    Run the Day 6 Agentic Orchestrator on a user task request.
    Analyzes intent, plans tasks with registered tools, executes automatic steps,
    and pauses at persistent actions awaiting explicit user approval.
    """
    valid_sid = validate_session_id(request.session_id, principal)
    try:
        return await agent_orchestrator.run_agent_task(
            message=request.effective_instruction,
            session_id=valid_sid,
            require_approval=request.require_approval,
            max_steps=request.max_steps
        )
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, "Agent execution error", req)

@app.get("/api/agent/tasks", response_model=List[AgentTask])
async def list_agent_tasks(
    req: Request,
    session_id: str = Query(default="default-session", description="Session identifier"),
    limit: int = Query(default=20, ge=1, le=100),
    principal: UserPrincipal = Depends(get_current_principal)
):
    """List agent tasks strictly scoped to the requesting session."""
    valid_sid = validate_session_id(session_id, principal)
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
    session_id: str = Query(default="default-session", description="Session identifier"),
    principal: UserPrincipal = Depends(get_current_principal)
):
    """Fetch task details and current plan status for an agent task."""
    valid_sid = validate_session_id(session_id, principal)
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
    req: Request,
    principal: UserPrincipal = Depends(get_current_principal)
):
    """
    Approve a pending approval step for an agent task using a cryptographically signed token.
    Resumes task execution from the pending step.
    """
    valid_sid = validate_session_id(request.session_id, principal)
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
    req: Request,
    principal: UserPrincipal = Depends(get_current_principal)
):
    """
    Reject a pending approval step for an agent task.
    Safely transitions task to CANCELLED and prevents further execution.
    """
    valid_sid = validate_session_id(request.session_id, principal)
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

@app.post("/api/agent/tasks/{task_id}/cancel", response_model=AgentTaskResponse)
async def cancel_agent_task(
    task_id: UUID,
    req: Request,
    session_id: str = Query(default="default-session", description="Session identifier"),
    principal: UserPrincipal = Depends(get_current_principal)
):
    """
    Safely cancels an in-progress or pending agent task and its remaining checkpoints.
    Does not delete or alter already-completed checkpoints or execution audit history.
    """
    valid_sid = validate_session_id(session_id, principal)
    try:
        return await agent_orchestrator.cancel_task(
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
        raise safe_internal_error(e, "Task cancellation failed", req)

@app.post("/api/agent/tasks/{task_id}/retry", response_model=AgentTaskResponse)
async def retry_agent_task(
    task_id: UUID,
    req: Request,
    session_id: str = Query(default="default-session", description="Session identifier"),
    principal: UserPrincipal = Depends(get_current_principal)
):
    """
    Resumes or retries an agent task from the last failed or pending checkpoint.
    Already-succeeded steps are preserved and not re-executed.
    """
    valid_sid = validate_session_id(session_id, principal)
    try:
        return await agent_orchestrator.retry_task(
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
        raise safe_internal_error(e, "Task retry failed", req)

@app.post("/api/agent/tasks/{task_id}/clarify", response_model=AgentTaskResponse)
async def clarify_agent_task(
    task_id: UUID,
    request: ClarificationActionRequest,
    req: Request,
    principal: UserPrincipal = Depends(get_current_principal)
):
    """
    Provide user clarification for an agent task in AWAITING_CLARIFICATION state.
    Resumes planning and execution with the augmented objective.
    """
    valid_sid = validate_session_id(request.session_id or "default-session", principal)
    try:
        return await agent_orchestrator.clarify_task(
            session_id=valid_sid,
            task_id=task_id,
            clarification=request.clarification
        )
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, "Task clarification failed", req)

@app.get("/api/agent/tasks/{task_id}/checkpoints", response_model=List[AgentTaskCheckpoint])
async def get_agent_task_checkpoints(
    task_id: UUID,
    req: Request,
    session_id: str = Query(default="default-session", description="Session identifier"),
    principal: UserPrincipal = Depends(get_current_principal)
):
    """Fetch durable step-level checkpoints for an agent task."""
    valid_sid = validate_session_id(session_id, principal)
    try:
        return await checkpoint_manager.get_task_checkpoints(task_id=task_id, session_id=valid_sid)
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, "Failed to fetch task checkpoints", req)

@app.get("/api/agent/tasks/{task_id}/logs", response_model=List[AgentExecutionEvent])
async def get_agent_task_logs(
    task_id: UUID,
    req: Request,
    session_id: str = Query(default="default-session", description="Session identifier"),
    principal: UserPrincipal = Depends(get_current_principal)
):
    """Fetch immutable execution audit logs for an agent task."""
    valid_sid = validate_session_id(session_id, principal)
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
    limit: int = Query(default=50, ge=1, le=100),
    principal: UserPrincipal = Depends(get_current_principal)
):
    """Retrieve persistent notes created by agent or user in this session."""
    valid_sid = validate_session_id(session_id, principal)
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
    session_id: str = Query(default="default-session", description="Session identifier"),
    principal: UserPrincipal = Depends(get_current_principal)
):
    """Delete a persistent note belonging to this session."""
    valid_sid = validate_session_id(session_id, principal)
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

# ==============================================================================
# SPRINT 2: ADVANCED MEMORY INTELLIGENCE 2.0 ENDPOINTS
# ==============================================================================

# ------------------------------------------------------------------------------
# Phase 1: Memory Relationship Graph
# ------------------------------------------------------------------------------

@app.post("/api/memories/relationships", response_model=MemoryRelationshipRecord)
async def create_memory_relationship(
    request: CreateRelationshipRequest,
    req: Request,
    principal: UserPrincipal = Depends(get_current_principal)
):
    """Create a directional typed relationship between two memories in a session."""
    valid_sid = validate_session_id(request.session_id, principal)
    try:
        rel = await relationship_service.create_relationship(
            session_id=valid_sid,
            source_memory_id=request.source_memory_id,
            target_memory_id=request.target_memory_id,
            relationship_type=request.relationship_type,
            strength=request.strength,
            metadata=request.metadata,
        )
        return rel
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, "Failed to create memory relationship", req)

@app.get("/api/memories/relationships", response_model=List[MemoryRelationshipRecord])
async def list_memory_relationships(
    req: Request,
    session_id: str = Query(default="default-session", description="Session identifier"),
    source_id: Optional[UUID] = Query(None, description="Filter by source memory ID"),
    target_id: Optional[UUID] = Query(None, description="Filter by target memory ID"),
    relationship_type: Optional[str] = Query(None, description="Filter by relationship type"),
    principal: UserPrincipal = Depends(get_current_principal)
):
    """List relationships for a session with optional node/type filtering."""
    valid_sid = validate_session_id(session_id, principal)
    try:
        return await relationship_service.list_relationships(
            session_id=valid_sid,
            source_id=source_id,
            target_id=target_id,
            relationship_type=relationship_type,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, "Failed to list memory relationships", req)

@app.delete("/api/memories/relationships/{relationship_id}", response_model=DeleteResponse)
async def delete_memory_relationship(
    relationship_id: UUID,
    req: Request,
    session_id: str = Query(default="default-session", description="Session identifier"),
    principal: UserPrincipal = Depends(get_current_principal)
):
    """Delete a specific memory relationship edge."""
    valid_sid = validate_session_id(session_id, principal)
    try:
        deleted = await relationship_service.delete_relationship(
            session_id=valid_sid,
            relationship_id=relationship_id,
        )
        if not deleted:
            raise HTTPException(status_code=404, detail="Relationship not found or does not belong to session.")
        return DeleteResponse(
            session_id=valid_sid,
            message="Relationship deleted successfully.",
            deleted_count=1,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, "Failed to delete relationship", req)

@app.get("/api/memories/{memory_id}/connected", response_model=List[ConnectedMemoryNode])
async def get_connected_memories(
    memory_id: UUID,
    req: Request,
    session_id: str = Query(default="default-session", description="Session identifier"),
    depth: int = Query(default=1, ge=1, le=2, description="Hop depth (1 or 2)"),
    principal: UserPrincipal = Depends(get_current_principal)
):
    """Traverse relationships connected to a specific memory node."""
    valid_sid = validate_session_id(session_id, principal)
    try:
        return await relationship_service.get_connected_memories(
            session_id=valid_sid,
            memory_id=memory_id,
            depth=depth,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, "Failed to get connected memories", req)

@app.get("/api/memories/graph", response_model=MemoryGraphResponse)
async def get_session_memory_graph(
    req: Request,
    session_id: str = Query(default="default-session", description="Session identifier"),
    principal: UserPrincipal = Depends(get_current_principal)
):
    """Retrieve full relationship graph topology (nodes and edges) for a session."""
    valid_sid = validate_session_id(session_id, principal)
    try:
        return await relationship_service.get_session_graph(session_id=valid_sid)
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, "Failed to retrieve session graph", req)

# ------------------------------------------------------------------------------
# Phase 2: Intelligent Memory Consolidation
# ------------------------------------------------------------------------------

@app.post("/api/memories/consolidation/preview", response_model=ConsolidationPreviewResponse)
async def preview_memory_consolidation(
    req: Request,
    session_id: str = Query(default="default-session", description="Session identifier"),
    similarity_threshold: float = Query(default=0.75, ge=0.50, le=0.99),
    principal: UserPrincipal = Depends(get_current_principal)
):
    """
    Identify semantically overlapping memories and generate candidate consolidation proposals.
    Non-destructive preview only; does not modify any database records.
    """
    valid_sid = validate_session_id(session_id, principal)
    try:
        return await consolidation_service.preview_consolidation(
            session_id=valid_sid,
            similarity_threshold=similarity_threshold,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, "Failed to preview memory consolidation", req)

@app.post("/api/memories/consolidation/apply", response_model=ApplyConsolidationResponse)
async def apply_memory_consolidation(
    request: ApplyConsolidationRequest,
    req: Request,
    principal: UserPrincipal = Depends(get_current_principal)
):
    """
    Apply a reviewed consolidation proposal: atomically creates a consolidated memory,
    transitions source memories to 'consolidated' status, creates lineage relationships,
    and logs governance lifecycle audit events.
    """
    valid_sid = validate_session_id(request.session_id, principal)
    try:
        return await consolidation_service.apply_consolidation(
            session_id=valid_sid,
            source_memory_ids=request.source_memory_ids,
            consolidated_content=request.consolidated_content,
            cluster_topic=request.cluster_topic,
            rationale=request.rationale,
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, "Failed to apply consolidation", req)

# ------------------------------------------------------------------------------
# Phase 3: Context-Aware Retrieval 2.0
# ------------------------------------------------------------------------------

@app.get("/api/memories/search/v2", response_model=List[ScoredMemoryRecord])
async def search_context_memories_v2(
    query: str = Query(..., description="Search query or context prompt"),
    req: Request = None,
    session_id: str = Query(default="default-session", description="Session identifier"),
    limit: int = Query(default=5, ge=1, le=20, description="Max memories to return"),
    category: Optional[str] = Query(None, description="Filter by category"),
    include_archived: bool = Query(default=False, description="Whether to include cold-storage archived memories"),
    debug_scores: bool = Query(default=True, description="Include detailed scoring breakdown"),
    principal: UserPrincipal = Depends(get_current_principal)
):
    """
    Context-Aware Retrieval 2.0:
    Multi-factor ranking incorporating semantic similarity (pgvector cosine), exact keyword matching,
    memory importance, confidence, asymptotic time-decay, and relationship graph proximity boost.
    """
    valid_sid = validate_session_id(session_id, principal)
    try:
        return await context_retriever.retrieve_context_aware(
            session_id=valid_sid,
            query=query,
            limit=limit,
            category=category,
            include_archived=include_archived,
            debug_scores=debug_scores,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, "Context-Aware Retrieval 2.0 failed", req)

# ------------------------------------------------------------------------------
# Phase 4: Memory Lifecycle Management
# ------------------------------------------------------------------------------

@app.post("/api/memories/{memory_id}/archive", response_model=MemoryRecord)
async def archive_memory(
    memory_id: UUID,
    req: Request,
    session_id: str = Query(default="default-session", description="Session identifier"),
    reason: str = Query(default="Archived by user", description="Reason for archival"),
    principal: UserPrincipal = Depends(get_current_principal)
):
    """Move a memory to cold storage archive. Preserved but excluded from active searches."""
    valid_sid = validate_session_id(session_id, principal)
    try:
        rec = await lifecycle_service.archive_memory(
            session_id=valid_sid,
            memory_id=memory_id,
            reason=reason,
            actor=principal.principal_id,
        )
        if not rec:
            raise HTTPException(status_code=404, detail="Memory not found or does not belong to session.")
        return rec
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, "Failed to archive memory", req)

@app.post("/api/memories/{memory_id}/restore", response_model=MemoryRecord)
async def restore_memory(
    memory_id: UUID,
    req: Request,
    session_id: str = Query(default="default-session", description="Session identifier"),
    reason: str = Query(default="Restored by user", description="Reason for restoration"),
    principal: UserPrincipal = Depends(get_current_principal)
):
    """Restore an archived memory back into active retrieval."""
    valid_sid = validate_session_id(session_id, principal)
    try:
        rec = await lifecycle_service.restore_memory(
            session_id=valid_sid,
            memory_id=memory_id,
            reason=reason,
            actor=principal.principal_id,
        )
        if not rec:
            raise HTTPException(status_code=404, detail="Memory not found or does not belong to session.")
        return rec
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, "Failed to restore memory", req)

@app.post("/api/memories/{memory_id}/forget", response_model=DeleteResponse)
async def forget_memory(
    memory_id: UUID,
    req: Request,
    session_id: str = Query(default="default-session", description="Session identifier"),
    reason: str = Query(default="User requested forgetting", description="Reason for forgetting"),
    principal: UserPrincipal = Depends(get_current_principal)
):
    """
    Immediately deactivates memory, removes from active retrieval, and completely nullifies
    its vector embedding. Minimal lifecycle governance audit entry preserved.
    """
    valid_sid = validate_session_id(session_id, principal)
    try:
        success = await lifecycle_service.forget_memory(
            session_id=valid_sid,
            memory_id=memory_id,
            reason=reason,
            actor=principal.principal_id,
        )
        if not success:
            raise HTTPException(status_code=404, detail="Memory not found or does not belong to session.")
        return DeleteResponse(
            session_id=valid_sid,
            message="Memory forgotten successfully. Embedding vector cleared immediately.",
            deleted_count=1,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, "Failed to forget memory", req)

@app.post("/api/memories/retention/check")
async def check_memory_retention(
    req: Request,
    session_id: str = Query(default="default-session", description="Session identifier"),
    principal: UserPrincipal = Depends(get_current_principal)
):
    """Scan and transition expired memories based on temporal validity TTL timestamps."""
    valid_sid = validate_session_id(session_id, principal)
    try:
        expired = await lifecycle_service.check_and_expire_retention(session_id=valid_sid)
        return {
            "session_id": valid_sid,
            "expired_count": len(expired),
            "expired_memory_ids": [str(eid) for eid in expired],
            "message": f"Successfully evaluated retention policy. {len(expired)} memories transitioned to expired.",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, "Failed to evaluate retention policy", req)

@app.get("/api/memories/lifecycle", response_model=List[MemoryLifecycleEventRecord])
async def list_lifecycle_events(
    req: Request,
    session_id: str = Query(default="default-session", description="Session identifier"),
    memory_id: Optional[UUID] = Query(None, description="Filter events for a specific memory"),
    limit: int = Query(default=50, ge=1, le=100),
    principal: UserPrincipal = Depends(get_current_principal)
):
    """Retrieve immutable lifecycle event audit trail for governance and compliance."""
    valid_sid = validate_session_id(session_id, principal)
    try:
        return await lifecycle_service.get_lifecycle_history(
            session_id=valid_sid,
            memory_id=memory_id,
            limit=limit,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, "Failed to fetch lifecycle events", req)

@app.get("/api/memories/lifecycle/stats", response_model=MemoryLifecycleStats)
async def get_lifecycle_stats(
    req: Request,
    session_id: str = Query(default="default-session", description="Session identifier"),
    principal: UserPrincipal = Depends(get_current_principal)
):
    """Get aggregated lifecycle metrics for memories in a session."""
    valid_sid = validate_session_id(session_id, principal)
    try:
        return await lifecycle_service.get_lifecycle_stats(session_id=valid_sid)
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, "Failed to fetch lifecycle stats", req)

# ------------------------------------------------------------------------------
# Phase 5: Memory Explainability
# ------------------------------------------------------------------------------

@app.get("/api/memories/{memory_id}/explain", response_model=MemoryExplanationResponse)
async def explain_memory_decision(
    memory_id: UUID,
    req: Request,
    session_id: str = Query(default="default-session", description="Session identifier"),
    principal: UserPrincipal = Depends(get_current_principal)
):
    """
    Return structured, transparent explanation of why a memory was extracted,
    why it is retained, its inference nature, source evidence, and relationship lineage.
    """
    valid_sid = validate_session_id(session_id, principal)
    try:
        explanation = await explainability_service.explain_memory(
            session_id=valid_sid,
            memory_id=memory_id,
        )
        if not explanation:
            raise HTTPException(status_code=404, detail="Memory not found or does not belong to session.")
        return explanation
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, "Failed to explain memory decision", req)

# ------------------------------------------------------------------------------
# Phase 6: Memory Health Dashboard
# ------------------------------------------------------------------------------

@app.get("/api/memories/dashboard", response_model=MemoryDashboardStats)
async def get_memory_dashboard_metrics(
    req: Request,
    session_id: str = Query(default="default-session", description="Session identifier"),
    principal: UserPrincipal = Depends(get_current_principal)
):
    """
    Aggregate live, verified database metrics for the Memory Health Dashboard:
    status counts, temporal distributions, category breakdown, graph size,
    consolidation count, evolution timeline, and retrieval performance.
    """
    valid_sid = validate_session_id(session_id, principal)
    try:
        return await dashboard_service.get_dashboard_stats(session_id=valid_sid)
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, "Failed to generate dashboard metrics", req)

@app.get("/api/memories/{memory_id}", response_model=MemoryRecord)
async def get_single_memory(
    memory_id: UUID,
    req: Request,
    session_id: str = Query(default="default-session", description="Session identifier"),
    principal: UserPrincipal = Depends(get_current_principal)
):
    valid_sid = validate_session_id(session_id, principal)
    try:
        mem = await get_memory(session_id=valid_sid, memory_id=memory_id)
        if not mem:
            raise HTTPException(status_code=404, detail="Memory not found or does not belong to this session.")
        return mem
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, f"Error fetching memory {memory_id}", req)

@app.patch("/api/memories/{memory_id}", response_model=MemoryRecord)
async def patch_memory(
    memory_id: UUID,
    request: UpdateMemoryRequest,
    req: Request,
    session_id: str = Query(default="default-session", description="Session identifier"),
    principal: UserPrincipal = Depends(get_current_principal)
):
    """Update fields on a specific memory record, enforcing session scope."""
    valid_sid = validate_session_id(session_id, principal)
    try:
        updated = await update_memory(
            session_id=valid_sid,
            memory_id=memory_id,
            content=request.content,
            confidence_score=request.confidence_score,
            category=request.category,
            is_active=request.is_active
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Memory not found or does not belong to this session.")
        return updated
    except HTTPException:
        raise
    except Exception as e:
        raise safe_internal_error(e, f"Error updating memory {memory_id}", req)

@app.delete("/api/memories/{memory_id}", response_model=DeleteResponse)
async def remove_memory(
    memory_id: UUID,
    req: Request,
    session_id: str = Query(default="default-session", description="Session identifier"),
    principal: UserPrincipal = Depends(get_current_principal)
):
    valid_sid = validate_session_id(session_id, principal)
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




