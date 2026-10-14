"""
MEMORA AI — Retrieval Evaluation Runner
Automates quantitative evaluation of hybrid memory retrieval across deterministic benchmark queries.
Measures Precision@K, Recall@K, MRR, NDCG@K, Latency, and Cross-Session Leakage.
"""
import logging
import time
import uuid
from typing import Dict, Any, List, Optional
from app.database import get_db_pool
from app.schemas import MemoryCandidate
from app.services.memory_service import add_memory, delete_all_memories
from app.services.hybrid_retriever import retrieve_hybrid_memories
from app.evaluation.dataset import (
    get_benchmark_seed_memories,
    EVALUATION_BENCHMARK_SUITE,
    TestCase
)
from app.evaluation.retrieval_metrics import (
    compute_precision_at_k,
    compute_recall_at_k,
    compute_reciprocal_rank,
    compute_ndcg_at_k,
    check_cross_session_leakage,
    EvaluationMetricsResult
)

logger = logging.getLogger(__name__)

async def run_retrieval_evaluation(
    primary_session_id: Optional[str] = None,
    distractor_session_id: Optional[str] = None,
    clean_after: bool = True
) -> Dict[str, Any]:
    """
    Executes the full MEMORA AI retrieval benchmark suite:
    1. Generates isolated primary and distractor session IDs.
    2. Seeds ground-truth memories with pgvector embeddings.
    3. Runs benchmark queries through HybridMemoryRetriever.
    4. Computes quantitative IR metrics and latency.
    5. Verifies zero cross-session privacy leakage.
    6. Returns structured evaluation summary.
    """
    primary_session = primary_session_id or f"eval_primary_{uuid.uuid4().hex[:8]}"
    distractor_session = distractor_session_id or f"eval_distractor_{uuid.uuid4().hex[:8]}"

    logger.info(f"Starting retrieval evaluation: primary='{primary_session}', distractor='{distractor_session}'")

    # 1. Seed benchmark memories
    seed_memories = get_benchmark_seed_memories()
    seeded_count = 0

    for seed in seed_memories:
        session = distractor_session if seed.is_distractor_session else primary_session
        candidate = MemoryCandidate(
            category=seed.category,
            memory_type=seed.memory_type,
            memory_key=seed.memory_key,
            content=seed.content,
            confidence_score=seed.confidence_score,
            importance_score=seed.importance_score,
            information_source=seed.information_source,
            persistence_type=seed.persistence_type,
            valid_until=seed.valid_until,
            reason_for_storage=f"Benchmark ground-truth seed for key '{seed.memory_key}'.",
            source_message=seed.source_message
        )
        await add_memory(session_id=session, candidate=candidate)
        seeded_count += 1

    logger.info(f"Successfully seeded {seeded_count} benchmark memories.")

    # 2. Execute test cases
    results: List[EvaluationMetricsResult] = []
    forbidden_distractor_keys = ["distractor_private_credit"]

    for tc in EVALUATION_BENCHMARK_SUITE:
        target_session = primary_session if tc.target_session == "primary" else distractor_session

        start_time = time.perf_counter()
        recalled = await retrieve_hybrid_memories(
            session_id=target_session,
            query=tc.query,
            limit=tc.k
        )
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

        retrieved_keys = [m.memory_key for m in recalled]

        p_at_k = compute_precision_at_k(retrieved_keys, tc.expected_keys, tc.k, forbidden_distractor_keys)
        r_at_k = compute_recall_at_k(retrieved_keys, tc.expected_keys, tc.k, forbidden_distractor_keys)
        rr = compute_reciprocal_rank(retrieved_keys, tc.expected_keys, forbidden_distractor_keys)
        ndcg = compute_ndcg_at_k(retrieved_keys, tc.expected_keys, tc.k, forbidden_distractor_keys)
        leakage = check_cross_session_leakage(retrieved_keys, forbidden_distractor_keys)

        # Success criteria:
        # Negative/privacy test: must have 0 leakage and 0 irrelevant/forbidden keys
        if not tc.expected_keys:
            has_irrelevant = any(k in tc.irrelevant_keys for k in retrieved_keys)
            if tc.id in ("TC-08", "TC-10"):
                passed = (len(retrieved_keys) == 0) and not leakage
            else:
                passed = (not leakage) and (not has_irrelevant)
        else:
            passed = (r_at_k > 0.0) and not leakage

        results.append(
            EvaluationMetricsResult(
                test_case_id=tc.id,
                name=tc.name,
                precision_at_k=p_at_k,
                recall_at_k=r_at_k,
                reciprocal_rank=rr,
                ndcg_at_k=ndcg,
                latency_ms=elapsed_ms,
                leakage_detected=leakage,
                retrieved_keys=retrieved_keys,
                expected_keys=tc.expected_keys,
                passed=passed
            )
        )

    # 3. Clean up benchmark sessions if requested
    if clean_after:
        await delete_all_memories(primary_session)
        await delete_all_memories(distractor_session)
        logger.info("Cleaned up benchmark evaluation sessions from database.")

    # 4. Compute aggregate metrics
    total_cases = len(results)
    passed_cases = sum(1 for r in results if r.passed)
    mean_p = round(sum(r.precision_at_k for r in results) / total_cases, 4)
    mean_r = round(sum(r.recall_at_k for r in results) / total_cases, 4)
    mean_mrr = round(sum(r.reciprocal_rank for r in results) / total_cases, 4)
    mean_ndcg = round(sum(r.ndcg_at_k for r in results) / total_cases, 4)
    mean_latency = round(sum(r.latency_ms for r in results) / total_cases, 2)
    total_leakages = sum(1 for r in results if r.leakage_detected)

    summary = {
        "benchmark_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_test_cases": total_cases,
        "passed_cases": passed_cases,
        "pass_rate_pct": round((passed_cases / total_cases) * 100, 2),
        "mean_precision_at_k": mean_p,
        "mean_recall_at_k": mean_r,
        "mean_reciprocal_rank_mrr": mean_mrr,
        "mean_ndcg_at_k": mean_ndcg,
        "mean_latency_ms": mean_latency,
        "cross_session_leakage_count": total_leakages,
        "detailed_results": [
            {
                "id": r.test_case_id,
                "name": r.name,
                "passed": r.passed,
                "precision_at_k": r.precision_at_k,
                "recall_at_k": r.recall_at_k,
                "mrr": r.reciprocal_rank,
                "ndcg_at_k": r.ndcg_at_k,
                "latency_ms": r.latency_ms,
                "leakage_detected": r.leakage_detected,
                "retrieved_keys": r.retrieved_keys,
                "expected_keys": r.expected_keys,
            }
            for r in results
        ]
    }

    return summary
