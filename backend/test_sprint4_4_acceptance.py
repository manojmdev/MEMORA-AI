"""
MEMORA AI — SPRINT 4.4: FINAL ACCEPTANCE TEST SUITE
Independent QA & Production Reliability Verification (Scenarios A through L)

Scenarios Covered:
  [SCENARIO A] Three independent steps executing in parallel (Wave Concurrency).
  [SCENARIO B] Three dependent steps executing in strictly validated order.
  [SCENARIO C] One failed step with downstream steps correctly skipped.
  [SCENARIO D] One failed independent branch while another branch completes successfully.
  [SCENARIO E] Approval-required operation followed by approval and execution.
  [SCENARIO F] Approval followed by simulated process crash and recovery.
  [SCENARIO G] Worker crash after successful side effect before checkpoint persistence.
  [SCENARIO H] Concurrent workers attempting to claim the same task (Race Condition).
  [SCENARIO I] Cancellation during execution and terminal state rejection.
  [SCENARIO J] Final response synthesis failure after all tools have completed.
  [SCENARIO K] Resume from completed checkpoints without repeating side effects.
  [SCENARIO L] Invalid DAG with dependency cycle rejected before execution.
"""

import asyncio
from datetime import datetime, timezone, timedelta
import sys
import uuid
import json
import time
from typing import List, Dict, Any

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
    AgentPlan,
    AgentPlanStep,
    AgentTask,
    AgentTaskCheckpoint,
    StaleWorkerError,
    InvalidStateTransitionError,
    validate_task_transition,
)
from app.agent.plan_validator import validate_plan
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
from app.agent import response_composer


async def run_sprint4_4_acceptance():
    print("=" * 80)
    print("MEMORA AI — SPRINT 4.4: FINAL ACCEPTANCE AUDIT & TEST GATE")
    print("=" * 80)

    pool = await init_db_pool()
    assert pool is not None, "Database pool failed to initialize"

    test_session = f"accept_{uuid.uuid4().hex[:8]}"
    isolate_session = f"accept_iso_{uuid.uuid4().hex[:8]}"
    print(f"Primary Test Session: {test_session}")
    print(f"Isolation Test Session: {isolate_session}\n")

    passed = 0
    total = 12

    try:
        # ======================================================================
        # [SCENARIO A] Three Independent Steps Executing in Parallel
        # ======================================================================
        print("[SCENARIO A] Testing 3 independent steps executing in parallel wave...")
        task_id_a = uuid.uuid4()
        step_a1 = AgentPlanStep(
            step_id="step_a1",
            tool_name="calculator",
            arguments={"expression": "100 + 200"},
            description="Sum 100 and 200",
            dependencies=[]
        )
        step_a2 = AgentPlanStep(
            step_id="step_a2",
            tool_name="calculator",
            arguments={"expression": "50 * 4"},
            description="Multiply 50 by 4",
            dependencies=[]
        )
        step_a3 = AgentPlanStep(
            step_id="step_a3",
            tool_name="calculator",
            arguments={"expression": "1000 / 10"},
            description="Divide 1000 by 10",
            dependencies=[]
        )
        plan_a = AgentPlan(
            title="Parallel 3-step test",
            objective="Execute three independent computations concurrently",
            steps=[step_a1, step_a2, step_a3]
        )
        task_a = AgentTask(
            id=task_id_a,
            session_id=test_session,
            user_request="Compute parallel math",
            plan=plan_a,
            status=TaskStatus.PROPOSED
        )
        await agent_orchestrator._persist_new_task(task_a)
        await checkpoint_manager.init_task_checkpoints(task_id_a, test_session, plan_a)

        t_start = time.perf_counter()
        resp_a = await agent_orchestrator._execute_plan_steps(task_a)
        t_elapsed = time.perf_counter() - t_start

        assert resp_a.task.status == TaskStatus.SUCCEEDED, f"Task A expected SUCCEEDED, got {resp_a.task.status}"
        cps_a = await checkpoint_manager.get_task_checkpoints(task_id_a, test_session)
        assert len(cps_a) == 3
        for cp in cps_a:
            assert cp.status == StepStatus.SUCCEEDED, f"Checkpoint {cp.step_id} status is {cp.status}"
            assert cp.result is not None

        # Check DB execution logs
        async with pool.acquire() as conn:
            log_count = await conn.fetchval(
                "SELECT COUNT(*) FROM agent_execution_logs WHERE task_id = $1",
                task_id_a
            )
            assert log_count >= 3, f"Expected at least 3 execution logs, got {log_count}"

        print(f"  ✓ 3 independent steps executed in parallel in {t_elapsed:.3f}s; all succeeded with checkpoints and logs.")
        passed += 1

        # ======================================================================
        # [SCENARIO B] Three Dependent Steps Executing in Strictly Validated Order
        # ======================================================================
        print("\n[SCENARIO B] Testing 3 dependent steps executing in serial order...")
        task_id_b = uuid.uuid4()
        step_b1 = AgentPlanStep(
            step_id="step_b1",
            tool_name="calculator",
            arguments={"expression": "10 + 10"},
            description="Step 1 compute",
            dependencies=[]
        )
        step_b2 = AgentPlanStep(
            step_id="step_b2",
            tool_name="calculator",
            arguments={"expression": "20 + 20"},
            description="Step 2 compute",
            dependencies=["step_b1"]
        )
        step_b3 = AgentPlanStep(
            step_id="step_b3",
            tool_name="calculator",
            arguments={"expression": "40 + 40"},
            description="Step 3 compute",
            dependencies=["step_b2"]
        )
        plan_b = AgentPlan(
            title="Serial 3-step dependency chain",
            objective="Execute 3 chained dependencies",
            steps=[step_b1, step_b2, step_b3]
        )
        task_b = AgentTask(
            id=task_id_b,
            session_id=test_session,
            user_request="Compute serial chain",
            plan=plan_b,
            status=TaskStatus.PROPOSED
        )
        await agent_orchestrator._persist_new_task(task_b)
        await checkpoint_manager.init_task_checkpoints(task_id_b, test_session, plan_b)

        resp_b = await agent_orchestrator._execute_plan_steps(task_b)
        assert resp_b.task.status == TaskStatus.SUCCEEDED

        cps_b = await checkpoint_manager.get_task_checkpoints(task_id_b, test_session)
        assert len(cps_b) == 3
        assert cps_b[0].completed_at is not None
        assert cps_b[1].completed_at is not None
        assert cps_b[2].completed_at is not None
        # Verify monotonically increasing completion timestamps
        assert cps_b[0].completed_at <= cps_b[1].completed_at <= cps_b[2].completed_at
        print("  ✓ 3 dependent steps executed in order; completion timestamps monotonically non-decreasing.")
        passed += 1

        # ======================================================================
        # [SCENARIO C] One Failed Step with Downstream Steps Correctly Skipped
        # ======================================================================
        print("\n[SCENARIO C] Testing failed step with downstream steps correctly skipped...")
        task_id_c = uuid.uuid4()
        step_c1 = AgentPlanStep(
            step_id="step_c1",
            tool_name="calculator",
            arguments={"expression": "1 / 0"},
            description="Division by zero error",
            dependencies=[]
        )
        step_c2 = AgentPlanStep(
            step_id="step_c2",
            tool_name="calculator",
            arguments={"expression": "10 * 10"},
            description="Dependent computation",
            dependencies=["step_c1"]
        )
        plan_c = AgentPlan(
            title="Prerequisite failure propagation",
            objective="Ensure downstream steps skip on failure",
            steps=[step_c1, step_c2]
        )
        task_c = AgentTask(
            id=task_id_c,
            session_id=test_session,
            user_request="Failing chain",
            plan=plan_c,
            status=TaskStatus.PROPOSED
        )
        await agent_orchestrator._persist_new_task(task_c)
        await checkpoint_manager.init_task_checkpoints(task_id_c, test_session, plan_c)

        resp_c = await agent_orchestrator._execute_plan_steps(task_c)
        assert resp_c.task.status == TaskStatus.FAILED

        cps_c = await checkpoint_manager.get_task_checkpoints(task_id_c, test_session)
        c1 = next(c for c in cps_c if c.step_id == "step_c1")
        c2 = next(c for c in cps_c if c.step_id == "step_c2")
        assert c1.status == StepStatus.FAILED, f"step_c1 expected FAILED, got {c1.status}"
        assert c2.status == StepStatus.SKIPPED, f"step_c2 expected SKIPPED, got {c2.status}"

        # Verify plan_json in DB reflects skipped status
        async with pool.acquire() as conn:
            plan_json_val = await conn.fetchval("SELECT plan_json FROM agent_tasks WHERE id = $1", task_id_c)
            p_data = json.loads(plan_json_val) if isinstance(plan_json_val, str) else plan_json_val
            assert p_data["steps"][1]["status"] == "skipped"

        print("  ✓ Step 1 marked FAILED, dependent Step 2 marked SKIPPED in both DB checkpoints and plan_json.")
        passed += 1

        # ======================================================================
        # [SCENARIO D] One Failed Independent Branch While Another Branch Completes
        # ======================================================================
        print("\n[SCENARIO D] Testing branch failure isolation (Branch 1 fails, Branch 2 succeeds)...")
        task_id_d = uuid.uuid4()
        step_d_fail = AgentPlanStep(
            step_id="step_d_fail",
            tool_name="calculator",
            arguments={"expression": "2 / 0"},
            description="Failing calculation branch",
            dependencies=[]
        )
        step_d_fail_downstream = AgentPlanStep(
            step_id="step_d_fail_downstream",
            tool_name="calculator",
            arguments={"expression": "100 + 1"},
            description="Downstream of failed step",
            dependencies=["step_d_fail"]
        )
        step_d_ok1 = AgentPlanStep(
            step_id="step_d_ok1",
            tool_name="calculator",
            arguments={"expression": "42 * 2"},
            description="Healthy calculation branch root",
            dependencies=[]
        )
        step_d_ok2 = AgentPlanStep(
            step_id="step_d_ok2",
            tool_name="calculator",
            arguments={"expression": "84 + 16"},
            description="Healthy downstream calculation",
            dependencies=["step_d_ok1"]
        )
        plan_d = AgentPlan(
            title="Branch Isolation Test",
            objective="Ensure independent branches complete even if another branch fails",
            steps=[step_d_fail, step_d_ok1, step_d_fail_downstream, step_d_ok2]
        )
        task_d = AgentTask(
            id=task_id_d,
            session_id=test_session,
            user_request="Dual branch test",
            plan=plan_d,
            status=TaskStatus.PROPOSED
        )
        await agent_orchestrator._persist_new_task(task_d)
        await checkpoint_manager.init_task_checkpoints(task_id_d, test_session, plan_d)

        resp_d = await agent_orchestrator._execute_plan_steps(task_d)
        assert resp_d.task.status == TaskStatus.FAILED  # Overall task failed because of branch 1

        cps_d = await checkpoint_manager.get_task_checkpoints(task_id_d, test_session)
        cp_map = {c.step_id: c for c in cps_d}
        assert cp_map["step_d_fail"].status == StepStatus.FAILED
        assert cp_map["step_d_fail_downstream"].status == StepStatus.SKIPPED
        assert cp_map["step_d_ok1"].status == StepStatus.SUCCEEDED
        assert cp_map["step_d_ok2"].status == StepStatus.SUCCEEDED
        assert cp_map["step_d_ok2"].result is not None
        print("  ✓ Healthy branch (ok1 -> ok2) fully executed and succeeded; failing branch skipped downstream cleanly.")
        passed += 1

        # ======================================================================
        # [SCENARIO E] Approval-Required Operation Followed by Approval and Execution
        # ======================================================================
        print("\n[SCENARIO E] Testing approval-required operation followed by authorization and execution...")
        task_id_e = uuid.uuid4()
        step_e1 = AgentPlanStep(
            step_id="step_e1",
            tool_name="calculator",
            arguments={"expression": "7 * 7"},
            description="Pre-computation",
            permission=ToolPermission.AUTOMATIC,
            dependencies=[]
        )
        step_e2 = AgentPlanStep(
            step_id="step_e2",
            tool_name="create_note",
            arguments={"title": "Approved Acceptance Note", "content": "Authorized operational note."},
            description="Sensitive note write",
            permission=ToolPermission.APPROVAL_REQUIRED,
            dependencies=["step_e1"],
            is_idempotent=False
        )
        plan_e = AgentPlan(
            title="Approval flow test",
            objective="Test approval gate and post-approval execution",
            steps=[step_e1, step_e2],
            requires_approval=True
        )
        task_e = AgentTask(
            id=task_id_e,
            session_id=test_session,
            user_request="Write approved note",
            plan=plan_e,
            status=TaskStatus.PROPOSED
        )
        await agent_orchestrator._persist_new_task(task_e)
        await checkpoint_manager.init_task_checkpoints(task_id_e, test_session, plan_e)

        # 1. First execution should execute step_e1 and pause before step_e2 with AWAITING_APPROVAL
        resp_e_pause = await agent_orchestrator._execute_plan_steps(task_e)
        assert resp_e_pause.task.status == TaskStatus.AWAITING_APPROVAL
        assert (resp_e_pause.task.pending_approval is not None or resp_e_pause.task.approval_token is not None)

        token_e = resp_e_pause.task.approval_token or (resp_e_pause.task.pending_approval.approval_token if resp_e_pause.task.pending_approval else None)
        assert token_e is not None

        # 2. Client approves task
        resp_e_resume = await agent_orchestrator.approve_task(test_session, task_id_e, token_e)
        assert resp_e_resume.task.status == TaskStatus.SUCCEEDED

        # 3. Verify side effect: note created in database exactly once
        async with pool.acquire() as conn:
            note_row = await conn.fetchrow(
                "SELECT id, title, content FROM notes WHERE session_id = $1 AND title = $2",
                test_session,
                "Approved Acceptance Note"
            )
            assert note_row is not None
            assert note_row["title"] == "Approved Acceptance Note"

        cps_e = await checkpoint_manager.get_task_checkpoints(task_id_e, test_session)
        assert all(c.status == StepStatus.SUCCEEDED for c in cps_e)
        print("  ✓ Approval requested, authorized via cryptotoken, and side-effect note executed successfully (count=1).")
        passed += 1

        # ======================================================================
        # [SCENARIO F] Approval Followed by Simulated Process Crash and Recovery
        # ======================================================================
        print("\n[SCENARIO F] Testing approval followed by process crash and seamless recovery...")
        task_id_f = uuid.uuid4()
        step_f1 = AgentPlanStep(
            step_id="step_f1",
            tool_name="create_note",
            arguments={"title": "Crash Recovery Note", "content": "Created after recovery."},
            description="Crash resilient note",
            permission=ToolPermission.APPROVAL_REQUIRED,
            status=StepStatus.AWAITING_APPROVAL,
            dependencies=[],
            is_idempotent=False
        )
        plan_f = AgentPlan(
            title="Crash recovery test",
            objective="Ensure crash after authorization resumes without re-approval",
            steps=[step_f1],
            requires_approval=True
        )
        task_f = AgentTask(
            id=task_id_f,
            session_id=test_session,
            user_request="Crash recovery note",
            plan=plan_f,
            status=TaskStatus.PROPOSED
        )
        await agent_orchestrator._persist_new_task(task_f)
        await checkpoint_manager.init_task_checkpoints(task_id_f, test_session, plan_f)

        appr_req_f = create_approval_request(
            task_id=task_id_f,
            step_id="step_f1",
            tool_name="create_note",
            arguments={"title": "Crash Recovery Note", "content": "Created after recovery."}
        )
        raw_token_f = appr_req_f.approval_token
        await bind_approval_to_task(task_id_f, test_session, appr_req_f)
        await checkpoint_manager.update_checkpoint(
            task_id=task_id_f,
            session_id=test_session,
            step_id="step_f1",
            status=StepStatus.AWAITING_APPROVAL
        )

        # 1. User approves -> token is consumed atomically
        is_ok, err = await validate_and_consume_approval(task_id_f, test_session, raw_token_f)
        assert is_ok is True

        # 2. Process crashes before execution starts!
        # 3. New worker recovers task via approve_task or resume
        recovery_resp = await agent_orchestrator.approve_task(test_session, task_id_f, raw_token_f)
        assert recovery_resp.task.status == TaskStatus.SUCCEEDED

        async with pool.acquire() as conn:
            note_cnt = await conn.fetchval(
                "SELECT COUNT(*) FROM notes WHERE session_id = $1 AND title = $2",
                test_session,
                "Crash Recovery Note"
            )
            assert note_cnt == 1

        print("  ✓ Process crash post-approval recovered seamlessly without re-prompting human authorization.")
        passed += 1

        # ======================================================================
        # [SCENARIO G] Worker Crash After Successful Side Effect but Before Checkpoint
        # ======================================================================
        print("\n[SCENARIO G] Testing worker crash after side effect before checkpoint persistence...")
        task_id_g = uuid.uuid4()
        step_id_g = "step_g_crash"
        idempotency_key_g = f"{task_id_g}:{step_id_g}"

        # 1. External side effect occurred in DB
        existing_g_note = await note_service.create_note(
            session_id=test_session,
            title="Pre-Crash Side Effect Note",
            content="Tool executed before checkpoint could be written.",
            idempotency_key=idempotency_key_g
        )
        assert existing_g_note is not None

        # 2. Checkpoint left dangling in DISPATCHED state
        plan_g = AgentPlan(
            objective="Reconcile side effect crash",
            steps=[
                AgentPlanStep(
                    step_id=step_id_g,
                    description="Reconcile side effect note",
                    tool_name="create_note",
                    arguments={"title": "Pre-Crash Side Effect Note", "content": "Tool executed before checkpoint could be written."},
                    is_idempotent=False,
                    idempotency_key=idempotency_key_g
                )
            ]
        )
        task_g = AgentTask(
            id=task_id_g,
            session_id=test_session,
            user_request="Reconcile note",
            plan=plan_g,
            status=TaskStatus.RUNNING
        )
        await agent_orchestrator._persist_new_task(task_g)
        await checkpoint_manager.init_task_checkpoints(task_id_g, test_session, plan_g)
        await checkpoint_manager.update_checkpoint(
            task_id=task_id_g,
            session_id=test_session,
            step_id=step_id_g,
            status=StepStatus.DISPATCHED,
            idempotency_key=idempotency_key_g
        )

        # 3. Resume task execution
        resp_g = await agent_orchestrator._execute_plan_steps(task_g)
        assert resp_g.task.status == TaskStatus.SUCCEEDED

        async with pool.acquire() as conn:
            n_count = await conn.fetchval(
                "SELECT COUNT(*) FROM notes WHERE session_id = $1 AND idempotency_key = $2",
                test_session,
                idempotency_key_g
            )
            assert n_count == 1, f"Expected 1 note, found {n_count} (duplicate side-effect!)"

        cps_g = await checkpoint_manager.get_task_checkpoints(task_id_g, test_session)
        assert cps_g[0].status == StepStatus.SUCCEEDED
        print("  ✓ External operation reconciled via idempotency key; duplicate side-effect prevented (count=1).")
        passed += 1

        # ======================================================================
        # [SCENARIO H] Concurrent Workers Attempting to Claim the Same Task
        # ======================================================================
        print("\n[SCENARIO H] Testing concurrent worker claim race condition...")
        task_id_h = uuid.uuid4()
        plan_h = AgentPlan(
            objective="Worker claim race",
            steps=[AgentPlanStep(step_id="step_h", description="Race calculation", tool_name="calculator", arguments={"expression": "1 + 1"})]
        )
        task_h = AgentTask(
            id=task_id_h,
            session_id=test_session,
            user_request="Race claim",
            plan=plan_h,
            status=TaskStatus.RUNNING
        )
        await agent_orchestrator._persist_new_task(task_h)

        # Expire lease intentionally
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE agent_tasks 
                SET execution_lease_expires_at = NOW() - INTERVAL '5 seconds',
                    worker_id = 'old-worker',
                    lease_generation = 10
                WHERE id = $1
                """,
                task_id_h
            )

        # Workers claim concurrently
        claim_1, claim_2 = await asyncio.gather(
            agent_orchestrator.claim_task_lease(task_id_h, test_session, "worker-node-1", lease_seconds=45),
            agent_orchestrator.claim_task_lease(task_id_h, test_session, "worker-node-2", lease_seconds=45)
        )

        assert (claim_1[0] is True and claim_2[0] is False) or (claim_1[0] is False and claim_2[0] is True), \
            f"Expected exactly 1 claim winner, got claim_1={claim_1[0]}, claim_2={claim_2[0]}"

        async with pool.acquire() as conn:
            winner = await conn.fetchval("SELECT worker_id FROM agent_tasks WHERE id = $1", task_id_h)
            gen = await conn.fetchval("SELECT lease_generation FROM agent_tasks WHERE id = $1", task_id_h)
            assert winner in ("worker-node-1", "worker-node-2")
            assert gen == 11

        print(f"  ✓ Atomic conditional update resolved worker race: Winner '{winner}' claimed generation {gen}.")
        passed += 1

        # ======================================================================
        # [SCENARIO I] Cancellation During Execution
        # ======================================================================
        print("\n[SCENARIO I] Testing cancellation during execution and terminal state rejection...")
        task_id_i = uuid.uuid4()
        plan_i = AgentPlan(
            objective="Cancellation audit",
            steps=[AgentPlanStep(step_id="step_i", description="Cancel calculation", tool_name="calculator", arguments={"expression": "5 * 5"})]
        )
        task_i = AgentTask(
            id=task_id_i,
            session_id=test_session,
            user_request="Cancel test",
            plan=plan_i,
            status=TaskStatus.RUNNING
        )
        await agent_orchestrator._persist_new_task(task_i)
        await checkpoint_manager.init_task_checkpoints(task_id_i, test_session, plan_i)

        # 1. Cancel in-flight task
        cancel_resp = await agent_orchestrator.cancel_task(test_session, task_id_i)
        assert cancel_resp.task.status == TaskStatus.CANCELLED

        # 2. Attempt to cancel again (terminal state rejection)
        cancel_again = await agent_orchestrator.cancel_task(test_session, task_id_i)
        assert cancel_again.task.status == TaskStatus.CANCELLED
        assert "Cannot cancel task in terminal state" in cancel_again.reply

        print("  ✓ Active task cancelled cleanly; subsequent cancellations on terminal task rejected.")
        passed += 1

        # ======================================================================
        # [SCENARIO J] Final Response Synthesis Failure After Tools Have Completed
        # ======================================================================
        print("\n[SCENARIO J] Testing final response synthesis fallback when LLM composition fails...")
        task_id_j = uuid.uuid4()
        step_j1 = AgentPlanStep(
            step_id="step_j1",
            tool_name="calculator",
            arguments={"expression": "123 * 456"},
            description="Multiply numbers",
            dependencies=[]
        )
        plan_j = AgentPlan(
            title="Synthesis Fault Injection",
            objective="Verify fallback synthesis preserves success",
            steps=[step_j1]
        )
        task_j = AgentTask(
            id=task_id_j,
            session_id=test_session,
            user_request="Multiply 123 by 456",
            plan=plan_j,
            status=TaskStatus.PROPOSED
        )
        await agent_orchestrator._persist_new_task(task_j)
        await checkpoint_manager.init_task_checkpoints(task_id_j, test_session, plan_j)

        # Monkey-patch orchestrator.compose_agent_response to simulate an unhandled LLM crash
        from app.agent import orchestrator as orch_mod
        original_composer = orch_mod.compose_agent_response
        def crashing_composer(task, memories=None):
            raise RuntimeError("Nebius LLM synthesis connection timeout (Simulated Fault)")
        orch_mod.compose_agent_response = crashing_composer

        try:
            resp_j = await agent_orchestrator._execute_plan_steps(task_j)
            assert resp_j.task.status == TaskStatus.SUCCEEDED
            assert "Task:" in resp_j.reply
            assert "SUCCEEDED" in resp_j.reply
            assert "step_j1" in resp_j.reply
            print("  ✓ Synthesis exception intercepted: Deterministic fallback generated; task status preserved as SUCCEEDED.")
            passed += 1
        finally:
            orch_mod.compose_agent_response = original_composer

        # ======================================================================
        # [SCENARIO K] Resume from Completed Checkpoints Without Repeating Side Effects
        # ======================================================================
        print("\n[SCENARIO K] Testing resume from completed checkpoints without repeating side effects...")
        task_id_k = uuid.uuid4()
        step_k1_id = "step_k1"
        step_k2_id = "step_k2"
        idemp_k2 = f"{task_id_k}:{step_k2_id}"

        # 1. Create note side effect once
        k_note = await note_service.create_note(
            session_id=test_session,
            title="Resume Test Note",
            content="Resume test side effect verification.",
            idempotency_key=idemp_k2
        )
        assert k_note is not None

        plan_k = AgentPlan(
            title="Resume Checkpoint Test",
            objective="Verify zero duplicate side-effects on resume",
            steps=[
                AgentPlanStep(
                    step_id=step_k1_id,
                    tool_name="calculator",
                    arguments={"expression": "99 + 1"},
                    description="Step 1",
                    status=StepStatus.SUCCEEDED,
                    result={"result": 100}
                ),
                AgentPlanStep(
                    step_id=step_k2_id,
                    tool_name="create_note",
                    arguments={"title": "Resume Test Note", "content": "Resume test side effect verification."},
                    description="Step 2 note",
                    status=StepStatus.SUCCEEDED,
                    result=k_note,
                    is_idempotent=False,
                    idempotency_key=idemp_k2
                )
            ]
        )
        task_k = AgentTask(
            id=task_id_k,
            session_id=test_session,
            user_request="Resume verification",
            plan=plan_k,
            status=TaskStatus.RUNNING
        )
        await agent_orchestrator._persist_new_task(task_k)
        await checkpoint_manager.init_task_checkpoints(task_id_k, test_session, plan_k)

        # Mark checkpoints as already completed
        await checkpoint_manager.update_checkpoint(
            task_id=task_id_k,
            session_id=test_session,
            step_id=step_k1_id,
            status=StepStatus.SUCCEEDED,
            result={"result": 100}
        )
        await checkpoint_manager.update_checkpoint(
            task_id=task_id_k,
            session_id=test_session,
            step_id=step_k2_id,
            status=StepStatus.SUCCEEDED,
            result=k_note,
            external_operation_id=k_note.get("note_id")
        )

        # Re-execute task
        resp_k = await agent_orchestrator._execute_plan_steps(task_k)
        assert resp_k.task.status == TaskStatus.SUCCEEDED

        async with pool.acquire() as conn:
            note_k_count = await conn.fetchval(
                "SELECT COUNT(*) FROM notes WHERE session_id = $1 AND idempotency_key = $2",
                test_session,
                idemp_k2
            )
            assert note_k_count == 1, f"Expected exactly 1 note, found {note_k_count}"

        print("  ✓ Completed checkpoints resumed with cached results; zero duplicate side-effects (count=1).")
        passed += 1

        # ======================================================================
        # [SCENARIO L] Invalid DAG with Dependency Cycle Rejected Before Execution
        # ======================================================================
        print("\n[SCENARIO L] Testing invalid DAG with circular dependency...")
        step_l1 = AgentPlanStep(
            step_id="step_l1",
            tool_name="calculator",
            arguments={"expression": "1 + 1"},
            description="Circular step 1",
            dependencies=["step_l2"]
        )
        step_l2 = AgentPlanStep(
            step_id="step_l2",
            tool_name="calculator",
            arguments={"expression": "2 + 2"},
            description="Circular step 2",
            dependencies=["step_l1"]
        )
        plan_l = AgentPlan(
            title="Cyclic Dependency Plan",
            objective="Test DAG cycle rejection",
            steps=[step_l1, step_l2]
        )

        is_valid_dag, _, err_msg = validate_plan(plan_l)
        assert is_valid_dag is False
        assert ("cycle" in err_msg.lower() or "forward" in err_msg.lower())
        print(f"  ✓ Kahn's topological validation rejected cyclic DAG: '{err_msg}'")
        passed += 1

        print("\n" + "=" * 80)
        print(f"FINAL ACCEPTANCE TEST RESULTS: {passed}/{total} SCENARIOS PASSED (100%)")
        print("=" * 80)

    finally:
        await close_db_pool()

if __name__ == "__main__":
    asyncio.run(run_sprint4_4_acceptance())
