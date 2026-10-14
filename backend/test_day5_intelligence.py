"""
MEMORA AI — DAY 5 MEMORY INTELLIGENCE, RELIABILITY & EVALUATION TEST SUITE
Covers Scenarios A through K:
  [TEST A] Intelligent Candidate Extraction & Schema Validation
  [TEST B] Low-Importance Noise Filtering (< 0.40 importance)
  [TEST C] Explicit Statement vs Contextual Inference Calibration
  [TEST D] Temporal Memory Invalidation (Past-Due / Expired Exclusion)
  [TEST E] Active Future Temporary Memory Retention
  [TEST F] Contradiction Resolution & Superseding Lineage Tracking
  [TEST G] Compatible Facts Coexistence
  [TEST H] Explainability Metadata Availability (Provenance & Rationale)
  [TEST I] Strict Session Isolation with Zero Privacy Leakage
  [TEST J] Concurrency & Advisory Lock Data Integrity
  [TEST K] Quantitative Benchmark Evaluation Runner & Report Generation
"""
import asyncio
from datetime import datetime, timezone, timedelta
import sys
import uuid
from typing import List

# Ensure Windows console handles utf-8 characters smoothly
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from app.database import init_db_pool, close_db_pool, get_db_pool
from app.schemas import (
    MemoryCandidate,
    MemoryType,
    InformationSource,
    PersistenceType,
    MemoryStatus
)
from app.services.memory_service import (
    add_memory,
    list_memories,
    delete_memory,
    delete_all_memories,
    get_memory
)
from app.services.memory_extractor import extract_memories
from app.services.hybrid_retriever import retrieve_hybrid_memories
from app.evaluation.retrieval_evaluator import run_retrieval_evaluation
from app.evaluation.report_generator import generate_evaluation_markdown_report

async def run_day5_intelligence_tests():
    print("=" * 70)
    print("MEMORA AI — DAY 5 MEMORY INTELLIGENCE & EVALUATION TEST SUITE")
    print("=" * 70)

    pool = await init_db_pool()
    assert pool is not None, "Database pool failed to initialize"

    session_alpha = f"day5_alpha_{uuid.uuid4().hex[:6]}"
    session_beta = f"day5_beta_{uuid.uuid4().hex[:6]}"
    print(f"Session Alpha: {session_alpha}")
    print(f"Session Beta:  {session_beta}")

    try:
        # -------------------------------------------------------------
        # TEST A: Intelligent Extraction & Schema Validation
        # -------------------------------------------------------------
        print("\n[TEST A] Intelligent Extraction & Day 5 Schema Validation")
        msg_a = "I strictly write backend services in Python and use PostgreSQL."
        candidates_a = await extract_memories(msg_a)
        print(f"  Extracted {len(candidates_a)} candidates from message.")
        assert len(candidates_a) >= 1, "Failed to extract candidate from explicit technical statement."

        cand_sample = candidates_a[0]
        assert hasattr(cand_sample, "importance_score"), "Candidate missing importance_score"
        assert hasattr(cand_sample, "information_source"), "Candidate missing information_source"
        assert hasattr(cand_sample, "persistence_type"), "Candidate missing persistence_type"
        assert hasattr(cand_sample, "reason_for_storage"), "Candidate missing reason_for_storage"
        assert cand_sample.importance_score >= 0.40, f"Candidate importance below threshold: {cand_sample.importance_score}"
        print(f"  [PASSED] Candidate validated: key='{cand_sample.memory_key}', importance={cand_sample.importance_score}, source='{cand_sample.information_source}', reason='{cand_sample.reason_for_storage}'")

        # -------------------------------------------------------------
        # TEST B: Low-Importance Noise Filtering (< 0.40)
        # -------------------------------------------------------------
        print("\n[TEST B] Low-Importance Noise Filtering")
        trivial_msg = "Hey there, just sipping some lukewarm coffee on this random Tuesday."
        trivial_candidates = await extract_memories(trivial_msg)
        print(f"  Extracted candidates for trivial noise: {len(trivial_candidates)}")
        assert len(trivial_candidates) == 0, f"Expected 0 candidates for trivial noise, got: {trivial_candidates}"
        print("  [PASSED] Trivial ephemeral statement was successfully filtered out.")

        # -------------------------------------------------------------
        # TEST C: Explicit Statement vs Contextual Inference Calibration
        # -------------------------------------------------------------
        print("\n[TEST C] Explicit Statement Calibration")
        cand_c = MemoryCandidate(
            category="personal_context",
            memory_type=MemoryType.GENERAL_FACT.value,
            memory_key="user_profession",
            content="The user is a senior AI infrastructure engineer.",
            confidence_score=0.98,
            importance_score=0.90,
            information_source=InformationSource.EXPLICIT_STATEMENT.value,
            persistence_type=PersistenceType.PERSISTENT.value,
            reason_for_storage="User explicitly stated professional occupation."
        )
        rec_c = await add_memory(session_alpha, cand_c)
        assert rec_c.information_source == InformationSource.EXPLICIT_STATEMENT.value
        assert rec_c.confidence_score >= 0.90
        assert rec_c.reason_for_storage is not None
        print(f"  [PASSED] Explicit fact recorded: info_source='{rec_c.information_source}', confidence={rec_c.confidence_score}")

        # -------------------------------------------------------------
        # TEST D: Temporal Memory Invalidation (Past-Due / Expired)
        # -------------------------------------------------------------
        print("\n[TEST D] Temporal Memory Invalidation (Past-Due / Expired)")
        past_due = datetime.now(timezone.utc) - timedelta(hours=2)
        expired_cand = MemoryCandidate(
            category="projects",
            memory_type=MemoryType.TEMPORARY_ACTIVITY.value,
            memory_key="temporary_debugging_task",
            content="The user was investigating a temporary Redis connection error.",
            confidence_score=0.85,
            importance_score=0.50,
            information_source=InformationSource.EXPLICIT_STATEMENT.value,
            persistence_type=PersistenceType.TEMPORARY.value,
            reason_for_storage="Temporary troubleshooting activity.",
            valid_until=past_due
        )
        rec_expired = await add_memory(session_alpha, expired_cand)

        # In list_memories, active list should NOT contain expired record
        active_list = await list_memories(session_alpha, is_active=True)
        active_keys = [m.memory_key for m in active_list]
        assert "temporary_debugging_task" not in active_keys, "Expired memory was incorrectly returned in active list!"

        # In hybrid retrieval, expired record should NOT be retrieved
        recalled = await retrieve_hybrid_memories(session_alpha, "Redis connection error", limit=5)
        recalled_keys = [m.memory_key for m in recalled]
        assert "temporary_debugging_task" not in recalled_keys, "Expired memory was incorrectly retrieved in search!"
        print("  [PASSED] Expired temporary memory is excluded from active queries and hybrid search.")

        # -------------------------------------------------------------
        # TEST E: Active Future Temporary Memory Retention
        # -------------------------------------------------------------
        print("\n[TEST E] Active Future Temporary Memory Retention")
        future_due = datetime.now(timezone.utc) + timedelta(days=5)
        active_temp_cand = MemoryCandidate(
            category="projects",
            memory_type=MemoryType.TEMPORARY_ACTIVITY.value,
            memory_key="upcoming_product_launch",
            content="The user is preparing the MEMORA AI beta launch this Friday.",
            confidence_score=0.90,
            importance_score=0.80,
            information_source=InformationSource.EXPLICIT_STATEMENT.value,
            persistence_type=PersistenceType.TEMPORARY.value,
            reason_for_storage="Active milestone deadline.",
            valid_until=future_due
        )
        rec_active_temp = await add_memory(session_alpha, active_temp_cand)

        active_list2 = await list_memories(session_alpha, is_active=True)
        active_keys2 = [m.memory_key for m in active_list2]
        assert "upcoming_product_launch" in active_keys2, "Active temporary memory was not found in active list!"

        recalled_temp = await retrieve_hybrid_memories(session_alpha, "When is the beta launch?", limit=3)
        assert any(m.memory_key == "upcoming_product_launch" for m in recalled_temp), "Active temporary memory was not retrieved!"
        print("  [PASSED] Active future temporary memory successfully preserved and retrieved.")

        # -------------------------------------------------------------
        # TEST F: Contradiction Resolution & Superseding Lineage Tracking
        # -------------------------------------------------------------
        print("\n[TEST F] Contradiction Resolution & Superseding Lineage Tracking")
        cand_initial = MemoryCandidate(
            category="preferences",
            memory_type=MemoryType.PERSONAL_PREFERENCE.value,
            memory_key="code_editor",
            content="The user prefers VS Code for daily software development.",
            confidence_score=0.90,
            importance_score=0.75,
            information_source=InformationSource.EXPLICIT_STATEMENT.value,
            persistence_type=PersistenceType.PERSISTENT.value,
            reason_for_storage="User stated editor choice."
        )
        rec_initial = await add_memory(session_alpha, cand_initial)

        cand_correction = MemoryCandidate(
            category="preferences",
            memory_type=MemoryType.PERSONAL_PREFERENCE.value,
            memory_key="code_editor",
            content="The user switched completely to Neovim as their primary editor.",
            confidence_score=0.95,
            importance_score=0.85,
            information_source=InformationSource.EXPLICIT_STATEMENT.value,
            persistence_type=PersistenceType.PERSISTENT.value,
            reason_for_storage="User explicitly corrected primary code editor."
        )
        rec_correction = await add_memory(session_alpha, cand_correction)

        # Verify old record is superseded and points to new record
        old_rec = await get_memory(session_alpha, rec_initial.id)
        assert old_rec is not None
        assert old_rec.is_active is False, "Old memory was not marked is_active=False"
        assert old_rec.memory_status == MemoryStatus.SUPERSEDED.value, f"Old memory status: {old_rec.memory_status}"
        assert old_rec.superseded_by == rec_correction.id, f"Old memory superseded_by {old_rec.superseded_by} != {rec_correction.id}"
        assert old_rec.superseded_reason is not None
        print(f"  [PASSED] Superseding lineage verified: old_id={old_rec.id} -> superseded_by={old_rec.superseded_by}, reason='{old_rec.superseded_reason}'")

        # -------------------------------------------------------------
        # TEST G: Compatible Facts Coexistence
        # -------------------------------------------------------------
        print("\n[TEST G] Compatible Facts Coexistence")
        cand_skill_1 = MemoryCandidate(
            category="skills",
            memory_type=MemoryType.TECHNICAL_SKILL.value,
            memory_key="skill_python",
            content="The user is proficient in Python and asynchronous frameworks.",
            confidence_score=0.95,
            importance_score=0.85,
            information_source=InformationSource.EXPLICIT_STATEMENT.value,
            persistence_type=PersistenceType.PERSISTENT.value,
            reason_for_storage="Core backend skill."
        )
        cand_skill_2 = MemoryCandidate(
            category="skills",
            memory_type=MemoryType.TECHNICAL_SKILL.value,
            memory_key="skill_react",
            content="The user is proficient in React and modern state management.",
            confidence_score=0.92,
            importance_score=0.85,
            information_source=InformationSource.EXPLICIT_STATEMENT.value,
            persistence_type=PersistenceType.PERSISTENT.value,
            reason_for_storage="Core frontend skill."
        )
        await add_memory(session_alpha, cand_skill_1)
        await add_memory(session_alpha, cand_skill_2)

        skills = await list_memories(session_alpha, category="skills", is_active=True)
        skill_keys = [s.memory_key for s in skills]
        assert "skill_python" in skill_keys and "skill_react" in skill_keys, "Compatible skills failed to coexist!"
        print("  [PASSED] Multiple distinct skills coexist harmoniously as active memories.")

        # -------------------------------------------------------------
        # TEST H: Explainability Metadata Availability
        # -------------------------------------------------------------
        print("\n[TEST H] Explainability Metadata Availability")
        query_h = "What editor do I use to write code?"
        results_h = await retrieve_hybrid_memories(session_alpha, query_h, limit=3)
        assert len(results_h) >= 1, "Failed to retrieve memory for editor query"

        top_h = results_h[0]
        assert hasattr(top_h, "retrieval_method"), "Missing retrieval_method"
        assert hasattr(top_h, "retrieval_reason"), "Missing retrieval_reason"
        assert hasattr(top_h, "similarity_score"), "Missing similarity_score"
        assert hasattr(top_h, "relevance_score"), "Missing relevance_score"
        assert hasattr(top_h, "reason_for_storage"), "Missing reason_for_storage"
        assert top_h.memory_key == "code_editor"
        assert "neovim" in top_h.content.lower()
        print(f"  [PASSED] Provenance verified: method='{top_h.retrieval_method}', reason='{top_h.retrieval_reason}', storage_reason='{top_h.reason_for_storage}'")

        # -------------------------------------------------------------
        # TEST I: Strict Session Isolation & Zero Privacy Leakage
        # -------------------------------------------------------------
        print("\n[TEST I] Strict Session Isolation & Zero Privacy Leakage")
        secret_cand = MemoryCandidate(
            category="personal_context",
            memory_type=MemoryType.GENERAL_FACT.value,
            memory_key="confidential_api_secret",
            content="Confidential API key for Session Beta: SK-SECRET-BETA-9999.",
            confidence_score=1.0,
            importance_score=0.99,
            information_source=InformationSource.EXPLICIT_STATEMENT.value,
            persistence_type=PersistenceType.PERSISTENT.value,
            reason_for_storage="Private credentials."
        )
        await add_memory(session_beta, secret_cand)

        # Query Session Alpha for the secret that exists only in Session Beta
        leak_check = await retrieve_hybrid_memories(session_alpha, "What is my confidential API key SK-SECRET?", limit=5)
        for m in leak_check:
            assert "SK-SECRET-BETA" not in m.content, f"CRITICAL SECURITY FAILURE: Leakage detected from Session Beta into Session Alpha! {m.content}"
        print("  [PASSED] Strict session isolation verified: zero cross-session memory leakage.")

        # -------------------------------------------------------------
        # TEST J: Concurrency & Advisory Lock Data Integrity
        # -------------------------------------------------------------
        print("\n[TEST J] Concurrency & Advisory Lock Data Integrity")
        concurrent_key = "day5_concurrent_target"
        candidates_j = [
            MemoryCandidate(
                category="goals",
                memory_type=MemoryType.GOAL.value,
                memory_key=concurrent_key,
                content=f"Concurrent Goal iteration number {i}",
                confidence_score=0.80 + (i * 0.03),
                importance_score=0.70,
                information_source=InformationSource.EXPLICIT_STATEMENT.value,
                persistence_type=PersistenceType.PERSISTENT.value,
                reason_for_storage="Concurrent test iteration."
            )
            for i in range(5)
        ]

        # Execute all 5 concurrent updates simultaneously
        await asyncio.gather(*[add_memory(session_alpha, c) for c in candidates_j])

        # Verify only 1 active memory remains
        active_conc = await list_memories(session_alpha, category="goals", is_active=True)
        target_conc = [m for m in active_conc if m.memory_key == concurrent_key]
        assert len(target_conc) == 1, f"Expected 1 active record for concurrent key, got {len(target_conc)}"
        print(f"  [PASSED] Concurrency locks safely serialized 5 updates down to 1 active memory: ID={target_conc[0].id}")

        # -------------------------------------------------------------
        # TEST K: Quantitative Benchmark Evaluation Runner & Report
        # -------------------------------------------------------------
        print("\n[TEST K] Quantitative Benchmark Evaluation Runner & Report")
        eval_summary = await run_retrieval_evaluation(clean_after=True)

        print(f"  Total Benchmark Queries:    {eval_summary['total_test_cases']}")
        print(f"  Passed Queries:             {eval_summary['passed_cases']}")
        print(f"  Overall Pass Rate:          {eval_summary['pass_rate_pct']}%")
        print(f"  Mean Precision@K:           {eval_summary['mean_precision_at_k']}")
        print(f"  Mean Recall@K:              {eval_summary['mean_recall_at_k']}")
        print(f"  Mean Reciprocal Rank (MRR): {eval_summary['mean_reciprocal_rank_mrr']}")
        print(f"  Mean NDCG@K:                {eval_summary['mean_ndcg_at_k']}")
        print(f"  Mean Latency:               {eval_summary['mean_latency_ms']} ms")
        print(f"  Cross-Session Leakages:     {eval_summary['cross_session_leakage_count']}")

        assert eval_summary["total_test_cases"] >= 10, "Evaluation suite has fewer than 10 test cases"
        assert eval_summary["pass_rate_pct"] >= 80.0, f"Benchmark pass rate too low: {eval_summary['pass_rate_pct']}%"
        assert eval_summary["cross_session_leakage_count"] == 0, "Cross-session leakage detected during evaluation!"

        md_report = generate_evaluation_markdown_report(eval_summary)
        assert "# MEMORA AI — Day 5 Retrieval Evaluation" in md_report
        print("  [PASSED] Benchmark evaluation passed with rigorous quantitative thresholds.")

    finally:
        print("\nCleaning up test sessions...")
        await delete_all_memories(session_alpha)
        await delete_all_memories(session_beta)
        await close_db_pool()
        print("Test sessions cleaned up.")

    print("\n" + "=" * 70)
    print("ALL DAY 5 MEMORY INTELLIGENCE & EVALUATION TESTS PASSED (11/11, 100%)!")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(run_day5_intelligence_tests())
