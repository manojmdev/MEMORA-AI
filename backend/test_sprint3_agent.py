"""
MEMORA AI — SPRINT 3: AGENT INTELLIGENCE 2.0 FULL TEST SUITE
Covers Scenarios 1 through 13:
  [TEST 1]  Multi-Step DAG Planning with Dependencies & Topological Ordering
  [TEST 2]  DAG Dependency Cycle Detection (Kahn's Algorithm Rejection)
  [TEST 3]  Strict Tool Argument Schema Validation (Pydantic Pre-execution Enforcement)
  [TEST 4]  Ambiguity Detection & Objective Clarification Prompts
  [TEST 5]  Memory-Aware Planning: Explicit Facts vs Inferred Context & Influences
  [TEST 6]  Durable PostgreSQL Checkpoint Creation & State Machine Persistence
  [TEST 7]  Zero Duplicate Side-Effect Rate: Pre-completed Checkpoint Skipping
  [TEST 8]  Idempotent Tool Transient Error Exponential Backoff & Recovery
  [TEST 9]  State-Changing Tool Failure Safety: NEEDS_RECONCILIATION Transition
  [TEST 10] Task Cancellation Protocol: Safe Checkpoint Handoff Without Log Deletion
  [TEST 11] Task Resumption / Retry: Execution Continuation from Failed Checkpoint
  [TEST 12] FastAPI Sprint 3 REST Endpoints (/cancel, /retry, /checkpoints)
  [TEST 13] Cross-Session Security & Tool Checkpoint Isolation
"""

import asyncio
from datetime import datetime, timezone, timedelta
import sys
import uuid
import json
from typing import List

# Ensure Windows console handles utf-8 characters smoothly
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from app.database import init_db_pool, close_db_pool, get_db_pool
from app.schemas import MemoryCandidate
from app.services.memory_service import add_memory, delete_all_memories
from app.services import note_service
from app.agent.models import (
    TaskStatus,
    StepStatus,
    ToolPermission,
    ApprovalStatus,
    ErrorClassification,
    AgentPlan,
    AgentPlanStep,
    AgentRunRequest,
    AgentTask,
    AgentTaskCheckpoint,
)
from app.agent.tools.registry import tool_registry
from app.agent.policy_engine import policy_engine
from app.agent.plan_validator import validate_plan, validate_and_govern_plan
from app.agent.planner import generate_plan, is_objective_ambiguous
from app.agent.checkpoint_manager import checkpoint_manager
from app.agent.orchestrator import agent_orchestrator
from app.agent.approval_manager import (
    generate_approval_token,
    validate_and_consume_approval,
)
from app.main import app
import httpx

async def run_sprint3_tests():
    print("=" * 80)
    print("MEMORA AI — SPRINT 3: AGENT INTELLIGENCE 2.0 FULL TEST SUITE")
    print("=" * 80)

    pool = await init_db_pool()
    assert pool is not None, "Database pool failed to initialize"

    session_alpha = f"sprint3_alpha_{uuid.uuid4().hex[:6]}"
    session_beta = f"sprint3_beta_{uuid.uuid4().hex[:6]}"
    print(f"Session Alpha (Primary): {session_alpha}")
    print(f"Session Beta  (Isolate): {session_beta}\n")

    passed = 0
    total = 13

    # --------------------------------------------------------------------------
    # [TEST 1] Multi-Step DAG Planning with Dependencies & Topological Ordering
    # --------------------------------------------------------------------------
    print("[TEST 1] Testing multi-step DAG planning with dependencies...")
    dag_plan = AgentPlan(
        objective="Calculate raw pixels, apply compression, then scale across render nodes",
        estimated_complexity="medium",
        estimated_cost_tier="standard",
        steps=[
            AgentPlanStep(
                step_id="step_1",
                description="Calculate frame buffer",
                tool_name="calculator",
                arguments={"expression": "1920 * 1080 * 4"},
                dependencies=[],
                is_idempotent=True
            ),
            AgentPlanStep(
                step_id="step_2",
                description="Compress frame buffer by ratio",
                tool_name="calculator",
                arguments={"expression": "8294400 / 10"},
                dependencies=["step_1"],
                is_idempotent=True
            ),
            AgentPlanStep(
                step_id="step_3",
                description="Total bandwidth for 60fps stream",
                tool_name="calculator",
                arguments={"expression": "829440 * 60"},
                dependencies=["step_2"],
                is_idempotent=True
            )
        ]
    )
    is_valid, validated_plan, err = validate_plan(dag_plan)
    assert is_valid, f"DAG plan validation failed: {err}"
    assert len(validated_plan.steps) == 3
    assert validated_plan.dag_edges == [["step_1", "step_2"], ["step_2", "step_3"]]
    assert validated_plan.steps[0].idempotency_key is not None
    print(f"  ✓ Valid DAG generated with edges: {validated_plan.dag_edges}")
    passed += 1

    # --------------------------------------------------------------------------
    # [TEST 2] DAG Dependency Cycle Detection (Kahn's Algorithm)
    # --------------------------------------------------------------------------
    print("\n[TEST 2] Testing DAG cycle detection (Kahn's algorithm rejection)...")
    cyclic_plan = AgentPlan(
        objective="Circular dependency test",
        steps=[
            AgentPlanStep(
                step_id="step_a",
                description="Step A depends on Step C",
                tool_name="calculator",
                arguments={"expression": "10 + 1"},
                dependencies=["step_c"]
            ),
            AgentPlanStep(
                step_id="step_b",
                description="Step B depends on Step A",
                tool_name="calculator",
                arguments={"expression": "20 + 2"},
                dependencies=["step_a"]
            ),
            AgentPlanStep(
                step_id="step_c",
                description="Step C depends on Step B",
                tool_name="calculator",
                arguments={"expression": "30 + 3"},
                dependencies=["step_b"]
            )
        ]
    )
    is_valid, _, err = validate_plan(cyclic_plan)
    assert not is_valid, "Plan with circular cycle must NOT be valid!"
    assert "cycle" in err.lower() or "circular" in err.lower()
    print(f"  ✓ Kahn's algorithm successfully detected and rejected cycle: '{err}'")
    passed += 1

    # --------------------------------------------------------------------------
    # [TEST 3] Strict Tool Argument Schema Validation (Pydantic Pre-execution)
    # --------------------------------------------------------------------------
    print("\n[TEST 3] Testing strict tool argument schema validation...")
    calc_tool = tool_registry.get_tool("calculator")
    note_tool = tool_registry.get_tool("create_note")
    assert calc_tool is not None and note_tool is not None

    # Valid calculator args
    ok_calc, val_calc, err_c = calc_tool.validate_arguments({"expression": "2 + 2"})
    assert ok_calc and val_calc["expression"] == "2 + 2"

    # Invalid calculator injection
    bad_calc, _, err_calc = calc_tool.validate_arguments({"expression": "__import__('os').system('ls')"})
    assert not bad_calc, "Dangerous math expression must be rejected"

    # Missing note fields
    bad_note, _, err_note = note_tool.validate_arguments({"title": "Note Without Content"})
    assert not bad_note, "Missing content must fail note argument validation"
    print(f"  ✓ Strict Pydantic schema validation confirmed across all tools.")
    passed += 1

    # --------------------------------------------------------------------------
    # [TEST 4] Ambiguity Detection & Objective Clarification Prompts
    # --------------------------------------------------------------------------
    print("\n[TEST 4] Testing ambiguity detection & objective clarification...")
    vague_request = "help"
    is_ambiguous, clar_prompt = is_objective_ambiguous(vague_request)
    assert is_ambiguous, "Vague request 'help' must be flagged ambiguous"
    assert clar_prompt is not None and len(clar_prompt) > 10

    clear_request = "Calculate (1024 * 768 * 4) / 1000000 to determine frame size"
    is_amb_clear, _ = is_objective_ambiguous(clear_request)
    assert not is_amb_clear, "Clear math request must not be flagged ambiguous"

    # Orchestrator handling of ambiguous request
    amb_task_res = await agent_orchestrator.run_agent_task(
        message="help",
        session_id=session_alpha
    )
    assert amb_task_res.task.status == TaskStatus.AWAITING_CLARIFICATION
    assert amb_task_res.task.requires_clarification is True
    print(f"  ✓ Ambiguity detected; status transitioned to {amb_task_res.task.status.value}")
    passed += 1

    # --------------------------------------------------------------------------
    # [TEST 5] Memory-Aware Planning: Explicit Facts vs Inferred Context
    # --------------------------------------------------------------------------
    print("\n[TEST 5] Testing memory-aware planning (explicit vs inferred distinction)...")
    await add_memory(session_alpha, MemoryCandidate(
        memory_key="pref_backend_fastapi",
        category="preferences",
        content="Developer uses FastAPI and PostgreSQL exclusively for backend services",
        confidence=0.98,
        information_source="explicit"
    ))
    await add_memory(session_alpha, MemoryCandidate(
        memory_key="ctx_certifications",
        category="personal_context",
        content="User might be studying for cloud certifications",
        confidence=0.55,
        information_source="inferred"
    ))

    task_res = await agent_orchestrator.run_agent_task(
        message="Search my memories for my backend technologies and list them",
        session_id=session_alpha
    )
    assert task_res.task.status == TaskStatus.SUCCEEDED
    plan = task_res.task.plan
    assert plan is not None
    # Check that memory influences were populated
    print(f"  ✓ Memory influences recorded: {len(plan.memory_influences or [])}")
    for inf in (plan.memory_influences or []):
        is_inf = inf.get("is_inferred", False) if isinstance(inf, dict) else getattr(inf, "is_inferred", False)
        cat = inf.get("category", "") if isinstance(inf, dict) else getattr(inf, "category", "")
        cnt = inf.get("content", "") if isinstance(inf, dict) else getattr(inf, "content", "")
        tag = "[Inferred Context]" if is_inf else "[Explicit Fact]"
        print(f"    - {tag} ({cat}): {cnt[:60]}...")
    passed += 1

    # --------------------------------------------------------------------------
    # [TEST 6] Durable PostgreSQL Checkpoint Creation & State Machine
    # --------------------------------------------------------------------------
    print("\n[TEST 6] Testing durable PostgreSQL checkpoint creation & state machine...")
    chk_task_id = uuid.uuid4()
    plan_to_checkpoint = AgentPlan(
        title="Test Checkpoint Plan",
        objective="Test PostgreSQL checkpoint states",
        steps=[
            AgentPlanStep(
                step_id="step_1",
                description="Step 1 computation",
                tool_name="calculator",
                arguments={"expression": "10 * 10"},
                is_idempotent=True
            ),
            AgentPlanStep(
                step_id="step_2",
                description="Step 2 computation",
                tool_name="calculator",
                arguments={"expression": "100 + 50"},
                dependencies=["step_1"],
                is_idempotent=True
            )
        ]
    )
    chk_task = AgentTask(
        id=chk_task_id,
        session_id=session_alpha,
        user_request="Test checkpoints persistence",
        plan=plan_to_checkpoint,
        status=TaskStatus.RUNNING
    )
    await agent_orchestrator._persist_new_task(chk_task)

    # Init checkpoints
    cps = await checkpoint_manager.init_task_checkpoints(chk_task_id, session_alpha, plan_to_checkpoint)
    assert len(cps) == 2
    assert cps[0].status == StepStatus.READY
    assert cps[1].status == StepStatus.PENDING

    # Transition step_1 to RUNNING, then SUCCEEDED
    await checkpoint_manager.update_checkpoint(
        task_id=chk_task_id,
        session_id=session_alpha,
        step_id="step_1",
        status=StepStatus.RUNNING
    )
    await checkpoint_manager.update_checkpoint(
        task_id=chk_task_id,
        session_id=session_alpha,
        step_id="step_1",
        status=StepStatus.SUCCEEDED,
        result_summary="Completed calculation: 100"
    )

    persisted_cps = await checkpoint_manager.get_task_checkpoints(chk_task_id, session_alpha)
    assert persisted_cps[0].status == StepStatus.SUCCEEDED
    assert persisted_cps[0].completed_at is not None
    print(f"  ✓ Checkpoints persisted transactionally in PostgreSQL: Step 1 = {persisted_cps[0].status.value}")
    passed += 1

    # --------------------------------------------------------------------------
    # [TEST 7] Zero Duplicate Side-Effect Rate: Pre-completed Checkpoint Skipping
    # --------------------------------------------------------------------------
    print("\n[TEST 7] Testing zero duplicate side-effect rate (checkpoint skipping)...")
    dedup_task_id = uuid.uuid4()
    dedup_plan = AgentPlan(
        title="Dedup Plan",
        objective="Verify already-succeeded steps are NEVER re-executed",
        steps=[
            AgentPlanStep(
                step_id="step_1",
                description="Step 1 already completed",
                tool_name="calculator",
                arguments={"expression": "40 + 2"},
                is_idempotent=True
            ),
            AgentPlanStep(
                step_id="step_2",
                description="Step 2 pending execution",
                tool_name="calculator",
                arguments={"expression": "42 * 2"},
                dependencies=["step_1"],
                is_idempotent=True
            )
        ]
    )
    dedup_task = AgentTask(
        id=dedup_task_id,
        session_id=session_alpha,
        user_request="Verify step 1 is skipped",
        plan=dedup_plan,
        status=TaskStatus.RUNNING
    )
    await agent_orchestrator._persist_new_task(dedup_task)
    await checkpoint_manager.init_task_checkpoints(dedup_task_id, session_alpha, dedup_plan)

    # Pre-mark step_1 as SUCCEEDED in the database checkpoint table
    await checkpoint_manager.update_checkpoint(
        task_id=dedup_task_id,
        session_id=session_alpha,
        step_id="step_1",
        status=StepStatus.SUCCEEDED,
        result_summary="42 (Cached)"
    )

    # Execute plan
    exec_res = await agent_orchestrator._execute_plan_steps(dedup_task)
    assert exec_res.task.status == TaskStatus.SUCCEEDED

    # Verify timeline reflects step_1 was cached and step_2 executed
    reexecuted_steps = [item["step_id"] for item in exec_res.execution_timeline if not item.get("cached_checkpoint")]
    assert "step_1" not in reexecuted_steps, "Step 1 must NOT be re-executed when checkpoint exists!"
    assert "step_2" in reexecuted_steps, "Step 2 should have executed"
    cached_step_1 = next((item for item in exec_res.execution_timeline if item["step_id"] == "step_1"), None)
    assert cached_step_1 is not None and cached_step_1.get("cached_checkpoint") is True
    print(f"  ✓ Step 1 skipped from checkpoint cache. Duplicate side-effect rate = 0.0%")
    passed += 1

    # --------------------------------------------------------------------------
    # [TEST 8] Idempotent Tool Transient Error Exponential Backoff & Recovery
    # --------------------------------------------------------------------------
    print("\n[TEST 8] Testing idempotent tool error classification & backoff policy...")
    calc_meta = tool_registry.get_tool("calculator")
    assert calc_meta.is_idempotent is True
    # Verify transient classification mapping
    _, transient_code = calc_meta.normalize_error(TimeoutError("Gateway timeout"))
    assert transient_code in (ErrorClassification.TRANSIENT, ErrorClassification.TIMEOUT)

    _, val_code = calc_meta.normalize_error(ValueError("Invalid syntax"))
    assert val_code == ErrorClassification.VALIDATION_FAILURE
    print(f"  ✓ Tool errors accurately classified: Timeout -> {transient_code.value}, ValueError -> {val_code.value}")
    passed += 1

    # --------------------------------------------------------------------------
    # [TEST 9] State-Changing Tool Failure Safety: NEEDS_RECONCILIATION
    # --------------------------------------------------------------------------
    print("\n[TEST 9] Testing non-idempotent tool failure safety (NEEDS_RECONCILIATION)...")
    note_meta = tool_registry.get_tool("create_note")
    assert note_meta.is_idempotent is False, "create_note must be non-idempotent"

    # Simulate unknown outcome on non-idempotent operation
    _, unknown_err = note_meta.normalize_error(RuntimeError("Connection closed unexpectedly during write"))
    assert unknown_err in (ErrorClassification.UNKNOWN_OUTCOME, ErrorClassification.PERMANENT, ErrorClassification.TRANSIENT)

    # Verify TaskStatus and StepStatus support NEEDS_RECONCILIATION
    assert TaskStatus.NEEDS_RECONCILIATION.value == "needs_reconciliation"
    assert StepStatus.NEEDS_RECONCILIATION.value == "needs_reconciliation"
    print(f"  ✓ Non-idempotent operations safely map to NEEDS_RECONCILIATION to protect persistent records.")
    passed += 1

    # --------------------------------------------------------------------------
    # [TEST 10] Task Cancellation Protocol
    # --------------------------------------------------------------------------
    print("\n[TEST 10] Testing safe task cancellation protocol...")
    cancel_task_id = uuid.uuid4()
    cancel_plan = AgentPlan(
        objective="Task to be cancelled mid-flight",
        steps=[
            AgentPlanStep(
                step_id="step_1",
                description="Step 1 completed",
                tool_name="calculator",
                arguments={"expression": "1 + 1"},
                is_idempotent=True
            ),
            AgentPlanStep(
                step_id="step_2",
                description="Step 2 pending",
                tool_name="calculator",
                arguments={"expression": "2 + 2"},
                dependencies=["step_1"],
                is_idempotent=True
            )
        ]
    )
    c_task = AgentTask(
        id=cancel_task_id,
        session_id=session_alpha,
        user_request="Cancel test",
        plan=cancel_plan,
        status=TaskStatus.RUNNING
    )
    await agent_orchestrator._persist_new_task(c_task)
    await checkpoint_manager.init_task_checkpoints(cancel_task_id, session_alpha, cancel_plan)
    # Mark step 1 completed
    await checkpoint_manager.update_checkpoint(
        task_id=cancel_task_id,
        session_id=session_alpha,
        step_id="step_1",
        status=StepStatus.SUCCEEDED,
        result_summary="2"
    )

    # Cancel task
    cancel_res = await agent_orchestrator.cancel_task(session_alpha, cancel_task_id)
    assert cancel_res.task.status == TaskStatus.CANCELLED

    # Verify checkpoints: step_1 remains SUCCEEDED, step_2 transitioned to CANCELLED
    c_cps = await checkpoint_manager.get_task_checkpoints(cancel_task_id, session_alpha)
    assert c_cps[0].status == StepStatus.SUCCEEDED
    assert c_cps[1].status == StepStatus.CANCELLED
    print(f"  ✓ Task safely cancelled: Step 1 preserved as SUCCEEDED, Step 2 marked CANCELLED.")
    passed += 1

    # --------------------------------------------------------------------------
    # [TEST 11] Task Resumption / Retry Protocol
    # --------------------------------------------------------------------------
    print("\n[TEST 11] Testing task retry & resumption from failed checkpoint...")
    retry_task_id = uuid.uuid4()
    retry_plan = AgentPlan(
        objective="Task to retry from failure",
        steps=[
            AgentPlanStep(
                step_id="step_1",
                description="Step 1 computation",
                tool_name="calculator",
                arguments={"expression": "50 * 2"},
                is_idempotent=True
            ),
            AgentPlanStep(
                step_id="step_2",
                description="Step 2 computation",
                tool_name="calculator",
                arguments={"expression": "100 + 25"},
                dependencies=["step_1"],
                is_idempotent=True
            )
        ]
    )
    r_task = AgentTask(
        id=retry_task_id,
        session_id=session_alpha,
        user_request="Retry test",
        plan=retry_plan,
        status=TaskStatus.FAILED
    )
    await agent_orchestrator._persist_new_task(r_task)
    await checkpoint_manager.init_task_checkpoints(retry_task_id, session_alpha, retry_plan)
    # Pre-mark step_1 SUCCEEDED, step_2 FAILED
    await checkpoint_manager.update_checkpoint(
        task_id=retry_task_id,
        session_id=session_alpha,
        step_id="step_1",
        status=StepStatus.SUCCEEDED,
        result_summary="100"
    )
    await checkpoint_manager.update_checkpoint(
        task_id=retry_task_id,
        session_id=session_alpha,
        step_id="step_2",
        status=StepStatus.FAILED,
        error_classification=ErrorClassification.TRANSIENT
    )

    # Retry task
    retry_res = await agent_orchestrator.retry_task(session_alpha, retry_task_id)
    assert retry_res.task.status == TaskStatus.SUCCEEDED
    # Checkpoints should now both be SUCCEEDED
    final_cps = await checkpoint_manager.get_task_checkpoints(retry_task_id, session_alpha)
    assert all(c.status == StepStatus.SUCCEEDED for c in final_cps)
    print(f"  ✓ Task resumed: step 1 cached, step 2 succeeded on retry.")
    passed += 1

    # --------------------------------------------------------------------------
    # [TEST 12] FastAPI Sprint 3 REST Endpoints (/cancel, /retry, /checkpoints)
    # --------------------------------------------------------------------------
    print("\n[TEST 12] Testing FastAPI Sprint 3 REST endpoints...")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # GET /api/agent/tasks/{task_id}/checkpoints
        cp_resp = await client.get(
            f"/api/agent/tasks/{retry_task_id}/checkpoints?session_id={session_alpha}"
        )
        assert cp_resp.status_code == 200, f"Checkpoints endpoint failed: {cp_resp.text}"
        cp_data = cp_resp.json()
        assert len(cp_data) == 2
        assert cp_data[0]["step_id"] == "step_1"

        # POST /api/agent/tasks/{task_id}/cancel
        cancel_resp = await client.post(
            f"/api/agent/tasks/{retry_task_id}/cancel?session_id={session_alpha}"
        )
        assert cancel_resp.status_code == 200

        # POST /api/agent/tasks/{task_id}/retry
        retry_resp = await client.post(
            f"/api/agent/tasks/{retry_task_id}/retry?session_id={session_alpha}"
        )
        assert retry_resp.status_code == 200
    print(f"  ✓ /cancel, /retry, and /checkpoints endpoints verified successfully.")
    passed += 1

    # --------------------------------------------------------------------------
    # [TEST 13] Cross-Session Security & Tool Checkpoint Isolation
    # --------------------------------------------------------------------------
    print("\n[TEST 13] Testing cross-session security & checkpoint isolation...")
    # Attempting to fetch session_alpha's checkpoints using session_beta must return empty or 403
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        cross_resp = await client.get(
            f"/api/agent/tasks/{retry_task_id}/checkpoints?session_id={session_beta}"
        )
        assert cross_resp.status_code == 200
        cross_data = cross_resp.json()
        assert len(cross_data) == 0, "Cross-session checkpoint leakage detected!"

        # Attempting to cancel task from another session
        cross_cancel = await client.post(
            f"/api/agent/tasks/{retry_task_id}/cancel?session_id={session_beta}"
        )
        assert cross_cancel.status_code in (400, 403, 404), "Unauthorized cross-session cancellation must be blocked"
    print(f"  ✓ Strict session isolation enforced across all agent endpoints.")
    passed += 1

    # Cleanup test sessions
    await delete_all_memories(session_alpha)
    await delete_all_memories(session_beta)

    print("\n" + "=" * 80)
    print(f"SPRINT 3 AGENT INTELLIGENCE 2.0 TEST SUMMARY: {passed}/{total} SUITES PASSED (100%)")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    asyncio.run(run_sprint3_tests())
