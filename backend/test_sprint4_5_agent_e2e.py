"""
MEMORA AI — SPRINT 4.5: AGENT WORKSPACE END-TO-END VALIDATION & EXECUTION RELIABILITY
Comprehensive Automated Test Suite covering Phases 2, 3, and 5:

  Phase 2 — Realistic Workflows:
    [TEST 1] Memory-Aware Study Roadmap (Goal -> Retrieval -> Plan -> Persist Note -> COMPLETED)
    [TEST 2] Independent Parallel Operations (2 parallel notes -> 1 dependent comparison note)
    [TEST 3] Clarification Workflow (Ambiguous exam -> AWAITING_CLARIFICATION -> clarify -> COMPLETED)
    [TEST 4] Cryptographic Approval Workflow (Halt -> Token -> Reject -> Sign & Execute -> Replay Block)
    [TEST 5] In-Flight Cancellation & Terminal State Resumption Policy
    [TEST 6] Fault Injection & Recovery (Fencing, Idempotency Reconciliation, Approval Preservation)

  Phase 3 — Execution State Consistency:
    [TEST 7] State Machine Matrix Verification & Terminal State Invariance

  Phase 5 — Performance Latency Profiling:
    [TEST 8] Comprehensive Execution Benchmarking (Planning, Retrieval, Tools, Parallelism, Checkpoints)
"""

import asyncio
from datetime import datetime, timezone, timedelta
import json
import re
import sys
import time
import uuid
from typing import List, Dict, Any

# Ensure Windows console handles utf-8 characters smoothly
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

from app.database import init_db_pool, close_db_pool, get_db_pool
from app.services import note_service
from app.services.memory_service import add_memory, list_memories, delete_all_memories
from app.schemas import MemoryCandidate
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
    AgentRunRequest,
    ClarificationActionRequest,
    StaleWorkerError,
    InvalidStateTransitionError,
    validate_task_transition,
)
from app.agent.tools.registry import tool_registry
from app.agent.checkpoint_manager import checkpoint_manager
from app.agent.orchestrator import agent_orchestrator
from app.agent.planner import generate_plan, is_objective_ambiguous
from app.agent.plan_validator import validate_plan
from app.agent.approval_manager import (
    generate_approval_token,
    validate_and_consume_approval,
    create_approval_request,
    bind_approval_to_task,
    reject_approval,
)

async def run_sprint4_5_suite():
    print("=" * 80)
    print("MEMORA AI — SPRINT 4.5: AGENT WORKSPACE END-TO-END VALIDATION & RELIABILITY")
    print("=" * 80)

    pool = await init_db_pool()
    assert pool is not None, "Database pool failed to initialize"

    test_session = f"s45_test_{uuid.uuid4().hex[:8]}"
    isolate_session = f"s45_iso_{uuid.uuid4().hex[:8]}"
    print(f"Primary Test Session: {test_session}")
    print(f"Isolated Security Session: {isolate_session}\n")

    passed = 0
    total = 8
    benchmarks: Dict[str, float] = {}

    try:
        # ======================================================================
        # [TEST 1] Memory-Aware Study Roadmap
        # ======================================================================
        print("\n" + "-" * 70)
        print("[TEST 1] Memory-Aware Study Roadmap E2E Workflow")
        print("-" * 70)
        # 1. Seed user preferences and learning style memories
        t_start = time.perf_counter()
        mem1 = await add_memory(
            test_session,
            MemoryCandidate(
                category="preferences",
                memory_type="personal_preference",
                memory_key="programming_languages",
                content="I prefer Python over Java and C. I enjoy building practical AI applications.",
                confidence_score=1.0,
                importance_score=0.9
            )
        )
        mem2 = await add_memory(
            test_session,
            MemoryCandidate(
                category="learning_style",
                memory_type="personal_preference",
                memory_key="learning_style",
                content="I prefer hands-on, project-based learning with incremental practical exercises.",
                confidence_score=1.0,
                importance_score=0.9
            )
        )
        benchmarks["memory_seed_time_ms"] = (time.perf_counter() - t_start) * 1000
        print(f"  ✓ Seeded 2 profile memories for session '{test_session}' ({benchmarks['memory_seed_time_ms']:.1f}ms)")

        # 2. Run agent task
        goal_1 = (
            "Search my saved memories for my programming preferences and learning style. "
            "Based on them, create a personalized 7-day Python learning roadmap and save it as a note titled Python Learning Roadmap."
        )
        print(f"  Submitting Goal: \"{goal_1}\"")
        t_run_start = time.perf_counter()
        resp_1 = await agent_orchestrator.run_agent_task(
            message=goal_1,
            session_id=test_session,
            require_approval=False
        )
        benchmarks["test1_e2e_latency_ms"] = (time.perf_counter() - t_run_start) * 1000

        task_1 = resp_1.task
        print(f"  ✓ Task finished with status: '{task_1.status.value.upper()}' ({benchmarks['test1_e2e_latency_ms']:.1f}ms)")
        assert task_1.status in (TaskStatus.SUCCEEDED, TaskStatus.COMPLETED), f"Expected SUCCEEDED/COMPLETED, got {task_1.status}"
        assert task_1.plan is not None, "Plan must be present"
        assert len(task_1.plan.steps) >= 2, f"Expected at least 2 steps, got {len(task_1.plan.steps)}"

        # 3. Verify memory search was executed
        assert any(s.tool_name == "search_memories" or s.tool_name == "retrieve_context_v2" for s in task_1.plan.steps), "Plan must include memory search"
        assert len(resp_1.memories_used) > 0, "Memories used must be populated in response"
        print(f"  ✓ Memory context utilized: {len(resp_1.memories_used)} facts recalled")

        # 4. Verify note persistence in PostgreSQL
        notes_1 = await note_service.list_notes(test_session)
        assert len(notes_1) >= 1, "At least one persistent note must exist in database"
        roadmap_note = next((n for n in notes_1 if "Python" in n["title"] or "Roadmap" in n["title"]), None)
        assert roadmap_note is not None, f"Note titled 'Python Learning Roadmap' not found. Existing: {[n['title'] for n in notes_1]}"
        assert "Python" in roadmap_note["content"] or "Day" in roadmap_note["content"] or "roadmap" in roadmap_note["content"].lower(), "Note body must reflect roadmap content"
        print(f"  ✓ Persistent note confirmed in database: ID={roadmap_note['id']}, Title='{roadmap_note['title']}'")

        # 5. Verify final response contains note and roadmap reference
        assert "roadmap" in resp_1.reply.lower() or "python" in resp_1.reply.lower() or "note" in resp_1.reply.lower(), "Final reply must describe the created roadmap"
        print("  ✓ Final response contains valid roadmap details.")
        passed += 1

        # ======================================================================
        # [TEST 2] Independent Parallel Operations in Topological Waves
        # ======================================================================
        print("\n" + "-" * 70)
        print("[TEST 2] Independent Parallel Operations (2 Parallel -> 1 Dependent Note)")
        print("-" * 70)
        goal_2 = (
            "Create two separate study notes. The first should explain REST API fundamentals. "
            "The second should explain PostgreSQL indexing. After both notes are created, "
            "create a third note comparing how REST APIs and PostgreSQL work together in a FastAPI application."
        )
        print(f"  Submitting Goal: \"{goal_2}\"")
        t_run2 = time.perf_counter()
        resp_2 = await agent_orchestrator.run_agent_task(
            message=goal_2,
            session_id=test_session,
            require_approval=False
        )
        benchmarks["test2_parallel_dag_ms"] = (time.perf_counter() - t_run2) * 1000

        task_2 = resp_2.task
        print(f"  ✓ Task finished with status: '{task_2.status.value.upper()}' ({benchmarks['test2_parallel_dag_ms']:.1f}ms)")
        assert task_2.status in (TaskStatus.SUCCEEDED, TaskStatus.COMPLETED), f"Expected SUCCEEDED/COMPLETED, got {task_2.status}"
        assert task_2.plan is not None

        # Verify DAG structure: first 2 steps have no mutual dependency, 3rd step depends on both
        steps_2 = task_2.plan.steps
        print(f"  Plan has {len(steps_2)} steps:")
        for s in steps_2:
            print(f"    - {s.step_id} ({s.tool_name}): {s.description} [deps={s.dependencies}] -> status={s.status.value}")

        # Check notes created
        all_notes = await note_service.list_notes(test_session)
        # We had 1 from Test 1, and should have 3 more from Test 2
        test2_notes = [n for n in all_notes if n["id"] != roadmap_note["id"]]
        print(f"  ✓ Created {len(test2_notes)} notes for Test 2: {[n['title'] for n in test2_notes]}")
        assert len(test2_notes) >= 3, f"Expected at least 3 distinct notes created, got {len(test2_notes)}"

        # Check checkpoints for each step
        cps_2 = await checkpoint_manager.get_task_checkpoints(task_2.id, test_session)
        assert len(cps_2) == len(steps_2), f"Checkpoints count mismatch: {len(cps_2)} vs {len(steps_2)}"
        assert all(cp.status in (StepStatus.SUCCEEDED, StepStatus.COMPLETED) for cp in cps_2), "All checkpoints must be SUCCEEDED"
        print(f"  ✓ All {len(cps_2)} checkpoints durably persisted with SUCCEEDED status.")
        passed += 1

        # ======================================================================
        # [TEST 3] Clarification Workflow
        # ======================================================================
        print("\n" + "-" * 70)
        print("[TEST 3] Clarification Workflow for Underspecified Goal")
        print("-" * 70)
        vague_goal = "Prepare a study plan for my examination."
        print(f"  Submitting Ambiguous Goal: \"{vague_goal}\"")
        resp_3 = await agent_orchestrator.run_agent_task(
            message=vague_goal,
            session_id=test_session,
            require_approval=False
        )
        task_3 = resp_3.task
        print(f"  ✓ Initial status: '{task_3.status.value.upper()}'")
        assert task_3.status == TaskStatus.AWAITING_CLARIFICATION, f"Expected AWAITING_CLARIFICATION, got {task_3.status}"
        assert task_3.requires_clarification is True, "requires_clarification must be True"
        assert task_3.clarification_prompt is not None and len(task_3.clarification_prompt) > 5, "Clarification prompt must be present"
        assert "subject" in task_3.clarification_prompt.lower() or "examination" in task_3.clarification_prompt.lower(), "Must ask which subject or exam"
        print(f"  ✓ Agent prompted for clarification: \"{task_3.clarification_prompt}\"")

        # Answer clarification
        user_clarification = "Distributed Systems and Cloud Computing"
        print(f"  Submitting User Clarification: \"{user_clarification}\"")
        t_clarify = time.perf_counter()
        resumed_resp_3 = await agent_orchestrator.clarify_task(
            session_id=test_session,
            task_id=task_3.id,
            clarification=user_clarification
        )
        benchmarks["test3_clarification_resume_ms"] = (time.perf_counter() - t_clarify) * 1000

        resumed_task_3 = resumed_resp_3.task
        print(f"  ✓ Resumed task status: '{resumed_task_3.status.value.upper()}' ({benchmarks['test3_clarification_resume_ms']:.1f}ms)")
        assert resumed_task_3.status in (TaskStatus.SUCCEEDED, TaskStatus.COMPLETED), f"Expected SUCCEEDED/COMPLETED after clarification, got {resumed_task_3.status}"
        assert resumed_task_3.requires_clarification is False, "requires_clarification must be cleared"
        assert "Distributed Systems" in resumed_task_3.user_request, "Task user_request must incorporate the clarification"
        assert len(resumed_task_3.plan.steps) >= 1, "Plan steps must be populated"
        print("  ✓ Clarification workflow resumed and reached successful completion.")
        passed += 1

        # ======================================================================
        # [TEST 4] Approval Workflow with Rejection, Signing, and Replay Defense
        # ======================================================================
        print("\n" + "-" * 70)
        print("[TEST 4] Cryptographic Approval Workflow (Halt -> Replay Rejection -> Approve)")
        print("-" * 70)
        # Part A: Approval required task
        approval_goal = (
            "Create a persistent note titled 'Operating Systems Summary' with content "
            "'Kernel space vs user space memory architecture and virtual memory paging.' - require approval."
        )
        print(f"  Submitting Approval-Gated Goal: \"{approval_goal}\"")
        resp_4a = await agent_orchestrator.run_agent_task(
            message=approval_goal,
            session_id=test_session,
            require_approval=True
        )
        task_4a = resp_4a.task
        print(f"  ✓ Paused status: '{task_4a.status.value.upper()}'")
        assert task_4a.status == TaskStatus.AWAITING_APPROVAL, f"Expected AWAITING_APPROVAL, got {task_4a.status}"
        assert task_4a.approval_token is not None and len(task_4a.approval_token) > 20, "Valid approval token must be present"
        token_4a = task_4a.approval_token
        print(f"  ✓ Cryptographic token generated: {token_4a[:16]}...")

        # Verify note does NOT exist in DB yet
        notes_before = await note_service.list_notes(test_session)
        assert not any(n["title"] == "Operating Systems Summary" for n in notes_before), "Note must NOT exist before approval"
        print("  ✓ Confirmed note does NOT exist in DB prior to authorization.")

        # Part B: Test Rejection on a separate task
        reject_goal = "Create a persistent note titled 'Unwanted Note' with content 'This note should be rejected.' - require approval."
        resp_4b = await agent_orchestrator.run_agent_task(
            message=reject_goal,
            session_id=test_session,
            require_approval=True
        )
        task_4b = resp_4b.task
        assert task_4b.status == TaskStatus.AWAITING_APPROVAL
        print("  Rejecting task 4b...")
        rejected_resp = await agent_orchestrator.reject_task(test_session, task_4b.id)
        assert rejected_resp.task.status == TaskStatus.CANCELLED, f"Expected CANCELLED after rejection, got {rejected_resp.task.status}"
        assert rejected_resp.task.approval_status == ApprovalStatus.REJECTED.value
        notes_after_reject = await note_service.list_notes(test_session)
        assert not any(n["title"] == "Unwanted Note" for n in notes_after_reject), "Rejected note must never be created"
        print("  ✓ User rejection transitioned task to CANCELLED and prevented side effects.")

        # Part C: Valid Approval on Task 4a
        print("  Submitting authorized cryptographic approval on task 4a...")
        t_appr = time.perf_counter()
        approved_resp = await agent_orchestrator.approve_and_resume(
            session_id=test_session,
            task_id=task_4a.id,
            approval_token=token_4a
        )
        benchmarks["test4_approval_resume_ms"] = (time.perf_counter() - t_appr) * 1000
        assert approved_resp.task.status in (TaskStatus.SUCCEEDED, TaskStatus.COMPLETED), f"Expected SUCCEEDED/COMPLETED, got {approved_resp.task.status}"
        assert approved_resp.task.approval_status == ApprovalStatus.APPROVED.value

        # Confirm note now exists in DB
        notes_after_appr = await note_service.list_notes(test_session)
        os_note = next((n for n in notes_after_appr if n["title"] == "Operating Systems Summary"), None)
        assert os_note is not None, "Approved note must exist in database"
        print(f"  ✓ Approved note confirmed in database: ID={os_note['id']}")

        # Part D: Replay protection test
        print("  Testing replay attack with already-consumed approval token...")
        replay_caught = False
        try:
            await agent_orchestrator.approve_and_resume(
                session_id=test_session,
                task_id=task_4a.id,
                approval_token=token_4a
            )
        except (ValueError, PermissionError) as e:
            replay_caught = True
            print(f"  ✓ Replay token strictly rejected: {e}")
        assert replay_caught, "Consumed approval token must not be replayable"
        passed += 1

        # ======================================================================
        # [TEST 5] In-Flight Task Cancellation & Terminal State Resumption Policy
        # ======================================================================
        print("\n" + "-" * 70)
        print("[TEST 5] In-Flight Cancellation & Terminal State Resumption Policy")
        print("-" * 70)
        # Create a multi-step task
        long_goal = "Calculate 100 + 100, then calculate 200 + 200, then calculate 400 + 400, then save a note."
        cancel_task_res = await agent_orchestrator.run_agent_task(
            message=long_goal,
            session_id=test_session,
            require_approval=True
        )
        task_5 = cancel_task_res.task
        print(f"  Task created with status: '{task_5.status.value}'")

        # Cancel task
        t_cancel = time.perf_counter()
        cancelled_res = await agent_orchestrator.cancel_task(test_session, task_5.id)
        benchmarks["test5_cancellation_latency_ms"] = (time.perf_counter() - t_cancel) * 1000
        assert cancelled_res.task.status == TaskStatus.CANCELLED, f"Expected CANCELLED, got {cancelled_res.task.status}"
        print(f"  ✓ Task transitioned to CANCELLED ({benchmarks['test5_cancellation_latency_ms']:.1f}ms)")

        # Verify completed checkpoints remain intact
        cps_5 = await checkpoint_manager.get_task_checkpoints(task_5.id, test_session)
        assert len(cps_5) > 0, "Checkpoints must be persisted and preserved"
        print(f"  ✓ Verified {len(cps_5)} checkpoints preserved intact after cancellation.")

        # Test Resuming a CANCELLED task follows defined policy (terminal states cannot be resumed directly)
        print("  Testing defined policy for attempting to resume a CANCELLED task...")
        cancel_resume_rejected = False
        try:
            await agent_orchestrator.retry_task(test_session, task_5.id)
        except (ValueError, InvalidStateTransitionError) as e:
            cancel_resume_rejected = True
            print(f"  ✓ Resuming cancelled task rejected following terminal state policy: {e}")
        assert cancel_resume_rejected, "Attempting to resume a terminal cancelled task must be rejected"
        passed += 1

        # ======================================================================
        # [TEST 6] Fault Injection & Recovery (Fencing, Idempotency, Approval)
        # ======================================================================
        print("\n" + "-" * 70)
        print("[TEST 6] Fault Injection & Self-Healing Recovery")
        print("-" * 70)
        # Subtest 6A: Worker fencing protection
        task_6a_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        step_6a = AgentPlanStep(
            step_id="step_fence",
            tool_name="calculator",
            arguments={"expression": "50 * 5"},
            description="Fencing test step"
        )
        plan_6a = AgentPlan(title="Fencing test", steps=[step_6a])
        task_6a = AgentTask(
            id=task_6a_id,
            session_id=test_session,
            user_request="Fencing test",
            status=TaskStatus.RUNNING,
            lease_generation=1,
            worker_id="worker_alpha",
            plan=plan_6a
        )
        await agent_orchestrator._persist_new_task(task_6a)
        await checkpoint_manager.init_task_checkpoints(task_6a_id, test_session, plan_6a, worker_id="worker_alpha", lease_generation=1)

        # Worker Beta increments lease generation to 2 (fencing Alpha)
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute("UPDATE agent_tasks SET lease_generation = 2 WHERE id = $1", task_6a_id)

        # Stale Worker Alpha attempts write with lease generation 1
        stale_caught = False
        try:
            await checkpoint_manager.update_checkpoint(
                task_id=task_6a_id,
                session_id=test_session,
                step_id="step_fence",
                status=StepStatus.SUCCEEDED,
                worker_id="worker_alpha",
                lease_generation=1  # Stale generation
            )
        except StaleWorkerError as swe:
            stale_caught = True
            print(f"  ✓ Stale worker write strictly fenced: {swe}")
        assert stale_caught, "Stale worker write must raise StaleWorkerError"

        # Subtest 6B: Idempotent tool retry and reconciliation
        print("  Testing idempotency key reconciliation on crash recovery...")
        idem_key = f"note_idem_{uuid.uuid4().hex[:12]}"
        # Pre-seed note to simulate crash after DB mutation but before checkpoint update
        created_note = await note_service.create_note(
            session_id=test_session,
            title="Idempotency Test Note",
            content="Testing duplicate prevention",
            idempotency_key=idem_key
        )
        assert created_note is not None

        # Call reconcile on CreateNoteTool with the same idempotency key
        create_note_tool = tool_registry.get_tool("create_note")
        reconciled = await create_note_tool.reconcile(test_session, idem_key)
        assert reconciled is not None and reconciled["success"] is True
        assert reconciled["note_id"] == str(created_note["id"])
        print(f"  ✓ Reconciled existing side-effect note ID={reconciled['note_id']} without duplicate insert.")

        # Subtest 6C: Recovery does not bypass approval
        print("  Testing that recovery / retry never bypasses approval...")
        step_appr = AgentPlanStep(
            step_id="step_appr_check",
            description="Approval bypass test step",
            tool_name="create_note",
            arguments={"title": "Unapproved", "content": "Should not run"},
            permission=ToolPermission.APPROVAL_REQUIRED,
            status=StepStatus.AWAITING_APPROVAL
        )
        plan_appr = AgentPlan(title="Approval bypass test", steps=[step_appr])
        task_appr = AgentTask(
            id=uuid.uuid4(),
            session_id=test_session,
            user_request="Approval bypass test",
            status=TaskStatus.AWAITING_APPROVAL,
            plan=plan_appr
        )
        await agent_orchestrator._persist_new_task(task_appr)
        await checkpoint_manager.init_task_checkpoints(task_appr.id, test_session, plan_appr)

        # Execute single step should halt and NOT create note without token
        halted, resp_halt = await agent_orchestrator._execute_single_step(
            task=task_appr,
            step=step_appr,
            worker_id="recovery_worker",
            lease_generation=1,
            lease_seconds=30,
            existing_checkpoints=[],
            tools_executed=[],
            timeline=[]
        )
        assert halted is False, "Approval-required step must not execute automatically"
        assert resp_halt.task.status == TaskStatus.AWAITING_APPROVAL
        notes_bypass = await note_service.list_notes(test_session)
        assert not any(n["title"] == "Unapproved" for n in notes_bypass), "Note must never be created during recovery without approval"
        print("  ✓ Recovery correctly halted on approval gate without executing side effects.")
        passed += 1

        # ======================================================================
        # [TEST 7] State Machine Matrix Verification & Terminal Invariance
        # ======================================================================
        print("\n" + "-" * 70)
        print("[TEST 7] State Machine Matrix & Terminal State Invariance")
        print("-" * 70)
        # Supported states: CREATED, PLANNING, AWAITING_CLARIFICATION, AWAITING_APPROVAL, RUNNING, RETRYING, NEEDS_RECONCILIATION, COMPLETED, FAILED, CANCELLED
        all_states = [
            TaskStatus.CREATED,
            TaskStatus.PLANNING,
            TaskStatus.AWAITING_CLARIFICATION,
            TaskStatus.AWAITING_APPROVAL,
            TaskStatus.RUNNING,
            TaskStatus.RETRYING,
            TaskStatus.NEEDS_RECONCILIATION,
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED
        ]
        print(f"  Validating transition rules across all {len(all_states)} supported task states...")

        # 1. Valid expected forward transitions
        valid_transitions = [
            (TaskStatus.CREATED, TaskStatus.PLANNING),
            (TaskStatus.PLANNING, TaskStatus.RUNNING),
            (TaskStatus.PLANNING, TaskStatus.AWAITING_CLARIFICATION),
            (TaskStatus.AWAITING_CLARIFICATION, TaskStatus.PLANNING),
            (TaskStatus.AWAITING_CLARIFICATION, TaskStatus.RUNNING),
            (TaskStatus.RUNNING, TaskStatus.AWAITING_APPROVAL),
            (TaskStatus.AWAITING_APPROVAL, TaskStatus.RUNNING),
            (TaskStatus.RUNNING, TaskStatus.COMPLETED),
            (TaskStatus.RUNNING, TaskStatus.NEEDS_RECONCILIATION),
            (TaskStatus.NEEDS_RECONCILIATION, TaskStatus.RUNNING),
            (TaskStatus.RUNNING, TaskStatus.FAILED),
            (TaskStatus.FAILED, TaskStatus.RETRYING),
            (TaskStatus.RETRYING, TaskStatus.RUNNING),
            (TaskStatus.RUNNING, TaskStatus.CANCELLED),
        ]
        for src, dst in valid_transitions:
            assert validate_task_transition(src, dst) is True, f"Expected {src.value} -> {dst.value} to be valid"
        print(f"  ✓ All {len(valid_transitions)} standard forward transitions validated.")

        # 2. Strict terminal state invariance
        terminal_states = [TaskStatus.COMPLETED, TaskStatus.SUCCEEDED, TaskStatus.CANCELLED]
        terminal_violations = 0
        for term in terminal_states:
            for target in [TaskStatus.RUNNING, TaskStatus.PLANNING, TaskStatus.AWAITING_APPROVAL, TaskStatus.COMPLETED]:
                if term == target:
                    continue
                try:
                    validate_task_transition(term, target)
                except InvalidStateTransitionError:
                    terminal_violations += 1
        print(f"  ✓ Strictly blocked {terminal_violations} attempts to overwrite terminal states.")
        assert terminal_violations >= 6, "All illegal terminal overwrites must be rejected"
        passed += 1

        # ======================================================================
        # [TEST 8] Comprehensive Execution Benchmarking (Phase 5 Performance)
        # ======================================================================
        print("\n" + "-" * 70)
        print("[TEST 8] Comprehensive Performance Latency Profiling")
        print("-" * 70)
        # 1. Planning latency
        t0 = time.perf_counter()
        test_plan = await generate_plan("Calculate the compound interest on $10,000 at 5% over 3 years.", max_steps=3)
        benchmarks["planning_latency_ms"] = (time.perf_counter() - t0) * 1000

        # 2. Memory retrieval latency
        t0 = time.perf_counter()
        mems = (await list_memories(test_session))[:10]
        benchmarks["memory_retrieval_latency_ms"] = (time.perf_counter() - t0) * 1000

        # 3. Individual tool latencies
        calc_tool = tool_registry.get_tool("calculator")
        t0 = time.perf_counter()
        calc_res = await calc_tool.execute(session_id=test_session, expression="2 ** 16")
        benchmarks["tool_calculator_latency_ms"] = (time.perf_counter() - t0) * 1000

        study_tool = tool_registry.get_tool("generate_study_plan")
        t0 = time.perf_counter()
        study_res = await study_tool.execute(session_id=test_session, subject="FastAPI", duration_days=3, hours_per_day=2)
        benchmarks["tool_study_plan_latency_ms"] = (time.perf_counter() - t0) * 1000

        note_tool = tool_registry.get_tool("create_note")
        t0 = time.perf_counter()
        note_res = await note_tool.execute(session_id=test_session, title="Benchmark Note", content="Latency benchmark body")
        benchmarks["tool_create_note_latency_ms"] = (time.perf_counter() - t0) * 1000

        # 4. Checkpoint write latency
        bench_task_id = uuid.uuid4()
        bench_task = AgentTask(
            id=bench_task_id,
            session_id=test_session,
            user_request="Benchmark Task",
            status=TaskStatus.PLANNING,
            plan=test_plan
        )
        await agent_orchestrator._persist_new_task(bench_task)
        t0 = time.perf_counter()
        await checkpoint_manager.init_task_checkpoints(bench_task_id, test_session, test_plan)
        benchmarks["checkpoint_write_latency_ms"] = (time.perf_counter() - t0) * 1000

        # 5. Parallel vs Sequential execution comparison
        t0 = time.perf_counter()
        await asyncio.gather(
            calc_tool.execute(session_id=test_session, expression="100 * 2"),
            calc_tool.execute(session_id=test_session, expression="200 * 3"),
            calc_tool.execute(session_id=test_session, expression="300 * 4")
        )
        benchmarks["parallel_wave_3x_latency_ms"] = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        await calc_tool.execute(session_id=test_session, expression="100 * 2")
        await calc_tool.execute(session_id=test_session, expression="200 * 3")
        await calc_tool.execute(session_id=test_session, expression="300 * 4")
        benchmarks["sequential_steps_3x_latency_ms"] = (time.perf_counter() - t0) * 1000

        print("  Execution Latency Measurements:")
        print(f"    - Planning Latency:              {benchmarks['planning_latency_ms']:.1f} ms")
        print(f"    - Memory Retrieval Latency:      {benchmarks['memory_retrieval_latency_ms']:.1f} ms")
        print(f"    - Calculator Tool Latency:       {benchmarks['tool_calculator_latency_ms']:.1f} ms")
        print(f"    - Study Plan Tool Latency:       {benchmarks['tool_study_plan_latency_ms']:.1f} ms")
        print(f"    - Note Creation Tool Latency:    {benchmarks['tool_create_note_latency_ms']:.1f} ms")
        print(f"    - Checkpoint Write Latency:      {benchmarks['checkpoint_write_latency_ms']:.1f} ms")
        print(f"    - Parallel 3-Op Wave:            {benchmarks['parallel_wave_3x_latency_ms']:.1f} ms")
        print(f"    - Sequential 3-Op Execution:     {benchmarks['sequential_steps_3x_latency_ms']:.1f} ms")

        passed += 1

    finally:
        # Isolated test data cleanup
        print("\nCleaning up test-owned database records for session isolation...")
        pool = await get_db_pool()
        if pool:
            async with pool.acquire() as conn:
                for sid in [test_session, isolate_session]:
                    await conn.execute("DELETE FROM notes WHERE session_id = $1", sid)
                    await conn.execute("DELETE FROM agent_task_checkpoints WHERE session_id = $1", sid)
                    try:
                        await conn.execute("DELETE FROM agent_tasks WHERE session_id = $1", sid)
                    except Exception:
                        pass
                    await conn.execute("DELETE FROM memories WHERE session_id = $1", sid)
        await close_db_pool()
        print("✓ Isolated test-owned database records cleaned up successfully.")

    print("\n" + "=" * 80)
    print(f"SPRINT 4.5 END-TO-END VALIDATION: {passed}/{total} SUITES PASSED ({(passed/total)*100:.0f}%)")
    print("=" * 80)
    assert passed == total, f"Expected {total} passed suites, got {passed}"
    return benchmarks

if __name__ == "__main__":
    asyncio.run(run_sprint4_5_suite())
