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
    TaskStatus,
    StepStatus,
    ToolPermission,
    ApprovalStatus,
    AgentTaskResponse,
    AgentExecutionEvent,
    ApprovalRequest
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
from app.agent.response_composer import compose_agent_response
from app.services.hybrid_retriever import retrieve_hybrid_memories

logger = logging.getLogger(__name__)

MAX_TASK_TIMEOUT_SECONDS = 60.0
MAX_TOOL_EXECUTIONS_PER_TASK = 5

class AgentOrchestrator:
    """Unified single-orchestrator controlling memory-aware task execution."""

    async def run_agent_task(
        self,
        message: str = "",
        session_id: str = "default-session",
        user_request: Optional[str] = None
    ) -> AgentTaskResponse:
        """Alias for run_task supporting message and session_id keyword arguments."""
        req = message or user_request or ""
        return await self.run_task(session_id=session_id, user_request=req)

    async def run_task(
        self,
        session_id: str = "default-session",
        user_request: str = "",
        message: Optional[str] = None
    ) -> AgentTaskResponse:
        """
        Execute an agent task:
        1. Retrieve relevant memories.
        2. Analyze intent.
        3. Plan and validate execution steps.
        4. Execute automatic steps or pause for user approval on persistent writes.
        """
        req = user_request or message or ""
        clean_session = session_id.strip() if session_id else "default-session"
        clean_request = req.strip()

        task_id = uuid4()
        now = datetime.now(timezone.utc)

        # 1. Retrieve relevant user memories for context
        recalled_memories = await retrieve_hybrid_memories(
            session_id=clean_session,
            query=clean_request,
            limit=4
        )

        # 2. Analyze intent
        intent_data = await analyze_intent(clean_request)
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
            )

        # 3. Generate plan
        proposed_plan = await generate_plan(
            user_request=clean_request,
            retrieved_memories=recalled_memories,
            max_steps=6
        )

        # 4. Validate plan authoritatively
        is_valid, plan, validation_error = validate_plan(proposed_plan)
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
            )

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

        # 6. Execute plan steps
        return await self._execute_plan_steps(task, recalled_memories)

    async def _execute_plan_steps(
        self,
        task: AgentTask,
        recalled_memories: Optional[List[Any]] = None
    ) -> AgentTaskResponse:
        """Run through remaining plan steps, stopping if approval is required or a step fails."""
        plan = task.plan
        if not plan:
            task.status = TaskStatus.FAILED
            await self._update_task_record(task)
            return AgentTaskResponse(task=task, reply="No valid plan found for task.")

        tool_exec_count = 0
        timeline = []
        tools_executed = []

        for step in plan.steps:
            if step.status == StepStatus.SUCCEEDED:
                tools_executed.append(step.tool_name or "reasoning")
                continue

            # Check dependencies: if any dependency failed, skip step
            dep_failed = False
            for dep_id in step.dependencies:
                dep_step = next((s for s in plan.steps if s.step_id == dep_id), None)
                if dep_step and dep_step.status != StepStatus.SUCCEEDED:
                    dep_failed = True
                    break

            if dep_failed:
                step.status = StepStatus.SKIPPED
                step.error = "Skipped due to dependency failure."
                timeline.append({"step_id": step.step_id, "status": "skipped"})
                continue

            # Check backend permissions (human-in-the-loop gate)
            if step.permission == ToolPermission.APPROVAL_REQUIRED:
                # Pause for approval
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
                await self._update_task_record(task)

                reply = compose_agent_response(task, recalled_memories)
                return AgentTaskResponse(
                    task=task,
                    reply=reply,
                    memories_used=[m.model_dump(mode="json") if hasattr(m, "model_dump") else m for m in (recalled_memories or [])],
                    tools_executed=tools_executed,
                    execution_timeline=timeline
                )

            # Enforce tool execution count limit per task
            tool_exec_count += 1
            if tool_exec_count > MAX_TOOL_EXECUTIONS_PER_TASK:
                step.status = StepStatus.FAILED
                step.error = f"Exceeded maximum limit of {MAX_TOOL_EXECUTIONS_PER_TASK} tool executions per task."
                task.status = TaskStatus.FAILED
                task.result_summary = step.error
                task.completed_at = datetime.now(timezone.utc)
                await self._update_task_record(task)
                reply = compose_agent_response(task, recalled_memories)
                return AgentTaskResponse(task=task, reply=reply, tools_executed=tools_executed, execution_timeline=timeline)

            # Execute step
            result = await execute_step(
                task_id=task.id,
                session_id=task.session_id,
                step=step
            )

            if step.tool_name:
                tools_executed.append(step.tool_name)

            timeline.append({
                "step_id": step.step_id,
                "tool": step.tool_name,
                "status": step.status.value,
                "duration_ms": result.duration_ms
            })

            if not result.success:
                task.status = TaskStatus.FAILED
                task.result_summary = f"Execution failed at {step.step_id} ({step.tool_name}): {result.error}"
                task.completed_at = datetime.now(timezone.utc)
                await self._update_task_record(task)
                reply = compose_agent_response(task, recalled_memories)
                return AgentTaskResponse(
                    task=task,
                    reply=reply,
                    memories_used=[m.model_dump(mode="json") if hasattr(m, "model_dump") else m for m in (recalled_memories or [])],
                    tools_executed=tools_executed,
                    execution_timeline=timeline
                )

        # All steps succeeded
        task.status = TaskStatus.SUCCEEDED
        task.completed_at = datetime.now(timezone.utc)
        task.result_summary = f"All {len(plan.steps)} plan steps executed successfully."
        await self._update_task_record(task)

        reply = compose_agent_response(task, recalled_memories)
        return AgentTaskResponse(
            task=task,
            reply=reply,
            memories_used=[m.model_dump(mode="json") if hasattr(m, "model_dump") else m for m in (recalled_memories or [])],
            tools_executed=tools_executed,
            execution_timeline=timeline
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
            if "access denied" in (err or "").lower() or "mismatch" in (err or "").lower():
                raise PermissionError(f"Approval validation failed: {err}")
            raise ValueError(f"Approval validation failed: {err}")

        task = await self.get_task(clean_session, task_id)
        if not task or not task.plan:
            return AgentTaskResponse(task=task, reply="Task or plan could not be restored.")

        task.status = TaskStatus.RUNNING
        task.pending_approval = None

        # Resume execution
        # Find the awaiting_approval step and mark it ready to execute
        for step in task.plan.steps:
            if step.status == StepStatus.AWAITING_APPROVAL:
                step.status = StepStatus.PENDING
                step.permission = ToolPermission.AUTOMATIC

        await self._update_task_record(task)
        return await self._execute_plan_steps(task)

    approve_and_resume = approve_task

    async def reject_task(
        self,
        session_id: str,
        task_id: UUID,
        approval_token: Optional[str] = None
    ) -> AgentTaskResponse:
        """User declined operation; transition task to CANCELLED."""
        clean_session = session_id.strip()
        success, err = await reject_approval(task_id, clean_session)
        task = await self.get_task(clean_session, task_id)

        reply = "Operation rejected. No persistent changes were made." if success else f"Rejection error: {err}"
        return AgentTaskResponse(
            task=task,
            reply=reply
        )

    async def get_task(self, session_id: str, task_id: UUID) -> Optional[AgentTask]:
        """Fetch an agent task by ID ensuring strict session ownership."""
        pool = await get_db_pool()
        if pool is None:
            return None

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, session_id, user_request, task_type, plan_json, status,
                       result_summary, approval_token, approval_status, approval_expires_at,
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
                            # Never expose token from historical queries
                            pending_req.approval_token = "[REDACTED_HISTORICAL_TOKEN]"
                            if row["approval_expires_at"]:
                                pending_req.expires_at = row["approval_expires_at"]
                            break

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

    async def _persist_new_task(self, task: AgentTask) -> None:
        """Insert a newly created task into agent_tasks in Neon DB."""
        pool = await get_db_pool()
        if pool is None:
            return

        plan_json_str = task.plan.model_dump_json() if task.plan else None
        now_utc = datetime.now(timezone.utc)
        is_running = (task.status == TaskStatus.RUNNING)
        worker_id = "memora-orchestrator-worker" if is_running else None
        last_heartbeat_at = now_utc if is_running else None
        execution_lease_expires_at = (now_utc + timedelta(minutes=5)) if is_running else None

        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO agent_tasks (
                    id, session_id, user_request, task_type, plan_json, status,
                    result_summary, approval_token, approval_status, approval_expires_at,
                    worker_id, last_heartbeat_at, execution_lease_expires_at,
                    created_at, updated_at, completed_at
                )
                VALUES (
                    $1, $2, $3, $4, $5::jsonb, $6,
                    $7, $8, $9, $10,
                    $11, $12, $13,
                    $14, $15, $16
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
                task.created_at,
                task.updated_at,
                task.completed_at,
            )

    async def _update_task_record(self, task: AgentTask) -> None:
        """Update existing task state in agent_tasks with execution lease tracking."""
        pool = await get_db_pool()
        if pool is None:
            return

        plan_json_str = task.plan.model_dump_json() if task.plan else None
        now_utc = datetime.now(timezone.utc)
        is_running = (task.status == TaskStatus.RUNNING)
        worker_id = "memora-orchestrator-worker" if is_running else None
        last_heartbeat_at = now_utc if is_running else None
        execution_lease_expires_at = (now_utc + timedelta(minutes=5)) if is_running else None

        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE agent_tasks
                SET plan_json = $1::jsonb,
                    status = $2,
                    result_summary = $3,
                    approval_status = $4,
                    approval_expires_at = $5,
                    worker_id = $6,
                    last_heartbeat_at = $7,
                    execution_lease_expires_at = $8,
                    updated_at = NOW(),
                    completed_at = $9
                WHERE id = $10 AND session_id = $11
                """,
                plan_json_str,
                task.status.value,
                task.result_summary,
                task.approval_status,
                task.approval_expires_at,
                worker_id,
                last_heartbeat_at,
                execution_lease_expires_at,
                task.completed_at,
                task.id,
                task.session_id,
            )

# Global orchestrator singleton
orchestrator = AgentOrchestrator()
agent_orchestrator = orchestrator

