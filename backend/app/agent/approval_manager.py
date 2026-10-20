import hashlib
import json
import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, Dict, Any
from uuid import UUID
from app.database import get_db_pool
from app.agent.models import ApprovalRequest, ApprovalStatus, TaskStatus

logger = logging.getLogger(__name__)

APPROVAL_VALIDITY_MINUTES = 15

def hash_token(token: str) -> str:
    """Compute deterministic SHA-256 hex digest for an approval token."""
    if not token:
        return ""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def generate_approval_token() -> str:
    """Generate a cryptographically secure 32-byte urlsafe approval token."""
    return secrets.token_urlsafe(32)

def is_token_expired(expires_at: datetime) -> bool:
    """Check if token expiration timestamp is in the past."""
    if not expires_at:
        return True
    now = datetime.now(timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at < now


def create_approval_request(
    task_id: UUID,
    step_id: str,
    tool_name: str,
    arguments: Dict[str, Any],
    ttl_seconds: Optional[int] = None
) -> ApprovalRequest:
    """Generate a cryptographically unpredictable approval request bound to task and step."""
    token = secrets.token_urlsafe(32)
    validity_delta = timedelta(seconds=ttl_seconds) if ttl_seconds is not None else timedelta(minutes=APPROVAL_VALIDITY_MINUTES)
    expires_at = datetime.now(timezone.utc) + validity_delta

    title = arguments.get("title") or "Persistent Note"
    content = arguments.get("content") or ""
    reason = f"Agent requests permission to persist note '{title}'."
    consequences = "A new persistent note will be created in your account. You can view or delete it anytime."

    return ApprovalRequest(
        task_id=task_id,
        step_id=step_id,
        approval_token=token,
        operation=tool_name,
        title=title,
        content=content,
        reason=reason,
        consequences=consequences,
        expires_at=expires_at
    )

async def bind_approval_to_task(task_id: UUID, session_id: str, request: ApprovalRequest) -> None:
    """
    Store approval token hash, status, and expiration on the agent task record in Neon DB.
    Never persists raw plaintext tokens in the database.
    """
    pool = await get_db_pool()
    if pool is None:
        raise RuntimeError("Database pool is unavailable.")

    token_hash = hash_token(request.approval_token)

    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE agent_tasks
            SET status = $1,
                approval_token = NULL,
                approval_token_hash = $2,
                approval_status = $3,
                approval_expires_at = $4,
                updated_at = NOW()
            WHERE id = $5 AND session_id = $6
            """,
            TaskStatus.AWAITING_APPROVAL.value,
            token_hash,
            ApprovalStatus.PENDING.value,
            request.expires_at,
            task_id,
            session_id.strip(),
        )
        logger.info(f"Task '{task_id}' transitioned to AWAITING_APPROVAL with hashed token bound.")

async def validate_and_consume_approval(
    task_id: UUID,
    session_id: str,
    approval_token: str
) -> Tuple[bool, Optional[str]]:
    """
    Atomically validate and consume an approval token within a database transaction.
    Uses SELECT ... FOR UPDATE to prevent concurrent race conditions and replay attacks.
    """
    if not approval_token or not isinstance(approval_token, str):
        return False, "Approval token cannot be empty."

    pool = await get_db_pool()
    if pool is None:
        return False, "Database pool is unavailable."

    async with pool.acquire() as conn:
        async with conn.transaction():
            # Acquire exclusive row-level lock on task record for duration of transaction
            row = await conn.fetchrow(
                """
                SELECT id, session_id, status, approval_token, approval_token_hash, approval_status, approval_expires_at, plan_json
                FROM agent_tasks
                WHERE id = $1 AND session_id = $2
                FOR UPDATE
                """,
                task_id,
                session_id.strip(),
            )

            if not row:
                return False, "Task not found or access denied for this session."

            if row["approval_status"] != ApprovalStatus.PENDING.value:
                return False, f"Approval has already been consumed (status: {row['approval_status']})."

            if row["status"] != TaskStatus.AWAITING_APPROVAL.value:
                return False, f"Task is in status '{row['status']}', not awaiting approval."

            now = datetime.now(timezone.utc)
            if row["approval_expires_at"] and row["approval_expires_at"] < now:
                # Update plan_json steps so the awaiting_approval step transitions to 'failed' with expiration error
                plan_json_data = json.loads(row["plan_json"]) if (row.get("plan_json") and isinstance(row["plan_json"], str)) else (row.get("plan_json") or {})
                if isinstance(plan_json_data, dict) and "steps" in plan_json_data:
                    for s in plan_json_data["steps"]:
                        if s.get("status") == "awaiting_approval":
                            s["status"] = "failed"
                            s["error"] = "Approval request expired before authorization was received."
                updated_plan_json = json.dumps(plan_json_data)

                await conn.execute(
                    """
                    UPDATE agent_tasks 
                    SET approval_status = $1, 
                        status = $2,
                        result_summary = 'Approval request expired before authorization was received.',
                        plan_json = $3::jsonb,
                        updated_at = NOW(),
                        completed_at = NOW()
                    WHERE id = $4
                    """,
                    ApprovalStatus.EXPIRED.value,
                    TaskStatus.FAILED.value,
                    updated_plan_json,
                    task_id,
                )
                await conn.execute(
                    """
                    UPDATE agent_task_checkpoints
                    SET status = 'failed',
                        error_message = 'Approval request expired before authorization was received.',
                        completed_at = NOW(),
                        updated_at = NOW()
                    WHERE task_id = $1 AND status IN ('awaiting_approval', 'pending', 'ready')
                    """,
                    task_id
                )
                return False, "Approval token has expired."

            # Verify token via SHA-256 hash (legacy plaintext fallback strictly removed)
            if not row["approval_token_hash"]:
                return False, "Approval token hash is missing or legacy record invalidated."

            provided_hash = hash_token(approval_token)
            if not secrets.compare_digest(row["approval_token_hash"], provided_hash):
                return False, "Invalid approval token."

            # Atomically update plan_json so awaiting_approval step transitions to pending
            plan_json_data = json.loads(row["plan_json"]) if (row.get("plan_json") and isinstance(row["plan_json"], str)) else (row.get("plan_json") or {})
            if isinstance(plan_json_data, dict) and "steps" in plan_json_data:
                for s in plan_json_data["steps"]:
                    if s.get("status") == "awaiting_approval":
                        s["status"] = "pending"
                        s["permission"] = "automatic"
            updated_plan_json = json.dumps(plan_json_data)

            # Atomically mark consumed/approved, set task status to RUNNING, and persist updated plan
            await conn.execute(
                """
                UPDATE agent_tasks
                SET approval_status = $1,
                    status = $2,
                    plan_json = $3::jsonb,
                    approval_token = NULL,
                    updated_at = NOW()
                WHERE id = $4
                """,
                ApprovalStatus.APPROVED.value,
                TaskStatus.RUNNING.value,
                updated_plan_json,
                task_id,
            )

            # Atomically advance checkpoint from awaiting_approval to ready
            await conn.execute(
                """
                UPDATE agent_task_checkpoints
                SET status = 'ready',
                    updated_at = NOW()
                WHERE task_id = $1 AND status = 'awaiting_approval'
                """,
                task_id,
            )

            # Record audit event atomically within the same transaction (failures roll back approval consumption)
            await conn.execute(
                """
                INSERT INTO agent_execution_logs (
                    task_id, session_id, step_id, tool_name, arguments_json,
                    status, approval_status, result_summary, duration_ms
                )
                VALUES ($1, $2, 'approval_gate', 'approval_manager', '{"action": "approve"}'::jsonb,
                        'succeeded', $3, 'Approval granted, consumed atomically, and execution resume intent recorded.', 0)
                """,
                task_id,
                session_id.strip(),
                ApprovalStatus.APPROVED.value,
            )

            return True, None

async def reject_approval(task_id: UUID, session_id: str, reason: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """
    Explicitly reject pending approval atomically and transition task to CANCELLED.
    Enforces state machine rules:
    - Task must exist and be owned by the session
    - Task must be in status AWAITING_APPROVAL
    - Approval status must be PENDING
    - Approval must not be expired
    - Transactional audit log insertion (failures roll back rejection)
    """
    if isinstance(task_id, str):
        task_id = UUID(task_id)

    rejection_msg = reason or "User rejected the requested operation."
    pool = await get_db_pool()
    if pool is None:
        return False, "Database pool is unavailable."

    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT id, session_id, status, approval_status, approval_expires_at, plan_json
                FROM agent_tasks
                WHERE id = $1 AND session_id = $2
                FOR UPDATE
                """,
                task_id,
                session_id.strip(),
            )
            if not row:
                return False, "Task not found or access denied."

            # State machine validations
            if row["status"] != TaskStatus.AWAITING_APPROVAL.value:
                return False, f"Cannot reject task in status '{row['status']}'; task is not awaiting approval."

            if row["approval_status"] != ApprovalStatus.PENDING.value:
                return False, f"Cannot reject approval in status '{row['approval_status']}'; only pending approvals can be rejected."

            # Expiration check
            now = datetime.now(timezone.utc)
            if row["approval_expires_at"] and row["approval_expires_at"] < now:
                plan_json_data = json.loads(row["plan_json"]) if (row.get("plan_json") and isinstance(row["plan_json"], str)) else (row.get("plan_json") or {})
                if isinstance(plan_json_data, dict) and "steps" in plan_json_data:
                    for s in plan_json_data["steps"]:
                        if s.get("status") == "awaiting_approval":
                            s["status"] = "failed"
                            s["error"] = "Approval request expired before rejection."
                updated_plan_json = json.dumps(plan_json_data)

                await conn.execute(
                    """
                    UPDATE agent_tasks
                    SET approval_status = $1,
                        status = $2,
                        result_summary = 'Approval request expired before rejection.',
                        plan_json = $3::jsonb,
                        completed_at = NOW(),
                        updated_at = NOW()
                    WHERE id = $4
                    """,
                    ApprovalStatus.EXPIRED.value,
                    TaskStatus.FAILED.value,
                    updated_plan_json,
                    task_id,
                )
                await conn.execute(
                    """
                    UPDATE agent_task_checkpoints
                    SET status = 'failed',
                        error_message = 'Approval request expired before rejection.',
                        completed_at = NOW(),
                        updated_at = NOW()
                    WHERE task_id = $1 AND status IN ('awaiting_approval', 'pending', 'ready')
                    """,
                    task_id
                )
                return False, "Approval request has expired."

            # Update plan_json steps so the awaiting_approval step transitions to 'cancelled'
            plan_json_data = json.loads(row["plan_json"]) if (row.get("plan_json") and isinstance(row["plan_json"], str)) else (row.get("plan_json") or {})
            if isinstance(plan_json_data, dict) and "steps" in plan_json_data:
                for s in plan_json_data["steps"]:
                    if s.get("status") == "awaiting_approval":
                        s["status"] = "cancelled"
                        s["error"] = rejection_msg
            updated_plan_json = json.dumps(plan_json_data)

            await conn.execute(
                """
                UPDATE agent_tasks
                SET status = $1,
                    approval_status = $2,
                    approval_token = NULL,
                    approval_token_hash = NULL,
                    result_summary = $3,
                    plan_json = $4::jsonb,
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE id = $5
                """,
                TaskStatus.CANCELLED.value,
                ApprovalStatus.REJECTED.value,
                rejection_msg,
                updated_plan_json,
                task_id,
            )
            await conn.execute(
                """
                UPDATE agent_task_checkpoints
                SET status = 'cancelled',
                    error_message = $1,
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE task_id = $2 AND status IN ('awaiting_approval', 'ready', 'pending')
                """,
                rejection_msg,
                task_id
            )

            # Record audit event atomically within the transaction (failures roll back rejection)
            await conn.execute(
                """
                INSERT INTO agent_execution_logs (
                    task_id, session_id, step_id, tool_name, arguments_json,
                    status, approval_status, result_summary, duration_ms
                )
                VALUES ($1, $2, 'approval_gate', 'approval_manager', '{"action": "reject"}'::jsonb,
                        'cancelled', $3, 'Operation declined by user.', 0)
                """,
                task_id,
                session_id.strip(),
                ApprovalStatus.REJECTED.value,
            )

            logger.info(f"Task '{task_id}' approval rejected by user; status marked CANCELLED.")
            return True, None
