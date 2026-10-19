"""
MEMORA AI - Phase 7: Advanced Retrieval 2.0 Comparative Evaluation Runner
Directly evaluates Baseline Hybrid Retrieval (Day 5) vs. Context-Aware Retrieval 2.0 (Sprint 2)
across challenging real-world memory benchmarks:
- Paraphrased queries without keyword overlap
- Multi-project disambiguation
- Outdated / Superseded preferences
- Contradictory memory handling
- Temporary TTL vs. Persistent facts
- Cross-session privacy leakage under semantic distractor pressure
- Graph proximity context-dependent queries
"""

import asyncio
import logging
import time
import uuid
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.database import get_db_pool
from app.schemas import MemoryCandidate, RelationshipType
from app.services.memory_service import add_memory, delete_all_memories
from app.services.hybrid_retriever import retrieve_hybrid_memories
from app.services.context_retriever import context_retriever
from app.services.relationship_service import relationship_service
from app.services.lifecycle_service import lifecycle_service
from app.evaluation.retrieval_metrics import (
    compute_precision_at_k,
    compute_recall_at_k,
    compute_reciprocal_rank,
    compute_ndcg_at_k,
    check_cross_session_leakage,
)

logger = logging.getLogger(__name__)

@dataclass
class ChallengeTestCase:
    id: str
    name: str
    category: str
    query: str
    k: int
    expected_keys: List[str]
    irrelevant_keys: List[str]
    description: str

CHALLENGE_BENCHMARK_SUITE: List[ChallengeTestCase] = [
    ChallengeTestCase(
        id="CH-01",
        name="Paraphrased Semantic Matching",
        category="paraphrase",
        query="What language ecosystem and async framework do I rely on for building backend endpoints?",
        k=3,
        expected_keys=["pref_backend_python", "skill_fastapi_framework"],
        irrelevant_keys=["pref_frontend_react"],
        description="Paraphrased query with zero exact token overlap testing semantic embeddings."
    ),
    ChallengeTestCase(
        id="CH-02",
        name="Multi-Project Disambiguation",
        category="multi_project",
        query="Which database architecture is utilized specifically for the MEMORA AI project?",
        k=2,
        expected_keys=["memora_db_lakebase_postgres"],
        irrelevant_keys=["other_project_mongodb"],
        description="Distinguishes between multiple distinct project databases."
    ),
    ChallengeTestCase(
        id="CH-03",
        name="Superseded Preference Exclusion",
        category="outdated_preference",
        query="What is my current preferred code editor and styling format?",
        k=2,
        expected_keys=["pref_current_editor_cursor"],
        irrelevant_keys=["pref_superseded_editor_vscode"],
        description="Verifies that superseded preference is excluded from active retrieval."
    ),
    ChallengeTestCase(
        id="CH-04",
        name="Contradictory Memory Handling",
        category="contradiction",
        query="What deployment cloud environment should be targeted for production?",
        k=2,
        expected_keys=["fact_prod_deployment_target"],
        irrelevant_keys=["fact_staging_deployment_target"],
        description="Tests disambiguation of conflicting deployment environment statements."
    ),
    ChallengeTestCase(
        id="CH-05",
        name="Expired Temporary TTL Fact Exclusion",
        category="temporal_validity",
        query="What temporary sprint sprint passcode or ephemeral conference room is assigned today?",
        k=2,
        expected_keys=[],  # Expired fact must not be retrieved
        irrelevant_keys=["temp_expired_room_passcode"],
        description="Ensures temporally elapsed TTL facts are not surfaced as active memories."
    ),
    ChallengeTestCase(
        id="CH-06",
        name="Cross-Session Isolation Under High Semantic Confusion",
        category="session_isolation",
        query="Retrieve private internal API credentials and salary tier information.",
        k=3,
        expected_keys=[],  # Forbidden in this session
        irrelevant_keys=["distractor_secret_credential"],
        description="Ensures distractor session secrets do not leak despite strong semantic pull."
    ),
    ChallengeTestCase(
        id="CH-07",
        name="Graph Context-Dependent Association",
        category="graph_context",
        query="Tell me about Python tools and associated frameworks used in my work.",
        k=3,
        expected_keys=["pref_backend_python", "skill_fastapi_framework", "tool_pytest"],
        irrelevant_keys=["fact_prod_deployment_target"],
        description="Graph expansion allows connected tools to receive proximity ranking boost."
    ),
]

async def seed_challenge_dataset(primary_session: str, distractor_session: str) -> Dict[str, Any]:
    """Seeds rich challenge test data into Neon Postgres with relationships and lifecycle states."""
    
    # 1. Primary Session Memories
    m1 = await add_memory(
        session_id=primary_session,
        candidate=MemoryCandidate(
            category="preference",
            memory_type="core",
            memory_key="pref_backend_python",
            content="I prefer Python for backend architecture and API microservice implementation.",
            confidence_score=0.98,
            importance_score=0.92,
            information_source="explicit_user_statement",
            persistence_type="persistent",
        )
    )

    m2 = await add_memory(
        session_id=primary_session,
        candidate=MemoryCandidate(
            category="skill",
            memory_type="core",
            memory_key="skill_fastapi_framework",
            content="Expert proficiency in FastAPI with asynchronous asyncpg connection pooling.",
            confidence_score=0.95,
            importance_score=0.88,
            information_source="explicit_user_statement",
            persistence_type="persistent",
        )
    )

    m3 = await add_memory(
        session_id=primary_session,
        candidate=MemoryCandidate(
            category="skill",
            memory_type="core",
            memory_key="tool_pytest",
            content="Uses pytest and testcontainers for strict integration testing.",
            confidence_score=0.90,
            importance_score=0.80,
            information_source="explicit_user_statement",
            persistence_type="persistent",
        )
    )

    m4 = await add_memory(
        session_id=primary_session,
        candidate=MemoryCandidate(
            category="project",
            memory_type="core",
            memory_key="memora_db_lakebase_postgres",
            content="The MEMORA AI project utilizes Neon Lakebase PostgreSQL with pgvector cosine indexing.",
            confidence_score=0.99,
            importance_score=0.95,
            information_source="explicit_user_statement",
            persistence_type="persistent",
        )
    )

    m5 = await add_memory(
        session_id=primary_session,
        candidate=MemoryCandidate(
            category="project",
            memory_type="core",
            memory_key="other_project_mongodb",
            content="The Legacy Analytics project previously utilized MongoDB document store.",
            confidence_score=0.85,
            importance_score=0.50,
            information_source="explicit_user_statement",
            persistence_type="persistent",
        )
    )

    # 2. Outdated preference superseded by newer one
    m_old_editor = await add_memory(
        session_id=primary_session,
        candidate=MemoryCandidate(
            category="preference",
            memory_type="core",
            memory_key="pref_superseded_editor_vscode",
            content="I used to use standard VS Code with default theme.",
            confidence_score=0.70,
            importance_score=0.40,
            information_source="explicit_user_statement",
            persistence_type="persistent",
        )
    )

    m_new_editor = await add_memory(
        session_id=primary_session,
        candidate=MemoryCandidate(
            category="preference",
            memory_type="core",
            memory_key="pref_current_editor_cursor",
            content="I exclusively use Cursor IDE with Tokyo Night dark styling for all development.",
            confidence_score=0.98,
            importance_score=0.90,
            information_source="explicit_user_statement",
            persistence_type="persistent",
        )
    )

    # Mark old editor as superseded
    await lifecycle_service.supersede_memory(
        session_id=primary_session,
        old_memory_id=m_old_editor.id,
        new_memory_id=m_new_editor.id,
        reason="Upgraded editor preference to Cursor IDE",
    )

    # 3. Contradictory statements
    await add_memory(
        session_id=primary_session,
        candidate=MemoryCandidate(
            category="fact",
            memory_type="core",
            memory_key="fact_prod_deployment_target",
            content="Production deployment target is LinuxONE container cluster with zero external egress.",
            confidence_score=0.96,
            importance_score=0.95,
            information_source="explicit_user_statement",
            persistence_type="persistent",
        )
    )

    await add_memory(
        session_id=primary_session,
        candidate=MemoryCandidate(
            category="fact",
            memory_type="core",
            memory_key="fact_staging_deployment_target",
            content="Staging environment runs on ephemeral cloud instances for quick manual review.",
            confidence_score=0.85,
            importance_score=0.60,
            information_source="explicit_user_statement",
            persistence_type="persistent",
        )
    )

    # 4. Expired temporary fact
    past_time = datetime.now(timezone.utc) - timedelta(hours=2)
    m_expired = await add_memory(
        session_id=primary_session,
        candidate=MemoryCandidate(
            category="fact",
            memory_type="ephemeral",
            memory_key="temp_expired_room_passcode",
            content="Temporary conference room passcode is #9842 valid until 2 hours ago.",
            confidence_score=0.90,
            importance_score=0.30,
            information_source="explicit_user_statement",
            persistence_type="temporary",
            valid_until=past_time,
        )
    )
    # Trigger retention expiry check to deactivate it
    await lifecycle_service.check_and_expire_retention(session_id=primary_session)

    # 5. Distractor session secret
    await add_memory(
        session_id=distractor_session,
        candidate=MemoryCandidate(
            category="fact",
            memory_type="core",
            memory_key="distractor_secret_credential",
            content="Secret production API token is live_sk_999888777 with executive payroll access.",
            confidence_score=0.99,
            importance_score=0.99,
            information_source="explicit_user_statement",
            persistence_type="persistent",
        )
    )

    # 6. Graph Relationships between Python -> FastAPI -> Pytest
    await relationship_service.create_relationship(
        session_id=primary_session,
        source_memory_id=m1.id,
        target_memory_id=m2.id,
        relationship_type=RelationshipType.USES.value,
        strength=1.0,
    )
    await relationship_service.create_relationship(
        session_id=primary_session,
        source_memory_id=m2.id,
        target_memory_id=m3.id,
        relationship_type=RelationshipType.APPLIED_IN.value,
        strength=0.9,
    )

    return {
        "m1": m1, "m2": m2, "m3": m3, "m4": m4, "m5": m5,
        "m_old_editor": m_old_editor, "m_new_editor": m_new_editor
    }

async def run_comparative_retrieval_evaluation(
    primary_session_id: Optional[str] = None,
    distractor_session_id: Optional[str] = None,
    clean_after: bool = True
) -> Dict[str, Any]:
    """
    Executes head-to-head comparison between Day 5 Hybrid Retrieval and Sprint 2 Retrieval 2.0.
    """
    primary_session = primary_session_id or f"eval_comp_pri_{uuid.uuid4().hex[:8]}"
    distractor_session = distractor_session_id or f"eval_comp_dis_{uuid.uuid4().hex[:8]}"
    forbidden_keys = ["distractor_secret_credential"]

    logger.info(f"Seeding challenge dataset for comparative evaluation...")
    await seed_challenge_dataset(primary_session, distractor_session)

    baseline_metrics = {
        "p_at_k": [], "r_at_k": [], "rr": [], "ndcg": [],
        "latency_ms": [], "leakage_count": 0, "superseded_retrieved": 0, "expired_retrieved": 0
    }
    v2_metrics = {
        "p_at_k": [], "r_at_k": [], "rr": [], "ndcg": [],
        "latency_ms": [], "leakage_count": 0, "superseded_retrieved": 0, "expired_retrieved": 0
    }

    test_case_comparisons = []

    for tc in CHALLENGE_BENCHMARK_SUITE:
        target_session = primary_session if tc.category != "session_isolation_distractor" else distractor_session

        # A. Baseline Retrieval (Day 5 Hybrid)
        t0 = time.perf_counter()
        recalled_base = await retrieve_hybrid_memories(
            session_id=target_session,
            query=tc.query,
            limit=tc.k
        )
        lat_base = round((time.perf_counter() - t0) * 1000, 2)
        base_keys = [m.memory_key for m in recalled_base]

        # B. Context-Aware Retrieval 2.0 (Sprint 2)
        t1 = time.perf_counter()
        recalled_v2 = await context_retriever.retrieve_context_aware(
            session_id=target_session,
            query=tc.query,
            limit=tc.k,
            include_archived=False,
            debug_scores=True,
        )
        lat_v2 = round((time.perf_counter() - t1) * 1000, 2)
        v2_keys = [m.memory_key for m in recalled_v2]

        # Compute IR metrics
        p_base = compute_precision_at_k(base_keys, tc.expected_keys, tc.k, forbidden_keys)
        r_base = compute_recall_at_k(base_keys, tc.expected_keys, tc.k, forbidden_keys)
        rr_base = compute_reciprocal_rank(base_keys, tc.expected_keys, forbidden_keys)
        ndcg_base = compute_ndcg_at_k(base_keys, tc.expected_keys, tc.k, forbidden_keys)
        leak_base = check_cross_session_leakage(base_keys, forbidden_keys)

        p_v2 = compute_precision_at_k(v2_keys, tc.expected_keys, tc.k, forbidden_keys)
        r_v2 = compute_recall_at_k(v2_keys, tc.expected_keys, tc.k, forbidden_keys)
        rr_v2 = compute_reciprocal_rank(v2_keys, tc.expected_keys, forbidden_keys)
        ndcg_v2 = compute_ndcg_at_k(v2_keys, tc.expected_keys, tc.k, forbidden_keys)
        leak_v2 = check_cross_session_leakage(v2_keys, forbidden_keys)

        baseline_metrics["p_at_k"].append(p_base)
        baseline_metrics["r_at_k"].append(r_base)
        baseline_metrics["rr"].append(rr_base)
        baseline_metrics["ndcg"].append(ndcg_base)
        baseline_metrics["latency_ms"].append(lat_base)
        if leak_base:
            baseline_metrics["leakage_count"] += 1
        if "pref_superseded_editor_vscode" in base_keys:
            baseline_metrics["superseded_retrieved"] += 1
        if "temp_expired_room_passcode" in base_keys:
            baseline_metrics["expired_retrieved"] += 1

        v2_metrics["p_at_k"].append(p_v2)
        v2_metrics["r_at_k"].append(r_v2)
        v2_metrics["rr"].append(rr_v2)
        v2_metrics["ndcg"].append(ndcg_v2)
        v2_metrics["latency_ms"].append(lat_v2)
        if leak_v2:
            v2_metrics["leakage_count"] += 1
        if "pref_superseded_editor_vscode" in v2_keys:
            v2_metrics["superseded_retrieved"] += 1
        if "temp_expired_room_passcode" in v2_keys:
            v2_metrics["expired_retrieved"] += 1

        test_case_comparisons.append({
            "test_id": tc.id,
            "name": tc.name,
            "category": tc.category,
            "baseline": {
                "retrieved_keys": base_keys,
                "precision": p_base,
                "recall": r_base,
                "mrr": rr_base,
                "ndcg": ndcg_base,
                "latency_ms": lat_base,
            },
            "retrieval_v2": {
                "retrieved_keys": v2_keys,
                "precision": p_v2,
                "recall": r_v2,
                "mrr": rr_v2,
                "ndcg": ndcg_v2,
                "latency_ms": lat_v2,
            }
        })

    # Summary aggregates
    n = len(CHALLENGE_BENCHMARK_SUITE)
    avg_base = {
        "precision_at_k": round(sum(baseline_metrics["p_at_k"]) / n, 4),
        "recall_at_k": round(sum(baseline_metrics["r_at_k"]) / n, 4),
        "mrr": round(sum(baseline_metrics["rr"]) / n, 4),
        "ndcg_at_k": round(sum(baseline_metrics["ndcg"]) / n, 4),
        "avg_latency_ms": round(sum(baseline_metrics["latency_ms"]) / n, 2),
        "cross_session_leakage": baseline_metrics["leakage_count"],
        "superseded_retrieved_count": baseline_metrics["superseded_retrieved"],
        "expired_retrieved_count": baseline_metrics["expired_retrieved"],
    }

    avg_v2 = {
        "precision_at_k": round(sum(v2_metrics["p_at_k"]) / n, 4),
        "recall_at_k": round(sum(v2_metrics["r_at_k"]) / n, 4),
        "mrr": round(sum(v2_metrics["rr"]) / n, 4),
        "ndcg_at_k": round(sum(v2_metrics["ndcg"]) / n, 4),
        "avg_latency_ms": round(sum(v2_metrics["latency_ms"]) / n, 2),
        "cross_session_leakage": v2_metrics["leakage_count"],
        "superseded_retrieved_count": v2_metrics["superseded_retrieved"],
        "expired_retrieved_count": v2_metrics["expired_retrieved"],
    }

    deltas = {
        "precision_delta": round(avg_v2["precision_at_k"] - avg_base["precision_at_k"], 4),
        "recall_delta": round(avg_v2["recall_at_k"] - avg_base["recall_at_k"], 4),
        "mrr_delta": round(avg_v2["mrr"] - avg_base["mrr"], 4),
        "ndcg_delta": round(avg_v2["ndcg_at_k"] - avg_base["ndcg_at_k"], 4),
        "latency_delta_ms": round(avg_v2["avg_latency_ms"] - avg_base["avg_latency_ms"], 2),
    }

    if clean_after:
        await delete_all_memories(primary_session)
        await delete_all_memories(distractor_session)

    return {
        "benchmark_suite_count": n,
        "baseline_day5": avg_base,
        "retrieval_2_0": avg_v2,
        "deltas": deltas,
        "test_case_comparisons": test_case_comparisons
    }

if __name__ == "__main__":
    async def main():
        res = await run_comparative_retrieval_evaluation()
        print("\n" + "=" * 80)
        print("MEMORA AI — SPRINT 2: RETRIEVAL 2.0 COMPARATIVE EVALUATION RESULTS")
        print("=" * 80)
        print(f"Total Test Cases Evaluated: {res['benchmark_suite_count']}")
        print("\n--- BASELINE (DAY 5 HYBRID RETRIEVAL) ---")
        for k, v in res["baseline_day5"].items():
            print(f"  {k}: {v}")
        print("\n--- RETRIEVAL 2.0 (SPRINT 2 CONTEXT-AWARE) ---")
        for k, v in res["retrieval_2_0"].items():
            print(f"  {k}: {v}")
        print("\n--- PERFORMANCE DELTAS (V2 vs BASELINE) ---")
        for k, v in res["deltas"].items():
            print(f"  {k}: {v}")
        print("=" * 80 + "\n")

    asyncio.run(main())
