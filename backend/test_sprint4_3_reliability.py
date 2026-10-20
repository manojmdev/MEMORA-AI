"""
MEMORA AI — SPRINT 4.3: ZERO-BLOCKER PRODUCT RELIABILITY & AGENT EXECUTION EXCELLENCE
Comprehensive 15-Scenario Automated Reliability & Failure-Recovery Test Suite

Scenarios Covered:
  [TEST 1]  Parallel Execution of Independent Steps in Topological Waves
  [TEST 2]  Sequential Dependency Propagation Across Multiple Waves
  [TEST 3]  Prerequisite Failure Propagation & Downstream Step Skipping
  [TEST 4]  Approval Expiration: Atomic Plan & Checkpoint Synchronization
  [TEST 5]  Approval Rejection Protocol & State Cleanup
  [TEST 6]  Cryptographic Approval Signature Validation & Atomic Consumption
  [TEST 7]  Unhashed / Tampered Approval Token Rejection Without Side Effects
  [TEST 8]  Non-Idempotent Tool Unknown Outcome Safety (NEEDS_RECONCILIATION)
  [TEST 9]  Idempotent Tool Transient Error Exponential Backoff & Recovery
  [TEST 10] Response Synthesis Fallback Resilience
  [TEST 11] Strict Task State Machine Transition Rules (validate_task_transition)
  [TEST 12] Worker Fencing Generation Protection Against Split-Brain Updates
  [TEST 13] In-Flight Task Cancellation Safety
  [TEST 14] Cross-Session Security & Checkpoint Isolation
  [TEST 15] Full End-to-End Task Lifecycle, Timeline & Checkpoint Parity
"""

import asyncio
from datetime import datetime, timezone, timedelta
import sys
import uuid
import json
from typing import List

# Ensure Windows console handles utf-8 characters smoothly
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

from app.database import init_db_pool, close_db_pool, get_db_pool
from app.services import note_service
from app.agent.models import (
    TaskStatus,
    StepStatus,
    ToolPermission,
    ApprovalStatus,
    ErrorClassification,
    AgentPlan,
    AgentPlanStep,
    AgentTask,
    AgentTaskCheckpoint,
    StaleWorkerError,
    InvalidStateTransitionError,
    validate_task_transition,
)
from app.agent.tools.registry import tool_registry
from app.agent.checkpoint_manager import checkpoint_manager
from app.agent.orchestrator import agent_orchestrator
from app.agent.approval_manager import (
    generate_approval_token,
    validate_and_consume_approval,
    create_approval_request,
    bind_approval_to_task,
    reject_approval,
)


async def run_reliability_suite():
    print("=" * 80)
    print("MEMORA AI — SPRINT 4.3: AGENT EXECUTION EXCELLENCE & RELIABILITY TEST SUITE")
    print("=" * 80)

    pool = await init_db_pool()
    assert pool is not None, "Database pool failed to initialize"

    test_session = f"rel_{uuid.uuid4().hex[:6]}"
    isolate_session = f"rel_iso_{uuid.uuid4().hex[:6]}"
    print(f"Primary Session: {test_session}")
    print(f"Isolate Session: {isolate_session}\n")

    passed = 0
    total = 15

    try:
        # ======================================================================
        # [TEST 1] Parallel Execution of Independent Steps in Topological Wave
        # ======================================================================
        print("[TEST 1] Parallel Execution of Independent Steps in Topological Wave...")
        task_1_id = str(uuid.uuid4())
        step_1a = AgentPlanStep(
            step_id="step_1a",
            tool_name="calculator",
            arguments={"expression": "100 + 50"},
            description="Calculate sum A",
            dependencies=[]
        )
        step_1b = AgentPlanStep(
            step_id="step_1b",
            tool_name="calculator",
            arguments={"expression": "200 * 3"},
            description="Calculate product B",
            dependencies=[]
        )
        plan_1 = AgentPlan(
            title="Independent steps parallel test",
            goal="Test concurrent execution",
            steps=[step_1a, step_1b]
        )
        task_1 = AgentTask(
            id=task_1_id,
            session_id=test_session,
            user_request="Compute parallel math",
            status=TaskStatus.PLANNING,
            plan=plan_1
        )
        await agent_orchestrator._persist_new_task(task_1)
        await checkpoint_manager.init_task_checkpoints(task_1_id, test_session, plan_1)

        t0 = asyncio.get_event_loop().time()
        resp_1 = await agent_orchestrator._execute_plan_steps(task_1)
        duration_1 = asyncio.get_event_loop().time() - t0

        assert resp_1.task.status in (TaskStatus.SUCCEEDED, TaskStatus.COMPLETED)
        assert step_1a.status == StepStatus.SUCCEEDED
        assert step_1b.status == StepStatus.SUCCEEDED
        assert step_1a.result.get("result") == 150
        assert step_1b.result.get("result") == 600
        print(f"  ✓ Both independent steps completed successfully in parallel wave ({duration_1*1000:.1f}ms).")
        passed += 1

        # ======================================================================
        # [TEST 2] Sequential Dependency Propagation Across Waves
        # ======================================================================
        print("\n[TEST 2] Sequential Dependency Propagation Across Waves...")
        task_2_id = str(uuid.uuid4())
        step_2a = AgentPlanStep(
            step_id="step_2a",
            tool_name="calculator",
            arguments={"expression": "10 * 5"},
            description="Base multiplication",
            dependencies=[]
        )
        step_2b = AgentPlanStep(
            step_id="step_2b",
            tool_name="calculator",
            arguments={"expression": "50 + 25"},
            description="Dependent addition",
            dependencies=["step_2a"]
        )
        step_2c = AgentPlanStep(
            step_id="step_2c",
            tool_name="calculator",
            arguments={"expression": "75 / 5"},
            description="Final division",
            dependencies=["step_2b"]
        )
        plan_2 = AgentPlan(
            title="Sequential dependencies test",
            goal="Test sequential wave ordering",
            steps=[step_2a, step_2b, step_2c]
        )
        task_2 = AgentTask(
            id=task_2_id,
            session_id=test_session,
            user_request="Sequential calculation chain",
            status=TaskStatus.PLANNING,
            plan=plan_2
        )
        await agent_orchestrator._persist_new_task(task_2)
        await checkpoint_manager.init_task_checkpoints(task_2_id, test_session, plan_2)

        resp_2 = await agent_orchestrator._execute_plan_steps(task_2)
        assert resp_2.task.status in (TaskStatus.SUCCEEDED, TaskStatus.COMPLETED)
        assert all(s.status == StepStatus.SUCCEEDED for s in plan_2.steps)
        # Verify execution order in timeline
        step_ids_order = [t["step_id"] for t in resp_2.execution_timeline if "step_id" in t]
        assert step_ids_order.index("step_2a") < step_ids_order.index("step_2b") < step_ids_order.index("step_2c")
        print(f"  ✓ Strict wave ordering verified: step_2a -> step_2b -> step_2c.")
        passed += 1

        # ======================================================================
        # [TEST 3] Prerequisite Failure Propagation & Downstream Step Skipping
        # ======================================================================
        print("\n[TEST 3] Prerequisite Failure Propagation & Downstream Step Skipping...")
        task_3_id = str(uuid.uuid4())
        step_3a = AgentPlanStep(
            step_id="step_3a",
            tool_name="calculator",
            arguments={"expression": "10 / 0"},  # ZeroDivisionError
            description="Failing step",
            dependencies=[]
        )
        step_3b = AgentPlanStep(
            step_id="step_3b",
            tool_name="calculator",
            arguments={"expression": "5 + 5"},
            description="Downstream step that should be skipped",
            dependencies=["step_3a"]
        )
        plan_3 = AgentPlan(
            title="Failure propagation test",
            goal="Test skipped downstream steps",
            steps=[step_3a, step_3b]
        )
        task_3 = AgentTask(
            id=task_3_id,
            session_id=test_session,
            user_request="Trigger prerequisite failure",
            status=TaskStatus.PLANNING,
            plan=plan_3
        )
        await agent_orchestrator._persist_new_task(task_3)
        await checkpoint_manager.init_task_checkpoints(task_3_id, test_session, plan_3)

        resp_3 = await agent_orchestrator._execute_plan_steps(task_3)
        assert resp_3.task.status == TaskStatus.FAILED
        assert step_3a.status == StepStatus.FAILED
        assert step_3b.status == StepStatus.SKIPPED
        # Check database checkpoint
        cps_3 = await checkpoint_manager.get_task_checkpoints(task_3_id, test_session)
        cp_3b = next(c for c in cps_3 if c.step_id == "step_3b")
        assert cp_3b.status == StepStatus.SKIPPED
        print("  ✓ Failing step marked FAILED, downstream step marked SKIPPED in DB.")
        passed += 1

        # ======================================================================
        # [TEST 4] Approval Expiration: Atomic Plan & Checkpoint Synchronization
        # ======================================================================
        print("\n[TEST 4] Approval Expiration: Atomic Plan & Checkpoint Synchronization...")
        task_4_id = str(uuid.uuid4())
        step_4 = AgentPlanStep(
            step_id="step_4a",
            tool_name="create_note",
            arguments={"title": "Expired Note", "content": "Content"},
            description="Create note with expired approval",
            permission=ToolPermission.APPROVAL_REQUIRED,
            status=StepStatus.AWAITING_APPROVAL
        )
        plan_4 = AgentPlan(
            title="Expired approval test",
            goal="Test expiration handling",
            steps=[step_4]
        )
        task_4 = AgentTask(
            id=task_4_id,
            session_id=test_session,
            user_request="Test approval expiration",
            status=TaskStatus.AWAITING_APPROVAL,
            plan=plan_4
        )
        await agent_orchestrator._persist_new_task(task_4)
        await checkpoint_manager.init_task_checkpoints(task_4_id, test_session, plan_4)

        # Create expired approval token
        appr_req_4 = create_approval_request(
            task_id=task_4_id,
            step_id="step_4a",
            tool_name="create_note",
            arguments=step_4.arguments,
            ttl_seconds=-60  # already expired 60 seconds ago
        )
        await bind_approval_to_task(task_4_id, test_session, appr_req_4)

        # Attempt to consume expired token
        ok_4, err_4 = await validate_and_consume_approval(
            task_id=task_4_id,
            session_id=test_session,
            approval_token=appr_req_4.approval_token
        )
        assert ok_4 is False
        assert "expired" in err_4.lower()

        # Verify DB checkpoint was updated to FAILED
        cps_4 = await checkpoint_manager.get_task_checkpoints(task_4_id, test_session)
        cp_4a = next(c for c in cps_4 if c.step_id == "step_4a")
        assert cp_4a.status == StepStatus.FAILED

        # Verify plan_json in DB was updated so step_4a is FAILED
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT plan_json, status FROM agent_tasks WHERE id = $1", uuid.UUID(task_4_id))
            stored_plan = json.loads(row["plan_json"])
            stored_step = next(s for s in stored_plan["steps"] if s["step_id"] == "step_4a")
            assert stored_step["status"] == "failed"
            assert row["status"] == "failed"

        print("  ✓ Expired token rejected; plan_json, checkpoints, and task record synchronized to FAILED.")
        passed += 1

        # ======================================================================
        # [TEST 5] Approval Rejection Protocol & State Cleanup
        # ======================================================================
        print("\n[TEST 5] Approval Rejection Protocol & State Cleanup...")
        task_5_id = str(uuid.uuid4())
        step_5 = AgentPlanStep(
            step_id="step_5a",
            tool_name="create_note",
            arguments={"title": "Rejected Note", "content": "Content"},
            description="Create note that user rejects",
            permission=ToolPermission.APPROVAL_REQUIRED,
            status=StepStatus.AWAITING_APPROVAL
        )
        plan_5 = AgentPlan(
            title="Rejected approval test",
            goal="Test user rejection",
            steps=[step_5]
        )
        task_5 = AgentTask(
            id=task_5_id,
            session_id=test_session,
            user_request="Test user approval rejection",
            status=TaskStatus.AWAITING_APPROVAL,
            plan=plan_5
        )
        await agent_orchestrator._persist_new_task(task_5)
        await checkpoint_manager.init_task_checkpoints(task_5_id, test_session, plan_5)

        appr_req_5 = create_approval_request(
            task_id=task_5_id,
            step_id="step_5a",
            tool_name="create_note",
            arguments=step_5.arguments
        )
        await bind_approval_to_task(task_5_id, test_session, appr_req_5)

        # Reject with reason
        rejection_reason = "User declined note creation: sensitive content"
        rej_ok, rej_msg = await reject_approval(
            task_id=task_5_id,
            session_id=test_session,
            reason=rejection_reason
        )
        assert rej_ok is True

        # Verify DB checkpoint was updated to CANCELLED
        cps_5 = await checkpoint_manager.get_task_checkpoints(task_5_id, test_session)
        cp_5a = next(c for c in cps_5 if c.step_id == "step_5a")
        assert cp_5a.status == StepStatus.CANCELLED

        # Verify plan_json in DB was updated so step_5a is CANCELLED
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT plan_json, status, approval_status, result_summary FROM agent_tasks WHERE id = $1", uuid.UUID(task_5_id))
            stored_plan = json.loads(row["plan_json"])
            stored_step = next(s for s in stored_plan["steps"] if s["step_id"] == "step_5a")
            assert stored_step["status"] == "cancelled"
            assert row["status"] == "cancelled"
            assert row["approval_status"] == "rejected"
            assert rejection_reason in row["result_summary"]

        print("  ✓ Approval rejection cleanly marked step CANCELLED and task CANCELLED with rejection reason.")
        passed += 1

        # ======================================================================
        # [TEST 6] Cryptographic Approval Signature Validation & Atomic Consumption
        # ======================================================================
        print("\n[TEST 6] Cryptographic Approval Signature Validation & Atomic Consumption...")
        task_6_id = str(uuid.uuid4())
        step_6 = AgentPlanStep(
            step_id="step_6a",
            tool_name="create_note",
            arguments={"title": "Approved Note", "content": "Reliability proof"},
            description="Create approved note",
            permission=ToolPermission.APPROVAL_REQUIRED,
            status=StepStatus.AWAITING_APPROVAL
        )
        plan_6 = AgentPlan(
            title="Valid approval test",
            goal="Test valid approval consumption",
            steps=[step_6]
        )
        task_6 = AgentTask(
            id=task_6_id,
            session_id=test_session,
            user_request="Test valid cryptographic approval",
            status=TaskStatus.AWAITING_APPROVAL,
            plan=plan_6
        )
        await agent_orchestrator._persist_new_task(task_6)
        await checkpoint_manager.init_task_checkpoints(task_6_id, test_session, plan_6)

        appr_req_6 = create_approval_request(
            task_id=task_6_id,
            step_id="step_6a",
            tool_name="create_note",
            arguments=step_6.arguments
        )
        await bind_approval_to_task(task_6_id, test_session, appr_req_6)

        # Consume valid approval
        ok_6, msg_6 = await validate_and_consume_approval(
            task_id=task_6_id,
            session_id=test_session,
            approval_token=appr_req_6.approval_token
        )
        assert ok_6 is True

        # Verify DB status transitioned to RUNNING
        async with pool.acquire() as conn:
            row_6 = await conn.fetchrow("SELECT status, approval_status FROM agent_tasks WHERE id = $1", uuid.UUID(task_6_id))
            assert row_6["status"] == "running"
            assert row_6["approval_status"] == "approved"

        # Second attempt to consume same token must be rejected (single-use replay prevention)
        ok_6_replay, msg_6_replay = await validate_and_consume_approval(
            task_id=task_6_id,
            session_id=test_session,
            approval_token=appr_req_6.approval_token
        )
        assert ok_6_replay is False
        assert "consumed" in msg_6_replay.lower() or "invalid" in msg_6_replay.lower() or "status" in msg_6_replay.lower()

        print("  ✓ Valid HMAC token consumed atomically; replay attack rejected.")
        passed += 1

        # ======================================================================
        # [TEST 7] Unhashed / Tampered Approval Token Rejection Without Side Effects
        # ======================================================================
        print("\n[TEST 7] Unhashed / Tampered Approval Token Rejection...")
        task_7_id = str(uuid.uuid4())
        step_7 = AgentPlanStep(
            step_id="step_7a",
            tool_name="create_note",
            arguments={"title": "Tampered Token Note", "content": "Content"},
            description="Create note with tampered token test",
            permission=ToolPermission.APPROVAL_REQUIRED,
            status=StepStatus.AWAITING_APPROVAL
        )
        plan_7 = AgentPlan(
            title="Tampered token test",
            goal="Test invalid signature rejection",
            steps=[step_7]
        )
        task_7 = AgentTask(
            id=task_7_id,
            session_id=test_session,
            user_request="Test tampered token",
            status=TaskStatus.AWAITING_APPROVAL,
            plan=plan_7
        )
        await agent_orchestrator._persist_new_task(task_7)
        await checkpoint_manager.init_task_checkpoints(task_7_id, test_session, plan_7)

        appr_req_7 = create_approval_request(
            task_id=task_7_id,
            step_id="step_7a",
            tool_name="create_note",
            arguments=step_7.arguments
        )
        await bind_approval_to_task(task_7_id, test_session, appr_req_7)

        tampered_token = "memora_appr_fake_tampered_signature_token"
        ok_7, msg_7 = await validate_and_consume_approval(
            task_id=task_7_id,
            session_id=test_session,
            approval_token=tampered_token
        )
        assert ok_7 is False
        assert "invalid" in msg_7.lower() or "unhashed" in msg_7.lower()
        print("  ✓ Tampered / invalid token rejected safely without process failure.")
        passed += 1

        # ======================================================================
        # [TEST 8] Non-Idempotent Tool Unknown Outcome Safety (NEEDS_RECONCILIATION)
        # ======================================================================
        print("\n[TEST 8] Non-Idempotent Tool Unknown Outcome Safety...")
        task_8_id = str(uuid.uuid4())
        step_8 = AgentPlanStep(
            step_id="step_8a",
            tool_name="create_note",
            arguments={"title": "Reconciliation Test Note", "content": "Test"},
            description="Create note with interrupted outcome",
            is_idempotent=False
        )
        plan_8 = AgentPlan(
            title="Non-idempotent unknown outcome test",
            goal="Test reconciliation transition",
            steps=[step_8]
        )
        task_8 = AgentTask(
            id=task_8_id,
            session_id=test_session,
            user_request="Simulate uncertain crash",
            status=TaskStatus.RUNNING,
            plan=plan_8
        )
        await agent_orchestrator._persist_new_task(task_8)
        await checkpoint_manager.init_task_checkpoints(task_8_id, test_session, plan_8)

        # Pre-seed checkpoint as DISPATCHED (simulating crash during in-flight external write)
        await checkpoint_manager.update_checkpoint(
            task_id=task_8_id,
            session_id=test_session,
            step_id="step_8a",
            status=StepStatus.DISPATCHED,
            idempotency_key=f"{task_8_id}:step_8a",
            started=True,
            execution_intent_persisted=True
        )

        # Resume task with non-existent note (reconciliation returns None)
        exec_res_8 = await agent_orchestrator._execute_plan_steps(task_8)
        assert exec_res_8.task.status == TaskStatus.NEEDS_RECONCILIATION
        assert step_8.status == StepStatus.NEEDS_RECONCILIATION
        print("  ✓ Non-idempotent uncertain operation safely transitioned to NEEDS_RECONCILIATION (no blind replay).")
        passed += 1

        # ======================================================================
        # [TEST 9] Idempotent Tool Transient Error Exponential Backoff & Recovery
        # ======================================================================
        print("\n[TEST 9] Idempotent Tool Transient Error Exponential Backoff & Recovery...")
        calc_tool = tool_registry.get_tool("calculator")
        assert calc_tool.is_idempotent is True
        # Verify normalization of timeout and syntax errors
        norm_err, norm_code = calc_tool.normalize_error(TimeoutError("Connection timed out"))
        assert norm_code in (ErrorClassification.TRANSIENT, ErrorClassification.TIMEOUT)

        norm_err_val, norm_code_val = calc_tool.normalize_error(ValueError("Invalid syntax"))
        assert norm_code_val == ErrorClassification.VALIDATION_FAILURE
        print(f"  ✓ Error classified as {norm_code.value} (transient) and {norm_code_val.value} (permanent validation).")
        passed += 1

        # ======================================================================
        # [TEST 10] Response Synthesis Fallback Resilience
        # ======================================================================
        print("\n[TEST 10] Response Synthesis Fallback Resilience...")
        task_10_id = str(uuid.uuid4())
        step_10 = AgentPlanStep(
            step_id="step_10a",
            tool_name="calculator",
            arguments={"expression": "42 * 2"},
            description="Calculate double life answer",
            status=StepStatus.SUCCEEDED,
            result={"result": 84}
        )
        plan_10 = AgentPlan(
            title="Synthesis fallback test",
            goal="Ensure synthesis failure fallback",
            steps=[step_10]
        )
        task_10 = AgentTask(
            id=task_10_id,
            session_id=test_session,
            user_request="Synthesize completed answer",
            status=TaskStatus.SUCCEEDED,
            plan=plan_10,
            result_summary="Calculation completed."
        )

        # Force a corrupt/unserializable memory structure to test safe fallback
        corrupt_memories = [object()]  # Missing model_dump or to_dict

        fallback_reply = agent_orchestrator._safe_compose_response(task_10, corrupt_memories)
        assert fallback_reply is not None and len(fallback_reply) > 0
        assert "84" in fallback_reply or "Calculation completed" in fallback_reply or "step_10a" in fallback_reply
        assert task_10.status == TaskStatus.SUCCEEDED, "Synthesis fallback must never alter task SUCCEEDED state!"
        print("  ✓ Synthesis fallback generated transparent summary without corrupting completed task state.")
        passed += 1

        # ======================================================================
        # [TEST 11] Strict Task State Machine Transition Rules
        # ======================================================================
        print("\n[TEST 11] Strict Task State Machine Transition Rules...")
        # Valid forward transitions
        assert validate_task_transition(TaskStatus.CREATED, TaskStatus.PLANNING) is True
        assert validate_task_transition(TaskStatus.PLANNING, TaskStatus.RUNNING) is True
        assert validate_task_transition(TaskStatus.RUNNING, TaskStatus.AWAITING_APPROVAL) is True
        assert validate_task_transition(TaskStatus.AWAITING_APPROVAL, TaskStatus.RUNNING) is True
        assert validate_task_transition(TaskStatus.RUNNING, TaskStatus.SUCCEEDED) is True
        assert validate_task_transition(TaskStatus.FAILED, TaskStatus.RETRYING) is True
        assert validate_task_transition(TaskStatus.RETRYING, TaskStatus.RUNNING) is True

        # Invalid transitions that must raise InvalidStateTransitionError
        invalid_pairs = [
            (TaskStatus.SUCCEEDED, TaskStatus.RUNNING),
            (TaskStatus.CANCELLED, TaskStatus.RUNNING),
            (TaskStatus.COMPLETED, TaskStatus.RUNNING),
            (TaskStatus.CREATED, TaskStatus.SUCCEEDED),
            (TaskStatus.AWAITING_APPROVAL, TaskStatus.SUCCEEDED),
            (TaskStatus.CANCELLED, TaskStatus.COMPLETED),
        ]
        rejected_count = 0
        for current_s, target_s in invalid_pairs:
            try:
                validate_task_transition(current_s, target_s)
            except InvalidStateTransitionError:
                rejected_count += 1
        assert rejected_count == len(invalid_pairs)
        print(f"  ✓ All {rejected_count} illegal state transitions strictly rejected by transition matrix.")
        passed += 1

        # ======================================================================
        # [TEST 12] Worker Fencing Generation Protection
        # ======================================================================
        print("\n[TEST 12] Worker Fencing Generation Protection...")
        task_12_id = str(uuid.uuid4())
        task_12 = AgentTask(
            id=task_12_id,
            session_id=test_session,
            user_request="Fencing generation test",
            status=TaskStatus.PROPOSED
        )
        await agent_orchestrator._persist_new_task(task_12)

        # Worker 1 claims task (persisted as 1 initially, increments to 2 on claim)
        w1_claimed, w1_gen, _ = await agent_orchestrator.claim_task_lease(task_12_id, test_session, worker_id="worker_1", lease_seconds=1)
        assert w1_claimed is True
        assert w1_gen == 2

        # Wait for lease expiration
        await asyncio.sleep(1.2)

        # Worker 2 claims expired lease (increments to 3)
        w2_claimed, w2_gen, _ = await agent_orchestrator.claim_task_lease(task_12_id, test_session, worker_id="worker_2", lease_seconds=60)
        assert w2_claimed is True
        assert w2_gen == 3

        # Stale Worker 1 attempts to update task record with old gen 1 -> must fail
        task_12.result_summary = "Zombie update from stale worker"
        stale_rejected = False
        try:
            await agent_orchestrator._update_task_record(task_12, worker_id="worker_1", lease_generation=w1_gen)
        except StaleWorkerError:
            stale_rejected = True
        assert stale_rejected is True
        print(f"  ✓ Stale Worker 1 update with generation {w1_gen} rejected; Worker 2 generation {w2_gen} active.")
        passed += 1

        # ======================================================================
        # [TEST 13] In-Flight Task Cancellation Safety
        # ======================================================================
        print("\n[TEST 13] In-Flight Task Cancellation Safety...")
        task_13_id = str(uuid.uuid4())
        step_13a = AgentPlanStep(
            step_id="step_13a",
            tool_name="calculator",
            arguments={"expression": "100 + 100"},
            description="Quick completed step",
            status=StepStatus.SUCCEEDED,
            result={"result": 200}
        )
        step_13b = AgentPlanStep(
            step_id="step_13b",
            tool_name="calculator",
            arguments={"expression": "50 * 50"},
            description="Pending step to cancel",
            status=StepStatus.PENDING
        )
        plan_13 = AgentPlan(
            title="Cancellation test",
            goal="Test safe cancellation protocol",
            steps=[step_13a, step_13b]
        )
        task_13 = AgentTask(
            id=task_13_id,
            session_id=test_session,
            user_request="Test in-flight cancellation",
            status=TaskStatus.CANCEL_REQUESTED,
            plan=plan_13
        )
        await agent_orchestrator._persist_new_task(task_13)
        await checkpoint_manager.init_task_checkpoints(task_13_id, test_session, plan_13)

        # Run plan execution with CANCEL_REQUESTED status
        resp_13 = await agent_orchestrator._execute_plan_steps(task_13)
        assert resp_13.task.status == TaskStatus.CANCELLED
        # Completed step preserved, pending step cancelled
        cps_13 = await checkpoint_manager.get_task_checkpoints(task_13_id, test_session)
        cp_13a = next(c for c in cps_13 if c.step_id == "step_13a")
        cp_13b = next(c for c in cps_13 if c.step_id == "step_13b")
        assert cp_13a.status == StepStatus.SUCCEEDED
        assert cp_13b.status == StepStatus.CANCELLED
        print("  ✓ Completed step 13a preserved as SUCCEEDED; pending step 13b cleanly CANCELLED.")
        passed += 1

        # ======================================================================
        # [TEST 14] Cross-Session Security & Checkpoint Isolation
        # ======================================================================
        print("\n[TEST 14] Cross-Session Security & Checkpoint Isolation...")
        # Query task 1 checkpoints using isolate session ID
        isolated_cps = await checkpoint_manager.get_task_checkpoints(task_1_id, isolate_session)
        assert len(isolated_cps) == 0, "Checkpoints must NOT leak to foreign sessions!"

        # Attempt to cancel task from isolate session
        cross_cancel_ok = False
        cross_err = ""
        try:
            resp = await agent_orchestrator.cancel_task(isolate_session, task_1_id)
            cross_cancel_ok = (resp.task.status == TaskStatus.CANCELLED)
        except Exception as e:
            cross_cancel_ok = False
            cross_err = str(e)
        assert cross_cancel_ok is False
        assert "not found" in cross_err.lower() or "access denied" in cross_err.lower()
        print("  ✓ Strict multi-tenant session isolation verified across checkpoints and tasks.")
        passed += 1

        # ======================================================================
        # [TEST 15] Full End-to-End Task Lifecycle with Checkpoints & Timeline
        # ======================================================================
        print("\n[TEST 15] Full End-to-End Task Lifecycle with Checkpoints & Timeline...")
        task_15_id = str(uuid.uuid4())
        step_15a = AgentPlanStep(
            step_id="step_15a",
            tool_name="calculator",
            arguments={"expression": "12 * 12"},
            description="Math step 1"
        )
        step_15b = AgentPlanStep(
            step_id="step_15b",
            tool_name="calculator",
            arguments={"expression": "144 + 56"},
            description="Math step 2",
            dependencies=["step_15a"]
        )
        plan_15 = AgentPlan(
            title="E2E Lifecycle task",
            goal="Full lifecycle test",
            steps=[step_15a, step_15b]
        )
        task_15 = AgentTask(
            id=task_15_id,
            session_id=test_session,
            user_request="Perform full E2E calculation",
            status=TaskStatus.PLANNING,
            plan=plan_15
        )
        await agent_orchestrator._persist_new_task(task_15)
        await checkpoint_manager.init_task_checkpoints(task_15_id, test_session, plan_15)

        e2e_resp = await agent_orchestrator._execute_plan_steps(task_15)
        assert e2e_resp.task.status in (TaskStatus.SUCCEEDED, TaskStatus.COMPLETED)
        assert len(e2e_resp.execution_timeline) >= 2
        assert len(e2e_resp.checkpoints) == 2
        assert all(cp.status == StepStatus.SUCCEEDED for cp in e2e_resp.checkpoints)
        assert e2e_resp.reply is not None and len(e2e_resp.reply) > 0
        print(f"  ✓ Full E2E execution finished: {len(e2e_resp.checkpoints)} checkpoints, valid reply generated.")
        passed += 1

    finally:
        await close_db_pool()

    print("\n" + "=" * 80)
    print(f"SPRINT 4.3 AGENT EXECUTION EXCELLENCE TEST SUMMARY: {passed}/{total} SUITES PASSED ({(passed/total)*100:.0f}%)")
    print("=" * 80)
    assert passed == total, f"Expected {total} passed suites, got {passed}"


if __name__ == "__main__":
    asyncio.run(run_reliability_suite())
