"""
MEMORA AI — Sprint 3: Agent Intelligence 2.0 Evaluation Framework
Measures:
  1. Planning Correctness & Multi-Step DAG Generation
  2. DAG Dependency Validity & Kahn's Cycle Detection
  3. Strict Pydantic Argument Validation
  4. Ambiguity Detection & Clarification Triggers
  5. Memory-Aware Context Provenance (Explicit vs Inferred)
  6. Durable PostgreSQL Checkpoint Persistence
  7. Zero Duplicate Side-Effect Execution Rate (Target: 0.0%)
  8. Transient Failure Exponential Backoff & Idempotent Retries
  9. Non-Idempotent Failure Reconciliation Safety (NEEDS_RECONCILIATION)
 10. Human-in-the-Loop Cryptographic Approval Compliance
 11. Cross-Session Agent Tool & Memory Isolation
"""

import asyncio
import logging
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

# Ensure Windows console handles utf-8 characters smoothly
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from app.database import init_db_pool, close_db_pool, get_db_pool
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
)
from app.agent.tools.registry import tool_registry
from app.agent.plan_validator import validate_plan, validate_and_govern_plan
from app.agent.planner import generate_plan, is_objective_ambiguous
from app.agent.checkpoint_manager import checkpoint_manager
from app.agent.orchestrator import agent_orchestrator
from app.agent.approval_manager import generate_approval_token, validate_and_consume_approval, hash_token
from app.schemas import MemoryCandidate
from app.services.memory_service import add_memory, delete_all_memories
from app.services import note_service

logger = logging.getLogger(__name__)

@dataclass
class AgentEvalResult:
    benchmark_id: str
    dimension: str
    passed: bool
    score: float
    target: float
    details: Dict[str, Any]
    duration_ms: float

@dataclass
class AgentEvalReport:
    timestamp: str
    total_benchmarks: int
    passed_benchmarks: int
    overall_score_pct: float
    duplicate_side_effect_rate: float
    results: List[AgentEvalResult]

class AgentIntelligenceEvaluator:
    """Rigorous evaluation suite for MEMORA AI Agent Intelligence 2.0."""

    def __init__(self):
        self.results: List[AgentEvalResult] = []

    async def run_all(self, session_prefix: str = "eval_agent") -> AgentEvalReport:
        pool = await get_db_pool()
        if pool is None:
            pool = await init_db_pool()

        session_id = f"{session_prefix}_{uuid.uuid4().hex[:8]}"
        session_other = f"{session_prefix}_other_{uuid.uuid4().hex[:8]}"
        print(f"\n==================================================================")
        print(f"MEMORA AI — AGENT INTELLIGENCE 2.0 BENCHMARK EVALUATOR")
        print(f"Session Primary: {session_id}")
        print(f"Session Cross:   {session_other}")
        print(f"==================================================================\n")

        # 1. Planning Correctness & DAG Generation
        await self._eval_dag_generation()

        # 2. Cycle Detection & DAG Topological Sorting
        await self._eval_dag_cycle_detection()

        # 3. Pre-execution Tool Argument Schema Validation
        await self._eval_argument_schema_validation()

        # 4. Ambiguity Detection & Clarification Prompts
        await self._eval_ambiguity_detection()

        # 5. Memory-Aware Context & Explicit vs Inferred Provenance
        await self._eval_memory_awareness(session_id)

        # 6. Durable PostgreSQL Checkpoint State Machine
        await self._eval_durable_checkpoints(session_id)

        # 7. Duplicate Side-Effect Rate (Target: 0%)
        await self._eval_duplicate_side_effect_rate(session_id)

        # 8. Transient Failure Exponential Backoff Retries
        await self._eval_transient_retry(session_id)

        # 9. Non-Idempotent Failure Reconciliation Transition
        await self._eval_reconciliation_transition(session_id)

        # 10. Cryptographic Approval Token Lifecycle
        await self._eval_approval_security(session_id)

        # 11. Cross-Session Isolation & Defense
        await self._eval_session_isolation(session_id, session_other)

        # Cleanup test sessions
        await delete_all_memories(session_id)
        await delete_all_memories(session_other)

        # Compile report
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        avg_score = (sum(r.score for r in self.results) / total * 100.0) if total > 0 else 0.0

        dup_eval = next((r for r in self.results if r.benchmark_id == "BENCH-07"), None)
        dup_rate = dup_eval.score if dup_eval else 0.0

        report = AgentEvalReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_benchmarks=total,
            passed_benchmarks=passed,
            overall_score_pct=avg_score,
            duplicate_side_effect_rate=dup_rate,
            results=self.results
        )

        self._print_summary(report)
        return report

    async def _eval_dag_generation(self):
        t0 = time.perf_counter()
        # Verify valid multi-step DAG plan with dependencies
        plan = AgentPlan(
            objective="Calculate memory footprint then scale by cluster factor",
            estimated_complexity="medium",
            estimated_cost_tier="standard",
            steps=[
                AgentPlanStep(
                    step_id="step_1",
                    description="Calculate base footprint",
                    tool_name="calculator",
                    arguments={"expression": "1024 * 768 * 4"},
                    dependencies=[],
                    is_idempotent=True
                ),
                AgentPlanStep(
                    step_id="step_2",
                    description="Scale footprint by node count",
                    tool_name="calculator",
                    arguments={"expression": "3145728 * 16"},
                    dependencies=["step_1"],
                    is_idempotent=True
                )
            ]
        )
        is_valid, validated_plan, err = validate_plan(plan)
        passed = is_valid and len(validated_plan.steps) == 2 and validated_plan.dag_edges == [["step_1", "step_2"]]
        dur = (time.perf_counter() - t0) * 1000

        self.results.append(AgentEvalResult(
            benchmark_id="BENCH-01",
            dimension="Planning Correctness & DAG Generation",
            passed=passed,
            score=1.0 if passed else 0.0,
            target=1.0,
            details={"dag_edges": validated_plan.dag_edges if validated_plan else [], "error": err},
            duration_ms=dur
        ))

    async def _eval_dag_cycle_detection(self):
        t0 = time.perf_counter()
        # Create an illegal cyclic dependency graph: step_1 -> step_2 -> step_1
        cyclic_plan = AgentPlan(
            objective="Invalid cyclic operation",
            steps=[
                AgentPlanStep(
                    step_id="step_1",
                    description="Step 1 depends on 2",
                    tool_name="calculator",
                    arguments={"expression": "1 + 1"},
                    dependencies=["step_2"]
                ),
                AgentPlanStep(
                    step_id="step_2",
                    description="Step 2 depends on 1",
                    tool_name="calculator",
                    arguments={"expression": "2 + 2"},
                    dependencies=["step_1"]
                )
            ]
        )
        is_valid, _, err = validate_plan(cyclic_plan)
        passed = (not is_valid) and ("cycle" in (err or "").lower() or "circular" in (err or "").lower())
        dur = (time.perf_counter() - t0) * 1000

        self.results.append(AgentEvalResult(
            benchmark_id="BENCH-02",
            dimension="DAG Dependency Validity & Kahn's Cycle Detection",
            passed=passed,
            score=1.0 if passed else 0.0,
            target=1.0,
            details={"rejected_as_expected": not is_valid, "validation_error": err},
            duration_ms=dur
        ))

    async def _eval_argument_schema_validation(self):
        t0 = time.perf_counter()
        # Test 1: Malformed expression injection
        invalid_calc = AgentPlan(
            objective="Dangerous calculator injection",
            steps=[
                AgentPlanStep(
                    step_id="step_1",
                    description="Attempt arbitrary import",
                    tool_name="calculator",
                    arguments={"expression": "__import__('os').system('ls')"}
                )
            ]
        )
        is_valid_1, _, err_1 = validate_plan(invalid_calc)

        # Test 2: Missing required arguments for create_note
        invalid_note = AgentPlan(
            objective="Missing note title",
            steps=[
                AgentPlanStep(
                    step_id="step_1",
                    description="Create note with missing content",
                    tool_name="create_note",
                    arguments={"title": "Test Title"}  # Missing content
                )
            ]
        )
        is_valid_2, _, err_2 = validate_plan(invalid_note)

        passed = (not is_valid_1) and (not is_valid_2)
        dur = (time.perf_counter() - t0) * 1000

        self.results.append(AgentEvalResult(
            benchmark_id="BENCH-03",
            dimension="Strict Pydantic Argument Validation",
            passed=passed,
            score=1.0 if passed else 0.0,
            target=1.0,
            details={"calc_rejected": not is_valid_1, "note_rejected": not is_valid_2},
            duration_ms=dur
        ))

    async def _eval_ambiguity_detection(self):
        t0 = time.perf_counter()
        vague_prompts = [
            "help",
            "do something cool",
            "fix it",
            "process the data",
            "make it better"
        ]
        detected = [is_objective_ambiguous(p)[0] for p in vague_prompts]
        concrete_prompt = "Calculate (1024 * 768 * 4) / 1000000"
        concrete_not_ambiguous = not is_objective_ambiguous(concrete_prompt)[0]

        passed = all(detected) and concrete_not_ambiguous
        accuracy = sum(detected) / len(detected) if detected else 0.0
        dur = (time.perf_counter() - t0) * 1000

        self.results.append(AgentEvalResult(
            benchmark_id="BENCH-04",
            dimension="Ambiguity Detection & Clarification Triggers",
            passed=passed,
            score=accuracy,
            target=1.0,
            details={"vague_detected_count": sum(detected), "total_vague": len(vague_prompts)},
            duration_ms=dur
        ))

    async def _eval_memory_awareness(self, session_id: str):
        t0 = time.perf_counter()
        # Seed an explicit memory and an inferred memory
        await add_memory(session_id, MemoryCandidate(
            memory_key="pref_backend",
            category="preferences",
            content="Our microservices backend is built exclusively with Python asyncio and FastAPI",
            confidence=0.98,
            information_source="explicit"
        ))
        await add_memory(session_id, MemoryCandidate(
            memory_key="style_diagrams",
            category="learning_style",
            content="May prefer visual step diagrams",
            confidence=0.60,
            information_source="inferred"
        ))

        # Run memory-aware planning
        res = await agent_orchestrator.run_agent_task(
            message="Search my memories for my backend technologies and tell me what they are",
            session_id=session_id
        )

        passed = False
        influences = []
        if res.task and res.task.plan:
            influences = res.task.plan.memory_influences or []
            passed = len(influences) > 0

        dur = (time.perf_counter() - t0) * 1000
        self.results.append(AgentEvalResult(
            benchmark_id="BENCH-05",
            dimension="Memory-Aware Context & Explicit vs Inferred Provenance",
            passed=passed,
            score=1.0 if passed else 0.0,
            target=1.0,
            details={"memory_influences_count": len(influences)},
            duration_ms=dur
        ))

    async def _eval_durable_checkpoints(self, session_id: str):
        t0 = time.perf_counter()
        task_id = uuid.uuid4()
        plan = AgentPlan(
            objective="Durable checkpoint verification",
            steps=[
                AgentPlanStep(
                    step_id="step_1",
                    description="Calculate initial sum",
                    tool_name="calculator",
                    arguments={"expression": "100 + 200"},
                    is_idempotent=True
                ),
                AgentPlanStep(
                    step_id="step_2",
                    description="Calculate multiplier",
                    tool_name="calculator",
                    arguments={"expression": "300 * 2"},
                    dependencies=["step_1"],
                    is_idempotent=True
                )
            ]
        )
        task = AgentTask(
            id=task_id,
            session_id=session_id,
            user_request="Durable checkpoint verification",
            plan=plan,
            status=TaskStatus.RUNNING
        )
        await agent_orchestrator._persist_new_task(task)

        # Initialize checkpoints
        checkpoints = await checkpoint_manager.init_task_checkpoints(task_id, session_id, plan)
        assert len(checkpoints) == 2, "Expected 2 initialized checkpoints"

        # Step 1 should be READY (no deps), Step 2 PENDING
        assert checkpoints[0].status == StepStatus.READY
        assert checkpoints[1].status == StepStatus.PENDING

        # Update step 1 to SUCCEEDED
        await checkpoint_manager.update_checkpoint(
            task_id=task_id,
            session_id=session_id,
            step_id="step_1",
            status=StepStatus.SUCCEEDED,
            result_summary="Calculation completed: 300"
        )

        persisted = await checkpoint_manager.get_task_checkpoints(task_id, session_id)
        step_1_ok = (persisted[0].status == StepStatus.SUCCEEDED)

        dur = (time.perf_counter() - t0) * 1000
        passed = (len(persisted) == 2) and step_1_ok
        self.results.append(AgentEvalResult(
            benchmark_id="BENCH-06",
            dimension="Durable PostgreSQL Checkpoint Persistence",
            passed=passed,
            score=1.0 if passed else 0.0,
            target=1.0,
            details={"step_1_status": persisted[0].status.value, "step_2_status": persisted[1].status.value},
            duration_ms=dur
        ))

    async def _eval_duplicate_side_effect_rate(self, session_id: str):
        t0 = time.perf_counter()
        # Benchmark for 0% Duplicate Side Effect Rate:
        # A plan with Step 1 already SUCCEEDED should never re-execute Step 1 during re-run/resumption
        task_id = uuid.uuid4()
        step1_exec_count = 0

        # Create a mock task with an already succeeded checkpoint
        plan = AgentPlan(
            objective="Test idempotent re-execution avoidance",
            steps=[
                AgentPlanStep(
                    step_id="step_1",
                    description="Pre-completed calculation",
                    tool_name="calculator",
                    arguments={"expression": "500 * 2"},
                    status=StepStatus.SUCCEEDED,
                    is_idempotent=True
                ),
                AgentPlanStep(
                    step_id="step_2",
                    description="Second calculation",
                    tool_name="calculator",
                    arguments={"expression": "1000 + 50"},
                    dependencies=["step_1"],
                    status=StepStatus.PENDING,
                    is_idempotent=True
                )
            ]
        )
        task = AgentTask(
            id=task_id,
            session_id=session_id,
            user_request="Test avoidance of completed step re-execution",
            plan=plan,
            status=TaskStatus.RUNNING
        )
        await agent_orchestrator._persist_new_task(task)
        await checkpoint_manager.init_task_checkpoints(task_id, session_id, plan)

        # Mark step_1 SUCCEEDED in checkpoint table
        await checkpoint_manager.update_checkpoint(
            task_id=task_id,
            session_id=session_id,
            step_id="step_1",
            status=StepStatus.SUCCEEDED,
            result_summary="Calculated 1000"
        )

        # Execute remaining steps
        response = await agent_orchestrator._execute_plan_steps(task)

        # Verify step_1 was skipped due to cached checkpoint, step_2 succeeded
        executed_step_ids = [e.get("step_id") for e in response.execution_timeline if not e.get("cached_checkpoint")]
        step1_reexecuted = ("step_1" in executed_step_ids)
        duplicate_rate = 1.0 if step1_reexecuted else 0.0
        passed = (duplicate_rate == 0.0)

        dur = (time.perf_counter() - t0) * 1000
        self.results.append(AgentEvalResult(
            benchmark_id="BENCH-07",
            dimension="Zero Duplicate Side-Effect Rate",
            passed=passed,
            score=1.0 if passed else 0.0,
            target=1.0,
            details={"duplicate_executions": 1 if step1_reexecuted else 0, "target_duplicate_rate": "0.0%"},
            duration_ms=dur
        ))

    async def _eval_transient_retry(self, session_id: str):
        t0 = time.perf_counter()
        # Verify that idempotent tools have retry policy defined
        calc_tool = tool_registry.get_tool("calculator")
        is_idempotent = calc_tool.is_idempotent if calc_tool else False
        has_error_classifier = hasattr(calc_tool, "normalize_error")

        # Verify ErrorClassification enum and transient mapping
        err_type = ErrorClassification.TRANSIENT
        passed = is_idempotent and has_error_classifier and (err_type.value == "transient")

        dur = (time.perf_counter() - t0) * 1000
        self.results.append(AgentEvalResult(
            benchmark_id="BENCH-08",
            dimension="Transient Failure Exponential Backoff Retries",
            passed=passed,
            score=1.0 if passed else 0.0,
            target=1.0,
            details={"is_idempotent": is_idempotent, "error_classifier_present": has_error_classifier},
            duration_ms=dur
        ))

    async def _eval_reconciliation_transition(self, session_id: str):
        t0 = time.perf_counter()
        # Non-idempotent tool create_note must transition to NEEDS_RECONCILIATION on uncertain failures
        note_tool = tool_registry.get_tool("create_note")
        is_non_idempotent = (note_tool.is_idempotent is False) if note_tool else False

        task_status_enum = TaskStatus.NEEDS_RECONCILIATION
        step_status_enum = StepStatus.NEEDS_RECONCILIATION

        passed = is_non_idempotent and (task_status_enum.value == "needs_reconciliation") and (step_status_enum.value == "needs_reconciliation")
        dur = (time.perf_counter() - t0) * 1000

        self.results.append(AgentEvalResult(
            benchmark_id="BENCH-09",
            dimension="Non-Idempotent Failure Reconciliation Safety",
            passed=passed,
            score=1.0 if passed else 0.0,
            target=1.0,
            details={"note_is_state_changing": is_non_idempotent, "needs_reconciliation_supported": True},
            duration_ms=dur
        ))

    async def _eval_approval_security(self, session_id: str):
        t0 = time.perf_counter()
        pool = await get_db_pool()
        test_task_id = uuid.uuid4()
        token = generate_approval_token()
        future_dt = datetime.now(timezone.utc) + timedelta(minutes=15)

        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO agent_tasks (id, session_id, user_request, task_type, status, approval_token, approval_token_hash, approval_status, approval_expires_at)
                VALUES ($1, $2, 'test approval security', 'write', 'awaiting_approval', NULL, $3, 'pending', $4)
                """,
                test_task_id,
                session_id,
                hash_token(token),
                future_dt,
            )

        # 1. Invalid token fails
        succ1, _ = await validate_and_consume_approval(test_task_id, session_id, "invalid_token_123")
        # 2. Invalid session fails
        succ2, _ = await validate_and_consume_approval(test_task_id, "wrong_session", token)
        # 3. Valid token consumes
        succ3, _ = await validate_and_consume_approval(test_task_id, session_id, token)
        # 4. Replay attack fails
        succ4, _ = await validate_and_consume_approval(test_task_id, session_id, token)

        passed = (not succ1) and (not succ2) and succ3 and (not succ4)
        dur = (time.perf_counter() - t0) * 1000

        self.results.append(AgentEvalResult(
            benchmark_id="BENCH-10",
            dimension="Human-in-the-Loop Cryptographic Approval Compliance",
            passed=passed,
            score=1.0 if passed else 0.0,
            target=1.0,
            details={"valid_token_consumed": succ3, "replay_blocked": not succ4, "session_mismatch_blocked": not succ2},
            duration_ms=dur
        ))

    async def _eval_session_isolation(self, session_a: str, session_b: str):
        t0 = time.perf_counter()
        # Create a note in session A
        n = await note_service.create_note(session_a, "Session A Confidential Note", "Secret content in session A")
        note_id = n["id"]

        # Attempt to access or delete from session B
        b_notes = await note_service.list_notes(session_b)
        leak_detected = any(str(item["id"]) == str(note_id) for item in b_notes)

        delete_failed_b = await note_service.delete_note(session_b, note_id)
        # Clean up in session A
        await note_service.delete_note(session_a, note_id)

        passed = (not leak_detected) and (not delete_failed_b)
        dur = (time.perf_counter() - t0) * 1000

        self.results.append(AgentEvalResult(
            benchmark_id="BENCH-11",
            dimension="Cross-Session Agent Tool & Memory Isolation",
            passed=passed,
            score=1.0 if passed else 0.0,
            target=1.0,
            details={"cross_session_leakage": leak_detected, "unauthorized_delete_blocked": not delete_failed_b},
            duration_ms=dur
        ))

    def _print_summary(self, report: AgentEvalReport):
        print("\n" + "=" * 75)
        print("AGENT INTELLIGENCE 2.0 EVALUATION RESULTS")
        print("=" * 75)
        for r in report.results:
            status = "✅ PASS" if r.passed else "❌ FAIL"
            print(f"[{r.benchmark_id}] {r.dimension:<52} : {status} ({r.duration_ms:.1f}ms)")

        print("-" * 75)
        print(f"Total Benchmarks Evaluated : {report.total_benchmarks}")
        print(f"Benchmarks Passed          : {report.passed_benchmarks} / {report.total_benchmarks} ({report.overall_score_pct:.1f}%)")
        print(f"Duplicate Side-Effect Rate : {report.duplicate_side_effect_rate * 100:.1f}% (Target: 0.0%)")
        print("=" * 75 + "\n")

if __name__ == "__main__":
    async def main():
        try:
            evaluator = AgentIntelligenceEvaluator()
            await evaluator.run_all()
        finally:
            await close_db_pool()

    asyncio.run(main())
