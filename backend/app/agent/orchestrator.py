"""
MEMORA AI — Central Agent Orchestrator
Coordinates intent analysis, memory retrieval, planning, validation, controlled execution, and approvals.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID, uuid4
from app.database import get_db_pool
from app.agent.models import (
    AgentTask,
    AgentPlan,
    AgentPlanStep,
    AgentTaskCheckpoint,
    TaskStatus,
    StepStatus,
    ToolPermission,
    ApprovalStatus,
    ErrorClassification,
    AgentTaskResponse,
    AgentExecutionEvent,
    ApprovalRequest,
    StaleWorkerError,
    TaskFailureDetails,
    validate_task_transition
)
from app.agent.intent_analyzer import analyze_intent
from app.agent.planner import generate_plan
from app.agent.plan_validator import validate_plan
from app.agent.policy_engine import policy_engine
from app.agent.approval_manager import (
    create_approval_request,
    bind_approval_to_task,
    validate_and_consume_approval,
    reject_approval
)
from app.agent.execution_engine import execute_step
from app.agent.checkpoint_manager import checkpoint_manager
from app.agent.response_composer import compose_agent_response
from app.agent.worker_identity import WorkerIdentity
from app.agent.tools.registry import tool_registry
from app.services.hybrid_retriever import retrieve_hybrid_memories
from app.config import settings

logger = logging.getLogger(__name__)

MAX_TASK_TIMEOUT_SECONDS = 60.0
MAX_TOOL_EXECUTIONS_PER_TASK = 5

class AgentOrchestrator:
    """Unified single-orchestrator controlling memory-aware task execution."""

    def __init__(self):
        self._active_tasks: Dict[UUID, asyncio.Task] = {}

    async def run_agent_task(
        self,
        message: str = "",
        session_id: str = "default-session",
        user_request: Optional[str] = None,
        require_approval: Optional[bool] = None,
        max_steps: int = 6
    ) -> AgentTaskResponse:
        """Alias for run_task supporting message, session_id, require_approval, and max_steps keyword arguments."""
        req = message or user_request or ""
        return await self.run_task(
            session_id=session_id,
            user_request=req,
            require_approval=require_approval,
            max_steps=max_steps
        )

    async def create_task(
        self,
        session_id: str = "default-session",
        user_request: str = "",
        message: Optional[str] = None,
        require_approval: Optional[bool] = None,
        max_steps: int = 6
    ) -> Tuple[AgentTaskResponse, Optional[List[Any]]]:
        """
        Durable task initialization:
        1. Retrieve relevant memories and analyze intent concurrently.
        2. Plan and validate execution steps.
        3. Persist task and initial checkpoints transactionally in Neon PostgreSQL.
        4. Return initial task state without executing steps.
        """
        req = user_request or message or ""
        clean_session = session_id.strip() if session_id else "default-session"
        clean_request = req.strip()

        # Determine effective require_approval setting
        prompt_lower = clean_request.lower()
        has_explicit_approval_cue = any(phrase in prompt_lower for phrase in [
            "require approval", "with approval", "ask for approval", "await approval", "require confirmation"
        ])
        if require_approval is not None:
            effective_require_approval = require_approval or has_explicit_approval_cue
        elif has_explicit_approval_cue:
            effective_require_approval = True
        else:
            effective_require_approval = True

        task_id = uuid4()
        now = datetime.now(timezone.utc)

        # 1 & 2. Concurrently retrieve relevant user memories and analyze intent
        recalled_memories_task = retrieve_hybrid_memories(
            session_id=clean_session,
            query=clean_request,
            limit=4
        )
        intent_task = analyze_intent(clean_request)
        recalled_memories, intent_data = await asyncio.gather(
            recalled_memories_task,
            intent_task
        )
        task_type = intent_data.get("intent", "general")

        if task_type == "disallowed":
            task = AgentTask(
                id=task_id,
                session_id=clean_session,
                user_request=clean_request,
                task_type="disallowed",
                status=TaskStatus.FAILED,
                result_summary="Request was blocked by security policy: arbitrary code, shell, or unauthorized commands are forbidden.",
                created_at=now,
                updated_at=now,
                completed_at=now
            )
            await self._persist_new_task(task)
            reply = "I cannot execute this request. MEMORA AI enforces strict security policies that block arbitrary code, shell commands, and raw database access."
            return AgentTaskResponse(
                task=task,
                reply=reply,
                memories_used=[],
                tools_executed=[],
                execution_timeline=[]
            ), recalled_memories

        # 3. Generate plan
        proposed_plan = await generate_plan(
            user_request=clean_request,
            retrieved_memories=recalled_memories,
            max_steps=max_steps
        )

        # 3b. Check for clarification requirement
        if proposed_plan.requires_clarification:
            task = AgentTask(
                id=task_id,
                session_id=clean_session,
                user_request=clean_request,
                task_type=task_type,
                plan=proposed_plan,
                status=TaskStatus.AWAITING_CLARIFICATION,
                requires_clarification=True,
                clarification_prompt=proposed_plan.clarification_prompt,
                result_summary=proposed_plan.clarification_prompt,
                created_at=now,
                updated_at=now,
                completed_at=None
            )
            await self._persist_new_task(task)
            reply = proposed_plan.clarification_prompt or "Your objective appears ambiguous or underspecified. Please specify what you would like to achieve."
            return AgentTaskResponse(
                task=task,
                reply=reply,
                memories_used=[m.model_dump(mode="json") for m in recalled_memories],
                tools_executed=[],
                execution_timeline=[]
            ), recalled_memories

        # 4. Validate plan authoritatively
        is_valid, plan, validation_error = validate_plan(proposed_plan, require_approval=effective_require_approval)
        if not is_valid:
            task = AgentTask(
                id=task_id,
                session_id=clean_session,
                user_request=clean_request,
                task_type=task_type,
                plan=proposed_plan,
                status=TaskStatus.FAILED,
                result_summary=f"Plan validation failed: {validation_error}",
                created_at=now,
                updated_at=now,
                completed_at=now
            )
            await self._persist_new_task(task)
            reply = f"Task planning failed validation: {validation_error}"
            return AgentTaskResponse(
                task=task,
                reply=reply,
                memories_used=[m.model_dump(mode="json") for m in recalled_memories],
                tools_executed=[],
                execution_timeline=[]
            ), recalled_memories

        # 5. Persist valid task
        task = AgentTask(
            id=task_id,
            session_id=clean_session,
            user_request=clean_request,
            task_type=task_type,
            plan=plan,
            status=TaskStatus.RUNNING,
            created_at=now,
            updated_at=now
        )
        await self._persist_new_task(task)
        await checkpoint_manager.init_task_checkpoints(task.id, task.session_id, plan)
        checkpoints = await checkpoint_manager.get_task_checkpoints(task.id, task.session_id)
        task.checkpoints = checkpoints

        reply = f"Task plan created with {len(plan.steps)} steps. Initialized for execution."
        return AgentTaskResponse(
            task=task,
            reply=reply,
            memories_used=[m.model_dump(mode="json") for m in recalled_memories],
            tools_executed=[],
            execution_timeline=[],
            checkpoints=checkpoints
        ), recalled_memories

    async def run_task(
        self,
        session_id: str = "default-session",
        user_request: str = "",
        message: Optional[str] = None,
        require_approval: Optional[bool] = None,
        max_steps: int = 6
    ) -> AgentTaskResponse:
        """
        Execute an agent task:
        1. Initialize and plan task in PostgreSQL.
        2. Execute plan steps within bounded execution budget.
        """
        init_resp, recalled_memories = await self.create_task(
            session_id=session_id,
            user_request=user_request,
            message=message,
            require_approval=require_approval,
            max_steps=max_steps
        )
        if init_resp.task and init_resp.task.status == TaskStatus.RUNNING:
            return await self._execute_plan_steps(init_resp.task, recalled_memories)
        return init_resp

    def _safe_compose_response(
        self,
        task: AgentTask,
        recalled_memories: Optional[List[Any]] = None
    ) -> str:
        """Compose transparent human-readable response with deterministic fallback so synthesis failure never corrupts or repeats a task."""
        try:
            return compose_agent_response(task, recalled_memories)
        except Exception as e:
            logger.error(f"Response synthesis encountered an error for task {task.id}: {e}. Generating deterministic fallback.")
            plan = task.plan
            lines = [f"### 📋 Task: {plan.title if plan else task.user_request}"]
            lines.append(f"**Status:** `{task.status.value.upper()}`")
            if task.result_summary:
                lines.append(f"**Summary:** {task.result_summary}")
            if plan and plan.steps:
                lines.append("\n**Steps:**")
                for s in plan.steps:
                    icon = "✅" if s.status in (StepStatus.SUCCEEDED, StepStatus.COMPLETED) else ("❌" if s.status == StepStatus.FAILED else "⏳")
                    lines.append(f"- {icon} **{s.step_id}** ({s.tool_name or 'reasoning'}): {s.description}")
                    if s.result:
                        try:
                            lines.append(f"  *Result:* `{json.dumps(s.result)[:150]}`")
                        except Exception:
                            lines.append(f"  *Result:* `{str(s.result)[:150]}`")
            return "\n".join(lines)

    async def _execute_single_step(
        self,
        task: AgentTask,
        step: AgentPlanStep,
        worker_id: str,
        lease_generation: int,
        lease_seconds: int,
        existing_checkpoints: List[AgentTaskCheckpoint],
        tools_executed: List[str],
        timeline: List[Dict[str, Any]],
        recalled_memories: Optional[List[Any]] = None
    ) -> Tuple[bool, Optional[AgentTaskResponse]]:
        """Execute a single step with idempotency, heartbeat lease renewal, and error handling."""
        matching_cp = next((c for c in existing_checkpoints if c.step_id == step.step_id), None)

        # 1. Skip already succeeded step (Idempotency and duplicate prevention)
        if step.status in (StepStatus.SUCCEEDED, StepStatus.COMPLETED) or (matching_cp and matching_cp.status in (StepStatus.SUCCEEDED, StepStatus.COMPLETED)):
            step.status = StepStatus.SUCCEEDED
            if matching_cp and matching_cp.result is not None:
                step.result = matching_cp.result
            if step.tool_name:
                tools_executed.append(step.tool_name)
            timeline.append({
                "step_id": step.step_id,
                "tool": step.tool_name,
                "status": "succeeded",
                "duration_ms": 0,
                "cached_checkpoint": True
            })
            return True, None

        # 1b. Check if prior run crashed while in DISPATCHED or RUNNING (downstream reconciliation)
        if matching_cp and matching_cp.status in (StepStatus.DISPATCHED, StepStatus.RUNNING):
            tool = tool_registry.get_tool(step.tool_name) if step.tool_name else None
            if tool and not tool.is_idempotent:
                logger.info(f"Step {step.step_id} ({tool.name}) was in {matching_cp.status.value} prior to crash. Initiating downstream reconciliation.")
                reconciled_res = await tool.reconcile(
                    session_id=task.session_id,
                    idempotency_key=matching_cp.idempotency_key,
                    **step.arguments
                )
                if reconciled_res:
                    logger.info(f"Reconciliation succeeded for step {step.step_id}: external operation confirmed.")
                    step.status = StepStatus.SUCCEEDED
                    step.result = reconciled_res
                    await checkpoint_manager.update_checkpoint(
                        task_id=task.id,
                        session_id=task.session_id,
                        step_id=step.step_id,
                        status=StepStatus.SUCCEEDED,
                        result=reconciled_res,
                        external_operation_id=reconciled_res.get("note_id") or reconciled_res.get("external_operation_id"),
                        worker_id=worker_id,
                        lease_generation=lease_generation,
                        completed=True
                    )
                    tools_executed.append(step.tool_name)
                    timeline.append({
                        "step_id": step.step_id,
                        "tool": step.tool_name,
                        "status": "succeeded",
                        "duration_ms": 0,
                        "reconciled": True
                    })
                    return True, None
                else:
                    # Uncertain outcome: do NOT blindly replay!
                    logger.warning(f"Reconciliation uncertain for step {step.step_id}. Halting and transitioning to NEEDS_RECONCILIATION.")
                    step.status = StepStatus.NEEDS_RECONCILIATION
                    task.status = TaskStatus.NEEDS_RECONCILIATION
                    task.result_summary = f"Step {step.step_id} ({tool.name}) was interrupted during execution and downstream status could not be confirmed. Manual reconciliation required."
                    await checkpoint_manager.update_checkpoint(
                        task_id=task.id,
                        session_id=task.session_id,
                        step_id=step.step_id,
                        status=StepStatus.NEEDS_RECONCILIATION,
                        error_message=task.result_summary,
                        error_classification=ErrorClassification.UNKNOWN_OUTCOME,
                        worker_id=worker_id,
                        lease_generation=lease_generation,
                        completed=True
                    )
                    await self._update_task_record(task, worker_id=worker_id, lease_generation=lease_generation)
                    checkpoints = await checkpoint_manager.get_task_checkpoints(task.id, task.session_id)
                    task.checkpoints = checkpoints
                    reply = self._safe_compose_response(task, recalled_memories)
                    return False, AgentTaskResponse(
                        task=task,
                        reply=reply,
                        tools_executed=tools_executed,
                        execution_timeline=timeline,
                        checkpoints=checkpoints
                    )

        # 2. Check backend permissions (human-in-the-loop gate)
        if step.permission == ToolPermission.APPROVAL_REQUIRED:
            approval_req = create_approval_request(
                task_id=task.id,
                step_id=step.step_id,
                tool_name=step.tool_name or "create_note",
                arguments=step.arguments
            )
            step.status = StepStatus.AWAITING_APPROVAL
            task.status = TaskStatus.AWAITING_APPROVAL
            task.pending_approval = approval_req
            task.approval_token = approval_req.approval_token
            task.approval_status = ApprovalStatus.PENDING.value
            task.approval_expires_at = approval_req.expires_at

            await bind_approval_to_task(task.id, task.session_id, approval_req)
            await checkpoint_manager.update_checkpoint(
                task_id=task.id,
                session_id=task.session_id,
                step_id=step.step_id,
                status=StepStatus.AWAITING_APPROVAL,
                worker_id=worker_id,
                lease_generation=lease_generation
            )
            await self._update_task_record(task, worker_id=worker_id, lease_generation=lease_generation)

            checkpoints = await checkpoint_manager.get_task_checkpoints(task.id, task.session_id)
            task.checkpoints = checkpoints
            reply = self._safe_compose_response(task, recalled_memories)
            return False, AgentTaskResponse(
                task=task,
                reply=reply,
                memories_used=[m.model_dump(mode="json") if hasattr(m, "model_dump") else m for m in (recalled_memories or [])],
                tools_executed=tools_executed,
                execution_timeline=timeline,
                checkpoints=checkpoints
            )

        # 3. Persist execution intent before dispatch
        step_idempotency_key = step.idempotency_key or f"{task.id}:{step.step_id}"
        step.idempotency_key = step_idempotency_key
        await checkpoint_manager.update_checkpoint(
            task_id=task.id,
            session_id=task.session_id,
            step_id=step.step_id,
            status=StepStatus.DISPATCHED,
            idempotency_key=step_idempotency_key,
            worker_id=worker_id,
            lease_generation=lease_generation,
            started=True,
            execution_intent_persisted=True
        )

        # 4. Checkpointed Execution & Retry loop with background heartbeat renewal
        max_attempts = 1 + (step.max_retries if step.is_idempotent else 0)
        attempt = 0
        step_success = False
        last_result = None

        while attempt < max_attempts:
            attempt += 1

            if task.status == TaskStatus.CANCEL_REQUESTED:
                step.status = StepStatus.CANCELLED
                await checkpoint_manager.update_checkpoint(
                    task_id=task.id,
                    session_id=task.session_id,
                    step_id=step.step_id,
                    status=StepStatus.CANCELLED,
                    worker_id=worker_id,
                    lease_generation=lease_generation,
                    completed=True
                )
                return False, None

            heartbeat_stop = asyncio.Event()

            async def _bg_heartbeat():
                while not heartbeat_stop.is_set():
                    try:
                        await asyncio.sleep(min(15, max(1, lease_seconds // 3)))
                        if heartbeat_stop.is_set():
                            break
                        ok = await self.renew_heartbeat(
                            task_id=task.id,
                            session_id=task.session_id,
                            worker_id=worker_id,
                            lease_generation=lease_generation,
                            lease_seconds=lease_seconds
                        )
                        if not ok:
                            logger.warning(f"Periodic heartbeat renewal failed for task {task.id}.")
                            break
                    except asyncio.CancelledError:
                        break
                    except Exception as e:
                        logger.error(f"Heartbeat loop exception: {e}")

            hb_task = asyncio.create_task(_bg_heartbeat())

            try:
                result = await execute_step(
                    task_id=task.id,
                    session_id=task.session_id,
                    step=step,
                    idempotency_key=step_idempotency_key
                )
            except asyncio.CancelledError:
                logger.warning(f"Step {step.step_id} received in-flight cancellation signal.")
                tool = tool_registry.get_tool(step.tool_name) if step.tool_name else None
                if tool and not tool.is_idempotent:
                    reconciled = await tool.reconcile(session_id=task.session_id, idempotency_key=step_idempotency_key, **step.arguments)
                    if reconciled:
                        step.status = StepStatus.SUCCEEDED
                        step.result = reconciled
                        task.status = TaskStatus.SUCCEEDED
                        task.result_summary = "Operation completed before cancellation could take effect."
                        await checkpoint_manager.update_checkpoint(
                            task_id=task.id,
                            session_id=task.session_id,
                            step_id=step.step_id,
                            status=StepStatus.SUCCEEDED,
                            result=reconciled,
                            worker_id=worker_id,
                            lease_generation=lease_generation,
                            completed=True
                        )
                    else:
                        step.status = StepStatus.NEEDS_RECONCILIATION
                        task.status = TaskStatus.NEEDS_RECONCILIATION
                        task.result_summary = "In-flight cancellation during non-idempotent operation requires reconciliation."
                        await checkpoint_manager.update_checkpoint(
                            task_id=task.id,
                            session_id=task.session_id,
                            step_id=step.step_id,
                            status=StepStatus.NEEDS_RECONCILIATION,
                            error_message="In-flight cancellation during non-idempotent operation requires reconciliation.",
                            error_classification=ErrorClassification.UNKNOWN_OUTCOME,
                            worker_id=worker_id,
                            lease_generation=lease_generation,
                            completed=True
                        )
                else:
                    step.status = StepStatus.CANCELLED
                    task.status = TaskStatus.CANCELLED
                    task.result_summary = "Task was cancelled by user."
                    await checkpoint_manager.update_checkpoint(
                        task_id=task.id,
                        session_id=task.session_id,
                        step_id=step.step_id,
                        status=StepStatus.CANCELLED,
                        worker_id=worker_id,
                        lease_generation=lease_generation,
                        completed=True
                    )
                task.completed_at = datetime.now(timezone.utc)
                await self._update_task_record(task, worker_id=worker_id, lease_generation=lease_generation)
                raise
            finally:
                heartbeat_stop.set()
                hb_task.cancel()

            last_result = result
            await self.renew_heartbeat(
                task_id=task.id,
                session_id=task.session_id,
                worker_id=worker_id,
                lease_generation=lease_generation,
                lease_seconds=lease_seconds
            )

            if result.success:
                step_success = True
                step.status = StepStatus.SUCCEEDED
                step.result = result.result
                await checkpoint_manager.update_checkpoint(
                    task_id=task.id,
                    session_id=task.session_id,
                    step_id=step.step_id,
                    status=StepStatus.SUCCEEDED,
                    result=result.result,
                    external_operation_id=result.external_operation_id,
                    worker_id=worker_id,
                    lease_generation=lease_generation,
                    completed=True
                )
                break
            else:
                err_cls = result.error_classification or ErrorClassification.PERMANENT
                if err_cls == ErrorClassification.UNKNOWN_OUTCOME or (not step.is_idempotent and err_cls not in (ErrorClassification.VALIDATION_FAILURE, ErrorClassification.AUTHORIZATION_FAILURE)):
                    logger.warning(f"Step {step.step_id} non-idempotent operation encountered unknown outcome. Transitioning to NEEDS_RECONCILIATION.")
                    step.status = StepStatus.NEEDS_RECONCILIATION
                    task.status = TaskStatus.NEEDS_RECONCILIATION
                    task.result_summary = f"Step {step.step_id} requires manual reconciliation: {result.error}"
                    await checkpoint_manager.update_checkpoint(
                        task_id=task.id,
                        session_id=task.session_id,
                        step_id=step.step_id,
                        status=StepStatus.NEEDS_RECONCILIATION,
                        error_message=result.error,
                        error_classification=err_cls,
                        worker_id=worker_id,
                        lease_generation=lease_generation,
                        completed=True
                    )
                    await self._update_task_record(task, worker_id=worker_id, lease_generation=lease_generation)
                    checkpoints = await checkpoint_manager.get_task_checkpoints(task.id, task.session_id)
                    task.checkpoints = checkpoints
                    reply = self._safe_compose_response(task, recalled_memories)
                    return False, AgentTaskResponse(
                        task=task,
                        reply=reply,
                        tools_executed=tools_executed,
                        execution_timeline=timeline,
                        checkpoints=checkpoints
                    )

                if err_cls in (ErrorClassification.TRANSIENT, ErrorClassification.TIMEOUT) and step.is_idempotent and attempt < max_attempts:
                    logger.info(f"Transient error at step {step.step_id}. Retrying attempt {attempt}/{step.max_retries}...")
                    step.status = StepStatus.RETRYING
                    step.retry_count = attempt
                    await checkpoint_manager.update_checkpoint(
                        task_id=task.id,
                        session_id=task.session_id,
                        step_id=step.step_id,
                        status=StepStatus.RETRYING,
                        error_message=result.error,
                        error_classification=err_cls,
                        worker_id=worker_id,
                        lease_generation=lease_generation,
                        increment_retry=True
                    )
                    backoff = min(0.25 * (2 ** (attempt - 1)), 2.0)
                    await asyncio.sleep(backoff)
                    continue
                else:
                    break

        if step.tool_name:
            tools_executed.append(step.tool_name)

        timeline.append({
            "step_id": step.step_id,
            "tool": step.tool_name,
            "status": step.status.value,
            "duration_ms": last_result.duration_ms if last_result else None
        })

        if not step_success:
            err_cls = last_result.error_classification if last_result else ErrorClassification.PERMANENT
            step.status = StepStatus.FAILED
            step.error = last_result.error if last_result else "Execution failed"
            await checkpoint_manager.update_checkpoint(
                task_id=task.id,
                session_id=task.session_id,
                step_id=step.step_id,
                status=StepStatus.FAILED,
                error_message=step.error,
                error_classification=err_cls,
                worker_id=worker_id,
                lease_generation=lease_generation,
                completed=True
            )
            task.failure_details = TaskFailureDetails(
                error_category=err_cls.value if hasattr(err_cls, "value") else str(err_cls),
                failed_step_id=step.step_id,
                tool_name=step.tool_name,
                failure_timestamp=datetime.now(timezone.utc),
                is_retryable=(err_cls in (ErrorClassification.TRANSIENT, ErrorClassification.TIMEOUT) and step.is_idempotent),
                attempt_count=attempt,
                safe_error_message=step.error,
                correlation_id=str(task.id)
            )
            return False, None

        return True, None

    async def _execute_plan_steps(
        self,
        task: AgentTask,
        recalled_memories: Optional[List[Any]] = None
    ) -> AgentTaskResponse:
        """Run through plan steps in dependency-aware topological waves with durable checkpointing, worker leasing, retries, and failure reconciliation."""
        plan = task.plan
        if not plan:
            task.status = TaskStatus.FAILED
            await self._update_task_record(task)
            return AgentTaskResponse(task=task, reply="No valid plan found for task.")

        worker_id = WorkerIdentity.get_worker_id()
        lease_seconds = getattr(settings, "WORKER_LEASE_SECONDS", 60)
        claimed, lease_generation, claim_err = await self.claim_task_lease(
            task.id, task.session_id, worker_id=worker_id, lease_seconds=lease_seconds
        )
        if not claimed:
            logger.error(f"Cannot execute task {task.id}: {claim_err}")
            raise StaleWorkerError(f"Cannot execute task: {claim_err}")

        task.worker_id = worker_id
        task.lease_generation = lease_generation

        # Track active task for in-flight cancellation
        current_async_task = asyncio.current_task()
        if current_async_task:
            self._active_tasks[task.id] = current_async_task

        try:
            tool_exec_count = 0
            timeline = []
            tools_executed = []

            # Load existing checkpoints to prevent duplicate execution of already-succeeded steps
            existing_checkpoints = await checkpoint_manager.get_task_checkpoints(task.id, task.session_id)
            succeeded_step_ids = {
                cp.step_id for cp in existing_checkpoints
                if cp.status in (StepStatus.SUCCEEDED, StepStatus.COMPLETED)
            }
            for step in plan.steps:
                matching_cp = next((c for c in existing_checkpoints if c.step_id == step.step_id), None)
                if matching_cp and matching_cp.status in (StepStatus.SUCCEEDED, StepStatus.COMPLETED):
                    step.status = StepStatus.SUCCEEDED
                    if matching_cp.result is not None:
                        step.result = matching_cp.result
                    succeeded_step_ids.add(step.step_id)
                    if step.tool_name and step.tool_name not in tools_executed:
                        tools_executed.append(step.tool_name)
                    timeline.append({
                        "step_id": step.step_id,
                        "tool": step.tool_name,
                        "status": "succeeded",
                        "duration_ms": 0,
                        "cached_checkpoint": True
                    })

            start_loop_time = asyncio.get_event_loop().time()
            slice_budget_seconds = float(getattr(settings, "MAX_TASK_EXECUTION_BUDGET_SECONDS", 120.0))

            while True:
                if (asyncio.get_event_loop().time() - start_loop_time) >= slice_budget_seconds:
                    logger.info(f"Task {task.id} execution reached slice time budget ({slice_budget_seconds}s). Halting bounded slice.")
                    break

                if task.status == TaskStatus.CANCEL_REQUESTED:
                    task.status = TaskStatus.CANCELLED
                    task.completed_at = datetime.now(timezone.utc)
                    task.result_summary = "Task was cancelled by user."
                    await checkpoint_manager.cancel_pending_checkpoints(task.id, task.session_id)
                    await self._update_task_record(task, worker_id=worker_id, lease_generation=lease_generation)
                    break

                # Mark any pending step whose dependencies failed/skipped as SKIPPED
                failed_or_skipped_ids = {
                    s.step_id for s in plan.steps
                    if s.status in (StepStatus.FAILED, StepStatus.SKIPPED, StepStatus.CANCELLED, StepStatus.NEEDS_RECONCILIATION)
                }
                for s in plan.steps:
                    if s.status in (StepStatus.PENDING, StepStatus.READY):
                        if any(dep in failed_or_skipped_ids for dep in s.dependencies):
                            s.status = StepStatus.SKIPPED
                            s.error = "Skipped due to failure or cancellation of prerequisite step."
                            await checkpoint_manager.update_checkpoint(
                                task_id=task.id,
                                session_id=task.session_id,
                                step_id=s.step_id,
                                status=StepStatus.SKIPPED,
                                error_message=s.error,
                                worker_id=worker_id,
                                lease_generation=lease_generation,
                                completed=True
                            )
                            timeline.append({"step_id": s.step_id, "status": "skipped"})

                # Find ready steps whose dependencies are all satisfied
                ready_steps = [
                    s for s in plan.steps
                    if s.status in (StepStatus.PENDING, StepStatus.READY)
                    and all(dep in succeeded_step_ids for dep in s.dependencies)
                ]

                if not ready_steps:
                    # No more reachable steps
                    break

                # Enforce max tool limit
                tool_exec_count += len(ready_steps)
                if tool_exec_count > MAX_TOOL_EXECUTIONS_PER_TASK * 2:
                    task.status = TaskStatus.FAILED
                    task.result_summary = f"Exceeded maximum limit of {MAX_TOOL_EXECUTIONS_PER_TASK} tool executions per task."
                    task.completed_at = datetime.now(timezone.utc)
                    break

                # Check for approval-required steps in ready steps
                approval_steps = [s for s in ready_steps if s.permission == ToolPermission.APPROVAL_REQUIRED]
                automatic_steps = [s for s in ready_steps if s.permission != ToolPermission.APPROVAL_REQUIRED]

                if approval_steps and not automatic_steps:
                    # Halt on approval step
                    step_to_approve = approval_steps[0]
                    ok, early_resp = await self._execute_single_step(
                        task=task,
                        step=step_to_approve,
                        worker_id=worker_id,
                        lease_generation=lease_generation,
                        lease_seconds=lease_seconds,
                        existing_checkpoints=existing_checkpoints,
                        tools_executed=tools_executed,
                        timeline=timeline,
                        recalled_memories=recalled_memories
                    )
                    if early_resp:
                        return early_resp
                    break

                steps_to_run = automatic_steps if automatic_steps else [approval_steps[0]]

                if len(steps_to_run) == 1:
                    ok, early_resp = await self._execute_single_step(
                        task=task,
                        step=steps_to_run[0],
                        worker_id=worker_id,
                        lease_generation=lease_generation,
                        lease_seconds=lease_seconds,
                        existing_checkpoints=existing_checkpoints,
                        tools_executed=tools_executed,
                        timeline=timeline,
                        recalled_memories=recalled_memories
                    )
                    if early_resp:
                        return early_resp
                    if ok:
                        succeeded_step_ids.add(steps_to_run[0].step_id)
                    else:
                        task.status = TaskStatus.FAILED
                        task.completed_at = datetime.now(timezone.utc)
                        task.result_summary = f"Execution failed at {steps_to_run[0].step_id} ({steps_to_run[0].tool_name}): {steps_to_run[0].error or 'Unknown error'}"
                        # Continue loop to allow independent branches to finish while skipping downstream of failed step
                else:
                    # Execute independent steps concurrently via asyncio.gather
                    logger.info(f"Executing {len(steps_to_run)} independent steps concurrently: {[s.step_id for s in steps_to_run]}")
                    results = await asyncio.gather(*[
                        self._execute_single_step(
                            task=task,
                            step=st,
                            worker_id=worker_id,
                            lease_generation=lease_generation,
                            lease_seconds=lease_seconds,
                            existing_checkpoints=existing_checkpoints,
                            tools_executed=tools_executed,
                            timeline=timeline,
                            recalled_memories=recalled_memories
                        )
                        for st in steps_to_run
                    ])
                    batch_failed = False
                    for (ok, early_resp), st in zip(results, steps_to_run):
                        if early_resp:
                            return early_resp
                        if ok:
                            succeeded_step_ids.add(st.step_id)
                        else:
                            batch_failed = True
                    if batch_failed:
                        task.status = TaskStatus.FAILED
                        task.completed_at = datetime.now(timezone.utc)
                        task.result_summary = "One or more independent steps failed during execution."
                        # Continue loop to allow independent branches to finish while skipping downstream of failed step

            # Final pass: mark any remaining pending step whose prerequisites failed/cancelled as SKIPPED
            failed_or_skipped_ids = {
                s.step_id for s in plan.steps
                if s.status in (StepStatus.FAILED, StepStatus.SKIPPED, StepStatus.CANCELLED, StepStatus.NEEDS_RECONCILIATION)
            }
            if failed_or_skipped_ids:
                for s in plan.steps:
                    if s.status in (StepStatus.PENDING, StepStatus.READY):
                        if any(dep in failed_or_skipped_ids for dep in s.dependencies):
                            s.status = StepStatus.SKIPPED
                            s.error = "Skipped due to failure or cancellation of prerequisite step."
                            await checkpoint_manager.update_checkpoint(
                                task_id=task.id,
                                session_id=task.session_id,
                                step_id=s.step_id,
                                status=StepStatus.SKIPPED,
                                error_message=s.error,
                                worker_id=worker_id,
                                lease_generation=lease_generation,
                                completed=True
                            )
                            timeline.append({"step_id": s.step_id, "status": "skipped"})
                            failed_or_skipped_ids.add(s.step_id)

            # Final status determination
            all_steps_done = all(s.status in (StepStatus.SUCCEEDED, StepStatus.COMPLETED) for s in plan.steps)
            if all_steps_done:
                task.status = TaskStatus.SUCCEEDED
                task.completed_at = datetime.now(timezone.utc)
                task.result_summary = f"All {len(plan.steps)} plan steps executed successfully."
            elif any(s.status == StepStatus.NEEDS_RECONCILIATION for s in plan.steps):
                task.status = TaskStatus.NEEDS_RECONCILIATION
            elif any(s.status == StepStatus.AWAITING_APPROVAL for s in plan.steps):
                task.status = TaskStatus.AWAITING_APPROVAL
            elif any(s.status == StepStatus.CANCELLED for s in plan.steps):
                task.status = TaskStatus.CANCELLED
            elif any(s.status == StepStatus.FAILED for s in plan.steps):
                task.status = TaskStatus.FAILED

            await self._update_task_record(task, worker_id=worker_id, lease_generation=lease_generation)
            checkpoints = await checkpoint_manager.get_task_checkpoints(task.id, task.session_id)
            task.checkpoints = checkpoints
            reply = self._safe_compose_response(task, recalled_memories)
            return AgentTaskResponse(
                task=task,
                reply=reply,
                memories_used=[m.model_dump(mode="json") if hasattr(m, "model_dump") else m for m in (recalled_memories or [])],
                tools_executed=tools_executed,
                execution_timeline=timeline,
                checkpoints=checkpoints
            )
        finally:
            self._active_tasks.pop(task.id, None)
        reply = self._safe_compose_response(task, recalled_memories)
        return AgentTaskResponse(
            task=task,
            reply=reply,
            memories_used=[m.model_dump(mode="json") if hasattr(m, "model_dump") else m for m in (recalled_memories or [])],
            tools_executed=tools_executed,
            execution_timeline=timeline,
            checkpoints=checkpoints
        )

    async def approve_task(
        self,
        session_id: str,
        task_id: UUID,
        approval_token: str
    ) -> AgentTaskResponse:
        """Validate approval, mark token consumed, and resume execution."""
        clean_session = session_id.strip()

        # 1. Server-side validation of approval token & session ownership
        is_valid, err = await validate_and_consume_approval(task_id, clean_session, approval_token)
        if not is_valid:
            # Check if this is a safe recovery from an already-approved crash scenario
            task = await self.get_task(clean_session, task_id)
            if task and task.approval_status == ApprovalStatus.APPROVED and task.status in (TaskStatus.RUNNING, TaskStatus.AWAITING_APPROVAL):
                logger.info(f"Task {task_id} was already approved; resuming execution from checkpoint.")
            else:
                if "access denied" in (err or "").lower() or "mismatch" in (err or "").lower():
                    raise PermissionError(f"Approval validation failed: {err}")
                raise ValueError(f"Approval validation failed: {err}")
        else:
            task = await self.get_task(clean_session, task_id)

        if not task or not task.plan:
            return AgentTaskResponse(task=task, reply="Task or plan could not be restored.")

        task.status = TaskStatus.RUNNING
        task.pending_approval = None

        # Resume execution: find awaiting_approval step and mark it ready
        for step in task.plan.steps:
            if step.status == StepStatus.AWAITING_APPROVAL:
                step.status = StepStatus.PENDING
                step.permission = ToolPermission.AUTOMATIC

        await self._update_task_record(task)
        return await self._execute_plan_steps(task)

    approve_and_resume = approve_task

    async def execute_task_slice(
        self,
        session_id: str,
        task_id: UUID,
        worker_id: Optional[str] = None,
        max_duration_seconds: float = 20.0,
        max_steps: int = 1
    ) -> AgentTaskResponse:
        """
        Execute a single bounded slice of an agent task in a serverless environment.
        1. Validates task existence, ownership, and non-terminal status.
        2. Claims worker lease with monotonic fencing token.
        3. Identifies next ready steps in DAG order.
        4. Executes ready step(s) with checkpointing and error handling.
        5. Updates task status and returns immediately.
        """
        clean_session = session_id.strip() if session_id else "default-session"
        if isinstance(task_id, str):
            task_id = UUID(task_id)

        task = await self.get_task(clean_session, task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' not found for session '{clean_session}'.")

        checkpoints = await checkpoint_manager.get_task_checkpoints(task_id, clean_session)
        task.checkpoints = checkpoints

        # 1. Guard terminal states - cannot be reopened
        if task.status in (TaskStatus.SUCCEEDED, TaskStatus.COMPLETED):
            return AgentTaskResponse(
                task=task,
                reply=f"Task is already {task.status.value}.",
                checkpoints=checkpoints
            )
        if task.status == TaskStatus.CANCELLED:
            return AgentTaskResponse(
                task=task,
                reply="Task is cancelled.",
                checkpoints=checkpoints
            )
        if task.status == TaskStatus.FAILED:
            return AgentTaskResponse(
                task=task,
                reply=task.result_summary or "Task execution failed.",
                checkpoints=checkpoints
            )
        if task.status == TaskStatus.AWAITING_APPROVAL:
            return AgentTaskResponse(
                task=task,
                reply="Task is awaiting explicit user approval. Grant approval with signed token to proceed.",
                checkpoints=checkpoints
            )
        if task.status == TaskStatus.AWAITING_CLARIFICATION:
            return AgentTaskResponse(
                task=task,
                reply=task.clarification_prompt or "Task requires user clarification.",
                checkpoints=checkpoints
            )
        if task.status == TaskStatus.NEEDS_RECONCILIATION:
            return AgentTaskResponse(
                task=task,
                reply=task.result_summary or "Task requires manual reconciliation before continuation.",
                checkpoints=checkpoints
            )

        if not task.plan or not task.plan.steps:
            task.status = TaskStatus.FAILED
            task.result_summary = "Task has no executable plan."
            task.completed_at = datetime.now(timezone.utc)
            await self._update_task_record(task)
            return AgentTaskResponse(task=task, reply="No valid plan found for task.", checkpoints=checkpoints)

        # 2. Claim execution lease with fencing generation
        eff_worker_id = worker_id or WorkerIdentity.get_worker_id()
        lease_seconds = getattr(settings, "WORKER_LEASE_SECONDS", 60)
        claimed, lease_generation, claim_err = await self.claim_task_lease(
            task.id, task.session_id, worker_id=eff_worker_id, lease_seconds=lease_seconds
        )
        if not claimed:
            logger.warning(f"Cannot execute task slice for {task.id}: {claim_err}")
            raise StaleWorkerError(f"Cannot execute task slice: {claim_err}")

        task.worker_id = eff_worker_id
        task.lease_generation = lease_generation
        task.status = TaskStatus.RUNNING

        # 3. Track active task for cancellation
        current_async_task = asyncio.current_task()
        if current_async_task:
            self._active_tasks[task.id] = current_async_task

        try:
            tools_executed = []
            timeline = []

            # Sync plan steps with existing checkpoints
            succeeded_step_ids = {
                cp.step_id for cp in checkpoints
                if cp.status in (StepStatus.SUCCEEDED, StepStatus.COMPLETED)
            }
            for step in task.plan.steps:
                matching_cp = next((c for c in checkpoints if c.step_id == step.step_id), None)
                if matching_cp and matching_cp.status in (StepStatus.SUCCEEDED, StepStatus.COMPLETED):
                    step.status = StepStatus.SUCCEEDED
                    if matching_cp.result is not None:
                        step.result = matching_cp.result
                    succeeded_step_ids.add(step.step_id)

            # Check if cancellation requested
            if task.status == TaskStatus.CANCEL_REQUESTED:
                task.status = TaskStatus.CANCELLED
                task.completed_at = datetime.now(timezone.utc)
                task.result_summary = "Task was cancelled by user."
                await checkpoint_manager.cancel_pending_checkpoints(task.id, task.session_id)
                await self._update_task_record(task, worker_id=eff_worker_id, lease_generation=lease_generation)
                fresh_cp = await checkpoint_manager.get_task_checkpoints(task.id, task.session_id)
                task.checkpoints = fresh_cp
                return AgentTaskResponse(task=task, reply="Task was cancelled by user.", checkpoints=fresh_cp)

            # Mark skipped steps whose prerequisites failed or were cancelled
            failed_or_skipped_ids = {
                s.step_id for s in task.plan.steps
                if s.status in (StepStatus.FAILED, StepStatus.SKIPPED, StepStatus.CANCELLED, StepStatus.NEEDS_RECONCILIATION)
            }
            for s in task.plan.steps:
                if s.status in (StepStatus.PENDING, StepStatus.READY):
                    if any(dep in failed_or_skipped_ids for dep in s.dependencies):
                        s.status = StepStatus.SKIPPED
                        s.error = "Skipped due to failure or cancellation of prerequisite step."
                        await checkpoint_manager.update_checkpoint(
                            task_id=task.id,
                            session_id=task.session_id,
                            step_id=s.step_id,
                            status=StepStatus.SKIPPED,
                            error_message=s.error,
                            worker_id=eff_worker_id,
                            lease_generation=lease_generation,
                            completed=True
                        )
                        timeline.append({"step_id": s.step_id, "status": "skipped"})
                        failed_or_skipped_ids.add(s.step_id)

            # Find ready steps
            ready_steps = [
                s for s in task.plan.steps
                if s.status in (StepStatus.PENDING, StepStatus.READY)
                and all(dep in succeeded_step_ids for dep in s.dependencies)
            ]

            if not ready_steps:
                # No more reachable steps; determine final state
                all_done = all(s.status in (StepStatus.SUCCEEDED, StepStatus.COMPLETED) for s in task.plan.steps)
                if all_done:
                    task.status = TaskStatus.SUCCEEDED
                    task.completed_at = datetime.now(timezone.utc)
                    task.result_summary = f"All {len(task.plan.steps)} plan steps executed successfully."
                elif any(s.status == StepStatus.NEEDS_RECONCILIATION for s in task.plan.steps):
                    task.status = TaskStatus.NEEDS_RECONCILIATION
                elif any(s.status == StepStatus.FAILED for s in task.plan.steps):
                    task.status = TaskStatus.FAILED
                    task.completed_at = datetime.now(timezone.utc)
                await self._update_task_record(task, worker_id=eff_worker_id, lease_generation=lease_generation)
                fresh_cp = await checkpoint_manager.get_task_checkpoints(task.id, task.session_id)
                task.checkpoints = fresh_cp
                reply = self._safe_compose_response(task)
                return AgentTaskResponse(
                    task=task,
                    reply=reply,
                    checkpoints=fresh_cp,
                    execution_timeline=timeline
                )

            # Approval check on the first ready step
            approval_steps = [s for s in ready_steps if s.permission == ToolPermission.APPROVAL_REQUIRED]
            automatic_steps = [s for s in ready_steps if s.permission != ToolPermission.APPROVAL_REQUIRED]

            if approval_steps and not automatic_steps:
                step_to_approve = approval_steps[0]
                ok, early_resp = await self._execute_single_step(
                    task=task,
                    step=step_to_approve,
                    worker_id=eff_worker_id,
                    lease_generation=lease_generation,
                    lease_seconds=lease_seconds,
                    existing_checkpoints=checkpoints,
                    tools_executed=tools_executed,
                    timeline=timeline
                )
                if early_resp:
                    return early_resp

            steps_to_run = automatic_steps if automatic_steps else [approval_steps[0]]
            steps_in_slice = steps_to_run[:max_steps]

            if len(steps_in_slice) == 1:
                try:
                    ok, early_resp = await asyncio.wait_for(
                        self._execute_single_step(
                            task=task,
                            step=steps_in_slice[0],
                            worker_id=eff_worker_id,
                            lease_generation=lease_generation,
                            lease_seconds=lease_seconds,
                            existing_checkpoints=checkpoints,
                            tools_executed=tools_executed,
                            timeline=timeline
                        ),
                        timeout=max_duration_seconds
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"Task {task.id} step {steps_in_slice[0].step_id} timed out after {max_duration_seconds}s")
                    steps_in_slice[0].status = StepStatus.FAILED
                    steps_in_slice[0].error = f"Step execution timed out after {max_duration_seconds}s."
                    await checkpoint_manager.update_checkpoint(
                        task_id=task.id,
                        session_id=task.session_id,
                        step_id=steps_in_slice[0].step_id,
                        status=StepStatus.FAILED,
                        error_message=steps_in_slice[0].error,
                        worker_id=eff_worker_id,
                        lease_generation=lease_generation,
                        completed=True
                    )
                    task.status = TaskStatus.FAILED
                    task.completed_at = datetime.now(timezone.utc)
                    task.result_summary = f"Execution timed out at step {steps_in_slice[0].step_id} after {max_duration_seconds}s."
                    await self._update_task_record(task, worker_id=eff_worker_id, lease_generation=lease_generation)
                    fresh_cp = await checkpoint_manager.get_task_checkpoints(task.id, task.session_id)
                    task.checkpoints = fresh_cp
                    return AgentTaskResponse(
                        task=task,
                        reply=f"Step execution timed out after {max_duration_seconds}s. All prior checkpoints are safely preserved. You may retry this task.",
                        checkpoints=fresh_cp
                    )

                if early_resp:
                    return early_resp
                if ok:
                    succeeded_step_ids.add(steps_in_slice[0].step_id)
                else:
                    task.status = TaskStatus.FAILED
                    task.completed_at = datetime.now(timezone.utc)
                    task.result_summary = f"Execution failed at {steps_in_slice[0].step_id}: {steps_in_slice[0].error or 'Unknown error'}"
            else:
                try:
                    results = await asyncio.wait_for(
                        asyncio.gather(*[
                            self._execute_single_step(
                                task=task,
                                step=st,
                                worker_id=eff_worker_id,
                                lease_generation=lease_generation,
                                lease_seconds=lease_seconds,
                                existing_checkpoints=checkpoints,
                                tools_executed=tools_executed,
                                timeline=timeline
                            )
                            for st in steps_in_slice
                        ]),
                        timeout=max_duration_seconds
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"Task {task.id} batch slice timed out after {max_duration_seconds}s")
                    task.status = TaskStatus.FAILED
                    task.completed_at = datetime.now(timezone.utc)
                    task.result_summary = f"Batch slice timed out after {max_duration_seconds}s."
                    await self._update_task_record(task, worker_id=eff_worker_id, lease_generation=lease_generation)
                    fresh_cp = await checkpoint_manager.get_task_checkpoints(task.id, task.session_id)
                    task.checkpoints = fresh_cp
                    return AgentTaskResponse(
                        task=task,
                        reply=f"Batch execution timed out after {max_duration_seconds}s. You may retry this task.",
                        checkpoints=fresh_cp
                    )

                batch_failed = False
                for (ok, early_resp), st in zip(results, steps_in_slice):
                    if early_resp:
                        return early_resp
                    if ok:
                        succeeded_step_ids.add(st.step_id)
                    else:
                        batch_failed = True
                if batch_failed:
                    task.status = TaskStatus.FAILED
                    task.completed_at = datetime.now(timezone.utc)
                    task.result_summary = "One or more steps failed during slice execution."

            # Final status check for this slice
            all_done = all(s.status in (StepStatus.SUCCEEDED, StepStatus.COMPLETED) for s in task.plan.steps)
            if all_done:
                task.status = TaskStatus.SUCCEEDED
                task.completed_at = datetime.now(timezone.utc)
                task.result_summary = f"All {len(task.plan.steps)} plan steps executed successfully."
            elif any(s.status == StepStatus.NEEDS_RECONCILIATION for s in task.plan.steps):
                task.status = TaskStatus.NEEDS_RECONCILIATION
            elif any(s.status == StepStatus.AWAITING_APPROVAL for s in task.plan.steps):
                task.status = TaskStatus.AWAITING_APPROVAL
            elif any(s.status == StepStatus.FAILED for s in task.plan.steps):
                task.status = TaskStatus.FAILED
            else:
                task.status = TaskStatus.RUNNING

            await self._update_task_record(task, worker_id=eff_worker_id, lease_generation=lease_generation)
            fresh_cp = await checkpoint_manager.get_task_checkpoints(task.id, task.session_id)
            task.checkpoints = fresh_cp
            reply = self._safe_compose_response(task)
            return AgentTaskResponse(
                task=task,
                reply=reply,
                tools_executed=tools_executed,
                execution_timeline=timeline,
                checkpoints=fresh_cp
            )
        finally:
            self._active_tasks.pop(task.id, None)

    async def reject_task(
        self,
        session_id: str,
        task_id: UUID,
        approval_token: Optional[str] = None
    ) -> AgentTaskResponse:
        """User declined operation; transition task to CANCELLED and cancel checkpoints."""
        clean_session = session_id.strip()
        success, err = await reject_approval(task_id, clean_session)
        await checkpoint_manager.cancel_pending_checkpoints(task_id, clean_session)
        task = await self.get_task(clean_session, task_id)

        reply = "Operation rejected. No persistent changes were made." if success else f"Rejection error: {err}"
        checkpoints = await checkpoint_manager.get_task_checkpoints(task_id, clean_session)
        if task:
            task.checkpoints = checkpoints
        return AgentTaskResponse(
            task=task,
            reply=reply,
            checkpoints=checkpoints
        )

    async def cancel_task(
        self,
        session_id: str,
        task_id: UUID
    ) -> AgentTaskResponse:
        """Cancel an in-flight, awaiting_approval, or paused task safely."""
        clean_session = session_id.strip()
        if isinstance(task_id, str):
            task_id = UUID(task_id)
        task = await self.get_task(clean_session, task_id)
        if not task:
            raise ValueError("Task not found or access denied for this session.")

        # Reject requests to cancel terminal tasks
        if task.status in (TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            logger.warning(f"Rejecting cancellation request: task {task_id} is in terminal state '{task.status.value}'.")
            checkpoints = await checkpoint_manager.get_task_checkpoints(task_id, clean_session)
            task.checkpoints = checkpoints
            return AgentTaskResponse(
                task=task,
                reply=f"Cannot cancel task in terminal state: {task.status.value}.",
                checkpoints=checkpoints
            )

        active_task = self._active_tasks.get(task_id)
        if active_task and not active_task.done():
            task.status = TaskStatus.CANCEL_REQUESTED
            await self._update_task_record(task)
            active_task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(active_task), timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                pass
            refreshed = await self.get_task(clean_session, task_id)
            if refreshed:
                task = refreshed
            checkpoints = await checkpoint_manager.get_task_checkpoints(task_id, clean_session)
            task.checkpoints = checkpoints
            return AgentTaskResponse(
                task=task,
                reply=task.result_summary or f"Task transitioned to {task.status.value}.",
                checkpoints=checkpoints
            )

        task.status = TaskStatus.CANCELLED
        task.completed_at = datetime.now(timezone.utc)
        task.result_summary = "Task was cancelled by user."
        await checkpoint_manager.cancel_pending_checkpoints(task_id, clean_session)
        await self._update_task_record(task)
        checkpoints = await checkpoint_manager.get_task_checkpoints(task_id, clean_session)
        task.checkpoints = checkpoints
        return AgentTaskResponse(
            task=task,
            reply="Task execution was cancelled successfully.",
            checkpoints=checkpoints
        )

    async def clarify_task(
        self,
        session_id: str,
        task_id: UUID,
        clarification: str
    ) -> AgentTaskResponse:
        """Provide clarification for a task awaiting clarification and resume planning/execution."""
        clean_session = session_id.strip()
        if isinstance(task_id, str):
            task_id = UUID(task_id)

        task = await self.get_task(clean_session, task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' not found for session '{clean_session}'.")

        if task.status != TaskStatus.AWAITING_CLARIFICATION:
            raise ValueError(f"Task is in status '{task.status.value}', not awaiting clarification.")

        clean_clarification = clarification.strip()
        if not clean_clarification:
            raise ValueError("Clarification text cannot be empty.")

        augmented_request = f"{task.user_request} (Subject/Detail: {clean_clarification})"
        task.user_request = augmented_request
        task.requires_clarification = False
        task.clarification_prompt = None
        task.status = TaskStatus.PLANNING
        task.updated_at = datetime.now(timezone.utc)
        await self._update_task_record(task)

        # Concurrently retrieve memories and generate plan
        recalled_memories_task = retrieve_hybrid_memories(clean_session, augmented_request, limit=4)
        intent_task = analyze_intent(augmented_request)
        recalled_memories, intent_data = await asyncio.gather(
            recalled_memories_task,
            intent_task
        )
        task.task_type = intent_data.get("intent", "general")

        proposed_plan = await generate_plan(augmented_request, recalled_memories, max_steps=6)
        if proposed_plan.requires_clarification:
            task.status = TaskStatus.AWAITING_CLARIFICATION
            task.requires_clarification = True
            task.clarification_prompt = proposed_plan.clarification_prompt
            task.result_summary = proposed_plan.clarification_prompt
            await self._update_task_record(task)
            reply = proposed_plan.clarification_prompt or "Further clarification is needed."
            return AgentTaskResponse(
                task=task,
                reply=reply,
                memories_used=[m.model_dump(mode="json") if hasattr(m, "model_dump") else m for m in recalled_memories],
                tools_executed=[],
                execution_timeline=[]
            )

        # Check approval preference
        prompt_lower = augmented_request.lower()
        eff_approval = any(phrase in prompt_lower for phrase in [
            "require approval", "with approval", "ask for approval", "await approval", "require confirmation"
        ])
        is_valid, plan, validation_error = validate_plan(proposed_plan, require_approval=eff_approval)
        if not is_valid:
            task.status = TaskStatus.FAILED
            task.result_summary = f"Plan validation failed: {validation_error}"
            task.completed_at = datetime.now(timezone.utc)
            await self._update_task_record(task)
            return AgentTaskResponse(
                task=task,
                reply=f"Task planning failed validation: {validation_error}",
                memories_used=[m.model_dump(mode="json") if hasattr(m, "model_dump") else m for m in recalled_memories],
                tools_executed=[],
                execution_timeline=[]
            )

        task.plan = plan
        task.status = TaskStatus.RUNNING
        await self._update_task_record(task)
        await checkpoint_manager.init_task_checkpoints(task.id, task.session_id, plan)
        return await self._execute_plan_steps(task, recalled_memories)

    async def retry_task(
        self,
        session_id: str,
        task_id: UUID
    ) -> AgentTaskResponse:
        """Resume execution of a failed, paused, or reconciled task from its last checkpoint."""
        clean_session = session_id.strip()
        if isinstance(task_id, str):
            task_id = UUID(task_id)
        task = await self.get_task(clean_session, task_id)
        if not task or not task.plan:
            raise ValueError("Task or plan could not be restored for retry.")

        if task.status in (TaskStatus.SUCCEEDED, TaskStatus.COMPLETED):
            checkpoints = await checkpoint_manager.get_task_checkpoints(task_id, clean_session)
            task.checkpoints = checkpoints
            return AgentTaskResponse(
                task=task,
                reply=f"Task is already {task.status.value}. Resumption is not required.",
                checkpoints=checkpoints
            )

        if task.status == TaskStatus.CANCELLED:
            raise ValueError(f"Cannot resume cancelled task {task_id}: task is in terminal status 'cancelled'. Resuming a cancelled task is disallowed by terminal state policy.")

        # Reopen failed, retrying, or needs_reconciliation steps
        for step in task.plan.steps:
            if step.status in (StepStatus.FAILED, StepStatus.RETRYING, StepStatus.NEEDS_RECONCILIATION, StepStatus.SKIPPED):
                step.status = StepStatus.PENDING
                step.error = None
                step.error_classification = None

        task.status = TaskStatus.RUNNING
        task.result_summary = None
        task.completed_at = None
        await self._update_task_record(task)
        return await self._execute_plan_steps(task)

    async def get_task(self, session_id: str, task_id: UUID) -> Optional[AgentTask]:
        """Fetch an agent task by ID ensuring strict session ownership and loading checkpoints."""
        pool = await get_db_pool()
        if pool is None:
            return None

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, session_id, user_request, task_type, plan_json, status,
                       result_summary, approval_token, approval_status, approval_expires_at,
                       estimated_complexity, estimated_cost_tier, requires_clarification, clarification_prompt,
                       lease_generation, worker_id, last_heartbeat_at, execution_lease_expires_at,
                       created_at, updated_at, completed_at
                FROM agent_tasks
                WHERE id = $1 AND session_id = $2
                """,
                task_id,
                session_id.strip(),
            )
            if not row:
                return None

            plan_obj = None
            if row["plan_json"]:
                try:
                    plan_data = json.loads(row["plan_json"]) if isinstance(row["plan_json"], str) else row["plan_json"]
                    plan_obj = AgentPlan.model_validate(plan_data)
                except Exception as e:
                    logger.warning(f"Could not deserialize plan_json: {e}")

            # Reconstruct pending approval if still awaiting
            pending_req = None
            if row["status"] == TaskStatus.AWAITING_APPROVAL.value:
                if plan_obj:
                    for s in plan_obj.steps:
                        if s.status == StepStatus.AWAITING_APPROVAL:
                            pending_req = create_approval_request(
                                task_id=row["id"],
                                step_id=s.step_id,
                                tool_name=s.tool_name or "create_note",
                                arguments=s.arguments
                            )
                            pending_req.approval_token = "[REDACTED_HISTORICAL_TOKEN]"
                            if row["approval_expires_at"]:
                                pending_req.expires_at = row["approval_expires_at"]
                            break

            checkpoints = await checkpoint_manager.get_task_checkpoints(task_id, session_id.strip())

            return AgentTask(
                id=row["id"],
                session_id=row["session_id"],
                user_request=row["user_request"],
                task_type=row["task_type"] or "general",
                plan=plan_obj,
                status=TaskStatus(row["status"]),
                result_summary=row["result_summary"],
                approval_token=None,
                approval_status=row["approval_status"],
                approval_expires_at=row["approval_expires_at"],
                pending_approval=pending_req,
                estimated_complexity=row.get("estimated_complexity") or "low",
                estimated_cost_tier=row.get("estimated_cost_tier") or "standard",
                requires_clarification=bool(row.get("requires_clarification", False)),
                clarification_prompt=row.get("clarification_prompt"),
                lease_generation=row.get("lease_generation") or 1,
                worker_id=row.get("worker_id"),
                last_heartbeat_at=row.get("last_heartbeat_at"),
                execution_lease_expires_at=row.get("execution_lease_expires_at"),
                checkpoints=checkpoints,
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                completed_at=row["completed_at"]
            )

    async def list_tasks(self, session_id: str, limit: int = 20) -> List[AgentTask]:
        """List tasks belonging to current session with sensitive tokens redacted."""
        pool = await get_db_pool()
        if pool is None:
            return []

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, session_id, user_request, task_type, plan_json, status,
                       result_summary, approval_token, approval_status, approval_expires_at,
                       estimated_complexity, estimated_cost_tier, requires_clarification, clarification_prompt,
                       created_at, updated_at, completed_at
                FROM agent_tasks
                WHERE session_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                session_id.strip(),
                limit,
            )

            tasks = []
            for r in rows:
                plan_obj = None
                if r["plan_json"]:
                    try:
                        plan_data = json.loads(r["plan_json"]) if isinstance(r["plan_json"], str) else r["plan_json"]
                        plan_obj = AgentPlan.model_validate(plan_data)
                    except Exception:
                        pass
                tasks.append(
                    AgentTask(
                        id=r["id"],
                        session_id=r["session_id"],
                        user_request=r["user_request"],
                        task_type=r["task_type"] or "general",
                        plan=plan_obj,
                        status=TaskStatus(r["status"]),
                        result_summary=r["result_summary"],
                        approval_token=None,
                        approval_status=r["approval_status"],
                        approval_expires_at=r["approval_expires_at"],
                        estimated_complexity=r.get("estimated_complexity") or "low",
                        estimated_cost_tier=r.get("estimated_cost_tier") or "standard",
                        requires_clarification=bool(r.get("requires_clarification", False)),
                        clarification_prompt=r.get("clarification_prompt"),
                        created_at=r["created_at"],
                        updated_at=r["updated_at"],
                        completed_at=r["completed_at"]
                    )
                )
            return tasks

    async def get_task_logs(self, session_id: str, task_id: UUID) -> List[AgentExecutionEvent]:
        """Fetch audit execution logs for a task, strictly scoped to session."""
        pool = await get_db_pool()
        if pool is None:
            return []

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, task_id, session_id, step_id, tool_name, arguments_json,
                       status, approval_status, result_summary, error_code, duration_ms, created_at
                FROM agent_execution_logs
                WHERE task_id = $1 AND session_id = $2
                ORDER BY created_at ASC
                """,
                task_id,
                session_id.strip(),
            )
            return [
                AgentExecutionEvent(
                    id=r["id"],
                    task_id=r["task_id"],
                    session_id=r["session_id"],
                    step_id=r["step_id"],
                    tool_name=r["tool_name"],
                    arguments_json=r["arguments_json"] if isinstance(r["arguments_json"], dict) else (json.loads(r["arguments_json"]) if r["arguments_json"] else None),
                    status=r["status"],
                    approval_status=r["approval_status"],
                    result_summary=r["result_summary"],
                    error_code=r["error_code"],
                    duration_ms=r["duration_ms"],
                    created_at=r["created_at"]
                )
                for r in rows
            ]

    async def claim_task_lease(
        self,
        task_id: UUID,
        session_id: str,
        worker_id: Optional[str] = None,
        lease_seconds: int = 60
    ) -> Tuple[bool, int, Optional[str]]:
        """
        Sprint 3.1: Monotonically increasing fencing token (lease_generation) lease claim.
        Conditional database update requiring the task to be unassigned, expired, or already owned.
        """
        if isinstance(task_id, str):
            task_id = UUID(task_id)

        pool = await get_db_pool()
        if pool is None:
            return False

        if isinstance(task_id, str):
            task_id = UUID(task_id), 0, "Database pool unavailable."

        eff_worker_id = worker_id or WorkerIdentity.get_worker_id()
        now_utc = datetime.now(timezone.utc)
        expires_at = now_utc + timedelta(seconds=lease_seconds)

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE agent_tasks
                SET worker_id = $1,
                    lease_generation = COALESCE(lease_generation, 0) + 1,
                    last_heartbeat_at = $2,
                    execution_lease_expires_at = $3,
                    status = CASE WHEN status = 'awaiting_approval' THEN 'awaiting_approval' ELSE 'running' END,
                    updated_at = NOW()
                WHERE id = $4 AND session_id = $5
                  AND (
                      execution_lease_expires_at IS NULL
                      OR execution_lease_expires_at < NOW()
                      OR worker_id = $1
                      OR status IN ('proposed', 'awaiting_approval')
                  )
                RETURNING lease_generation;
                """,
                eff_worker_id,
                now_utc,
                expires_at,
                task_id,
                session_id.strip()
            )
            if row:
                gen = row["lease_generation"]
                logger.info(f"Worker {eff_worker_id} successfully claimed lease on task {task_id} with fencing generation {gen}.")
                return True, gen, None

            cur = await conn.fetchrow(
                "SELECT worker_id, lease_generation, execution_lease_expires_at, status FROM agent_tasks WHERE id = $1",
                task_id
            )
            if cur:
                return False, cur["lease_generation"] or 0, f"Task lease held by active worker {cur['worker_id']} until {cur['execution_lease_expires_at']}."
            return False, 0, "Task not found."

    async def renew_heartbeat(
        self,
        task_id: UUID,
        session_id: str,
        worker_id: Optional[str] = None,
        lease_generation: Optional[int] = None,
        lease_seconds: Optional[int] = None,
        lease_minutes: Optional[int] = None
    ) -> bool:
        """
        Sprint 3.1: Renewable execution heartbeat with fencing token enforcement.
        Extends task lease only if worker_id and lease_generation match the current lease.
        """
        pool = await get_db_pool()
        if pool is None:
            return False

        if isinstance(task_id, str):
            task_id = UUID(task_id)

        eff_worker_id = worker_id or WorkerIdentity.get_worker_id()
        duration_sec = lease_seconds if lease_seconds is not None else (lease_minutes * 60 if lease_minutes is not None else getattr(settings, "WORKER_LEASE_MINUTES", 5) * 60)
        now_utc = datetime.now(timezone.utc)
        expires_at = now_utc + timedelta(seconds=duration_sec)

        query = """
            UPDATE agent_tasks
            SET last_heartbeat_at = $1,
                execution_lease_expires_at = $2,
                updated_at = NOW()
            WHERE id = $3 AND session_id = $4 AND worker_id = $5
              AND status IN ('running', 'cancel_requested')
        """
        params = [now_utc, expires_at, task_id, session_id.strip(), eff_worker_id]

        if lease_generation is not None:
            query += " AND lease_generation = $6"
            params.append(lease_generation)

        async with pool.acquire() as conn:
            result = await conn.execute(query, *params)
            count = int(result.split()[-1]) if result else 0
            if count > 0:
                logger.debug(f"Heartbeat renewed for task {task_id} by worker {eff_worker_id} (lease valid until {expires_at}).")
                return True
            logger.warning(f"Failed to renew heartbeat for task {task_id}: worker {eff_worker_id} or lease_generation {lease_generation} is stale.")
            return False

    async def _persist_new_task(self, task: AgentTask) -> None:
        """Insert a newly created task into agent_tasks in Neon DB."""
        pool = await get_db_pool()
        if pool is None:
            return

        plan_json_str = task.plan.model_dump_json() if task.plan else None
        now_utc = datetime.now(timezone.utc)
        is_running = (task.status == TaskStatus.RUNNING)
        worker_id = WorkerIdentity.get_worker_id() if is_running else None
        last_heartbeat_at = now_utc if is_running else None
        lease_minutes = getattr(settings, "WORKER_LEASE_MINUTES", 5)
        execution_lease_expires_at = (now_utc + timedelta(minutes=lease_minutes)) if is_running else None
        lease_gen = getattr(task, "lease_generation", 1) or 1

        complexity = task.estimated_complexity or (task.plan.estimated_complexity if task.plan else "low")
        cost_tier = task.estimated_cost_tier or (task.plan.estimated_cost_tier if task.plan else "standard")
        req_clar = bool(task.requires_clarification or (task.plan.requires_clarification if task.plan else False))
        clar_prompt = task.clarification_prompt or (task.plan.clarification_prompt if task.plan else None)

        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO agent_tasks (
                    id, session_id, user_request, task_type, plan_json, status,
                    result_summary, approval_token, approval_status, approval_expires_at,
                    worker_id, last_heartbeat_at, execution_lease_expires_at, lease_generation,
                    estimated_complexity, estimated_cost_tier, requires_clarification, clarification_prompt,
                    created_at, updated_at, completed_at
                )
                VALUES (
                    $1, $2, $3, $4, $5::jsonb, $6,
                    $7, $8, $9, $10,
                    $11, $12, $13, $14,
                    $15, $16, $17, $18,
                    $19, $20, $21
                )
                """,
                task.id,
                task.session_id,
                task.user_request,
                task.task_type,
                plan_json_str,
                task.status.value,
                task.result_summary,
                None,
                task.approval_status,
                task.approval_expires_at,
                worker_id,
                last_heartbeat_at,
                execution_lease_expires_at,
                lease_gen,
                complexity,
                cost_tier,
                req_clar,
                clar_prompt,
                task.created_at,
                task.updated_at,
                task.completed_at,
            )

    async def _update_task_record(
        self,
        task: AgentTask,
        worker_id: Optional[str] = None,
        lease_generation: Optional[int] = None
    ) -> None:
        """Update existing task state in agent_tasks with execution lease and fencing token tracking."""
        pool = await get_db_pool()
        if pool is None:
            return

        # Ensure a task cannot become SUCCEEDED/COMPLETED if any required step failed
        if task.status in (TaskStatus.SUCCEEDED, TaskStatus.COMPLETED) and task.plan:
            has_failed_step = any(
                s.status in (StepStatus.FAILED, StepStatus.NEEDS_RECONCILIATION, StepStatus.CANCELLED)
                for s in task.plan.steps
            )
            if has_failed_step:
                logger.error(
                    f"Integrity violation: Task {task.id} attempted to become {task.status.value} "
                    f"while containing failed/cancelled steps. Forcing status to FAILED."
                )
                task.status = TaskStatus.FAILED

        plan_json_str = task.plan.model_dump_json() if task.plan else None
        now_utc = datetime.now(timezone.utc)
        is_running = (task.status == TaskStatus.RUNNING)
        eff_worker_id = worker_id or (WorkerIdentity.get_worker_id() if is_running else None)
        last_heartbeat_at = now_utc if is_running else None
        lease_minutes = getattr(settings, "WORKER_LEASE_MINUTES", 5)
        execution_lease_expires_at = (now_utc + timedelta(minutes=lease_minutes)) if is_running else None
        eff_lease_gen = lease_generation or getattr(task, "lease_generation", 1)

        complexity = task.estimated_complexity or (task.plan.estimated_complexity if task.plan else "low")
        cost_tier = task.estimated_cost_tier or (task.plan.estimated_cost_tier if task.plan else "standard")
        req_clar = bool(task.requires_clarification or (task.plan.requires_clarification if task.plan else False))
        clar_prompt = task.clarification_prompt or (task.plan.clarification_prompt if task.plan else None)

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE agent_tasks
                SET plan_json = $1::jsonb,
                    status = $2,
                    result_summary = $3,
                    approval_status = $4,
                    approval_expires_at = $5,
                    worker_id = COALESCE($6, worker_id),
                    last_heartbeat_at = $7,
                    execution_lease_expires_at = $8,
                    estimated_complexity = $9,
                    estimated_cost_tier = $10,
                    requires_clarification = $11,
                    clarification_prompt = $12,
                    lease_generation = COALESCE($13, lease_generation),
                    updated_at = NOW(),
                    completed_at = $14
                WHERE id = $15 AND session_id = $16
                  AND (
                      $13::int IS NULL
                      OR lease_generation IS NULL
                      OR lease_generation <= $13::int
                  )
                  AND (
                      status NOT IN ('succeeded', 'completed', 'cancelled')
                      OR $2 IN ('succeeded', 'completed', 'cancelled')
                      OR ($2 IN ('retrying', 'running') AND $13::int > COALESCE(lease_generation, 0))
                  )
                RETURNING lease_generation;
                """,
                plan_json_str,
                task.status.value,
                task.result_summary,
                task.approval_status,
                task.approval_expires_at,
                eff_worker_id,
                last_heartbeat_at,
                execution_lease_expires_at,
                complexity,
                cost_tier,
                req_clar,
                clar_prompt,
                eff_lease_gen,
                task.completed_at,
                task.id,
                task.session_id,
            )
            if not row and eff_lease_gen:
                cur = await conn.fetchrow("SELECT lease_generation, worker_id FROM agent_tasks WHERE id = $1", task.id)
                if cur and cur["lease_generation"] and cur["lease_generation"] > eff_lease_gen:
                    logger.error(
                        f"Fencing violation: Worker {eff_worker_id} (gen={eff_lease_gen}) attempted updating task {task.id}, "
                        f"but active DB generation is {cur['lease_generation']}."
                    )
                    raise StaleWorkerError(
                        f"Stale worker update rejected on task {task.id}: current generation is {cur['lease_generation']}, "
                        f"attempted with {eff_lease_gen}."
                    )

# Global orchestrator singleton
orchestrator = AgentOrchestrator()
agent_orchestrator = orchestrator

