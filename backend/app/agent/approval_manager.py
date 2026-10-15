import hashlib
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
    arguments: Dict[str, Any]
) -> ApprovalRequest:
    """Generate a cryptographically unpredictable approval request bound to task and step."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=APPROVAL_VALIDITY_MINUTES)

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
                SELECT id, session_id, status, approval_token, approval_token_hash, approval_status, approval_expires_at
                FROM agent_tasks
                WHERE id = $1 AND session_id = $2
                FOR UPDATE
                """,
                task_id,
                session_id.strip(),
            )

            if not row:
                return False, "Task not found or access denied for this session."

            if row["status"] != TaskStatus.AWAITING_APPROVAL.value:
                return False, f"Task is in status '{row['status']}', not awaiting approval."

            if row["approval_status"] != ApprovalStatus.PENDING.value:
                return False, f"Approval has already been consumed (status: {row['approval_status']})."

            now = datetime.now(timezone.utc)
            if row["approval_expires_at"] and row["approval_expires_at"] < now:
                await conn.execute(
                    """
                    UPDATE agent_tasks 
                    SET approval_status = $1, 
                        updated_at = NOW() 
                    WHERE id = $2
                    """,
                    ApprovalStatus.EXPIRED.value,
                    task_id,
                )
                return False, "Approval token has expired."

            # Verify token via SHA-256 hash (legacy plaintext fallback strictly removed)
            if not row["approval_token_hash"]:
                return False, "Approval token hash is missing or legacy record invalidated."

            provided_hash = hash_token(approval_token)
            if not secrets.compare_digest(row["approval_token_hash"], provided_hash):
                return False, "Invalid approval token."

            # Atomically mark consumed/approved
            await conn.execute(
                """
                UPDATE agent_tasks
                SET approval_status = $1,
                    approval_token = NULL,
                    updated_at = NOW()
                WHERE id = $2
                """,
                ApprovalStatus.APPROVED.value,
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
                        'succeeded', $3, 'Approval granted and consumed atomically.', 0)
                """,
                task_id,
                session_id.strip(),
                ApprovalStatus.APPROVED.value,
            )

            return True, None

async def reject_approval(task_id: UUID, session_id: str) -> Tuple[bool, Optional[str]]:
    """
    Explicitly reject pending approval atomically and transition task to CANCELLED.
    Enforces state machine rules:
    - Task must exist and be owned by the session
    - Task must be in status AWAITING_APPROVAL
    - Approval status must be PENDING
    - Approval must not be expired
    - Transactional audit log insertion (failures roll back rejection)
    """
    pool = await get_db_pool()
    if pool is None:
        return False, "Database pool is unavailable."

    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT id, session_id, status, approval_status, approval_expires_at
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
                await conn.execute(
                    """
                    UPDATE agent_tasks
                    SET approval_status = $1,
                        status = $2,
                        result_summary = 'Approval request expired before rejection.',
                        updated_at = NOW()
                    WHERE id = $3
                    """,
                    ApprovalStatus.EXPIRED.value,
                    TaskStatus.FAILED.value,
                    task_id,
                )
                return False, "Approval request has expired."

            await conn.execute(
                """
                UPDATE agent_tasks
                SET status = $1,
                    approval_status = $2,
                    approval_token = NULL,
                    approval_token_hash = NULL,
                    result_summary = 'User rejected the requested operation.',
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE id = $3
                """,
                TaskStatus.CANCELLED.value,
                ApprovalStatus.REJECTED.value,
                task_id,
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
