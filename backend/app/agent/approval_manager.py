"""
MEMORA AI — Agent Approval Manager
Enforces cryptographically unpredictable, session-bound, single-use approval requests for persistent writes.
"""
import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, Dict, Any
from uuid import UUID
from app.database import get_db_pool
from app.agent.models import ApprovalRequest, ApprovalStatus, TaskStatus

logger = logging.getLogger(__name__)

APPROVAL_VALIDITY_MINUTES = 15

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
    """Store approval token, status, and expiration on the agent task record in Neon DB."""
    pool = await get_db_pool()
    if pool is None:
        raise RuntimeError("Database pool is unavailable.")

    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE agent_tasks
            SET status = $1,
                approval_token = $2,
                approval_status = $3,
                approval_expires_at = $4,
                updated_at = NOW()
            WHERE id = $5 AND session_id = $6
            """,
            TaskStatus.AWAITING_APPROVAL.value,
            request.approval_token,
            ApprovalStatus.PENDING.value,
            request.expires_at,
            task_id,
            session_id.strip(),
        )
        logger.info(f"Task '{task_id}' transitioned to AWAITING_APPROVAL with token bound.")

async def validate_and_consume_approval(
    task_id: UUID,
    session_id: str,
    approval_token: str
) -> Tuple[bool, Optional[str]]:
    """
    Validate that:
    1. Task exists and belongs to the calling session.
    2. Task is in 'awaiting_approval' status.
    3. Token matches exactly and has not expired.
    4. Approval status is 'pending' (single-use protection against replay attacks).
    """
    pool = await get_db_pool()
    if pool is None:
        return False, "Database pool is unavailable."

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, session_id, status, approval_token, approval_status, approval_expires_at
            FROM agent_tasks
            WHERE id = $1 AND session_id = $2
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

        if not secrets.compare_digest(row["approval_token"] or "", approval_token):
            return False, "Invalid approval token."

        now = datetime.now(timezone.utc)
        if row["approval_expires_at"] and row["approval_expires_at"] < now:
            await conn.execute(
                "UPDATE agent_tasks SET approval_status = $1, updated_at = NOW() WHERE id = $2",
                ApprovalStatus.EXPIRED.value,
                task_id,
            )
            return False, "Approval token has expired."

        # Mark consumed/approved
        await conn.execute(
            """
            UPDATE agent_tasks
            SET approval_status = $1,
                updated_at = NOW()
            WHERE id = $2
            """,
            ApprovalStatus.APPROVED.value,
            task_id,
        )
        return True, None

async def reject_approval(task_id: UUID, session_id: str) -> Tuple[bool, Optional[str]]:
    """Explicitly reject pending approval and transition task to CANCELLED."""
    pool = await get_db_pool()
    if pool is None:
        return False, "Database pool is unavailable."

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, status, approval_status
            FROM agent_tasks
            WHERE id = $1 AND session_id = $2
            """,
            task_id,
            session_id.strip(),
        )
        if not row:
            return False, "Task not found or access denied."

        await conn.execute(
            """
            UPDATE agent_tasks
            SET status = $1,
                approval_status = $2,
                result_summary = 'User rejected the requested operation.',
                completed_at = NOW(),
                updated_at = NOW()
            WHERE id = $3
            """,
            TaskStatus.CANCELLED.value,
            ApprovalStatus.REJECTED.value,
            task_id,
        )
        logger.info(f"Task '{task_id}' approval rejected by user; status marked CANCELLED.")
        return True, None
