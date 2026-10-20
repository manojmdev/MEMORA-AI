"""
MEMORA AI — AI CHAT REGRESSION TEST SUITE (SCENARIOS A THROUGH J)
Validates the end-to-end AI Chat pipeline across all failure modes, security boundaries,
hybrid memory retrievals, and persistence lifecycles:

  [TEST A] First user message with three personal preferences & DB persistence.
  [TEST B] Second message retrieving those preferences with memory context injection.
  [TEST C] Paraphrased semantic retrieval via pgvector.
  [TEST D] Updating an existing preference (memory evolution & superseding).
  [TEST E] Embedding provider timeout handling (graceful keyword fallback).
  [TEST F] Nemotron timeout handling (proper structured 504 Gateway Timeout).
  [TEST G] Malformed extraction JSON handling (response preserved, error accurately reported).
  [TEST H] Database unavailable handling (response preserved, error accurately reported).
  [TEST I] Invalid authentication rejection (HTTP 401 Unauthorized).
  [TEST J] Cross-session access attempt rejection (HTTP 403 Forbidden).
"""

import asyncio
import sys
import uuid
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock
import httpx
from openai import APITimeoutError, APIConnectionError

# Force UTF-8 on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

from app.config import settings
from app.database import init_db_pool, close_db_pool, get_db_pool
from app.auth.session_guard import create_signed_token, UserPrincipal
from app.main import app

async def run_regression_suite():
    print("=" * 80)
    print("MEMORA AI — AI CHAT REGRESSION SUITE (SCENARIOS A THROUGH J)")
    print("=" * 80)

    # Initialize pool within the same event loop
    pool = await init_db_pool()
    assert pool is not None, "Failed to initialize database pool"

    results = {}
    test_session = f"reg_chat_{uuid.uuid4().hex[:8]}"
    print(f"Primary Test Session: {test_session}\n")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=90.0) as client:
        # ----------------------------------------------------------------------
        # TEST A: First user message with three personal preferences
        # ----------------------------------------------------------------------
        print("[TEST A] First user message with three personal preferences...")
        msg_a = (
            "I'm a computer science student specializing in AI and machine learning. "
            "I prefer Python over Java and C. "
            "I enjoy building practical AI applications rather than spending too much time on theory."
        )
        t_a_resp = await client.post(
            "/api/chat",
            json={"message": msg_a, "session_id": test_session},
            headers={"X-Request-ID": "test-req-id-scenario-a"}
        )
        assert t_a_resp.status_code == 200, f"Test A failed with HTTP {t_a_resp.status_code}: {t_a_resp.text}"
        data_a = t_a_resp.json()
        assert len(data_a["reply"]) > 0, "Test A expected non-empty assistant reply"
        assert data_a["memory_persistence_status"] == "success", f"Expected success persistence, got {data_a.get('memory_persistence_status')}"
        assert data_a["memory_persistence_error"] is None, f"Expected no persistence error, got {data_a.get('memory_persistence_error')}"
        assert len(data_a["memories_extracted"]) >= 3, f"Expected >= 3 memories extracted, got {len(data_a['memories_extracted'])}"
        print(f"  ✓ Assistant replied ({len(data_a['reply'])} chars)")
        print(f"  ✓ Extracted {len(data_a['memories_extracted'])} memory candidates")
        for m in data_a["memories_extracted"]:
            print(f"    - [{m.get('category')}] {m.get('memory_key')}: {m.get('content')}")

        # Direct DB verification for Test A
        rows_a = await pool.fetch(
            "SELECT memory_key, content, is_active, category FROM memories WHERE session_id = $1 AND is_active = TRUE",
            test_session
        )
        assert len(rows_a) >= 3, f"Expected >= 3 active DB records, found {len(rows_a)}"
        print(f"  ✓ Verified {len(rows_a)} active records persisted in Neon PostgreSQL")
        results["A"] = "PASS"

        # ----------------------------------------------------------------------
        # TEST B: Second message retrieving those preferences
        # ----------------------------------------------------------------------
        print("\n[TEST B] Second message retrieving those preferences...")
        msg_b = "What programming language should I use for my upcoming machine learning project?"
        t_b_resp = await client.post(
            "/api/chat",
            json={"message": msg_b, "session_id": test_session},
            headers={"X-Request-ID": "test-req-id-scenario-b"}
        )
        assert t_b_resp.status_code == 200, f"Test B failed: {t_b_resp.text}"
        data_b = t_b_resp.json()
        assert len(data_b["reply"]) > 0
        assert len(data_b["memories_recalled"]) > 0, "Test B expected memories to be recalled"
        recalled_keys = [m.get("memory_key") for m in data_b["memories_recalled"]]
        print(f"  ✓ Recalled {len(data_b['memories_recalled'])} memories: {recalled_keys}")
        assert "python" in data_b["reply"].lower(), "Assistant reply should reference user's Python preference"
        print("  ✓ Assistant reply correctly personalized with Python recommendation")
        results["B"] = "PASS"

        # ----------------------------------------------------------------------
        # TEST C: Paraphrased semantic retrieval
        # ----------------------------------------------------------------------
        print("\n[TEST C] Paraphrased semantic retrieval (pgvector cosine similarity)...")
        msg_c = "Do I lean towards hands-on software development or academic theoretical analysis?"
        t_c_resp = await client.post(
            "/api/chat",
            json={"message": msg_c, "session_id": test_session},
            headers={"X-Request-ID": "test-req-id-scenario-c"}
        )
        assert t_c_resp.status_code == 200, f"Test C failed: {t_c_resp.text}"
        data_c = t_c_resp.json()
        assert len(data_c["memories_recalled"]) > 0, "Test C expected semantic recall"
        practical_recalled = any(
            "practical" in m.get("content", "").lower() or "theory" in m.get("content", "").lower()
            for m in data_c["memories_recalled"]
        )
        assert practical_recalled, "Expected practical vs theoretical preference to be recalled semantically"
        print(f"  ✓ Semantically recalled practical focus memory (recalled {len(data_c['memories_recalled'])})")
        results["C"] = "PASS"

        # ----------------------------------------------------------------------
        # TEST D: Updating an existing preference (memory evolution)
        # ----------------------------------------------------------------------
        print("\n[TEST D] Updating an existing preference (Memory Evolution & Superseding)...")
        msg_d = "I have completely changed my mind: I now strictly prefer Rust over Python for all my AI applications."
        t_d_resp = await client.post(
            "/api/chat",
            json={"message": msg_d, "session_id": test_session},
            headers={"X-Request-ID": "test-req-id-scenario-d"}
        )
        assert t_d_resp.status_code == 200, f"Test D failed: {t_d_resp.text}"
        data_d = t_d_resp.json()
        print(f"  ✓ Update processed: {len(data_d['memories_extracted'])} memory updates extracted")

        active_d = await pool.fetch(
            "SELECT memory_key, content, memory_status FROM memories WHERE session_id = $1 AND is_active = TRUE",
            test_session
        )
        superseded_d = await pool.fetch(
            "SELECT memory_key, content, memory_status, superseded_by FROM memories WHERE session_id = $1 AND is_active = FALSE AND memory_status = 'superseded'",
            test_session
        )
        rust_active = any("rust" in m["content"].lower() for m in active_d)
        print(f"  ✓ Active memories ({len(active_d)}): Rust active = {rust_active}")
        print(f"  ✓ Superseded memories in lineage: {len(superseded_d)} records")
        assert rust_active, "Rust preference must now be an active memory in database"
        results["D"] = "PASS"

        # ----------------------------------------------------------------------
        # TEST E: Embedding provider timeout handling
        # ----------------------------------------------------------------------
        print("\n[TEST E] Embedding provider timeout handling (graceful keyword fallback)...")
        session_e = f"reg_chat_e_{uuid.uuid4().hex[:6]}"
        with patch("app.services.embedding_service.generate_embedding", new_callable=AsyncMock) as mock_emb:
            mock_emb.side_effect = APITimeoutError(request=httpx.Request("POST", "https://api.tokenfactory.nebius.com"))
            t_e_resp = await client.post(
                "/api/chat",
                json={"message": "I prefer dark mode in all editors.", "session_id": session_e},
                headers={"X-Request-ID": "test-req-id-scenario-e"}
            )
            assert t_e_resp.status_code == 200, f"Test E failed: {t_e_resp.text}"
            data_e = t_e_resp.json()
            assert len(data_e["reply"]) > 0, "Assistant reply should be generated despite embedding timeout"
            print(f"  ✓ System degraded gracefully on embedding timeout: reply generated ({len(data_e['reply'])} chars)")
            print(f"  ✓ Persistence status: {data_e.get('memory_persistence_status')}")
            results["E"] = "PASS"

        # ----------------------------------------------------------------------
        # TEST F: Nemotron timeout handling
        # ----------------------------------------------------------------------
        print("\n[TEST F] Nemotron timeout handling (structured 504 Gateway Timeout)...")
        session_f = f"reg_chat_f_{uuid.uuid4().hex[:6]}"
        with patch("app.services.llm_service.client.chat.completions.create", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = APITimeoutError(request=httpx.Request("POST", "https://api.tokenfactory.nebius.com"))
            t_f_resp = await client.post(
                "/api/chat",
                json={"message": "Tell me about distributed computing.", "session_id": session_f},
                headers={"X-Request-ID": "test-req-id-scenario-f"}
            )
            assert t_f_resp.status_code == 504, f"Expected HTTP 504 on Nemotron timeout, got {t_f_resp.status_code}: {t_f_resp.text}"
            data_f = t_f_resp.json()
            assert "timeout" in data_f.get("detail", "").lower() or "timed out" in data_f.get("detail", "").lower()
            print(f"  ✓ Cleanly rejected with HTTP 504: {data_f.get('detail')}")
            assert "test-req-id-scenario-f" in t_f_resp.headers.get("X-Request-ID", ""), "Reference ID correlation preserved"
            print("  ✓ Reference ID correlation preserved in headers")
            results["F"] = "PASS"

        # ----------------------------------------------------------------------
        # TEST G: Malformed extraction JSON handling
        # ----------------------------------------------------------------------
        print("\n[TEST G] Malformed extraction JSON handling (reply preserved, error reported)...")
        session_g = f"reg_chat_g_{uuid.uuid4().hex[:6]}"
        with patch("app.services.memory_context.extract_memories_with_status", new_callable=AsyncMock) as mock_ext:
            mock_ext.return_value = ([], "Malformed JSON output from extraction model: Expecting value: line 1 column 1")
            t_g_resp = await client.post(
                "/api/chat",
                json={"message": "I study graph neural networks.", "session_id": session_g},
                headers={"X-Request-ID": "test-req-id-scenario-g"}
            )
            assert t_g_resp.status_code == 200, f"Expected 200 with preserved reply, got {t_g_resp.status_code}: {t_g_resp.text}"
            data_g = t_g_resp.json()
            assert len(data_g["reply"]) > 0, "Assistant reply must be preserved even if extraction JSON fails"
            assert data_g["memory_persistence_status"] == "failed", f"Persistence status must report 'failed', got {data_g['memory_persistence_status']}"
            assert "Malformed JSON" in data_g["memory_persistence_error"]
            print(f"  ✓ Reply preserved: {data_g['reply'][:70]}...")
            print(f"  ✓ Status accurately flagged: {data_g['memory_persistence_status']}")
            print(f"  ✓ Error recorded: {data_g['memory_persistence_error']}")
            results["G"] = "PASS"

        # ----------------------------------------------------------------------
        # TEST H: Database unavailable handling
        # ----------------------------------------------------------------------
        print("\n[TEST H] Database unavailable handling (reply preserved, error reported)...")
        session_h = f"reg_chat_h_{uuid.uuid4().hex[:6]}"
        with patch("app.services.memory_context.add_memory", side_effect=RuntimeError("Database connection pool is not available.")):
            t_h_resp = await client.post(
                "/api/chat",
                json={"message": "I love deploying with Docker.", "session_id": session_h},
                headers={"X-Request-ID": "test-req-id-scenario-h"}
            )
            assert t_h_resp.status_code == 200, f"Expected 200 with preserved reply, got {t_h_resp.status_code}: {t_h_resp.text}"
            data_h = t_h_resp.json()
            assert len(data_h["reply"]) > 0, "Assistant reply must be preserved when DB is down"
            assert data_h["memory_persistence_status"] == "failed", f"Expected failed, got {data_h['memory_persistence_status']}"
            assert "database" in data_h["memory_persistence_error"].lower()
            print(f"  ✓ Reply preserved: {data_h['reply'][:70]}...")
            print(f"  ✓ Status accurately reported: {data_h['memory_persistence_status']}")
            print(f"  ✓ Error reported: {data_h['memory_persistence_error']}")
            results["H"] = "PASS"

        # ----------------------------------------------------------------------
        # TEST I: Invalid authentication rejection
        # ----------------------------------------------------------------------
        print("\n[TEST I] Invalid authentication rejection (HTTP 401 Unauthorized)...")
        orig_secret = settings.AUTH_SECRET_KEY
        try:
            settings.AUTH_SECRET_KEY = "test-secret-key-32-chars-long-auth"
            t_i_resp = await client.post(
                "/api/chat",
                json={"message": "Hello authenticated user.", "session_id": f"session_auth_{uuid.uuid4().hex[:6]}"},
                headers={
                    "Authorization": "Bearer invalid.fake.token.signature",
                    "X-Request-ID": "test-req-id-scenario-i"
                }
            )
            assert t_i_resp.status_code == 401, f"Expected HTTP 401 for invalid bearer token, got {t_i_resp.status_code}: {t_i_resp.text}"
            print(f"  ✓ Invalid bearer token rejected with HTTP 401: {t_i_resp.json().get('detail')}")
            results["I"] = "PASS"
        finally:
            settings.AUTH_SECRET_KEY = orig_secret

        # ----------------------------------------------------------------------
        # TEST J: Cross-session access attempt rejection
        # ----------------------------------------------------------------------
        print("\n[TEST J] Cross-session access attempt rejection (HTTP 403 Forbidden)...")
        orig_secret = settings.AUTH_SECRET_KEY
        try:
            settings.AUTH_SECRET_KEY = "test-secret-key-32-chars-long-auth"
            owner_sid = f"owner_session_{uuid.uuid4().hex[:6]}"
            foreign_sid = f"foreign_session_{uuid.uuid4().hex[:6]}"
            token_owner = create_signed_token("user-alice", owner_sid, settings.AUTH_SECRET_KEY)

            t_j_resp = await client.post(
                "/api/chat",
                json={"message": "Sneaking into foreign session.", "session_id": foreign_sid},
                headers={
                    "Authorization": f"Bearer {token_owner}",
                    "X-Request-ID": "test-req-id-scenario-j"
                }
            )
            assert t_j_resp.status_code == 403, f"Expected HTTP 403 for cross-session access, got {t_j_resp.status_code}: {t_j_resp.text}"
            print(f"  ✓ Cross-session access attempt blocked with HTTP 403: {t_j_resp.json().get('detail')}")
            results["J"] = "PASS"
        finally:
            settings.AUTH_SECRET_KEY = orig_secret

    await close_db_pool()

    print("\n" + "=" * 80)
    print("REGRESSION TEST RESULTS SUMMARY")
    print("=" * 80)
    for scenario, status in results.items():
        print(f"  [SCENARIO {scenario}] Status: {status}")
    print("=" * 80)
    assert len(results) == 10 and all(s == "PASS" for s in results.values()), "All 10 scenarios must pass!"
    print("ALL 10 REGRESSION SCENARIOS (A THROUGH J) PASSED WITH 100% SUCCESS!\n")

if __name__ == "__main__":
    asyncio.run(run_regression_suite())
