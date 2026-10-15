"""
MEMORA AI — Agent Tool Execution Engine
Handles safe tool dispatching, timeout enforcement, output bounds checking, and audit event persistence.
"""
import asyncio
import json
import logging
import time
from typing import Dict, Any, Optional, Tuple
from uuid import UUID
from app.database import get_db_pool
from app.agent.models import AgentPlanStep, StepStatus, ToolResult
from app.agent.tools.registry import tool_registry

logger = logging.getLogger(__name__)

DEFAULT_STEP_TIMEOUT_SECONDS = 45.0
MAX_OUTPUT_BYTES = 8192

async def log_execution_event(
    task_id: UUID,
    session_id: str,
    step_id: Optional[str],
    tool_name: str,
    arguments: Dict[str, Any],
    status: str,
    approval_status: Optional[str] = None,
    result_summary: Optional[str] = None,
    error_code: Optional[str] = None,
    duration_ms: Optional[int] = None
) -> None:
    """Persist an execution log event into agent_execution_logs table in Neon DB."""
    try:
        pool = await get_db_pool()
        if pool is None:
            return

        # Sanitize arguments: never log raw API keys or passwords
        sanitized_args = {
            k: ("[REDACTED]" if any(secret in k.lower() for secret in ["key", "secret", "password", "token"]) else v)
            for k, v in arguments.items()
        }

        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO agent_execution_logs (
                    task_id, session_id, step_id, tool_name, arguments_json,
                    status, approval_status, result_summary, error_code, duration_ms
                )
                VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8, $9, $10)
                """,
                task_id,
                session_id.strip(),
                step_id,
                tool_name,
                json.dumps(sanitized_args),
                status,
                approval_status,
                result_summary[:500] if result_summary else None,
                error_code,
                duration_ms,
            )
    except Exception as e:
        logger.error(f"Failed to record execution log event: {e}")

async def execute_step(
    task_id: UUID,
    session_id: str,
    step: AgentPlanStep
) -> ToolResult:
    """
    Execute a single tool step with bounded timeout and output clamping.
    """
    if not step.tool_name:
        # Step has no registered tool (pure reasoning / planning step)
        step.status = StepStatus.SUCCEEDED
        return ToolResult(
            tool_name="none",
            success=True,
            result={"description": step.description}
        )

    tool = tool_registry.get_tool(step.tool_name)
    if not tool:
        err = f"Tool '{step.tool_name}' not found in registry."
        step.status = StepStatus.FAILED
        step.error = err
        await log_execution_event(
            task_id=task_id,
            session_id=session_id,
            step_id=step.step_id,
            tool_name=step.tool_name,
            arguments=step.arguments,
            status=StepStatus.FAILED.value,
            error_code="UNKNOWN_TOOL",
            result_summary=err
        )
        return ToolResult(tool_name=step.tool_name, success=False, error=err)

    step.status = StepStatus.RUNNING
    start_time = time.perf_counter()
    timeout = getattr(tool, "timeout_seconds", DEFAULT_STEP_TIMEOUT_SECONDS)

    try:
        # Execute tool with strict timeout
        result_data = await asyncio.wait_for(
            tool.execute(session_id=session_id, **step.arguments),
            timeout=timeout
        )
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        # Output bounds checking (prevent memory bloat / gigantic responses)
        serialized = json.dumps(result_data, default=str)
        if len(serialized.encode("utf-8")) > MAX_OUTPUT_BYTES:
            logger.warning(f"Tool '{tool.name}' output ({len(serialized)} bytes) exceeded limit. Clamping.")
            result_data = {
                "summary": "Tool output clamped to maximum size.",
                "preview": serialized[:500]
            }

        step.status = StepStatus.SUCCEEDED
        step.result = result_data

        await log_execution_event(
            task_id=task_id,
            session_id=session_id,
            step_id=step.step_id,
            tool_name=tool.name,
            arguments=step.arguments,
            status=StepStatus.SUCCEEDED.value,
            result_summary=f"Success: {str(result_data)[:200]}",
            duration_ms=elapsed_ms
        )

        return ToolResult(
            tool_name=tool.name,
            success=True,
            result=result_data,
            duration_ms=elapsed_ms
        )

    except asyncio.TimeoutError:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        err = f"Tool '{tool.name}' execution timed out after {timeout} seconds."
        step.status = StepStatus.FAILED
        step.error = err

        await log_execution_event(
            task_id=task_id,
            session_id=session_id,
            step_id=step.step_id,
            tool_name=tool.name,
            arguments=step.arguments,
            status=StepStatus.FAILED.value,
            error_code="TIMEOUT",
            result_summary=err,
            duration_ms=elapsed_ms
        )
        return ToolResult(tool_name=tool.name, success=False, error=err, duration_ms=elapsed_ms)

    except Exception as e:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        err = f"Tool '{tool.name}' execution error: {str(e)}"
        step.status = StepStatus.FAILED
        step.error = err

        await log_execution_event(
            task_id=task_id,
            session_id=session_id,
            step_id=step.step_id,
            tool_name=tool.name,
            arguments=step.arguments,
            status=StepStatus.FAILED.value,
            error_code="EXECUTION_ERROR",
            result_summary=err,
            duration_ms=elapsed_ms
        )
        return ToolResult(tool_name=tool.name, success=False, error=err, duration_ms=elapsed_ms)
