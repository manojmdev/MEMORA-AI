"""
MEMORA AI — DAY 7.2 PRODUCTION HARDENING & INTEGRITY TEST SUITE
Validates:
1. Genuine authentication, signed bearer tokens & preshared token registry.
2. Endpoint-level API session ownership enforcement and production lockout.
3. Unique worker identity derivation and renewable task execution heartbeats.
4. Safe interrupted task recovery with active lease preservation.
5. Strict append-only audit table immutability (zero session ID backdoor).
6. Human-in-the-loop approval transitions and atomicity.
"""
import asyncio
import os
import secrets
import uuid
import httpx
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException

from app.config import settings
from app.database import (
    init_db_pool,
    close_db_pool,
    get_db_pool,
    recover_interrupted_tasks
)
from app.auth.session_guard import (
    UserPrincipal,
    create_signed_token,
    verify_token_credential,
    verify_session_ownership,
    validate_session_format,
    validate_session_id,
    get_current_principal
)
from app.agent.worker_identity import WorkerIdentity
from app.agent.models import TaskStatus, ApprovalStatus
from app.agent.approval_manager import (
    create_approval_request,
    bind_approval_to_task,
    validate_and_consume_approval,
    reject_approval
)
from app.agent.orchestrator import agent_orchestrator
from app.services import note_service
from app.main import app

async def run_day7_2_tests():
    print("=" * 80)
    print("MEMORA AI — DAY 7.2 MASTER HARDENING & INTEGRITY TEST SUITE")
    print("=" * 80)

    pool = await init_db_pool()
    assert pool is not None, "Database pool failed to initialize"

    test_session = f"test-72-{uuid.uuid4().hex[:8]}"
    print(f"[*] Initialized Day 7.2 test session: {test_session}")

    # =========================================================================
    # TEST 1: Genuine Authentication Verification & Signed Tokens
    # =========================================================================
    print("\n--- [TEST 1] Genuine Authentication Verification & Signed Tokens ---")
    test_secret = "test-hmac-secret-key-32-chars-long"
    orig_secret = settings.AUTH_SECRET_KEY
    orig_tokens = settings.API_AUTH_TOKENS
    orig_env = settings.ENVIRONMENT

    try:
        settings.AUTH_SECRET_KEY = test_secret
        uid = "user-alpha-99"
        sid = "session-alpha-99"
        valid_token = create_signed_token(uid, sid, test_secret, scopes=["memora:read", "memora:write"])

        # 1. Valid signature verifies successfully
        principal = verify_token_credential(valid_token)
        assert principal is not None, "Valid signed token must verify successfully"
        assert principal.is_authenticated is True
        assert principal.id == uid
        assert principal.session_id == sid
        assert "memora:read" in principal.scopes
        print("  [PASS] Cryptographically signed HMAC-SHA256 token verified.")

        # 2. Tampered token payload is strictly rejected
        tampered_token = valid_token[:-4] + "ffff"
        assert verify_token_credential(tampered_token) is None, "Tampered token must be rejected"
        print("  [PASS] Tampered token signature rejected.")

        # 3. Token expiration verification
        expiring_token = create_signed_token(uid, sid, test_secret, expires_in_seconds=-5)
        assert verify_token_credential(expiring_token) is None, "Expired token must be rejected"
        print("  [PASS] Expired token signature rejected cleanly.")

        # 4. Token revocation verification
        from app.auth.session_guard import revoke_token, clear_revocation_cache
        revocable_token = create_signed_token(uid, sid, test_secret)
        assert verify_token_credential(revocable_token) is not None
        revoke_token(revocable_token)
        assert verify_token_credential(revocable_token) is None, "Revoked token must be rejected"
        clear_revocation_cache()
        print("  [PASS] Token revocation registry verified; revoked token rejected.")

        # 5. Secret rotation verification
        old_secret = "old-secret-key-that-was-rotated"
        new_secret = "new-active-secret-key-in-service"
        # Token generated under old secret
        rotated_old_token = create_signed_token(uid, sid, old_secret)
        # Server configured with rotation list: "new_secret,old_secret"
        settings.AUTH_SECRET_KEY = f"{new_secret},{old_secret}"
        # Both old and new verify successfully
        assert verify_token_credential(rotated_old_token) is not None, "Old secret token must verify during rotation grace period"
        rotated_new_token = create_signed_token(uid, sid, new_secret)
        assert verify_token_credential(rotated_new_token) is not None, "New secret token must verify"
        # Unknown third secret fails
        untrusted_token = create_signed_token(uid, sid, "untrusted-attacker-key")
        assert verify_token_credential(untrusted_token) is None, "Untrusted secret must be rejected"
        settings.AUTH_SECRET_KEY = test_secret
        print("  [PASS] Zero-downtime secret rotation verified with multi-key support.")

        # 6. Pre-shared API token registry verification
        settings.API_AUTH_TOKENS = "tok_sec_123:reg-user:reg-session,tok_sec_456:reg-user2:reg-session2"
        preshared_p = verify_token_credential("tok_sec_123")
        assert preshared_p is not None, "Registered pre-shared token must verify"
        assert preshared_p.is_authenticated is True
        assert preshared_p.id == "reg-user"
        assert preshared_p.session_id == "reg-session"
        print("  [PASS] Pre-shared API token registry matched and verified.")

        # 7. Arbitrary unverified token in production MUST NOT be trusted
        settings.ENVIRONMENT = "production"
        unverified_token = "arbitrary-unverified-bearer-string"
        assert verify_token_credential(unverified_token) is None

        # Verify get_current_principal rejects unverified token in production with 401
        try:
            await get_current_principal(
                request=None,
                authorization=f"Bearer {unverified_token}",
                x_session_id=None,
                session_id=None
            )
            assert False, "Production must refuse unverified bearer token with 401"
        except HTTPException as e:
            assert e.status_code == 401
            assert "unverified" in e.detail.lower() or "invalid" in e.detail.lower()
        print("  [PASS] Production strictly rejects unverified tokens with 401; zero credential inventing.")

    finally:
        settings.AUTH_SECRET_KEY = orig_secret
        settings.API_AUTH_TOKENS = orig_tokens
        settings.ENVIRONMENT = orig_env

    # =========================================================================
    # TEST 2: Endpoint API Ownership Enforcement via FastAPI TestClient
    # =========================================================================
    print("\n--- [TEST 2] Endpoint API Ownership Enforcement ---")
    transport = httpx.ASGITransport(app=app)
    orig_env = settings.ENVIRONMENT
    orig_secret = settings.AUTH_SECRET_KEY

    try:
        settings.ENVIRONMENT = "production"
        settings.AUTH_SECRET_KEY = "prod-test-key-for-ownership-gating"

        owner_uid = "owner-corp-1"
        owner_sid = "corp-session-alpha"
        foreign_sid = "corp-session-beta"
        owner_token = create_signed_token(owner_uid, owner_sid, settings.AUTH_SECRET_KEY)

        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Unauthenticated request to protected endpoint in production -> 401
            r_unauth = await client.get("/api/notes", params={"session_id": owner_sid})
            assert r_unauth.status_code == 401, f"Expected 401, got {r_unauth.status_code}"
            print("  [PASS] Unauthenticated request to /api/notes blocked with 401 in production.")

            # 2. Authenticated request matching owner session -> 200
            auth_headers = {"Authorization": f"Bearer {owner_token}"}
            r_auth = await client.get("/api/notes", params={"session_id": owner_sid}, headers=auth_headers)
            assert r_auth.status_code == 200, f"Expected 200, got {r_auth.status_code}"
            print("  [PASS] Authenticated request to own session succeeded (200).")

            # 3. Ownership violation: Caller authenticated for session-alpha attempts to access session-beta -> 403
            r_violation = await client.get("/api/notes", params={"session_id": foreign_sid}, headers=auth_headers)
            assert r_violation.status_code == 403, f"Expected 403, got {r_violation.status_code}"
            assert "ownership violation" in r_violation.text.lower()
            print("  [PASS] Cross-tenant session access blocked with 403 Forbidden.")

            # 4. Prohibit default-session in production even with bearer header -> 403
            r_def = await client.get("/api/notes", params={"session_id": "default-session"}, headers=auth_headers)
            assert r_def.status_code == 403
            print("  [PASS] Default session access strictly blocked in production.")

    finally:
        settings.ENVIRONMENT = orig_env
        settings.AUTH_SECRET_KEY = orig_secret

    # =========================================================================
    # TEST 3: Unique Worker Identity & Renewable Heartbeats
    # =========================================================================
    print("\n--- [TEST 3] Unique Worker Identity & Renewable Heartbeats ---")
    worker_1 = WorkerIdentity.get_worker_id()
    assert worker_1.startswith("memora-worker-")
    assert len(worker_1) > 20

    # Verify worker ID consistency across calls within the same process
    assert WorkerIdentity.get_worker_id() == worker_1
    print(f"  [PASS] Worker identity verified: {worker_1}")

    # Create a test running task in database
    task_id_hb = uuid.uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agent_tasks (
                id, session_id, user_request, status, worker_id, last_heartbeat_at, execution_lease_expires_at
            )
            VALUES ($1, $2, 'Heartbeat test task', 'running', $3, NOW(), NOW() + INTERVAL '1 minute')
            """,
            task_id_hb,
            test_session,
            worker_1
        )

    # Initial lease timestamp
    async with pool.acquire() as conn:
        t_row1 = await conn.fetchrow("SELECT last_heartbeat_at, execution_lease_expires_at FROM agent_tasks WHERE id = $1", task_id_hb)
    t1_lease = t_row1["execution_lease_expires_at"]

    # Sleep briefly to ensure clock advances
    await asyncio.sleep(0.05)

    # Renew heartbeat
    renewed = await agent_orchestrator.renew_heartbeat(task_id_hb, test_session, lease_minutes=10)
    assert renewed is True, "Heartbeat renewal must succeed on active running task"

    async with pool.acquire() as conn:
        t_row2 = await conn.fetchrow("SELECT last_heartbeat_at, execution_lease_expires_at FROM agent_tasks WHERE id = $1", task_id_hb)
    t2_lease = t_row2["execution_lease_expires_at"]

    assert t2_lease > t1_lease, f"Expected lease extension: {t2_lease} > {t1_lease}"
    print("  [PASS] Active task heartbeat renewed and execution lease extended.")

    # Renewal on wrong session or non-running status must fail
    fake_session_renew = await agent_orchestrator.renew_heartbeat(task_id_hb, "wrong-session")
    assert fake_session_renew is False
    print("  [PASS] Heartbeat renewal denied for mismatched session.")

    # =========================================================================
    # TEST 4: Safe Interrupted Task Recovery with Active Lease Protection
    # =========================================================================
    print("\n--- [TEST 4] Safe Interrupted Task Recovery with Active Lease Protection ---")
    active_task_id = uuid.uuid4()
    stale_task_id = uuid.uuid4()

    async with pool.acquire() as conn:
        # 1. Active task with lease expiring 10 minutes in the future
        await conn.execute(
            """
            INSERT INTO agent_tasks (id, session_id, user_request, status, worker_id, execution_lease_expires_at)
            VALUES ($1, $2, 'Active job with lease', 'running', $3, NOW() + INTERVAL '10 minutes')
            """,
            active_task_id,
            test_session,
            worker_1
        )
        # 2. Stale task whose lease expired 5 minutes ago
        await conn.execute(
            """
            INSERT INTO agent_tasks (id, session_id, user_request, status, worker_id, execution_lease_expires_at)
            VALUES ($1, $2, 'Dead worker job', 'running', 'defunct-worker-dead', NOW() - INTERVAL '5 minutes')
            """,
            stale_task_id,
            test_session
        )

    # Run recovery sweep
    recovered_count = await recover_interrupted_tasks(stale_threshold_minutes=5)
    assert recovered_count >= 1, f"Expected at least 1 recovered task, got {recovered_count}"

    async with pool.acquire() as conn:
        active_status = await conn.fetchval("SELECT status FROM agent_tasks WHERE id = $1", active_task_id)
        stale_status = await conn.fetchval("SELECT status FROM agent_tasks WHERE id = $1", stale_task_id)
        stale_lease = await conn.fetchval("SELECT execution_lease_expires_at FROM agent_tasks WHERE id = $1", stale_task_id)

    assert active_status == "running", f"Active task with valid lease must remain RUNNING, got: {active_status}"
    assert stale_status == "failed", f"Stale task with expired lease must transition to FAILED, got: {stale_status}"
    assert stale_lease is None, "Failed task lease must be cleared to NULL"
    print("  [PASS] Stale task recovered; active task with valid lease was safely preserved as RUNNING.")

    # =========================================================================
    # TEST 5: Strict Append-Only Audit Table Protection (Zero Session Backdoor)
    # =========================================================================
    print("\n--- [TEST 5] Strict Append-Only Audit Table Protection ---")
    audit_task_id = uuid.uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agent_tasks (id, session_id, user_request, status)
            VALUES ($1, $2, 'Audit test task', 'succeeded')
            """,
            audit_task_id,
            test_session
        )
        await conn.execute(
            """
            INSERT INTO agent_execution_logs (task_id, session_id, tool_name, status, result_summary)
            VALUES ($1, $2, 'test_tool', 'succeeded', 'Day 7.2 audit record')
            """,
            audit_task_id,
            test_session
        )

        log_id = await conn.fetchval("SELECT id FROM agent_execution_logs WHERE task_id = $1 LIMIT 1", audit_task_id)
        assert log_id is not None

        # 1. Direct UPDATE must be blocked
        try:
            await conn.execute("UPDATE agent_execution_logs SET result_summary = 'tampered' WHERE id = $1", log_id)
            assert False, "UPDATE on agent_execution_logs must be rejected"
        except Exception as e:
            assert "append-only" in str(e).lower() or "forbidden" in str(e).lower()
        print("  [PASS] Database trigger blocked unauthorized UPDATE on audit logs.")

        # 2. Direct DELETE on test-prefixed session must ALSO be blocked (no backdoor!)
        try:
            await conn.execute("DELETE FROM agent_execution_logs WHERE session_id = $1", test_session)
            assert False, "DELETE on test-prefixed session must be rejected"
        except Exception as e:
            assert "append-only" in str(e).lower() or "forbidden" in str(e).lower()
        print("  [PASS] Zero-backdoor trigger blocked direct DELETE on test-prefixed session.")

        # 3. Direct DELETE on arbitrary named session must be blocked
        try:
            await conn.execute("DELETE FROM agent_execution_logs WHERE id = $1", log_id)
            assert False, "Direct DELETE by ID must be rejected"
        except Exception as e:
            assert "append-only" in str(e).lower() or "forbidden" in str(e).lower()
        print("  [PASS] Database trigger blocked direct DELETE by ID.")

        # 4. Task deletion cannot cascade-delete audit history
        try:
            await conn.execute("DELETE FROM agent_tasks WHERE id = $1", audit_task_id)
            assert False, "Task DELETE must not cascade-delete audit history"
        except Exception as e:
            assert "append-only" in str(e).lower() or "forbidden" in str(e).lower()
        log_still_exists = await conn.fetchval("SELECT count(*) FROM agent_execution_logs WHERE id = $1", log_id)
        assert log_still_exists == 1, "Audit log must remain intact"
        print("  [PASS] Task deletion blocked from cascade-deleting audit history.")

        # 5. Clean up authorized test fixtures using explicit transaction session setting
        async with conn.transaction():
            await conn.execute("SET LOCAL memora.allow_audit_cleanup = 'on'")
            await conn.execute("DELETE FROM agent_execution_logs WHERE session_id = $1", test_session)
            await conn.execute("DELETE FROM agent_tasks WHERE session_id = $1", test_session)

    print("  [PASS] Strict append-only audit enforcement verified; authorized admin cleanup functional.")

    # =========================================================================
    # TEST 6: Approval State Machine & Resumption Reliability
    # =========================================================================
    print("\n--- [TEST 6] Approval State Machine & Resumption Reliability ---")
    task_id_sm = uuid.uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agent_tasks (id, session_id, user_request, status, approval_status, approval_expires_at)
            VALUES ($1, $2, 'State machine test', $3, $4, NOW() + INTERVAL '10 minutes')
            """,
            task_id_sm,
            test_session,
            TaskStatus.AWAITING_APPROVAL.value,
            ApprovalStatus.PENDING.value
        )

    # Rejection of awaiting task transitions to CANCELLED
    rej_ok, rej_err = await reject_approval(task_id_sm, test_session)
    assert rej_ok is True
    async with pool.acquire() as conn:
        sm_status = await conn.fetchval("SELECT status FROM agent_tasks WHERE id = $1", task_id_sm)
    assert sm_status == TaskStatus.CANCELLED.value

    # Rejection of already-cancelled task is denied
    rej_again_ok, _ = await reject_approval(task_id_sm, test_session)
    assert rej_again_ok is False
    print("  [PASS] Approval state transitions enforce valid initial states.")

    # Duplicate execution prevention: concurrent approval consumption
    task_id_race = uuid.uuid4()
    approval_req = create_approval_request(
        task_id=task_id_race,
        step_id="step_race_01",
        tool_name="create_note",
        arguments={"title": "race test"}
    )
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agent_tasks (id, session_id, user_request, status)
            VALUES ($1, $2, 'Race task test', 'pending')
            """,
            task_id_race,
            test_session
        )
    await bind_approval_to_task(task_id_race, test_session, approval_req)

    # Attempt concurrent execution of the same approval token
    concurrent_results = await asyncio.gather(
        validate_and_consume_approval(task_id_race, test_session, approval_req.approval_token),
        validate_and_consume_approval(task_id_race, test_session, approval_req.approval_token),
        validate_and_consume_approval(task_id_race, test_session, approval_req.approval_token)
    )
    successes = [res[0] for res in concurrent_results if res[0] is True]
    assert len(successes) == 1, f"Expected exactly 1 successful consumption, got {len(successes)}"
    print("  [PASS] Duplicate execution prevented: exactly 1 concurrent consumer acquired approval.")

    # Clean up any leftover tasks
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL memora.allow_audit_cleanup = 'on'")
            await conn.execute("DELETE FROM agent_execution_logs WHERE session_id = $1", test_session)
            await conn.execute("DELETE FROM agent_tasks WHERE session_id = $1", test_session)

    await close_db_pool()

    print("\n" + "=" * 80)
    print("ALL 6 DAY 7.2 MASTER HARDENING & INTEGRITY TEST SCENARIOS PASSED (100%)!")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(run_day7_2_tests())
