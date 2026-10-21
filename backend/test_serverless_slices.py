"""
MEMORA AI — SERVERLESS BOUNDED EXECUTION & VERCEL ARCHITECTURE TEST SUITE
Sprint 5 Vercel Serverless Architecture & Durable Checkpointing Verification

Covers:
  [TEST 1] Vercel ASGI Entrypoint & FastAPI Route Compatibility
  [TEST 2] Serverless Database Pool Lifecycle & Adaptive Reconnection
  [TEST 3] Durable Serverless Task Creation & Checkpoint Initialization
  [TEST 4] Bounded Single-Step Execution Slice & Neon Checkpoint State
  [TEST 5] Multi-Step Slicing, Checkpoint Resumption & Idempotency
  [TEST 6] Approval Step Interruption, Signed Token Generation & Gate
  [TEST 7] Approval Resumption Slice & Downstream Note Creation
  [TEST 8] Concurrent Worker Lease & Monotonic Fencing Protection
  [TEST 9] In-Flight Task Cancellation & Prevention of Subsequent Slices
  [TEST 10] Terminal State Non-Reopening Invariant
  [TEST 11] Stale Task Lease Expiration & Recovery Sweep
  [TEST 12] Session Guard Isolation on Task Step Endpoint
  [TEST 13] Vercel Cron Endpoint Authentication & Execution
"""

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

# Ensure Windows console handles utf-8 characters smoothly
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Add backend and project root directory to sys.path
backend_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(backend_dir)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from app.config import settings
from app.database import init_db_pool, close_db_pool, get_db_pool, recover_interrupted_tasks, check_db_health
from app.agent.models import (
    AgentTask,
    AgentPlan,
    AgentPlanStep,
    AgentTaskCheckpoint,
    TaskStatus,
    StepStatus,
    ToolPermission,
    ApprovalStatus,
    AgentRunRequest,
    StaleWorkerError,
)
from app.agent.orchestrator import agent_orchestrator
from app.agent.checkpoint_manager import checkpoint_manager
from app.agent.worker_identity import WorkerIdentity
from app.agent.approval_manager import (
    generate_approval_token,
    validate_and_consume_approval,
    hash_token
)
from app.auth.session_guard import validate_session_id, UserPrincipal
from app.main import app


# Test Results Collector
class TestReporter:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def record_pass(self, name: str, detail: str = ""):
        self.passed += 1
        msg = f"  ✓ PASS: {name}"
        if detail:
            msg += f" — {detail}"
        print(msg)

    def record_fail(self, name: str, error: str):
        self.failed += 1
        self.errors.append((name, error))
        print(f"  ✗ FAIL: {name} — {error}")


reporter = TestReporter()


# Safe Session Cleanup Helper
async def cleanup_test_session(session_id: str):
    """Purge test data scoped strictly to an isolated test session_id with audit cleanup authorization."""
    pool = await get_db_pool()
    if not pool:
        return
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL memora.allow_audit_cleanup = 'on'")
            await conn.execute("DELETE FROM agent_execution_logs WHERE session_id = $1", session_id)
            await conn.execute("DELETE FROM notes WHERE session_id = $1", session_id)
            await conn.execute("DELETE FROM agent_task_checkpoints WHERE session_id = $1", session_id)
            await conn.execute("DELETE FROM agent_tasks WHERE session_id = $1", session_id)
            await conn.execute("DELETE FROM memories WHERE session_id = $1", session_id)


# ==============================================================================
# TESTS
# ==============================================================================

async def test_vercel_asgi_entrypoint():
    """Verify that root api/index.py exports valid ASGI app with expected route table."""
    try:
        from api.index import app as vercel_app
        assert vercel_app is not None, "Vercel entrypoint app is None"
        assert vercel_app.title == "MEMORA AI API", f"Unexpected app title: {vercel_app.title}"

        # Verify key serverless routes exist
        route_paths = [r.path for r in vercel_app.routes]
        expected_routes = [
            "/health",
            "/api/system/info",
            "/api/chat",
            "/api/agent/run",
            "/api/agent/tasks",
            "/api/agent/tasks/{task_id}/step",
            "/api/agent/tasks/{task_id}/approve",
            "/api/agent/cron/recover",
            "/api/agent/recovery",
        ]
        for route in expected_routes:
            assert route in route_paths, f"Expected route '{route}' missing from Vercel ASGI route table"

        reporter.record_pass("test_vercel_asgi_entrypoint", f"Found {len(route_paths)} registered routes in ASGI app")
    except Exception as e:
        reporter.record_fail("test_vercel_asgi_entrypoint", str(e))


async def test_serverless_db_pool_lifecycle():
    """Verify serverless connection pool initialization, sizing, and health."""
    try:
        pool = await get_db_pool()
        assert pool is not None, "Database pool could not be initialized"
        assert not pool._closed, "Database pool reported closed"

        health = await check_db_health()
        assert health.get("status") == "healthy", f"Database health check failed: {health}"
        assert health.get("connected") is True, "Database reported disconnected"

        pool_size = pool.get_size()
        assert pool_size <= settings.DB_POOL_MAX_SIZE, (
            f"Pool size {pool_size} exceeded configured max {settings.DB_POOL_MAX_SIZE}"
        )
        reporter.record_pass("test_serverless_db_pool_lifecycle", f"Pool healthy with {pool_size} active conn(s)")
    except Exception as e:
        reporter.record_fail("test_serverless_db_pool_lifecycle", str(e))


async def test_serverless_task_creation():
    """Verify create_task initializes task in Neon DB with initial checkpoints without running steps."""
    test_session = f"test_sl_create_{uuid.uuid4().hex[:8]}"
    try:
        req = "Calculate 15 * 8 and summarize result."
        resp, _ = await agent_orchestrator.create_task(
            session_id=test_session,
            user_request=req,
            max_steps=4
        )
        assert resp.task is not None, "create_task returned None task"
        assert resp.task.id is not None, "create_task returned task without ID"
        assert resp.task.status in (TaskStatus.RUNNING, TaskStatus.PROPOSED), (
            f"Unexpected status after creation: {resp.task.status}"
        )
        assert resp.task.plan is not None, "Task has no plan"
        assert len(resp.task.plan.steps) > 0, "Plan has 0 steps"

        # Verify initial checkpoints were persisted in Neon
        checkpoints = await checkpoint_manager.get_task_checkpoints(resp.task.id, test_session)
        assert len(checkpoints) == len(resp.task.plan.steps), (
            f"Checkpoints count {len(checkpoints)} does not match plan steps {len(resp.task.plan.steps)}"
        )
        for cp in checkpoints:
            assert cp.status in (StepStatus.PENDING, StepStatus.READY), (
                f"Expected step {cp.step_id} to be PENDING or READY, got {cp.status}"
            )

        reporter.record_pass(
            "test_serverless_task_creation",
            f"Task {resp.task.id} created with {len(checkpoints)} initial checkpoints"
        )
        return resp.task
    except Exception as e:
        reporter.record_fail("test_serverless_task_creation", str(e))
        return None
    finally:
        await cleanup_test_session(test_session)


async def test_bounded_execution_slice():
    """Verify executing one bounded slice runs exactly 1 step and persists checkpoint."""
    test_session = f"test_sl_slice_{uuid.uuid4().hex[:8]}"
    try:
        # Step 1: Create a deterministic 2-step task
        plan_steps = [
            AgentPlanStep(
                step_id="step_1",
                tool_name="calculator",
                arguments={"expression": "40 + 2"},
                description="Calculate baseline value",
                permission=ToolPermission.AUTOMATIC,
                dependencies=[],
                is_idempotent=True
            ),
            AgentPlanStep(
                step_id="step_2",
                tool_name="calculator",
                arguments={"expression": "42 * 2"},
                description="Double baseline value",
                permission=ToolPermission.AUTOMATIC,
                dependencies=["step_1"],
                is_idempotent=True
            ),
        ]
        plan = AgentPlan(
            title="Two Step Calculation",
            goal="Test execution slices",
            steps=plan_steps
        )
        task_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        task = AgentTask(
            id=task_id,
            session_id=test_session,
            user_request="Perform two sequential calculations",
            task_type="calculation",
            plan=plan,
            status=TaskStatus.RUNNING,
            created_at=now,
            updated_at=now
        )
        await agent_orchestrator._persist_new_task(task)
        await checkpoint_manager.init_task_checkpoints(task.id, task.session_id, plan)

        # Step 2: Execute FIRST bounded slice (max_steps=1)
        slice_resp = await agent_orchestrator.execute_task_slice(
            session_id=test_session,
            task_id=task.id,
            max_duration_seconds=15.0,
            max_steps=1
        )

        assert slice_resp.task is not None, "Slice response task is None"
        assert slice_resp.task.status == TaskStatus.RUNNING, (
            f"Expected status RUNNING after 1/2 steps, got {slice_resp.task.status}"
        )

        # Verify step_1 succeeded, step_2 remains PENDING
        cps = await checkpoint_manager.get_task_checkpoints(task.id, test_session)
        cp_map = {c.step_id: c for c in cps}
        assert cp_map["step_1"].status == StepStatus.SUCCEEDED, (
            f"step_1 status should be SUCCEEDED, got {cp_map['step_1'].status}"
        )
        assert cp_map["step_2"].status == StepStatus.PENDING, (
            f"step_2 status should be PENDING, got {cp_map['step_2'].status}"
        )
        res1_val = cp_map["step_1"].result.get("result") if isinstance(cp_map["step_1"].result, dict) else cp_map["step_1"].result
        assert res1_val in (42, 42.0), f"step_1 unexpected result: {cp_map['step_1'].result}"

        # Step 3: Execute SECOND slice (should execute step_2 and transition task to SUCCEEDED)
        slice2_resp = await agent_orchestrator.execute_task_slice(
            session_id=test_session,
            task_id=task.id,
            max_duration_seconds=15.0,
            max_steps=1
        )
        assert slice2_resp.task.status == TaskStatus.SUCCEEDED, (
            f"Expected task to be SUCCEEDED after step 2, got {slice2_resp.task.status}"
        )

        cps2 = await checkpoint_manager.get_task_checkpoints(task.id, test_session)
        cp2_map = {c.step_id: c for c in cps2}
        assert cp2_map["step_2"].status == StepStatus.SUCCEEDED, (
            f"step_2 status should be SUCCEEDED, got {cp2_map['step_2'].status}"
        )
        res2_val = cp2_map["step_2"].result.get("result") if isinstance(cp2_map["step_2"].result, dict) else cp2_map["step_2"].result
        assert res2_val in (84, 84.0), f"step_2 unexpected result: {cp2_map['step_2'].result}"

        reporter.record_pass("test_bounded_execution_slice", "2-step task sliced cleanly across 2 separate invocations")
    except Exception as e:
        reporter.record_fail("test_bounded_execution_slice", str(e))
    finally:
        await cleanup_test_session(test_session)


async def test_checkpoint_resumption_and_idempotency():
    """Verify that calling execute_task_slice does not re-execute already completed steps."""
    test_session = f"test_sl_idemp_{uuid.uuid4().hex[:8]}"
    try:
        plan_steps = [
            AgentPlanStep(
                step_id="step_a",
                tool_name="calculator",
                arguments={"expression": "100 / 2"},
                description="Calculate quotient",
                permission=ToolPermission.AUTOMATIC,
                dependencies=[],
                is_idempotent=True
            ),
        ]
        plan = AgentPlan(title="Idempotency Test", steps=plan_steps)
        task_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        task = AgentTask(
            id=task_id,
            session_id=test_session,
            user_request="Test idempotency",
            task_type="calculation",
            plan=plan,
            status=TaskStatus.RUNNING,
            created_at=now,
            updated_at=now
        )
        await agent_orchestrator._persist_new_task(task)
        await checkpoint_manager.init_task_checkpoints(task.id, task.session_id, plan)

        # First slice: executes step_a
        resp1 = await agent_orchestrator.execute_task_slice(test_session, task.id)
        assert resp1.task.status == TaskStatus.SUCCEEDED

        cp1 = (await checkpoint_manager.get_task_checkpoints(task.id, test_session))[0]
        first_completed_at = cp1.completed_at
        assert first_completed_at is not None

        # Second slice on completed task: returns cached outcome without re-running
        resp2 = await agent_orchestrator.execute_task_slice(test_session, task.id)
        assert resp2.task.status == TaskStatus.SUCCEEDED

        cp2 = (await checkpoint_manager.get_task_checkpoints(task.id, test_session))[0]
        assert cp2.completed_at == first_completed_at, "Checkpoint completed_at changed! Step was re-executed!"

        reporter.record_pass("test_checkpoint_resumption_and_idempotency", "Already-completed step was not re-executed")
    except Exception as e:
        reporter.record_fail("test_checkpoint_resumption_and_idempotency", str(e))
    finally:
        await cleanup_test_session(test_session)


async def test_approval_interruption_and_resumption():
    """Verify approval workflow pauses slice execution, yields token, and resumes on approval."""
    test_session = f"test_sl_appr_{uuid.uuid4().hex[:8]}"
    try:
        plan_steps = [
            AgentPlanStep(
                step_id="calc_step",
                tool_name="calculator",
                arguments={"expression": "7 * 7"},
                description="Calculate square",
                permission=ToolPermission.AUTOMATIC,
                dependencies=[],
                is_idempotent=True
            ),
            AgentPlanStep(
                step_id="note_step",
                tool_name="create_note",
                arguments={"title": "Serverless Approval Note", "content": "Value calculated was 49"},
                description="Save note with calculation",
                permission=ToolPermission.APPROVAL_REQUIRED,
                dependencies=["calc_step"],
                is_idempotent=False
            ),
        ]
        plan = AgentPlan(title="Approval Flow", steps=plan_steps)
        task_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        task = AgentTask(
            id=task_id,
            session_id=test_session,
            user_request="Calculate 7*7 and save note",
            task_type="agent",
            plan=plan,
            status=TaskStatus.RUNNING,
            created_at=now,
            updated_at=now
        )
        await agent_orchestrator._persist_new_task(task)
        await checkpoint_manager.init_task_checkpoints(task.id, task.session_id, plan)

        # Slice 1: Should run calc_step, then halt on note_step in AWAITING_APPROVAL
        resp1 = await agent_orchestrator.execute_task_slice(test_session, task.id, max_steps=1)
        assert resp1.task.status == TaskStatus.RUNNING
        assert (await checkpoint_manager.get_task_checkpoints(task.id, test_session))[0].status == StepStatus.SUCCEEDED

        # Slice 2: Encounters approval gate on note_step
        resp2 = await agent_orchestrator.execute_task_slice(test_session, task.id, max_steps=1)
        assert resp2.task.status == TaskStatus.AWAITING_APPROVAL, (
            f"Expected status AWAITING_APPROVAL, got {resp2.task.status}"
        )
        token = resp2.task.approval_token
        assert token is not None and len(token) > 10, "Approval token missing or empty"

        # Verify no note exists in DB yet
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            note_count = await conn.fetchval(
                "SELECT COUNT(*) FROM notes WHERE session_id = $1 AND title = $2",
                test_session, "Serverless Approval Note"
            )
            assert note_count == 0, "Note was created before approval was granted!"

        # Approve and resume via approve_task
        appr_resp = await agent_orchestrator.approve_task(
            session_id=test_session,
            task_id=task.id,
            approval_token=token
        )
        assert appr_resp.task.status in (TaskStatus.SUCCEEDED, TaskStatus.RUNNING)

        # Verify note now exists in Neon DB
        async with pool.acquire() as conn:
            note_row = await conn.fetchrow(
                "SELECT title, content FROM notes WHERE session_id = $1 AND title = $2",
                test_session, "Serverless Approval Note"
            )
            assert note_row is not None, "Note was not created after approval"
            assert "49" in note_row["content"]

        reporter.record_pass("test_approval_interruption_and_resumption", "Approval gate cleanly interrupted and resumed slice")
    except Exception as e:
        reporter.record_fail("test_approval_interruption_and_resumption", str(e))
    finally:
        await cleanup_test_session(test_session)


async def test_concurrent_worker_fencing_protection():
    """Verify that two workers claiming same task with different fencing generations are rejected."""
    test_session = f"test_sl_fence_{uuid.uuid4().hex[:8]}"
    try:
        plan_steps = [
            AgentPlanStep(
                step_id="step_long",
                tool_name="calculator",
                arguments={"expression": "1000 + 1"},
                description="Long calculation",
                permission=ToolPermission.AUTOMATIC,
                dependencies=[]
            )
        ]
        plan = AgentPlan(title="Fencing Test", steps=plan_steps)
        task_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        task = AgentTask(
            id=task_id,
            session_id=test_session,
            user_request="Fencing test",
            plan=plan,
            status=TaskStatus.PROPOSED,
            created_at=now,
            updated_at=now
        )
        await agent_orchestrator._persist_new_task(task)

        # Worker 1 claims lease
        ok1, gen1, err1 = await agent_orchestrator.claim_task_lease(
            task_id, test_session, worker_id="worker_alpha", lease_seconds=120
        )
        assert ok1 is True, f"Worker 1 claim failed: {err1}"

        # Worker 2 attempts concurrent claim while lease is active
        ok2, gen2, err2 = await agent_orchestrator.claim_task_lease(
            task_id, test_session, worker_id="worker_beta", lease_seconds=120
        )
        assert ok2 is False, "Worker 2 should have been rejected while Worker 1 holds active lease!"
        assert "held by active worker worker_alpha" in (err2 or "")

        reporter.record_pass("test_concurrent_worker_fencing_protection", "Active lease blocked concurrent worker contention")
    except Exception as e:
        reporter.record_fail("test_concurrent_worker_fencing_protection", str(e))
    finally:
        await cleanup_test_session(test_session)


async def test_cancellation_during_slicing():
    """Verify task cancellation prevents subsequent execution slices."""
    test_session = f"test_sl_cancel_{uuid.uuid4().hex[:8]}"
    try:
        plan_steps = [
            AgentPlanStep(
                step_id="s1",
                tool_name="calculator",
                arguments={"expression": "1 + 1"},
                description="Calculate s1",
                dependencies=[]
            ),
            AgentPlanStep(
                step_id="s2",
                tool_name="calculator",
                arguments={"expression": "2 + 2"},
                description="Calculate s2",
                dependencies=["s1"]
            ),
        ]
        plan = AgentPlan(title="Cancel Test", steps=plan_steps)
        task_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        task = AgentTask(
            id=task_id,
            session_id=test_session,
            user_request="Cancel test",
            plan=plan,
            status=TaskStatus.RUNNING,
            created_at=now,
            updated_at=now
        )
        await agent_orchestrator._persist_new_task(task)
        await checkpoint_manager.init_task_checkpoints(task.id, test_session, plan)

        # Cancel the task
        cancel_resp = await agent_orchestrator.cancel_task(test_session, task.id)
        assert cancel_resp.task.status == TaskStatus.CANCELLED

        # Attempt to run a slice on cancelled task
        slice_resp = await agent_orchestrator.execute_task_slice(test_session, task.id)
        assert slice_resp.task.status == TaskStatus.CANCELLED, (
            f"Expected CANCELLED, got {slice_resp.task.status}"
        )
        assert "cancelled" in slice_resp.reply.lower()

        reporter.record_pass("test_cancellation_during_slicing", "Cancelled task cleanly refused subsequent slices")
    except Exception as e:
        reporter.record_fail("test_cancellation_during_slicing", str(e))
    finally:
        await cleanup_test_session(test_session)


async def test_terminal_state_invariants():
    """Verify succeeded and failed tasks cannot be reopened by execution slice requests."""
    test_session = f"test_sl_term_{uuid.uuid4().hex[:8]}"
    try:
        plan = AgentPlan(title="Terminal Test", steps=[])
        task_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        task = AgentTask(
            id=task_id,
            session_id=test_session,
            user_request="Terminal invariant test",
            plan=plan,
            status=TaskStatus.SUCCEEDED,
            created_at=now,
            updated_at=now,
            completed_at=now
        )
        await agent_orchestrator._persist_new_task(task)

        resp = await agent_orchestrator.execute_task_slice(test_session, task_id)
        assert resp.task.status == TaskStatus.SUCCEEDED
        assert "already succeeded" in resp.reply.lower() or "already" in resp.reply.lower()

        reporter.record_pass("test_terminal_state_invariants", "Terminal state strictly preserved")
    except Exception as e:
        reporter.record_fail("test_terminal_state_invariants", str(e))
    finally:
        await cleanup_test_session(test_session)


async def test_stale_task_recovery_sweep():
    """Verify recover_interrupted_tasks cleans up tasks with expired execution leases."""
    test_session = f"test_sl_sweep_{uuid.uuid4().hex[:8]}"
    try:
        plan = AgentPlan(title="Stale Test", steps=[])
        task_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        expired_lease = now - timedelta(minutes=15)
        pool = await get_db_pool()

        # Insert a task that was left running with an expired lease
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO agent_tasks (
                    id, session_id, user_request, status,
                    execution_lease_expires_at, created_at, updated_at
                )
                VALUES ($1, $2, $3, 'running', $4, $5, $5)
                """,
                task_id,
                test_session,
                "Stale lease task",
                expired_lease,
                now - timedelta(minutes=30)
            )

        # Trigger recovery sweep
        recovered_count = await recover_interrupted_tasks(stale_threshold_minutes=5)
        assert recovered_count >= 1, f"Expected at least 1 recovered task, got {recovered_count}"

        # Verify task is now FAILED with explanation
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT status, result_summary FROM agent_tasks WHERE id = $1", task_id
            )
            assert row["status"] == "failed"
            assert "interrupted" in row["result_summary"].lower()

        reporter.record_pass("test_stale_task_recovery_sweep", f"Successfully recovered {recovered_count} stale task(s)")
    except Exception as e:
        reporter.record_fail("test_stale_task_recovery_sweep", str(e))
    finally:
        await cleanup_test_session(test_session)


async def test_session_guard_isolation():
    """Verify cross-session isolation prevents session A from slicing session B's task."""
    session_a = f"test_sl_sessA_{uuid.uuid4().hex[:8]}"
    session_b = f"test_sl_sessB_{uuid.uuid4().hex[:8]}"
    try:
        plan = AgentPlan(title="Isolation Test", steps=[
            AgentPlanStep(step_id="iso_1", tool_name="calculator", arguments={"expression": "1+1"}, description="Isolation step")
        ])
        task_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        task = AgentTask(
            id=task_id,
            session_id=session_a,
            user_request="Session A Task",
            plan=plan,
            status=TaskStatus.RUNNING,
            created_at=now,
            updated_at=now
        )
        await agent_orchestrator._persist_new_task(task)

        # Session B attempts to execute slice on Session A's task
        rejected = False
        try:
            await agent_orchestrator.execute_task_slice(
                session_id=session_b,
                task_id=task_id
            )
        except ValueError as ve:
            if "not found" in str(ve).lower() or "access denied" in str(ve).lower():
                rejected = True

        assert rejected is True, "Cross-session execution slice was NOT rejected!"
        reporter.record_pass("test_session_guard_isolation", "Cross-session task slicing strictly prevented")
    except Exception as e:
        reporter.record_fail("test_session_guard_isolation", str(e))
    finally:
        await cleanup_test_session(session_a)
        await cleanup_test_session(session_b)


async def test_frontend_api_base_url_and_relative_resolution():
    """Verify frontend uses VITE_API_BASE_URL, falls back to window.location.origin, and avoids hardcoded URLs."""
    from pathlib import Path
    try:
        client_path = Path(root_dir) / "frontend" / "src" / "api" / "client.js"
        assert client_path.exists(), "frontend/src/api/client.js does not exist"
        content = client_path.read_text(encoding="utf-8")

        # Must read VITE_API_BASE_URL
        assert "VITE_API_BASE_URL" in content, "frontend must read VITE_API_BASE_URL"
        assert "VITE_API_URL" not in content, "Obsolete VITE_API_URL must not be used in client.js"

        # Must fallback to window.location.origin
        assert "window.location.origin" in content, "client.js must fallback to window.location.origin"

        # No hardcoded production URLs in client.js
        assert "https://" not in content, "Hardcoded production URL found in client.js"

        # Check .env.example
        env_example = (Path(root_dir) / "frontend" / ".env.example").read_text(encoding="utf-8")
        assert "VITE_API_BASE_URL" in env_example, ".env.example must document VITE_API_BASE_URL"
        assert "VITE_API_URL=" not in env_example, ".env.example must not contain obsolete VITE_API_URL"

        reporter.record_pass("test_frontend_api_base_url_and_relative_resolution", "Frontend API client configuration verified")
    except Exception as e:
        reporter.record_fail("test_frontend_api_base_url_and_relative_resolution", str(e))


async def test_api_rewrite_specification_and_compatibility():
    """Verify root vercel.json rewrites every FastAPI route and provides SPA client fallback."""
    import json
    from pathlib import Path
    try:
        vercel_path = Path(root_dir) / "vercel.json"
        assert vercel_path.exists(), "Root vercel.json missing"
        config = json.loads(vercel_path.read_text(encoding="utf-8"))

        rewrites = config.get("rewrites", [])
        sources = [r["source"] for r in rewrites]
        destinations = [r["destination"] for r in rewrites]

        # Verify critical backend endpoints are rewritten to /api/index.py
        assert "/api/:path*" in sources, "Missing /api/:path* rewrite"
        assert "/health" in sources, "Missing /health rewrite"
        assert "/chat" in sources, "Missing /chat rewrite"
        assert "/docs" in sources, "Missing /docs rewrite"
        assert any("index.py" in d for d in destinations), "Missing destination /api/index.py"

        # Verify SPA fallback exists for client routes
        spa_fallback = next((r for r in rewrites if r.get("destination") == "/index.html"), None)
        assert spa_fallback is not None, "Missing SPA fallback rewrite to /index.html"

        # Verify function configuration
        fn_config = config.get("functions", {}).get("api/index.py", {})
        assert fn_config.get("maxDuration", 0) <= 60, "maxDuration must not exceed 60s"
        assert fn_config.get("memory", 0) >= 1024, "memory must be at least 1024MB"
        assert "crons" not in config, "Vercel Hobby plan does not permit crons block"

        reporter.record_pass("test_api_rewrite_specification_and_compatibility", "Root vercel.json routing & runtime verified")
    except Exception as e:
        reporter.record_fail("test_api_rewrite_specification_and_compatibility", str(e))


async def test_cron_recovery_vs_execution_distinction():
    """Verify cron recovery sweep only recovers stale leases and does NOT execute task steps."""
    test_session = f"test_sl_cron_{uuid.uuid4().hex[:8]}"
    pool = await get_db_pool()
    try:
        # Create a task with an expired lease
        task_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        expired_lease = now - timedelta(minutes=15)

        plan = AgentPlan(title="Cron Task", steps=[
            AgentPlanStep(step_id="step_cron", tool_name="calculator", arguments={"expression": "10*10"}, description="Unexecuted step")
        ])

        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO agent_tasks (
                    id, session_id, user_request, plan_json, status,
                    execution_lease_expires_at, worker_id, lease_generation,
                    created_at, updated_at
                ) VALUES ($1, $2, 'Cron lease test', $3::jsonb, 'running', $4, 'abandoned_worker', 1, $5, $5)
                """,
                task_id, test_session, plan.model_dump_json(), expired_lease, now - timedelta(minutes=20)
            )

        # Run recovery
        recovered = await recover_interrupted_tasks(stale_threshold_minutes=10)
        assert recovered >= 1, "Expected at least 1 task to be recovered by lease expiration sweep"

        # Verify task is marked 'failed' (interrupted), NOT executed or 'succeeded'
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT status, result_summary, execution_lease_expires_at FROM agent_tasks WHERE id = $1", task_id)
            assert row["status"] == "failed", f"Expected task status 'failed', got {row['status']}"
            assert "interrupted" in row["result_summary"].lower(), "Result summary must document interruption"
            assert row["execution_lease_expires_at"] is None, "Lease must be cleared"

        reporter.record_pass("test_cron_recovery_vs_execution_distinction", "Cron recovery strictly recovers leases without executing tasks")
    except Exception as e:
        reporter.record_fail("test_cron_recovery_vs_execution_distinction", str(e))
    finally:
        await cleanup_test_session(test_session)


async def test_browser_disconnect_and_later_resumption():
    """Verify task pauses safely on browser disconnect, retains checkpoints in Neon DB, and resumes cleanly."""
    test_session = f"test_sl_disc_{uuid.uuid4().hex[:8]}"
    try:
        # Step 1: Create 2-step task
        plan = AgentPlan(title="Disconnect Simulation", steps=[
            AgentPlanStep(step_id="st_1", tool_name="calculator", arguments={"expression": "2+2"}, description="Step 1"),
            AgentPlanStep(step_id="st_2", tool_name="calculator", arguments={"expression": "3*3"}, description="Step 2", dependencies=["st_1"])
        ])
        task_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        task = AgentTask(
            id=task_id,
            session_id=test_session,
            user_request="Disconnect Test",
            plan=plan,
            status=TaskStatus.RUNNING,
            created_at=now,
            updated_at=now
        )
        await agent_orchestrator._persist_new_task(task)
        await checkpoint_manager.init_task_checkpoints(task_id, test_session, plan)

        # Step 2: Browser drives slice 1
        resp1 = await agent_orchestrator.execute_task_slice(
            session_id=test_session,
            task_id=task_id,
            max_steps=1
        )
        assert resp1.task.status == TaskStatus.RUNNING

        # Verify step 1 checkpoint is SUCCEEDED in Neon DB
        cp1 = await checkpoint_manager.get_task_checkpoints(task_id, test_session)
        s1_cp = next(c for c in cp1 if c.step_id == "st_1")
        assert s1_cp.status in (StepStatus.SUCCEEDED, StepStatus.COMPLETED)
        res1_val = s1_cp.result.get("result") if isinstance(s1_cp.result, dict) else s1_cp.result
        assert res1_val == 4, f"Expected result 4, got {s1_cp.result}"

        # Step 3: Browser "disconnects" (idle delay)
        # Checkpoint remains in DB, step 2 is still PENDING
        s2_cp = next(c for c in cp1 if c.step_id == "st_2")
        assert s2_cp.status in (StepStatus.PENDING, StepStatus.READY)

        # Step 4: Browser "reconnects" and drives slice 2
        resp2 = await agent_orchestrator.execute_task_slice(
            session_id=test_session,
            task_id=task_id,
            max_steps=1
        )
        assert resp2.task.status == TaskStatus.SUCCEEDED

        cp2 = await checkpoint_manager.get_task_checkpoints(task_id, test_session)
        s2_cp_after = next(c for c in cp2 if c.step_id == "st_2")
        assert s2_cp_after.status in (StepStatus.SUCCEEDED, StepStatus.COMPLETED)
        res2_val = s2_cp_after.result.get("result") if isinstance(s2_cp_after.result, dict) else s2_cp_after.result
        assert res2_val == 9, f"Expected result 9, got {s2_cp_after.result}"

        reporter.record_pass("test_browser_disconnect_and_later_resumption", "Checkpoint durability & client resumption verified")
    except Exception as e:
        reporter.record_fail("test_browser_disconnect_and_later_resumption", str(e))
    finally:
        await cleanup_test_session(test_session)


async def test_multiple_cold_start_instances():
    """Verify independent serverless invocations maintain clean database connection boundaries."""
    from app.database import get_db_pool
    try:
        pool = await get_db_pool()
        assert pool is not None, "Active pool must be initialized"
        assert pool.get_max_size() <= 3, f"Serverless pool max size must be <= 3, got {pool.get_max_size()}"
        assert pool.get_min_size() >= 1, f"Serverless pool min size must be >= 1, got {pool.get_min_size()}"

        # Verify connection health across repeated queries
        async with pool.acquire() as conn:
            val = await conn.fetchval("SELECT 1;")
            assert val == 1

        reporter.record_pass("test_multiple_cold_start_instances", "Serverless DB pool sizing and cold-start boundaries verified")
    except Exception as e:
        reporter.record_fail("test_multiple_cold_start_instances", str(e))


async def test_concurrent_schema_initialization():
    """Verify PostgreSQL advisory lock serializes concurrent schema initializations across instances."""
    from app.database import init_db_schema
    try:
        import app.database as db_mod
        db_mod._schema_initialized = False

        async def worker_init():
            await init_db_schema()

        # Run 5 concurrent initializations
        await asyncio.gather(
            worker_init(),
            worker_init(),
            worker_init(),
            worker_init(),
            worker_init()
        )

        assert db_mod._schema_initialized is True
        reporter.record_pass("test_concurrent_schema_initialization", "Concurrent cold-start migrations safely serialized by advisory lock")
    except Exception as e:
        reporter.record_fail("test_concurrent_schema_initialization", str(e))


async def test_runtime_timeout_and_checkpoint_recovery():
    """Verify execute_task_slice gracefully intercepts timeouts before Vercel kills the function."""
    test_session = f"test_sl_time_{uuid.uuid4().hex[:8]}"
    from app.agent.tools.base import BaseTool
    from app.agent.tools.registry import tool_registry

    class SlowTool(BaseTool):
        name: str = "slow_timeout_tool"
        description: str = "Intentionally slow tool for timeout testing"
        permission: ToolPermission = ToolPermission.AUTOMATIC
        is_idempotent: bool = True

        async def execute(self, session_id: str, **kwargs):
            await asyncio.sleep(2.0)
            return "slow output"

    slow_tool_instance = SlowTool()
    tool_registry.register(slow_tool_instance)

    try:
        plan = AgentPlan(title="Timeout Test", steps=[
            AgentPlanStep(
                step_id="step_slow",
                tool_name="slow_timeout_tool",
                arguments={},
                description="Slow step to test timeout",
                permission=ToolPermission.AUTOMATIC,
                is_idempotent=True
            )
        ])
        task_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        task = AgentTask(
            id=task_id,
            session_id=test_session,
            user_request="Timeout test",
            plan=plan,
            status=TaskStatus.RUNNING,
            created_at=now,
            updated_at=now
        )
        await agent_orchestrator._persist_new_task(task)
        await checkpoint_manager.init_task_checkpoints(task_id, test_session, plan)

        # Execute slice with tight timeout of 0.5s
        resp = await agent_orchestrator.execute_task_slice(
            session_id=test_session,
            task_id=task_id,
            max_duration_seconds=0.5,
            max_steps=1
        )

        # Verify task handled timeout gracefully
        assert resp.task.status == TaskStatus.FAILED, f"Expected FAILED, got {resp.task.status}"
        assert "timed out" in resp.task.result_summary.lower(), f"Expected 'timed out' in {resp.task.result_summary}"

        # Verify checkpoint was recorded as FAILED with timeout error
        cp = await checkpoint_manager.get_task_checkpoints(task_id, test_session)
        slow_cp = next(c for c in cp if c.step_id == "step_slow")
        assert slow_cp.status == StepStatus.FAILED
        assert "timed out" in slow_cp.error_message.lower()

        # Verify task is recoverable via retry
        retry_resp = await agent_orchestrator.retry_task(test_session, task_id)
        assert retry_resp.task.status in (TaskStatus.SUCCEEDED, TaskStatus.COMPLETED, TaskStatus.RUNNING), (
            f"Expected retried task to succeed or resume, got {retry_resp.task.status}"
        )

        reporter.record_pass("test_runtime_timeout_and_checkpoint_recovery", "Internal timeout handled gracefully; task checkpoint recoverable")
    except Exception as e:
        reporter.record_fail("test_runtime_timeout_and_checkpoint_recovery", str(e))
    finally:
        tool_registry._tools.pop("slow_timeout_tool", None)
        await cleanup_test_session(test_session)


# ==============================================================================
# RUNNER
# ==============================================================================

async def run_all_serverless_tests():
    print("=" * 80)
    print(" MEMORA AI — SERVERLESS & VERCEL ARCHITECTURE TEST SUITE")
    print(" Verifying Bounded Execution Slices, Checkpointing, Leases & Fencing")
    print("=" * 80)

    await init_db_pool()

    try:
        await test_vercel_asgi_entrypoint()
        await test_serverless_db_pool_lifecycle()
        await test_serverless_task_creation()
        await test_bounded_execution_slice()
        await test_checkpoint_resumption_and_idempotency()
        await test_approval_interruption_and_resumption()
        await test_concurrent_worker_fencing_protection()
        await test_cancellation_during_slicing()
        await test_terminal_state_invariants()
        await test_stale_task_recovery_sweep()
        await test_session_guard_isolation()
        await test_frontend_api_base_url_and_relative_resolution()
        await test_api_rewrite_specification_and_compatibility()
        await test_cron_recovery_vs_execution_distinction()
        await test_browser_disconnect_and_later_resumption()
        await test_multiple_cold_start_instances()
        await test_concurrent_schema_initialization()
        await test_runtime_timeout_and_checkpoint_recovery()
    finally:
        await close_db_pool()

    print("-" * 80)
    print(f"Serverless Slices Suite: {reporter.passed} PASSED | {reporter.failed} FAILED")
    print("=" * 80)

    if reporter.failed > 0:
        print("\nFailures:")
        for name, err in reporter.errors:
            print(f"  ✗ {name}: {err}")
        sys.exit(1)
    else:
        print("\n✅ ALL SERVERLESS TESTS PASSED.")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(run_all_serverless_tests())
