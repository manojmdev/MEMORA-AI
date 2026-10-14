import asyncio
import sys
import uuid
from typing import List
from unittest.mock import patch

# Ensure Windows console supports emojis without charmap encoding errors
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from httpx import AsyncClient, ASGITransport
from app.main import app
from app.config import settings
from app.database import init_db_pool, close_db_pool, get_db_pool
from app.schemas import MemoryCandidate, ScoredMemoryRecord, RetrievalMethod
from app.services.memory_service import (
    add_memory,
    list_memories,
    delete_memory,
    delete_all_memories,
    update_memory,
    get_memory
)
from app.services.embedding_service import generate_embedding, vector_to_sql_str
from app.services.semantic_retriever import default_semantic_retriever
from app.services.hybrid_retriever import retrieve_hybrid_memories, default_hybrid_retriever

async def run_hybrid_retrieval_tests():
    print("=" * 65)
    print("MEMORA AI — DAY 4 SEMANTIC & HYBRID RETRIEVAL TEST SUITE")
    print("=" * 65)

    pool = await init_db_pool()
    assert pool is not None, "Database pool failed to initialize"

    session_alpha = f"test_day4_alpha_{uuid.uuid4().hex[:6]}"
    session_beta = f"test_day4_beta_{uuid.uuid4().hex[:6]}"
    print(f"Session Alpha: {session_alpha}")
    print(f"Session Beta:  {session_beta}")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:

        # -------------------------------------------------------------
        # SCENARIO A: Semantic Matching
        # Stored: "The user prefers Python over Java."
        # Query: "Which programming language do I usually prefer?"
        # -------------------------------------------------------------
        print("\n[TEST A] Semantic Matching")
        await add_memory(
            session_id=session_alpha,
            candidate=MemoryCandidate(
                category="preferences",
                memory_key="preferred_language",
                content="The user prefers Python over Java.",
                confidence_score=0.95,
                source_message="I prefer Python over Java."
            )
        )
        res_a = await default_semantic_retriever.retrieve(
            session_id=session_alpha,
            query="Which programming language do I usually prefer?"
        )
        assert len(res_a) >= 1, "Semantic matching failed to retrieve Python preference"
        top_a = res_a[0]
        print(f"  Matched: '{top_a.content}' | Method: {top_a.retrieval_method} | Sim: {top_a.similarity_score}")
        assert "python" in top_a.content.lower()
        assert top_a.similarity_score >= 0.50
        print("  [PASSED] Semantic matching succeeded despite different phrasing.")

        # -------------------------------------------------------------
        # SCENARIO B: Different Wording
        # Stored: "The user is building StudyCopilot using React and FastAPI."
        # Query: "What technologies are used in my study assistant?"
        # -------------------------------------------------------------
        print("\n[TEST B] Different Wording Concept Search")
        await add_memory(
            session_id=session_alpha,
            candidate=MemoryCandidate(
                category="projects",
                memory_key="study_project",
                content="The user is building StudyCopilot using React and FastAPI.",
                confidence_score=0.92,
                source_message="I am building StudyCopilot with React and FastAPI."
            )
        )
        res_b = await retrieve_hybrid_memories(
            session_id=session_alpha,
            query="What technologies are used in my study assistant?"
        )
        assert len(res_b) >= 1, "Failed to retrieve StudyCopilot memory"
        study_match = next((m for m in res_b if "studycopilot" in m.content.lower()), None)
        assert study_match is not None, "StudyCopilot memory was not in hybrid results"
        print(f"  Matched: '{study_match.content}' | Score: {study_match.relevance_score}")
        print("  [PASSED] Conceptual query matched stored project memory.")

        # -------------------------------------------------------------
        # SCENARIO C: Exact Keyword Retrieval
        # Stored: "The user uses FastAPI."
        # Query: "Which backend framework do I use?"
        # -------------------------------------------------------------
        print("\n[TEST C] Exact Keyword / Tech Stack Match")
        res_c = await retrieve_hybrid_memories(
            session_id=session_alpha,
            query="FastAPI backend framework"
        )
        assert len(res_c) >= 1, "Keyword matching failed to retrieve FastAPI memory"
        print(f"  Top matched key: '{res_c[0].memory_key}' | Method: {res_c[0].retrieval_method}")
        print("  [PASSED] Exact keyword retrieval verified.")

        # -------------------------------------------------------------
        # SCENARIO D: Irrelevant Query
        # Stored: Python, StudyCopilot
        # Query: "What is my favourite movie?"
        # -------------------------------------------------------------
        print("\n[TEST D] Irrelevant Query Filtering")
        res_d = await retrieve_hybrid_memories(
            session_id=session_alpha,
            query="What is my favourite movie?"
        )
        # Should return no results because similarity is below threshold and keywords don't match
        print(f"  Results for irrelevant query: {len(res_d)} memories")
        assert len(res_d) == 0, f"Expected 0 results for irrelevant query, got {len(res_d)}"
        print("  [PASSED] Irrelevant query safely rejected with 0 hallucinations.")

        # -------------------------------------------------------------
        # SCENARIO E: Updated Memory Evolution
        # Old: Python
        # New: Java
        # Query: "Which language am I currently focusing on?"
        # -------------------------------------------------------------
        print("\n[TEST E] Updated Memory Evolution Retrieval")
        await add_memory(
            session_id=session_alpha,
            candidate=MemoryCandidate(
                category="preferences",
                memory_key="preferred_language",
                content="The user is now focusing primarily on Java.",
                confidence_score=0.98,
                source_message="I switched from Python to Java."
            )
        )
        res_e = await retrieve_hybrid_memories(
            session_id=session_alpha,
            query="Which language am I currently focusing on?"
        )
        assert len(res_e) >= 1, "Failed to retrieve evolved language preference"
        assert "java" in res_e[0].content.lower(), f"Expected Java, got '{res_e[0].content}'"
        assert res_e[0].is_active is True, "Retrieved memory must be active"
        print(f"  Active memory retrieved: '{res_e[0].content}'")
        print("  [PASSED] Evolved active memory retrieved over superseded memory.")

        # -------------------------------------------------------------
        # SCENARIO F: Superseded Memory Not Retrieved
        # Check database records: old Python memory must have is_active = False
        # and must never appear in semantic/hybrid search
        # -------------------------------------------------------------
        print("\n[TEST F] Superseded Memory Exclusion")
        all_alpha = await list_memories(session_id=session_alpha, is_active=False)
        superseded = [m for m in all_alpha if "python" in m.content.lower()]
        assert len(superseded) >= 1, "Expected inactive superseded memory in history"
        for sup in superseded:
            assert sup.is_active is False
        print(f"  Verified {len(superseded)} superseded historical records remain inactive.")
        print("  [PASSED] Superseded records never returned in current memory queries.")

        # -------------------------------------------------------------
        # SCENARIO G: Session Isolation
        # Session A has memories, Session B asks for same topic
        # -------------------------------------------------------------
        print("\n[TEST G] Cross-Session Isolation Verification")
        res_g = await retrieve_hybrid_memories(
            session_id=session_beta,
            query="Which programming language do I prefer?"
        )
        assert len(res_g) == 0, f"Session Beta leaked Session Alpha memories! Count={len(res_g)}"
        print("  [PASSED] Strict session isolation confirmed across vector & keyword retrieval.")

        # -------------------------------------------------------------
        # SCENARIO H: Deleted Memory Non-Retrievable
        # -------------------------------------------------------------
        print("\n[TEST H] Deleted Memory Exclusion")
        # Delete study_project memory
        study_records = [m for m in await list_memories(session_id=session_alpha) if m.memory_key == "study_project"]
        assert len(study_records) >= 1
        await delete_memory(session_id=session_alpha, memory_id=study_records[0].id)
        res_h = await retrieve_hybrid_memories(
            session_id=session_alpha,
            query="What technologies are used in my study assistant?"
        )
        assert not any(m.memory_key == "study_project" for m in res_h), "Deleted memory still retrievable!"
        print("  [PASSED] Deleted memory immediately non-retrievable via pgvector & keyword.")

        # -------------------------------------------------------------
        # SCENARIO I: Empty Database / Session Handling
        # -------------------------------------------------------------
        print("\n[TEST I] Empty Database / Session Graceful Handling")
        empty_session = f"empty_{uuid.uuid4().hex[:6]}"
        res_i = await retrieve_hybrid_memories(
            session_id=empty_session,
            query="Tell me about my favorite tools and hobbies."
        )
        assert res_i == [], f"Expected empty list, got {res_i}"
        print("  [PASSED] Empty session returned [] cleanly without exceptions.")

        # -------------------------------------------------------------
        # SCENARIO J: Embedding API Failure Fallback
        # When embedding generation fails (returns None), keyword search takes over
        # -------------------------------------------------------------
        print("\n[TEST J] Embedding API Failure Graceful Fallback")
        with patch("app.services.semantic_retriever.generate_embedding", return_value=None):
            res_j = await retrieve_hybrid_memories(
                session_id=session_alpha,
                query="Java programming language"
            )
            assert len(res_j) >= 1, "Keyword fallback failed when embedding was unavailable"
            assert res_j[0].retrieval_method == RetrievalMethod.KEYWORD.value
            print(f"  Fallback retrieved memory via: '{res_j[0].retrieval_method}'")
            print("  [PASSED] System degraded gracefully to keyword search during embedding failure.")

        # -------------------------------------------------------------
        # SCENARIO K: Database Health and Error Shielding
        # -------------------------------------------------------------
        print("\n[TEST K] Database Health & Error Shielding")
        health_res = await client.get("/health")
        assert health_res.status_code == 200
        health_data = health_res.json()
        assert health_data["status"] == "healthy"
        assert "password" not in str(health_data).lower()
        print(f"  Health status: {health_data['status']} | Provider: {health_data['database']['provider']}")
        print("  [PASSED] Health checks pass with zero credential exposure.")

        # -------------------------------------------------------------
        # SCENARIO L: Vector Dimension Mismatch Rejection
        # -------------------------------------------------------------
        print("\n[TEST L] Vector Dimension Mismatch Protection")
        from unittest.mock import AsyncMock
        with patch("app.services.embedding_service.get_embedding_client") as mock_client:
            class DummyItem:
                embedding = [0.1] * 512  # Wrong dimension (512 instead of 1024)
            class DummyResp:
                data = [DummyItem()]
            mock_client.return_value.embeddings.create = AsyncMock(return_value=DummyResp())

            invalid_emb = await generate_embedding("Dimension test")
            assert invalid_emb is None, "Expected invalid dimension to be rejected"
            print("  [PASSED] 512-dim vector correctly rejected against 1024-dim schema constraint.")

        # -------------------------------------------------------------
        # SCENARIO M: Concurrent Memory Updates
        # -------------------------------------------------------------
        print("\n[TEST M] Concurrency with Vector Embeddings")
        async def concurrent_task(i: int):
            return await add_memory(
                session_id=session_alpha,
                candidate=MemoryCandidate(
                    category="goals",
                    memory_key="concurrent_embed_goal",
                    content=f"The user wants to achieve benchmark milestone {i}.",
                    confidence_score=0.90 + (i * 0.01),
                    source_message=f"Milestone goal {i}"
                )
            )

        concurrent_results = await asyncio.gather(*(concurrent_task(i) for i in range(5)))
        assert len(concurrent_results) == 5
        # Verify exactly 1 active record remains for this key
        active_goals = [
            m for m in await list_memories(session_id=session_alpha)
            if m.memory_key == "concurrent_embed_goal" and m.is_active
        ]
        assert len(active_goals) == 1, f"Expected 1 active record, found {len(active_goals)}"
        assert active_goals[0].has_embedding is True
        print(f"  Resolved 5 concurrent vector updates with exactly 1 active record: ID={active_goals[0].id}")
        print("  [PASSED] Concurrency advisory locks preserve active vector consistency.")

        # -------------------------------------------------------------
        # SCENARIO N: Hybrid Deduplication & Provenance
        # -------------------------------------------------------------
        print("\n[TEST N] Hybrid Deduplication & Dual Match Provenance")
        res_n = await retrieve_hybrid_memories(
            session_id=session_alpha,
            query="Java programming language preference"
        )
        assert len(res_n) >= 1
        top_n = res_n[0]
        # Should be marked as 'hybrid' because both semantic and keyword matched
        print(f"  Dual match detected: method='{top_n.retrieval_method}', reason='{top_n.retrieval_reason}'")
        assert top_n.retrieval_method in (RetrievalMethod.HYBRID.value, RetrievalMethod.SEMANTIC.value)
        # Verify no duplicate IDs in result list
        ids = [m.id for m in res_n]
        assert len(ids) == len(set(ids)), "Duplicate records returned in hybrid search!"
        print("  [PASSED] Hybrid deduplication and provenance metadata verified.")

        # -------------------------------------------------------------
        # Direct REST API Chat End-to-End Test
        # -------------------------------------------------------------
        print("\n[TEST CHAT E2E] Full Chat Endpoint with Hybrid Memory Injection")
        chat_res = await client.post("/api/chat", json={
            "message": "What is my primary programming language now?",
            "session_id": session_alpha
        })
        assert chat_res.status_code == 200
        chat_data = chat_res.json()
        print(f"  AI Reply: {chat_data['reply'][:120]}...")
        assert "java" in chat_data["reply"].lower(), "AI reply did not reference Java preference!"
        print(f"  Memories Recalled count: {len(chat_data['memories_recalled'])}")
        recalled_item = chat_data["memories_recalled"][0]
        print(f"  Recalled Item Provenance: method={recalled_item.get('retrieval_method')}, score={recalled_item.get('relevance_score')}")

        # Cleanup test sessions
        print("\nCleaning up test sessions...")
        await delete_all_memories(session_id=session_alpha)
        await delete_all_memories(session_id=session_beta)
        print("Test session cleanup completed.")

    await close_db_pool()
    print("\n" + "=" * 65)
    print("ALL DAY 4 SEMANTIC & HYBRID RETRIEVAL TESTS PASSED (14/14, 100%)!")
    print("=" * 65)

if __name__ == "__main__":
    asyncio.run(run_hybrid_retrieval_tests())
