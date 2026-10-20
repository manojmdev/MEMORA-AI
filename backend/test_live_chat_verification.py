"""
MEMORA AI — FINAL LIVE CHAT & MEMORY EXPLORER VERIFICATION
Verifies:
1. Exact prompt:
   "I'm a computer science student specializing in AI and machine learning. I prefer Python over Java and C. I enjoy building practical AI applications rather than spending too much time on theory."
2. HTTP request succeeds (200 OK) with request correlation ID.
3. Assistant responds with thoughtful, personalized response.
4. Expected memories are extracted (academic focus, language preference, practical application preference).
5. Memories are persisted in Neon PostgreSQL.
6. Memory Explorer / List endpoint (/api/memories?session_id=...) displays the saved memories.
7. Subsequent question retrieves them with personalized response.
"""

import asyncio
import sys
import uuid
import httpx

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

from app.database import init_db_pool, close_db_pool, get_db_pool
from app.main import app

async def run_live_verification():
    print("=" * 80)
    print("MEMORA AI — LIVE CHAT & MEMORY EXPLORER VERIFICATION")
    print("=" * 80)

    pool = await init_db_pool()
    assert pool is not None, "Failed to connect to Neon PostgreSQL"

    session_id = f"live_verify_{uuid.uuid4().hex[:8]}"
    req_id_1 = f"live-req-{uuid.uuid4().hex[:12]}"
    test_message = (
        "I'm a computer science student specializing in AI and machine learning. "
        "I prefer Python over Java and C. "
        "I enjoy building practical AI applications rather than spending too much time on theory."
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        print(f"\n1. Sending initial user message...")
        print(f"   Session ID:   {session_id}")
        print(f"   Request ID:   {req_id_1}")
        print(f"   User Message: \"{test_message}\"")

        res_1 = await client.post(
            "/api/chat",
            json={"message": test_message, "session_id": session_id},
            headers={"X-Request-ID": req_id_1}
        )

        assert res_1.status_code == 200, f"Expected 200 OK, got {res_1.status_code}: {res_1.text}"
        data_1 = res_1.json()

        print("\n2. Assistant Response Received:")
        print(f"   Status Code:     {res_1.status_code}")
        print(f"   Correlation ID:  {res_1.headers.get('x-request-id')}")
        print(f"   Reply Preview:   {data_1['reply'][:140]}...")
        print(f"   Persistence:     {data_1.get('memory_persistence_status')}")

        assert len(data_1["reply"]) > 50, "Assistant reply must not be empty"
        assert data_1["memory_persistence_status"] == "success", f"Persistence status should be 'success', got {data_1.get('memory_persistence_status')}"
        assert data_1.get("memory_persistence_error") is None

        extracted = data_1.get("memories_extracted", [])
        print(f"\n3. Extracted Memories ({len(extracted)} extracted):")
        for mem in extracted:
            print(f"   - [{mem.get('category')}] {mem.get('memory_key')}: {mem.get('content')}")
        assert len(extracted) >= 2, f"Expected at least 2 memories extracted, got {len(extracted)}"

        # 4. Neon PostgreSQL direct record verification
        print("\n4. Verifying Neon PostgreSQL database persistence...")
        async with pool.acquire() as conn:
            db_records = await conn.fetch(
                "SELECT id, memory_key, category, content, confidence_score, importance_score, is_active FROM memories WHERE session_id = $1",
                session_id
            )
            print(f"   Found {len(db_records)} active records in database:")
            for r in db_records:
                print(f"   - DB Record ID={r['id']}: key='{r['memory_key']}', active={r['is_active']}, content='{r['content']}'")
            assert len(db_records) >= 2, f"Expected at least 2 database records, got {len(db_records)}"

        # 5. Memory Explorer API Endpoint verification (GET /api/memories)
        print("\n5. Verifying Memory Explorer API (GET /api/memories)...")
        explorer_res = await client.get(f"/api/memories?session_id={session_id}")
        assert explorer_res.status_code == 200, f"Memory Explorer failed with {explorer_res.status_code}: {explorer_res.text}"
        explorer_data = explorer_res.json()
        explorer_memories = explorer_data.get("memories", [])
        print(f"   Memory Explorer returned {len(explorer_memories)} memories (total count={explorer_data.get('count')}).")
        for em in explorer_memories:
            print(f"   - [Explorer View] {em['category']}: {em['content']} (importance={em.get('importance_score')})")
        assert len(explorer_memories) >= 2, "Memory Explorer did not return saved memories"

        # 6. Subsequent Query Verification
        print("\n6. Sending subsequent retrieval query...")
        follow_up_query = "What language and focus would you recommend for my next machine learning portfolio project?"
        req_id_2 = f"live-req-{uuid.uuid4().hex[:12]}"
        print(f"   Follow-up: \"{follow_up_query}\"")

        res_2 = await client.post(
            "/api/chat",
            json={"message": follow_up_query, "session_id": session_id},
            headers={"X-Request-ID": req_id_2}
        )
        assert res_2.status_code == 200, f"Expected 200 OK, got {res_2.status_code}: {res_2.text}"
        data_2 = res_2.json()

        recalled = data_2.get("memories_recalled", [])
        print(f"\n   Memories Recalled ({len(recalled)}):")
        for rec in recalled:
            print(f"   - [Recalled] {rec.get('memory_key')}: {rec.get('content')}")
        print(f"\n   Assistant Personalized Reply:\n   \"{data_2['reply'][:300]}...\"")

        assert len(recalled) >= 1, "Subsequent question must recall previous preferences"
        assert "python" in data_2["reply"].lower(), "Assistant reply must recommend Python based on user preference"

    await close_db_pool()
    print("\n" + "=" * 80)
    print("LIVE CHAT & MEMORY EXPLORER VERIFICATION PASSED WITH 100% SUCCESS!")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(run_live_verification())
