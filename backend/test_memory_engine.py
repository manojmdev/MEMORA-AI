import asyncio
import sys
import uuid
from typing import List

# Ensure Windows console supports emojis without charmap encoding errors
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import init_db_pool, close_db_pool, get_db_pool
from app.schemas import MemoryCandidate
from app.services.memory_service import (
    add_memory,
    list_memories,
    delete_memory,
    delete_all_memories,
    get_memory
)
from app.services.memory_extractor import clean_json_string
from app.services.memory_retriever import retrieve_relevant_memories

async def run_memory_engine_tests():
    print("=" * 60)
    print("MEMORA AI — DAY 3 MEMORY EVOLUTION ENGINE TEST SUITE")
    print("=" * 60)

    # Initialize pool in this event loop
    pool = await init_db_pool()
    assert pool is not None, "Database pool failed to initialize"

    # Unique test sessions to ensure isolated runs
    session_alpha = f"test_alpha_{uuid.uuid4().hex[:6]}"
    session_beta = f"test_beta_{uuid.uuid4().hex[:6]}"
    print(f"Session Alpha: {session_alpha}")
    print(f"Session Beta:  {session_beta}")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # ---------------------------------------------------------
        # SCENARIO 1: Remember ("I prefer Python over Java.")
        # ---------------------------------------------------------
        print("\n[TEST 1] Remember: 'I prefer Python over Java.'")
        res1 = await client.post("/api/chat", json={
            "message": "I prefer Python over Java.",
            "session_id": session_alpha
        })
        assert res1.status_code == 200, f"Chat failed: {res1.text}"
        data1 = res1.json()
        print(f"  AI Reply: {data1['reply'][:80]}...")
        print(f"  Extracted memories: {data1.get('memories_extracted')}")

        # Verify saved in database
        mems_alpha = await list_memories(session_id=session_alpha)
        assert len(mems_alpha) >= 1, "Expected at least 1 extracted memory in Session Alpha"
        py_mem = next((m for m in mems_alpha if "python" in m.content.lower() or "python" in m.memory_key.lower()), None)
        assert py_mem is not None, "Python preference was not saved to database"
        print(f"  Verified DB storage: id={py_mem.id}, key='{py_mem.memory_key}', content='{py_mem.content}'")

        # ---------------------------------------------------------
        # SCENARIO 2: Recall ("Which programming language do I prefer?")
        # ---------------------------------------------------------
        print("\n[TEST 2] Recall: 'Which programming language do I prefer?'")
        res2 = await client.post("/api/chat", json={
            "message": "Which programming language do I prefer?",
            "session_id": session_alpha
        })
        assert res2.status_code == 200
        data2 = res2.json()
        print(f"  AI Reply: {data2['reply']}")
        recalled_keys = [m['memory_key'] for m in data2.get('memories_recalled', [])]
        print(f"  Recalled keys: {recalled_keys}")
        assert any("python" in k.lower() or "language" in k.lower() or "prefer" in k.lower() for k in recalled_keys), "Python preference was not recalled!"
        assert "python" in data2['reply'].lower(), "Model reply did not recall Python preference"

        # ---------------------------------------------------------
        # SCENARIO 3: Update ("I am now focusing primarily on Java.")
        # ---------------------------------------------------------
        print("\n[TEST 3] Update: 'I am now focusing primarily on Java.'")
        res3 = await client.post("/api/chat", json={
            "message": "I am now focusing primarily on Java instead of Python.",
            "session_id": session_alpha
        })
        assert res3.status_code == 200
        data3 = res3.json()
        print(f"  AI Reply: {data3['reply'][:80]}...")
        print(f"  Extracted: {data3.get('memories_extracted')}")

        # Verify evolution/superseding in database
        active_mems = await list_memories(session_id=session_alpha, is_active=True)
        java_mem = next((m for m in active_mems if "java" in m.content.lower() or "java" in m.memory_key.lower()), None)
        assert java_mem is not None, "Java update was not persisted"
        print(f"  Active memory now: key='{java_mem.memory_key}', content='{java_mem.content}'")

        # ---------------------------------------------------------
        # SCENARIO 4: Conflict ("I prefer Python again.")
        # ---------------------------------------------------------
        print("\n[TEST 4] Conflict/Evolution: 'I prefer Python again.'")
        res4 = await client.post("/api/chat", json={
            "message": "I changed my mind, I prefer Python again.",
            "session_id": session_alpha
        })
        assert res4.status_code == 200
        data4 = res4.json()
        print(f"  AI Reply: {data4['reply'][:80]}...")

        active_mems_after = await list_memories(session_id=session_alpha, is_active=True)
        current_fav = next((m for m in active_mems_after if "python" in m.content.lower()), None)
        assert current_fav is not None, "Preference was not restored to Python"
        print(f"  Updated active memory: key='{current_fav.memory_key}', content='{current_fav.content}'")

        # ---------------------------------------------------------
        # SCENARIO 5: Explain ("Why do you associate me with Python?")
        # ---------------------------------------------------------
        print("\n[TEST 5] Explain: 'Why do you associate me with Python?'")
        res5 = await client.post("/api/chat", json={
            "message": "Why do you associate me with Python?",
            "session_id": session_alpha
        })
        assert res5.status_code == 200
        data5 = res5.json()
        print(f"  AI Explanation: {data5['reply']}")
        assert "python" in data5['reply'].lower(), "Model did not explain based on Python memory"

        # ---------------------------------------------------------
        # SCENARIO 6: Forget (Delete preference)
        # ---------------------------------------------------------
        print("\n[TEST 6] Forget: Delete memory via API")
        del_res = await client.delete(f"/api/memories/{current_fav.id}?session_id={session_alpha}")
        assert del_res.status_code == 200, f"Delete failed: {del_res.text}"
        print(f"  Delete API response: {del_res.json()}")

        # Verify memory is gone
        mems_after_del = await list_memories(session_id=session_alpha, is_active=True)
        assert not any(m.id == current_fav.id for m in mems_after_del), "Deleted memory still exists!"
        print("  Verified: Memory is no longer in active storage.")

        # ---------------------------------------------------------
        # SCENARIO 7: Session Isolation
        # ---------------------------------------------------------
        print("\n[TEST 7] Session Isolation (Session Beta vs Session Alpha)")
        # Add a unique secret to Alpha
        await add_memory(
            session_id=session_alpha,
            candidate=MemoryCandidate(
                category="projects",
                memory_key="alpha_secret_project",
                content="The user is developing Project Hyperion secretly.",
                confidence_score=1.0,
                source_message="My secret project is Hyperion"
            )
        )

        # Query memories for Beta
        res_beta_mems = await client.get(f"/api/memories?session_id={session_beta}")
        assert res_beta_mems.status_code == 200
        beta_data = res_beta_mems.json()
        assert beta_data["count"] == 0, f"Session Beta leaked memories: {beta_data}"
        print("  GET /api/memories for Session Beta returned 0 memories (PASSED)")

        # Ask in Beta about the secret
        res_beta_chat = await client.post("/api/chat", json={
            "message": "What is my secret project name?",
            "session_id": session_beta
        })
        assert res_beta_chat.status_code == 200
        beta_reply = res_beta_chat.json()
        assert len(beta_reply.get("memories_recalled", [])) == 0, "Session Beta recalled Alpha memories!"
        assert "hyperion" not in beta_reply["reply"].lower(), "Session Beta leaked secret project Hyperion!"
        print(f"  Session Beta AI Reply: {beta_reply['reply'][:80]}... (PASSED)")

        # ---------------------------------------------------------
        # RESILIENCE & EDGE CASE TESTS
        # ---------------------------------------------------------
        print("\n[TEST 8] Resilience: Malformed Extraction Parser")
        garbage_output = "```json\n{ invalid_json, non_bracketed\n```"
        cleaned = clean_json_string(garbage_output)
        assert cleaned == "{ invalid_json, non_bracketed"
        print("  clean_json_string stripped markdown fences cleanly (PASSED)")

        print("\n[TEST 9] Deduplication: Duplicate Memory Candidate Insert")
        dup_cand = MemoryCandidate(
            category="skills",
            memory_key="core_skill",
            content="The user is proficient in Python and SQL.",
            confidence_score=0.9,
            source_message="I know Python and SQL"
        )
        m1 = await add_memory(session_alpha, dup_cand)
        m2 = await add_memory(session_alpha, dup_cand)
        assert m1.id == m2.id, "Duplicate candidate created a second row instead of updating"
        print(f"  Deduplication verified: Both operations referenced ID {m1.id} (PASSED)")

        print("\n[TEST 10] Concurrency: Concurrent Memory Updates")
        async def concurrent_update(idx: int):
            c = MemoryCandidate(
                category="goals",
                memory_key="concurrent_target_goal",
                content=f"Goal iteration {idx}",
                confidence_score=0.9
            )
            return await add_memory(session_alpha, c)

        results = await asyncio.gather(*(concurrent_update(i) for i in range(5)))
        assert len(results) == 5
        active_concurrent = await list_memories(session_alpha, category="goals", is_active=True)
        matching = [m for m in active_concurrent if m.memory_key == "concurrent_target_goal"]
        assert len(matching) == 1, f"Expected 1 active record, found {len(matching)}"
        print(f"  Concurrency verified: 5 concurrent updates resolved safely with 1 active record (PASSED)")

        print("\n[TEST 11] Empty Retrieval Graceful Handling")
        empty_mems = await retrieve_relevant_memories(session_id="empty_nonexistent_session", query="anything")
        assert empty_mems == [], "Empty retrieval did not return empty list"
        print("  Empty retrieval returned [] safely (PASSED)")

        # Cleanup test sessions
        await delete_all_memories(session_alpha)
        await delete_all_memories(session_beta)
        print("\nTest session cleanup completed.")

    await close_db_pool()
    print("\n" + "=" * 60)
    print("ALL DAY 3 TEST SUITE SCENARIOS PASSED WITH 100% SUCCESS!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_memory_engine_tests())
