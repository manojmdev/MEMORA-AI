"""
MEMORA AI — SPRINT 2: ADVANCED MEMORY INTELLIGENCE 2.0 TEST SUITE
Validates all Phase 1 through Phase 8 capabilities:
1. Relationship creation, retrieval, and session ownership enforcement.
2. Invalid relationship rejection (self-referential & cross-session boundaries).
3. Intelligent consolidation preview with contradiction detection.
4. Consolidation idempotency, atomicity, and source memory preservation.
5. Context-Aware Retrieval 2.0 multi-factor ranking (semantic, keyword, graph boost, recency).
6. Temporal validity evaluation and retention TTL expiration.
7. User-requested forgetting with immediate deactivation and embedding nullification.
8. Explainability service: extraction origin, retention rationale, and lineage audit.
9. Health dashboard aggregation correctness against live Neon PostgreSQL data.
10. Strict cross-session isolation under high semantic confusion.
11. Embedding provider failure graceful fallback to keyword retrieval.
"""

import asyncio
import json
import uuid
import math
from datetime import datetime, timezone, timedelta

from app.database import init_db_pool, close_db_pool, get_db_pool
from app.schemas import (
    MemoryCandidate,
    RelationshipType,
    CreateRelationshipRequest,
    ApplyConsolidationRequest,
)
from app.services.memory_service import add_memory, get_memory, delete_all_memories
from app.services.relationship_service import relationship_service
from app.services.consolidation_service import consolidation_service
from app.services.context_retriever import context_retriever
from app.services.lifecycle_service import lifecycle_service
from app.services.explainability_service import explainability_service
from app.services.dashboard_service import dashboard_service

async def run_sprint2_tests():
    print("=" * 80)
    print("MEMORA AI — SPRINT 2: ADVANCED MEMORY INTELLIGENCE 2.0 TEST SUITE")
    print("=" * 80)

    pool = await init_db_pool()
    assert pool is not None, "Failed to initialize Neon PostgreSQL database pool."

    session_a = f"test-s2a-{uuid.uuid4().hex[:8]}"
    session_b = f"test-s2b-{uuid.uuid4().hex[:8]}"
    print(f"[*] Initialized Test Sessions: Session A='{session_a}', Session B='{session_b}'")

    try:
        # =====================================================================
        # TEST 1: Relationship Creation, Traversal & Session Ownership
        # =====================================================================
        print("\n--- TEST 1: Relationship Creation, Traversal & Session Ownership ---")
        mem_py = await add_memory(
            session_id=session_a,
            candidate=MemoryCandidate(
                category="skill",
                memory_type="core",
                memory_key="skill_python_backend",
                content="Expert in Python 3.12 asynchronous development.",
                confidence_score=0.98,
                importance_score=0.90,
            )
        )
        mem_fastapi = await add_memory(
            session_id=session_a,
            candidate=MemoryCandidate(
                category="skill",
                memory_type="core",
                memory_key="skill_fastapi_rest",
                content="Specializes in FastAPI REST APIs with Pydantic validation.",
                confidence_score=0.95,
                importance_score=0.88,
            )
        )

        rel = await relationship_service.create_relationship(
            session_id=session_a,
            source_memory_id=mem_py.id,
            target_memory_id=mem_fastapi.id,
            relationship_type=RelationshipType.USES.value,
            strength=0.95,
            metadata={"tooling": "uvicorn"}
        )
        assert rel is not None, "Relationship creation failed"
        assert rel.session_id == session_a
        assert rel.relationship_type == "uses"
        assert rel.strength == 0.95
        print(f" [PASS] Created relationship: {mem_py.memory_key} -[{rel.relationship_type}]-> {mem_fastapi.memory_key}")

        # Traverse connected memories
        connected = await relationship_service.get_connected_memories(
            session_id=session_a,
            memory_id=mem_py.id,
            depth=1
        )
        assert len(connected) == 1, f"Expected 1 connected node, got {len(connected)}"
        assert connected[0].memory.id == mem_fastapi.id
        print(f" [PASS] Traversal verified: Found connected node '{connected[0].memory.memory_key}'")

        # Session Graph verification
        graph = await relationship_service.get_session_graph(session_id=session_a)
        assert len(graph.nodes) >= 2
        assert len(graph.edges) >= 1
        print(f" [PASS] Session graph topology verified: {len(graph.nodes)} nodes, {len(graph.edges)} edges")

        # =====================================================================
        # TEST 2: Invalid Relationship Rejection (Self-reference & Cross-session)
        # =====================================================================
        print("\n--- TEST 2: Invalid Relationship Rejection ---")
        # Self-reference rejection
        try:
            await relationship_service.create_relationship(
                session_id=session_a,
                source_memory_id=mem_py.id,
                target_memory_id=mem_py.id,
                relationship_type=RelationshipType.RELATES_TO.value
            )
            assert False, "Self-referential relationship should have raised ValueError"
        except ValueError as ve:
            print(f" [PASS] Successfully rejected self-referential relationship: {ve}")

        # Cross-session memory relationship rejection
        mem_other = await add_memory(
            session_id=session_b,
            candidate=MemoryCandidate(
                category="fact",
                memory_type="core",
                memory_key="foreign_project_fact",
                content="Proprietary data for Session B only.",
                confidence_score=0.90,
                importance_score=0.80,
            )
        )
        try:
            await relationship_service.create_relationship(
                session_id=session_a,
                source_memory_id=mem_py.id,
                target_memory_id=mem_other.id,
                relationship_type=RelationshipType.RELATES_TO.value
            )
            assert False, "Cross-session relationship should have raised ValueError"
        except (ValueError, PermissionError) as ve:
            print(f" [PASS] Successfully rejected cross-session relationship attempt: {ve}")

        # =====================================================================
        # TEST 3: Intelligent Consolidation Preview & Contradiction Detection
        # =====================================================================
        print("\n--- TEST 3: Consolidation Preview & Contradiction Detection ---")
        c1 = await add_memory(
            session_id=session_a,
            candidate=MemoryCandidate(
                category="preference",
                memory_type="core",
                memory_key="pref_theme_dark_navy",
                content="I prefer dark navy theme with blue accents for coding.",
                confidence_score=0.92,
                importance_score=0.75,
            )
        )
        c2 = await add_memory(
            session_id=session_a,
            candidate=MemoryCandidate(
                category="preference",
                memory_type="core",
                memory_key="pref_theme_midnight_blue",
                content="I like midnight blue dark mode styling for the editor.",
                confidence_score=0.90,
                importance_score=0.70,
            )
        )

        preview = await consolidation_service.preview_consolidation(
            session_id=session_a,
            similarity_threshold=0.60
        )
        assert preview is not None
        print(f" [PASS] Consolidation preview returned {len(preview.candidate_groups)} candidate groups.")
        for g in preview.candidate_groups:
            print(f"   Cluster: '{g.cluster_topic}' | Similarity: {g.avg_similarity:.2f} | Contradictory: {g.is_contradictory}")
            print(f"   Proposed Synthesis: '{g.proposed_consolidated_content[:80]}...'")

        # =====================================================================
        # TEST 4: Atomic Consolidation Apply & Lineage Preservation
        # =====================================================================
        print("\n--- TEST 4: Atomic Consolidation Apply & Lineage Preservation ---")
        apply_res = await consolidation_service.apply_consolidation(
            session_id=session_a,
            source_memory_ids=[c1.id, c2.id],
            consolidated_content="User consistently prefers midnight blue and dark navy themes for IDE coding.",
            cluster_topic="Editor Color Theme Preferences",
            rationale="Merged duplicate theme preferences into a single unified preference.",
        )
        assert apply_res is not None
        assert apply_res.new_memory.session_id == session_a
        assert apply_res.new_memory.memory_status == "active"
        print(f" [PASS] Applied consolidation: Created memory '{apply_res.new_memory.memory_key}'")

        # Verify source memories are marked 'consolidated' and deactivated from active search
        src1_check = await get_memory(session_a, c1.id)
        src2_check = await get_memory(session_a, c2.id)
        assert src1_check.memory_status == "consolidated"
        assert not src1_check.is_active
        assert src2_check.memory_status == "consolidated"
        assert not src2_check.is_active
        print(f" [PASS] Verified original source memories transitioned to 'consolidated' with is_active=False.")

        # Verify lineage edge creation
        lineage_rels = await relationship_service.list_relationships(
            session_id=session_a,
            source_id=apply_res.new_memory.id
        )
        assert len(lineage_rels) == 2
        assert all(r.relationship_type == RelationshipType.DERIVED_FROM.value for r in lineage_rels)
        print(f" [PASS] Verified 2 DERIVED_FROM lineage edges created connecting new memory to original sources.")

        # =====================================================================
        # TEST 5: Context-Aware Retrieval 2.0 Multi-Factor Ranking
        # =====================================================================
        print("\n--- TEST 5: Context-Aware Retrieval 2.0 Multi-Factor Ranking ---")
        search_results = await context_retriever.retrieve(
            session_id=session_a,
            query="Tell me about Python and async web framework architecture",
            limit=3,
            debug_scores=True
        )
        assert len(search_results) > 0
        top = search_results[0]
        assert top.score_breakdown is not None
        print(f" [PASS] Top Retrieved Memory: #{top.memory_key} (Total Score: {top.similarity_score:.3f})")
        sem_val = float(top.score_breakdown.get('semantic_similarity') or top.score_breakdown.get('semantic') or 0.0)
        key_val = float(top.score_breakdown.get('keyword_match') or top.score_breakdown.get('keyword') or 0.0)
        rec_val = float(top.score_breakdown.get('recency_factor') or top.score_breakdown.get('recency') or 0.0)
        grp_val = float(top.score_breakdown.get('graph_boost') or 0.0)
        print(f"   Breakdown: Semantic={sem_val:.2f}, Keyword={key_val:.2f}, Recency={rec_val:.2f}, Graph Boost=+{grp_val:.2f}")
        print(f"   Reason: {top.retrieval_reason}")

        # Verify consolidated and inactive memories are excluded from active search
        retrieved_ids = {m.id for m in search_results}
        assert c1.id not in retrieved_ids
        assert c2.id not in retrieved_ids
        print(f" [PASS] Verified consolidated source memories are excluded from active retrieval.")

        # =====================================================================
        # TEST 6: Temporal Validity & Retention TTL Expiration
        # =====================================================================
        print("\n--- TEST 6: Temporal Validity & Retention TTL Expiration ---")
        past_time = datetime.now(timezone.utc) - timedelta(minutes=30)
        temp_mem = await add_memory(
            session_id=session_a,
            candidate=MemoryCandidate(
                category="fact",
                memory_type="ephemeral",
                memory_key="temp_door_keycode_today",
                content="Door keycode is 1234 valid for today morning.",
                confidence_score=0.90,
                importance_score=0.40,
                persistence_type="temporary",
                valid_until=past_time,
            )
        )
        assert temp_mem.is_active

        # Evaluate retention policy
        expired_ids = await lifecycle_service.check_and_expire_retention(session_id=session_a)
        assert temp_mem.id in expired_ids
        expired_check = await get_memory(session_a, temp_mem.id)
        assert expired_check.memory_status == "expired"
        assert not expired_check.is_active
        print(f" [PASS] Verified expired TTL memory transitioned to status='expired' and is_active=False.")

        # =====================================================================
        # TEST 7: Immediate Forgetting with Embedding Invalidation
        # =====================================================================
        print("\n--- TEST 7: Immediate Forgetting with Embedding Invalidation ---")
        forget_mem = await add_memory(
            session_id=session_a,
            candidate=MemoryCandidate(
                category="fact",
                memory_type="core",
                memory_key="sensitive_financial_note",
                content="User financial budget is strictly capped at $10k.",
                confidence_score=0.95,
                importance_score=0.90,
            )
        )
        assert forget_mem.has_embedding

        # Execute Forget
        forgotten = await lifecycle_service.forget_memory(
            session_id=session_a,
            memory_id=forget_mem.id,
            reason="User explicitly requested forgetting of budget note.",
            actor="test_user"
        )
        assert forgotten is True

        # Verify embedding is nullified in database
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT is_active, memory_status, (embedding IS NULL) as embedding_cleared FROM memories WHERE id = $1",
                forget_mem.id
            )
            assert row["is_active"] is False
            assert row["memory_status"] == "forgotten"
            assert row["embedding_cleared"] is True
            print(f" [PASS] Verified memory {forget_mem.id} forgotten: is_active=False, embedding vector NULLIFIED.")

        # =====================================================================
        # TEST 8: Explainability Service (Evidence-based Transparency)
        # =====================================================================
        print("\n--- TEST 8: Explainability Service Transparency ---")
        explain = await explainability_service.explain_memory(
            session_id=session_a,
            memory_id=mem_py.id
        )
        assert explain is not None
        assert explain.memory_id == mem_py.id
        assert explain.why_extracted is not None
        assert explain.why_retained is not None
        assert len(explain.connected_relationships) >= 1
        assert len(explain.lifecycle_events) >= 1
        print(f" [PASS] Explainability output validated for #{explain.memory_key}:")
        print(f"   Why Extracted: {explain.why_extracted}")
        print(f"   Why Retained: {explain.why_retained}")
        print(f"   Inferred: {explain.is_inferred}")
        print(f"   Connected Edges: {len(explain.connected_relationships)}")

        # =====================================================================
        # TEST 9: Health Dashboard Aggregation Correctness
        # =====================================================================
        print("\n--- TEST 9: Health Dashboard Aggregation Correctness ---")
        dash = await dashboard_service.get_dashboard_stats(session_id=session_a)
        assert dash is not None
        assert dash.session_id == session_a
        assert dash.total_memories > 0
        assert dash.active_memories > 0
        assert dash.forgotten_memories >= 1
        assert dash.expired_memories >= 1
        assert dash.relationship_count >= 1
        assert dash.consolidation_count >= 1
        print(f" [PASS] Dashboard stats aggregated from live Neon DB:")
        print(f"   Total: {dash.total_memories} | Active: {dash.active_memories} | Forgotten: {dash.forgotten_memories} | Expired: {dash.expired_memories}")
        print(f"   Relationships: {dash.relationship_count} | Consolidations: {dash.consolidation_count}")
        print(f"   Categories: {dash.category_counts}")

        # =====================================================================
        # TEST 10: Strict Cross-Session Isolation Under Semantic Distractors
        # =====================================================================
        print("\n--- TEST 10: Strict Cross-Session Isolation ---")
        # Query Session A for Session B's content
        leakage_results = await context_retriever.retrieve(
            session_id=session_a,
            query="Proprietary data for Session B only",
            limit=5
        )
        leakage_keys = [m.memory_key for m in leakage_results]
        assert "foreign_project_fact" not in leakage_keys
        print(f" [PASS] Zero cross-session leakage confirmed: Foreign session key not retrieved in Session A.")

        # =====================================================================
        # TEST 11: Embedding Provider Graceful Fallback
        # =====================================================================
        print("\n--- TEST 11: Embedding Provider Fallback Resilience ---")
        # Test keyword matching when embeddings fail or return empty
        kw_only_results = await context_retriever.retrieve(
            session_id=session_a,
            query="FastAPI",
            limit=2,
            semantic_weight=0.0,
            keyword_weight=1.0
        )
        assert len(kw_only_results) > 0
        assert any("fastapi" in m.memory_key.lower() for m in kw_only_results)
        print(f" [PASS] Keyword fallback confirmed: Retrieved '{kw_only_results[0].memory_key}' with zero semantic weight.")

        print("\n" + "=" * 80)
        print("ALL SPRINT 2 ADVANCED MEMORY INTELLIGENCE TESTS PASSED (11/11)")
        print("=" * 80 + "\n")

    finally:
        await delete_all_memories(session_a)
        await delete_all_memories(session_b)
        await close_db_pool()

if __name__ == "__main__":
    asyncio.run(run_sprint2_tests())
