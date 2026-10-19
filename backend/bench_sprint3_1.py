"""
MEMORA AI — SPRINT 3.1: BENCHMARK & LATENCY PROFILING SUITE
Measures:
  1. BENCH-05 re-run and breakdown (Intent Analysis + Memory Recall + Plan Generation).
  2. Cold vs Warm latency distributions (p50, p95, p99).
  3. Checkpoint overhead per step.
  4. Recovery latency after simulated crash.
"""

import asyncio
import time
import sys
import uuid
from typing import List

def calc_percentile(data: List[float], p: float) -> float:
    if not data:
        return 0.0
    s = sorted(data)
    idx = (len(s) - 1) * (p / 100.0)
    floor_idx = int(idx)
    ceil_idx = min(floor_idx + 1, len(s) - 1)
    if floor_idx == ceil_idx:
        return float(s[floor_idx])
    return float(s[floor_idx] * (ceil_idx - idx) + s[ceil_idx] * (idx - floor_idx))

def mean(data: List[float]) -> float:
    return sum(data) / len(data) if data else 0.0

# Ensure Windows console handles utf-8 characters smoothly
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from app.database import init_db_pool, close_db_pool, get_db_pool
from app.schemas import MemoryCandidate
from app.services.memory_service import add_memory, delete_all_memories
from app.services import note_service
from app.services.hybrid_retriever import retrieve_hybrid_memories
from app.agent.intent_analyzer import analyze_intent
from app.agent.planner import generate_plan
from app.agent.orchestrator import agent_orchestrator
from app.agent.checkpoint_manager import checkpoint_manager
from app.agent.models import (
    AgentPlan,
    AgentPlanStep,
    AgentTask,
    TaskStatus,
    StepStatus,
)

async def run_profiling():
    print("=" * 80)
    print("MEMORA AI — SPRINT 3.1: BENCHMARK & LATENCY PROFILING")
    print("=" * 80)

    pool = await init_db_pool()
    assert pool is not None, "Database pool failed to initialize"

    bench_session = f"bench_sprint3_1_{uuid.uuid4().hex[:6]}"
    print(f"Profiling Session ID: {bench_session}\n")

    # Seed memories for memory-aware planning
    await add_memory(bench_session, MemoryCandidate(
        memory_key="pref_backend",
        category="preferences",
        content="Our microservices backend is built exclusively with Python asyncio and FastAPI",
        confidence=0.98,
        information_source="explicit"
    ))
    await add_memory(bench_session, MemoryCandidate(
        memory_key="pref_db",
        category="preferences",
        content="Primary datastore is Neon PostgreSQL with pgvector extension enabled",
        confidence=0.95,
        information_source="explicit"
    ))

    query = "Search my memories for my backend technologies and tell me what they are"

    # --------------------------------------------------------------------------
    # 1. LATENCY BREAKDOWN (Intent Analysis + Recall + Plan Generation)
    # --------------------------------------------------------------------------
    print("[1] Measuring component-level latency breakdown...")

    # A. Intent Analysis
    t0 = time.perf_counter()
    intent_res = await analyze_intent(query)
    intent_ms = (time.perf_counter() - t0) * 1000

    # B. Graph / Hybrid Memory Recall
    t0 = time.perf_counter()
    recalled = await retrieve_hybrid_memories(session_id=bench_session, query=query, limit=5)
    recall_ms = (time.perf_counter() - t0) * 1000

    # C. Plan Generation
    t0 = time.perf_counter()
    plan_res = await generate_plan(query, retrieved_memories=recalled, max_steps=4)
    plan_ms = (time.perf_counter() - t0) * 1000

    # Parallel execution (optimized path in Sprint 3.1)
    t0 = time.perf_counter()
    intent_par, recalled_par = await asyncio.gather(
        analyze_intent(query),
        retrieve_hybrid_memories(session_id=bench_session, query=query, limit=5)
    )
    plan_par = await generate_plan(query, retrieved_memories=recalled_par, max_steps=4)
    parallel_total_ms = (time.perf_counter() - t0) * 1000

    print(f"  - Intent Analysis Latency      : {intent_ms:.2f} ms")
    print(f"  - Hybrid Memory Recall Latency : {recall_ms:.2f} ms")
    print(f"  - Plan Generation Latency      : {plan_ms:.2f} ms")
    print(f"  - Sequential Sum               : {intent_ms + recall_ms + plan_ms:.2f} ms")
    print(f"  - Parallel Orchestrated Latency: {parallel_total_ms:.2f} ms")
    print(f"  - Parallelization Speedup      : {(intent_ms + recall_ms + plan_ms) - parallel_total_ms:.2f} ms saved\n")

    # --------------------------------------------------------------------------
    # 2. BENCH-05: COLD VS WARM LATENCY (p50, p95, p99)
    # --------------------------------------------------------------------------
    print("[2] Running BENCH-05 Cold vs Warm measurements...")

    # Cold Run (empty embedding cache, initial connection warmup)
    t0 = time.perf_counter()
    cold_res = await agent_orchestrator.run_agent_task(
        message="Search my memories for my backend technologies and tell me what they are",
        session_id=bench_session
    )
    cold_ms = (time.perf_counter() - t0) * 1000
    print(f"  - Cold Run E2E Latency: {cold_ms:.2f} ms (Status: {cold_res.task.status.value})")

    # Warm Runs (cached embeddings, warm pool, warm schema cache)
    warm_samples = []
    for i in range(5):
        t0 = time.perf_counter()
        w_res = await agent_orchestrator.run_agent_task(
            message="Search my memories for my backend technologies and tell me what they are",
            session_id=bench_session
        )
        dur = (time.perf_counter() - t0) * 1000
        warm_samples.append(dur)
        print(f"    Sample {i+1}: {dur:.2f} ms")

    warm_p50 = calc_percentile(warm_samples, 50)
    warm_p95 = calc_percentile(warm_samples, 95)
    warm_p99 = calc_percentile(warm_samples, 99)
    print(f"  - Warm p50: {warm_p50:.2f} ms | p95: {warm_p95:.2f} ms | p99: {warm_p99:.2f} ms\n")

    # --------------------------------------------------------------------------
    # 3. CHECKPOINT OVERHEAD PER STEP
    # --------------------------------------------------------------------------
    print("[3] Measuring Checkpoint Persistence Overhead per Step...")
    task_cp_id = uuid.uuid4()
    plan_cp = AgentPlan(
        objective="Measure checkpoint overhead",
        steps=[AgentPlanStep(step_id="step_1", description="Benchmark step", is_idempotent=True)]
    )
    task_cp = AgentTask(id=task_cp_id, session_id=bench_session, user_request="CP test", plan=plan_cp, status=TaskStatus.RUNNING)
    await agent_orchestrator._persist_new_task(task_cp)
    await checkpoint_manager.init_task_checkpoints(task_cp_id, bench_session, plan_cp)

    cp_samples = []
    for i in range(20):
        t0 = time.perf_counter()
        await checkpoint_manager.update_checkpoint(
            task_id=task_cp_id,
            session_id=bench_session,
            step_id="step_1",
            status=StepStatus.RUNNING,
            lease_generation=1
        )
        cp_ms = (time.perf_counter() - t0) * 1000
        cp_samples.append(cp_ms)

    cp_p50 = calc_percentile(cp_samples, 50)
    cp_p95 = calc_percentile(cp_samples, 95)
    cp_p99 = calc_percentile(cp_samples, 99)
    print(f"  - Checkpoint Write p50: {cp_p50:.2f} ms | p95: {cp_p95:.2f} ms | p99: {cp_p99:.2f} ms (Mean: {mean(cp_samples):.2f} ms)\n")

    # --------------------------------------------------------------------------
    # 4. RECOVERY LATENCY AFTER SIMULATED CRASH
    # --------------------------------------------------------------------------
    print("[4] Measuring Crash Recovery Latency...")
    recovery_samples = []
    for i in range(5):
        t_rec_id = uuid.uuid4()
        s_rec_id = "step_rec"
        idempotency_key = f"{t_rec_id}:{s_rec_id}"

        # Seed existing note from downstream operation
        await note_service.create_note(
            session_id=bench_session,
            title=f"Recovery Note {i}",
            content="Content saved before simulated crash",
            idempotency_key=idempotency_key
        )

        p_rec = AgentPlan(
            objective="Recovery benchmark",
            steps=[AgentPlanStep(step_id=s_rec_id, description="Reconciled step", tool_name="create_note", arguments={"title": f"Recovery Note {i}", "content": "Content saved before simulated crash"}, is_idempotent=False, idempotency_key=idempotency_key)]
        )
        t_rec = AgentTask(id=t_rec_id, session_id=bench_session, user_request="Rec test", plan=p_rec, status=TaskStatus.RUNNING)
        await agent_orchestrator._persist_new_task(t_rec)
        await checkpoint_manager.init_task_checkpoints(t_rec_id, bench_session, p_rec)
        await checkpoint_manager.update_checkpoint(task_id=t_rec_id, session_id=bench_session, step_id=s_rec_id, status=StepStatus.DISPATCHED, idempotency_key=idempotency_key)

        # Measure recovery execution
        t0 = time.perf_counter()
        resp = await agent_orchestrator._execute_plan_steps(t_rec)
        rec_dur = (time.perf_counter() - t0) * 1000
        assert resp.task.status == TaskStatus.SUCCEEDED
        recovery_samples.append(rec_dur)

    rec_p50 = calc_percentile(recovery_samples, 50)
    rec_p95 = calc_percentile(recovery_samples, 95)
    rec_p99 = calc_percentile(recovery_samples, 99)
    print(f"  - Recovery Latency p50: {rec_p50:.2f} ms | p95: {rec_p95:.2f} ms | p99: {rec_p99:.2f} ms (Mean: {mean(recovery_samples):.2f} ms)\n")

    # Cleanup
    await delete_all_memories(bench_session)
    print("=" * 80)
    print("PROFILING COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(run_profiling())
