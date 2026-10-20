"""
MEMORA AI — Agent Task Checkpoint Manager
Provides durable, transactional execution checkpoints stored in PostgreSQL.
Tracks step-level status, dependencies, retries, idempotency, and failure classifications.
"""
import json
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from uuid import UUID, uuid4

from app.database import get_db_pool
from app.agent.models import (
    AgentPlan,
    AgentPlanStep,
    AgentTaskCheckpoint,
    StepStatus,
    ErrorClassification,
    ToolPermission,
    StaleWorkerError
)

logger = logging.getLogger(__name__)

class CheckpointManager:
    """Manages transactional step checkpoints for agent tasks in Neon PostgreSQL."""

    async def init_task_checkpoints(
        self,
        task_id: UUID,
        session_id: str,
        plan: AgentPlan,
        worker_id: Optional[str] = None,
        lease_generation: int = 1
    ) -> List[AgentTaskCheckpoint]:
        """
        Atomically initialize all step checkpoints in PENDING/READY state at task creation time.
        """
        pool = await get_db_pool()
        if pool is None:
            raise RuntimeError("Database connection pool is not available.")

        checkpoints: List[AgentTaskCheckpoint] = []
        now = datetime.now(timezone.utc)

        async with pool.acquire() as conn:
            async with conn.transaction():
                for step in plan.steps:
                    cp_id = uuid4()
                    if step.status and step.status != StepStatus.PENDING:
                        initial_status = step.status.value
                    elif not step.dependencies:
                        initial_status = StepStatus.READY.value
                    else:
                        initial_status = StepStatus.PENDING.value

                    args_json = json.dumps(step.arguments or {}, default=str)
                    deps = list(step.dependencies or [])

                    row = await conn.fetchrow(
                        """
                        INSERT INTO agent_task_checkpoints (
                            id, task_id, session_id, step_id, tool_name,
                            arguments_json, dependencies, status,
                            retry_count, max_retries, idempotency_key,
                            worker_id, lease_generation,
                            created_at, updated_at
                        )
                        VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                        ON CONFLICT (task_id, step_id) DO UPDATE
                        SET arguments_json = EXCLUDED.arguments_json,
                            dependencies = EXCLUDED.dependencies,
                            worker_id = COALESCE(EXCLUDED.worker_id, agent_task_checkpoints.worker_id),
                            lease_generation = GREATEST(EXCLUDED.lease_generation, agent_task_checkpoints.lease_generation),
                            updated_at = NOW()
                        RETURNING *
                        """,
                        cp_id,
                        task_id,
                        session_id.strip(),
                        step.step_id,
                        step.tool_name,
                        args_json,
                        deps,
                        initial_status,
                        step.retry_count,
                        step.max_retries,
                        step.idempotency_key or f"step_{step.step_id}",
                        worker_id,
                        lease_generation,
                        now,
                        now
                    )

                    checkpoints.append(
                        AgentTaskCheckpoint(
                            id=row["id"],
                            task_id=row["task_id"],
                            session_id=row["session_id"],
                            step_id=row["step_id"],
                            tool_name=row["tool_name"],
                            arguments=json.loads(row["arguments_json"]) if isinstance(row["arguments_json"], str) else (row["arguments_json"] or {}),
                            dependencies=list(row["dependencies"] or []),
                            status=StepStatus(row["status"]),
                            error_classification=ErrorClassification(row["error_classification"]) if row["error_classification"] else None,
                            retry_count=row["retry_count"],
                            max_retries=row["max_retries"],
                            idempotency_key=row["idempotency_key"],
                            external_operation_id=row.get("external_operation_id"),
                            execution_intent_persisted_at=row.get("execution_intent_persisted_at"),
                            lease_generation=row.get("lease_generation") or 1,
                            worker_id=row.get("worker_id"),
                            result=json.loads(row["result_json"]) if isinstance(row["result_json"], str) else row["result_json"],
                            error_message=row["error_message"],
                            started_at=row["started_at"],
                            completed_at=row["completed_at"],
                            created_at=row["created_at"],
                            updated_at=row["updated_at"]
                        )
                    )

        return checkpoints

    async def get_task_checkpoints(self, task_id: UUID, session_id: str) -> List[AgentTaskCheckpoint]:
        """Fetch all execution checkpoints for a specific task ordered by step_id."""
        pool = await get_db_pool()
        if pool is None:
            return []

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, task_id, session_id, step_id, tool_name,
                       arguments_json, dependencies, status, error_classification,
                       retry_count, max_retries, idempotency_key,
                       external_operation_id, execution_intent_persisted_at,
                       lease_generation, worker_id, result_json,
                       error_message, started_at, completed_at, created_at, updated_at
                FROM agent_task_checkpoints
                WHERE task_id = $1 AND session_id = $2
                ORDER BY step_id ASC
                """,
                task_id,
                session_id.strip()
            )

            checkpoints = []
            for r in rows:
                status_val = r["status"].lower() if r["status"] else "pending"
                matching_status = next((s for s in StepStatus if s.value == status_val), StepStatus.PENDING)
                checkpoints.append(
                    AgentTaskCheckpoint(
                        id=r["id"],
                        task_id=r["task_id"],
                        session_id=r["session_id"],
                        step_id=r["step_id"],
                        tool_name=r["tool_name"],
                        arguments=json.loads(r["arguments_json"]) if isinstance(r["arguments_json"], str) else (r["arguments_json"] or {}),
                        dependencies=list(r["dependencies"] or []),
                        status=matching_status,
                        error_classification=ErrorClassification(r["error_classification"]) if r["error_classification"] else None,
                        retry_count=r["retry_count"],
                        max_retries=r["max_retries"],
                        idempotency_key=r["idempotency_key"],
                        external_operation_id=r["external_operation_id"],
                        execution_intent_persisted_at=r["execution_intent_persisted_at"],
                        lease_generation=r["lease_generation"] or 1,
                        worker_id=r["worker_id"],
                        result=json.loads(r["result_json"]) if isinstance(r["result_json"], str) else r["result_json"],
                        error_message=r["error_message"],
                        started_at=r["started_at"],
                        completed_at=r["completed_at"],
                        created_at=r["created_at"],
                        updated_at=r["updated_at"]
                    )
                )
            return checkpoints

    async def update_checkpoint(
        self,
        task_id: UUID,
        session_id: str,
        step_id: str,
        status: StepStatus,
        result: Optional[Any] = None,
        result_summary: Optional[Any] = None,
        error_message: Optional[str] = None,
        error_classification: Optional[ErrorClassification] = None,
        increment_retry: bool = False,
        started: bool = False,
        completed: bool = False,
        external_operation_id: Optional[str] = None,
        execution_intent_persisted: bool = False,
        idempotency_key: Optional[str] = None,
        worker_id: Optional[str] = None,
        lease_generation: Optional[int] = None
    ) -> Optional[AgentTaskCheckpoint]:
        """Atomically update a step checkpoint status in PostgreSQL with worker fencing protection."""
        pool = await get_db_pool()
        if pool is None:
            return None

        actual_res = result if result is not None else result_summary
        result_json = json.dumps(actual_res, default=str) if actual_res is not None else None

        if status in (StepStatus.SUCCEEDED, StepStatus.COMPLETED, StepStatus.FAILED, StepStatus.CANCELLED):
            completed = True

        started_clause = "started_at = COALESCE(started_at, NOW())," if started else ""
        completed_clause = "completed_at = NOW()," if completed else ""
        retry_clause = "retry_count = retry_count + 1," if increment_retry else ""
        intent_clause = "execution_intent_persisted_at = NOW()," if execution_intent_persisted else ""

        query = f"""
            UPDATE agent_task_checkpoints cp
            SET status = $1,
                {started_clause}
                {completed_clause}
                {retry_clause}
                {intent_clause}
                result_json = COALESCE($2::jsonb, cp.result_json),
                error_message = $3,
                error_classification = $4,
                external_operation_id = COALESCE($5, cp.external_operation_id),
                idempotency_key = COALESCE($6, cp.idempotency_key),
                worker_id = COALESCE($7, cp.worker_id),
                lease_generation = COALESCE($8, cp.lease_generation),
                updated_at = NOW()
            FROM agent_tasks t
            WHERE cp.task_id = t.id AND cp.session_id = t.session_id
              AND cp.task_id = $9 AND cp.session_id = $10 AND cp.step_id = $11
              AND (
                  $8::int IS NULL
                  OR (
                      (cp.lease_generation IS NULL OR cp.lease_generation <= $8::int)
                      AND (t.lease_generation IS NULL OR t.lease_generation <= $8::int)
                  )
              )
            RETURNING cp.*;
        """

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                status.value,
                result_json,
                error_message,
                error_classification.value if error_classification else None,
                external_operation_id,
                idempotency_key,
                worker_id,
                lease_generation,
                task_id,
                session_id.strip(),
                step_id
            )

            if not row:
                # Check if row exists but task or checkpoint had a newer lease_generation (stale worker fencing violation)
                existing_task = await conn.fetchrow(
                    "SELECT lease_generation, worker_id FROM agent_tasks WHERE id = $1", task_id
                )
                existing_cp = await conn.fetchrow(
                    "SELECT lease_generation, worker_id FROM agent_task_checkpoints WHERE task_id = $1 AND step_id = $2",
                    task_id, step_id
                )
                cur_gen = max(
                    (existing_task["lease_generation"] if existing_task and existing_task["lease_generation"] else 0),
                    (existing_cp["lease_generation"] if existing_cp and existing_cp["lease_generation"] else 0)
                )
                if cur_gen > (lease_generation or 0):
                    logger.error(
                        f"Fencing violation: Worker {worker_id} (gen={lease_generation}) attempted update "
                        f"on step {step_id}, but database is at generation {cur_gen}."
                    )
                    raise StaleWorkerError(
                        f"Stale worker update rejected: current generation is {cur_gen}, "
                        f"attempted by generation {lease_generation}."
                    )
                return None

            status_val = row["status"].lower() if row["status"] else "pending"
            matching_status = next((s for s in StepStatus if s.value == status_val), StepStatus.PENDING)

            return AgentTaskCheckpoint(
                id=row["id"],
                task_id=row["task_id"],
                session_id=row["session_id"],
                step_id=row["step_id"],
                tool_name=row["tool_name"],
                arguments=json.loads(row["arguments_json"]) if isinstance(row["arguments_json"], str) else (row["arguments_json"] or {}),
                dependencies=list(row["dependencies"] or []),
                status=matching_status,
                error_classification=ErrorClassification(row["error_classification"]) if row["error_classification"] else None,
                retry_count=row["retry_count"],
                max_retries=row["max_retries"],
                idempotency_key=row["idempotency_key"],
                external_operation_id=row.get("external_operation_id"),
                execution_intent_persisted_at=row.get("execution_intent_persisted_at"),
                lease_generation=row.get("lease_generation") or 1,
                worker_id=row.get("worker_id"),
                result=json.loads(row["result_json"]) if isinstance(row["result_json"], str) else row["result_json"],
                error_message=row["error_message"],
                started_at=row["started_at"],
                completed_at=row["completed_at"],
                created_at=row["created_at"],
                updated_at=row["updated_at"]
            )

    async def cancel_pending_checkpoints(self, task_id: UUID, session_id: str) -> int:
        """Cancel all pending, ready, or awaiting_approval checkpoints when a task is cancelled."""
        pool = await get_db_pool()
        if pool is None:
            return 0

        async with pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE agent_task_checkpoints
                SET status = 'cancelled',
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE task_id = $1 AND session_id = $2
                  AND status IN ('pending', 'ready', 'awaiting_approval', 'cancel_requested')
                """,
                task_id,
                session_id.strip()
            )
            try:
                count = int(result.split()[-1])
            except Exception:
                count = 0
            return count

checkpoint_manager = CheckpointManager()
