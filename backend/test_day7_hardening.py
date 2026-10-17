"""
MEMORA AI — DAY 7 PRODUCTION HARDENING & EXECUTION INTEGRITY TEST SUITE
Covers Scenarios 1 through 10:
  [TEST 1] Atomic Approval Consumption & Race Condition Defense (asyncio.gather)
  [TEST 2] Approval Token Hashing in Database (SHA-256 hex digest, plaintext NULL)
  [TEST 3] Approval Token Expiration & Tamper / Replay Rejection
  [TEST 4] Task History Approval Token Redaction (API & Orchestrator level)
  [TEST 5] Strict Session Identifier Validation & Production Environment Refusal
  [TEST 6] Correlation ID Middleware & Sanitized Public Errors / Health Endpoints
  [TEST 7] Evaluation Endpoint Production Gating (403 Forbidden enforcement)
  [TEST 8] Interrupted Task Startup Recovery Sweep (stale running task recovery)
  [TEST 9] Calculator Resource Safety, AST Depth, Node Count & Numerical Limits
  [TEST 10] Concurrent Note Creation Database-Level Idempotency (Unique Index)
"""
import asyncio
from datetime import datetime, timezone, timedelta
import hashlib
import sys
import uuid
from typing import List

# Ensure Windows console handles utf-8 characters smoothly
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from app.database import init_db_pool, close_db_pool, get_db_pool, recover_interrupted_tasks, check_db_health
from app.config import settings
from app.agent.models import (
    TaskStatus,
    StepStatus,
    ToolPermission,
    ApprovalStatus,
    AgentPlan,
    AgentPlanStep,
    ApprovalRequest,
)
from app.agent.approval_manager import (
    generate_approval_token,
    hash_token,
    create_approval_request,
    bind_approval_to_task,
    validate_and_consume_approval,
    reject_approval,
)
from app.agent.orchestrator import agent_orchestrator
from app.agent.tools.calculator import CalculatorTool
from app.services import note_service
from app.auth.session_guard import (
    validate_session_id,
    validate_session_format,
    verify_session_ownership,
    UserPrincipal
)
from app.main import app
import httpx
from fastapi import HTTPException

async def run_day7_hardening_tests():
    print("=" * 80)
    print("MEMORA AI — DAY 7 PRODUCTION HARDENING & EXECUTION INTEGRITY TEST SUITE")
    print("=" * 80)

    pool = await init_db_pool()
    assert pool is not None, "Database pool failed to initialize"

    test_session = f"test-harden-{uuid.uuid4().hex[:8]}"
    print(f"[*] Initialized test session: {test_session}")

    # Clean up any potential artifacts for this test session
    await note_service.delete_all_notes(test_session)

    # =========================================================================
    # TEST 1: Atomic Approval Consumption & Concurrency Defense (asyncio.gather)
    # =========================================================================
    print("\n--- [TEST 1] Atomic Approval Consumption & Race Condition Defense ---")
    task_id_1 = uuid.uuid4()
    plan_1 = AgentPlan(
        title="Test Plan",
        objective="Test concurrent approval",
        steps=[AgentPlanStep(step_id="step_1", description="Create test note", tool_name="create_note", arguments={"title": "T1", "content": "C1"})]
    )

    # Insert task into agent_tasks
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agent_tasks (id, session_id, user_request, status, plan_json)
            VALUES ($1, $2, 'Test concurrency', $3, $4::jsonb)
            """,
            task_id_1,
            test_session,
            TaskStatus.PROPOSED.value,
            plan_1.model_dump_json(),
        )

    approval_req_1 = create_approval_request(
        task_id=task_id_1,
        step_id="step_1",
        tool_name="create_note",
        arguments={"title": "T1", "content": "C1"}
    )
    raw_token_1 = approval_req_1.approval_token
    await bind_approval_to_task(task_id_1, test_session, approval_req_1)

    # Concurrently attempt to consume the same approval token
    results = await asyncio.gather(
        validate_and_consume_approval(task_id_1, test_session, raw_token_1),
        validate_and_consume_approval(task_id_1, test_session, raw_token_1)
    )

    successes = [r for r in results if r[0] is True]
    failures = [r for r in results if r[0] is False]

    assert len(successes) == 1, f"Expected exactly 1 success in concurrent consumption, got {len(successes)}"
    assert len(failures) == 1, f"Expected exactly 1 failure in concurrent consumption, got {len(failures)}"
    assert "already been consumed" in failures[0][1], f"Unexpected failure reason: {failures[0][1]}"
    print("  [✓] Exactly 1 concurrent consumption succeeded; race condition prevented by row lock.")

    # Replay attempt
    replay_valid, replay_err = await validate_and_consume_approval(task_id_1, test_session, raw_token_1)
    assert not replay_valid, "Replay attack must be rejected"
    print("  [✓] Subsequent token replay rejected immediately.")

    # =========================================================================
    # TEST 2: Approval Token Hashing in Database
    # =========================================================================
    print("\n--- [TEST 2] Approval Token Hashing in Database ---")
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT approval_token, approval_token_hash FROM agent_tasks WHERE id = $1",
            task_id_1
        )
    assert row["approval_token"] is None, "Plaintext approval token must be NULL in database"
    expected_hash = hashlib.sha256(raw_token_1.encode("utf-8")).hexdigest()
    assert row["approval_token_hash"] == expected_hash, "approval_token_hash must match SHA-256 hex digest"
    print("  [✓] Plaintext token is NULL in database; SHA-256 hash verified.")

    # =========================================================================
    # TEST 3: Approval Token Expiration & Tamper / Invalid Rejection
    # =========================================================================
    print("\n--- [TEST 3] Approval Token Expiration & Tamper Rejection ---")
    task_id_2 = uuid.uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agent_tasks (id, session_id, user_request, status, plan_json)
            VALUES ($1, $2, 'Test expiration', $3, '{}'::jsonb)
            """,
            task_id_2,
            test_session,
            TaskStatus.PROPOSED.value
        )
    approval_req_2 = create_approval_request(task_id_2, "s1", "create_note", {"title": "T2"})
    raw_token_2 = approval_req_2.approval_token
    await bind_approval_to_task(task_id_2, test_session, approval_req_2)

    # Force expiration in database
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE agent_tasks SET approval_expires_at = NOW() - INTERVAL '5 minutes' WHERE id = $1",
            task_id_2
        )

    exp_valid, exp_err = await validate_and_consume_approval(task_id_2, test_session, raw_token_2)
    assert not exp_valid, "Expired token must be rejected"
    assert "expired" in exp_err.lower(), f"Expected expiration error, got: {exp_err}"
    print("  [✓] Expired token correctly rejected and flagged as expired.")

    # Create task 3 for invalid token check
    task_id_3 = uuid.uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agent_tasks (id, session_id, user_request, status, plan_json)
            VALUES ($1, $2, 'Test invalid token', $3, '{}'::jsonb)
            """,
            task_id_3,
            test_session,
            TaskStatus.PROPOSED.value
        )
    approval_req_3 = create_approval_request(task_id_3, "s1", "create_note", {"title": "T3"})
    await bind_approval_to_task(task_id_3, test_session, approval_req_3)

    tamper_valid, tamper_err = await validate_and_consume_approval(task_id_3, test_session, "tampered-token-12345")
    assert not tamper_valid, "Tampered/invalid token must be rejected"
    assert "invalid" in tamper_err.lower(), f"Expected invalid token error, got: {tamper_err}"
    print("  [✓] Tampered/invalid token rejected.")

    # =========================================================================
    # TEST 4: Task History Approval Token Redaction
    # =========================================================================
    print("\n--- [TEST 4] Task History Approval Token Redaction ---")
    fetched_task = await agent_orchestrator.get_task(test_session, task_id_1)
    assert fetched_task is not None, "Failed to retrieve task"
    assert fetched_task.approval_token is None, "approval_token must be None when queried from task history"

    task_list = await agent_orchestrator.list_tasks(test_session)
    for t in task_list:
        assert t.approval_token is None, "approval_token must be None in all list_tasks entries"
    print("  [✓] Task history query returns None for approval_token; no token leakage in logs.")

    # =========================================================================
    # TEST 5: Strict Session Identifier Validation & Production Refusal
    # =========================================================================
    print("\n--- [TEST 5] Strict Session Identifier Validation & Production Refusal ---")
    # Valid sessions
    assert validate_session_id("my-session_123") == "my-session_123"
    assert validate_session_id("abc") == "abc"
    assert validate_session_format("my-session_123") == "my-session_123"

    # Invalid session formats: every single one must raise 400 without skipping!
    bad_sessions = ["", "  ", "ab", "bad session with spaces", "bad/slash", "a" * 150, "<script>"]
    for bad_sid in bad_sessions:
        try:
            validate_session_format(bad_sid)
            assert False, f"Expected 400 for bad session format: '{bad_sid}'"
        except HTTPException as e:
            assert e.status_code == 400, f"Expected 400 for '{bad_sid}', got {e.status_code}"

    # Production mode refusal of default-session and unauthenticated access
    original_env = settings.ENVIRONMENT
    try:
        settings.ENVIRONMENT = "production"
        try:
            validate_session_id("default-session")
            assert False, "default-session must be rejected in production"
        except HTTPException as e:
            assert e.status_code == 403, f"Expected 403 Forbidden for default-session in production, got {e.status_code}"

        try:
            validate_session_id(None)
            assert False, "None session must be rejected in production"
        except HTTPException as e:
            assert e.status_code == 400, f"Expected 400 for missing session in production, got {e.status_code}"

        try:
            validate_session_id("")
            assert False, "Empty session must be rejected in production"
        except HTTPException as e:
            assert e.status_code == 400, f"Expected 400 for empty session in production, got {e.status_code}"

        # Principal ownership in production
        anon_principal = UserPrincipal(
            user_id="anon",
            is_authenticated=False,
            allowed_sessions=set(),
            is_demo_mode=False
        )
        try:
            verify_session_ownership("prod-user-session", anon_principal)
            assert False, "Unauthenticated principal must be rejected in production"
        except HTTPException as e:
            assert e.status_code == 401, f"Expected 401 for unauthenticated in production, got {e.status_code}"

        auth_principal = UserPrincipal(
            user_id="user_prod_1",
            is_authenticated=True,
            allowed_sessions={"prod-user-session"},
            is_demo_mode=False
        )
        assert verify_session_ownership("prod-user-session", auth_principal) == "prod-user-session"
        try:
            verify_session_ownership("foreign-user-session", auth_principal)
            assert False, "Mismatched session must be rejected with 403"
        except HTTPException as e:
            assert e.status_code == 403, f"Expected 403 for mismatched session, got {e.status_code}"
    finally:
        settings.ENVIRONMENT = original_env

    print("  [✓] Strict session format validation, production lockout, and principal ownership verified.")

    # =========================================================================
    # TEST 6: Correlation ID Middleware & Sanitized Public Errors / Health
    # =========================================================================
    print("\n--- [TEST 6] Correlation ID Middleware & Sanitized Public Errors ---")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Custom correlation ID
        resp1 = await client.get("/health", headers={"X-Request-ID": "test-trace-id-12345"})
        assert resp1.headers.get("X-Request-ID") == "test-trace-id-12345", "X-Request-ID header must be echoed"

        # Generated correlation ID
        resp2 = await client.get("/health")
        generated_corr = resp2.headers.get("X-Request-ID")
        assert generated_corr is not None and len(generated_corr) > 0, "X-Request-ID header must be generated"

        # Health endpoint sanitization
        data = resp2.json()
        assert data.get("status") in ["healthy", "degraded"], "Health status missing or invalid"
        # Ensure no database credentials or connection strings leaked
        assert "postgresql://" not in str(data), "Connection string leaked in health response"
        assert "password" not in str(data), "Password field leaked in health response"

    print("  [✓] Correlation ID middleware verified and health endpoint contains no sensitive credentials.")

    # =========================================================================
    # TEST 7: Evaluation Endpoint Production Gating
    # =========================================================================
    print("\n--- [TEST 7] Evaluation Endpoint Production Gating ---")
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        original_env = settings.ENVIRONMENT
        original_eval_enabled = settings.ENABLE_EVALUATION_ENDPOINT
        try:
            settings.ENVIRONMENT = "production"
            settings.ENABLE_EVALUATION_ENDPOINT = False
            resp_eval = await client.post("/api/evaluation/run", headers={"X-Session-ID": "prod-user-123"})
            assert resp_eval.status_code == 403, f"Expected 403 Forbidden in production, got {resp_eval.status_code}"
        finally:
            settings.ENVIRONMENT = original_env
            settings.ENABLE_EVALUATION_ENDPOINT = original_eval_enabled
    print("  [✓] Evaluation run endpoint strictly blocked in production.")

    # =========================================================================
    # TEST 8: Interrupted Task Startup Recovery Sweep & Active Lease Preservation
    # =========================================================================
    print("\n--- [TEST 8] Interrupted Task Startup Recovery Sweep & Active Lease Preservation ---")
    stale_task_id = uuid.uuid4()
    active_task_id = uuid.uuid4()
    async with pool.acquire() as conn:
        # 1. Stale task whose execution lease expired 10 minutes ago
        await conn.execute(
            """
            INSERT INTO agent_tasks (id, session_id, user_request, status, plan_json, execution_lease_expires_at, created_at, updated_at)
            VALUES ($1, $2, 'Interrupted stale job', $3, '{}'::jsonb, NOW() - INTERVAL '10 minutes', NOW() - INTERVAL '30 minutes', NOW() - INTERVAL '30 minutes')
            """,
            stale_task_id,
            test_session,
            TaskStatus.RUNNING.value
        )
        # 2. Active running task whose execution lease is valid for the next 5 minutes
        await conn.execute(
            """
            INSERT INTO agent_tasks (id, session_id, user_request, status, plan_json, execution_lease_expires_at, created_at, updated_at)
            VALUES ($1, $2, 'Active running job', $3, '{}'::jsonb, NOW() + INTERVAL '5 minutes', NOW(), NOW())
            """,
            active_task_id,
            test_session,
            TaskStatus.RUNNING.value
        )

    # Trigger recovery sweep
    recovered = await recover_interrupted_tasks()
    assert recovered >= 1, "Recovery sweep should recover at least 1 stale task"

    async with pool.acquire() as conn:
        stale_row = await conn.fetchrow("SELECT status, result_summary FROM agent_tasks WHERE id = $1", stale_task_id)
        active_row = await conn.fetchrow("SELECT status FROM agent_tasks WHERE id = $1", active_task_id)

    assert stale_row["status"] == TaskStatus.FAILED.value, f"Expected stale task to be FAILED, got {stale_row['status']}"
    assert "interrupted" in stale_row["result_summary"].lower(), f"Unexpected error message: {stale_row['result_summary']}"
    assert active_row["status"] == TaskStatus.RUNNING.value, f"Expected active task with valid lease to remain RUNNING, got {active_row['status']}"
    print("  [✓] Stale task recovered to FAILED; active task with valid lease was safely preserved as RUNNING.")

    # =========================================================================
    # TEST 9: Calculator Resource Safety, AST Depth, Node Count & Numerical Limits
    # =========================================================================
    print("\n--- [TEST 9] Calculator Resource Safety & Limits ---")
    calc = CalculatorTool()

    # Valid execution
    valid_res = await calc.execute(test_session, expression="((15 * 4) + 20) / 8")
    assert valid_res["result"] == 10, f"Expected 10, got {valid_res['result']}"

    # Nesting depth > 8 (nested binary operations)
    try:
        await calc.execute(test_session, expression="1 + (1 + (1 + (1 + (1 + (1 + (1 + (1 + 1)))))))")
        assert False, "Expected error on AST nesting depth > 8"
    except ValueError as e:
        assert "nesting depth" in str(e).lower(), f"Unexpected error: {e}"

    # Node count > 40 with depth <= 8 (balanced tree expression exceeding node limit without exceeding 150 char length)
    high_complexity = "(((1+1)+(1+1)) + ((1+1)+(1+1))) + (((1+1)+(1+1)) + ((1+1)+(1+1)))"
    try:
        await calc.execute(test_session, expression=high_complexity)
        assert False, "Expected error on AST node count > 40"
    except ValueError as e:
        assert "complexity" in str(e).lower(), f"Unexpected error: {e}"

    # Expression length > 150
    too_long = "1 + " * 45
    try:
        await calc.execute(test_session, expression=too_long)
        assert False, "Expected error on expression length > 150"
    except ValueError as e:
        assert "length" in str(e).lower(), f"Unexpected error: {e}"

    # Literal digit length > 40
    huge_int_literal = "9" * 45 + " + 1"
    try:
        await calc.execute(test_session, expression=huge_int_literal)
        assert False, "Expected error on integer literal > 40 digits"
    except ValueError as e:
        assert "digits" in str(e).lower(), f"Unexpected error: {e}"

    # Booleans rejected
    try:
        await calc.execute(test_session, expression="True + 1")
        assert False, "Expected error on boolean literal"
    except ValueError as e:
        assert "boolean" in str(e).lower() or "syntax" in str(e).lower(), f"Unexpected error: {e}"

    # Complex power rejection
    try:
        await calc.execute(test_session, expression="(-4) ** 0.5")
        assert False, "Expected error on fractional power of negative number"
    except ValueError as e:
        assert "complex" in str(e).lower(), f"Unexpected error: {e}"

    # Overflow / huge exponent
    try:
        await calc.execute(test_session, expression="10 ** 100")
        assert False, "Expected error on large exponent"
    except ValueError as e:
        assert "large" in str(e).lower() or "overflow" in str(e).lower(), f"Unexpected error: {e}"

    # Magnitude > 1e15
    try:
        await calc.execute(test_session, expression="1000000000000001 + 1")
        assert False, "Expected error on magnitude > 1e15"
    except ValueError as e:
        assert "magnitude" in str(e).lower(), f"Unexpected error: {e}"

    print("  [✓] Calculator tool AST depth, node limit, digit limit, booleans, and magnitude guards verified.")

    # =========================================================================
    # TEST 10: Concurrent Note Creation Database-Level Idempotency
    # =========================================================================
    print("\n--- [TEST 10] Concurrent Note Creation Database-Level Idempotency ---")
    note_title = "Concurrent Safety Test Note"
    note_content = "This content should only be saved once, even when multiple concurrent requests attempt creation."

    # Launch 5 concurrent creations with identical content
    concurrent_notes = await asyncio.gather(*[
        note_service.create_note(test_session, note_title, note_content)
        for _ in range(5)
    ])

    assert len(concurrent_notes) == 5, "All 5 calls should succeed"
    # All 5 returned notes should refer to the same note ID
    returned_ids = {n["id"] for n in concurrent_notes}
    assert len(returned_ids) == 1, f"Expected 1 unique note ID across all 5 concurrent creations, got {len(returned_ids)}"

    # Query DB to ensure exactly 1 row exists
    async with pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM notes WHERE session_id = $1 AND title = $2",
            test_session,
            note_title
        )
    assert count == 1, f"Expected exactly 1 note in database, found {count}"
    print("  [✓] Database unique index and ON CONFLICT handling guaranteed concurrent note idempotency.")

    # =========================================================================
    # TEST 11: Approval State Machine Validations & Legacy Token Invalidation
    # =========================================================================
    print("\n--- [TEST 11] Approval State Machine Validations & Legacy Token Invalidation ---")
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
    
    # Valid rejection
    reject_ok, reject_err = await reject_approval(task_id_sm, test_session)
    assert reject_ok is True, f"Rejection failed: {reject_err}"
    
    # Verify task transitioned to CANCELLED and REJECTED
    async with pool.acquire() as conn:
        sm_row = await conn.fetchrow("SELECT status, approval_status FROM agent_tasks WHERE id = $1", task_id_sm)
    assert sm_row["status"] == TaskStatus.CANCELLED.value
    assert sm_row["approval_status"] == ApprovalStatus.REJECTED.value

    # Rejecting an already rejected task must be denied
    reject_again_ok, reject_again_err = await reject_approval(task_id_sm, test_session)
    assert reject_again_ok is False
    assert "cannot reject" in reject_again_err.lower()

    # Rejecting task in non-awaiting status must be denied
    task_id_completed = uuid.uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agent_tasks (id, session_id, user_request, status, approval_status)
            VALUES ($1, $2, 'Completed job', $3, $4)
            """,
            task_id_completed,
            test_session,
            TaskStatus.SUCCEEDED.value,
            ApprovalStatus.APPROVED.value
        )
    comp_rej_ok, comp_rej_err = await reject_approval(task_id_completed, test_session)
    assert comp_rej_ok is False
    assert "not awaiting approval" in comp_rej_err.lower()

    # Rejecting expired task transitions it to expired/failed
    task_id_expired = uuid.uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agent_tasks (id, session_id, user_request, status, approval_status, approval_expires_at)
            VALUES ($1, $2, 'Expired job', $3, $4, NOW() - INTERVAL '5 minutes')
            """,
            task_id_expired,
            test_session,
            TaskStatus.AWAITING_APPROVAL.value,
            ApprovalStatus.PENDING.value
        )
    exp_rej_ok, exp_rej_err = await reject_approval(task_id_expired, test_session)
    assert exp_rej_ok is False
    assert "expired" in exp_rej_err.lower()

    # Legacy token fallback removal: token with plaintext only and NULL hash cannot be consumed
    task_id_legacy = uuid.uuid4()
    legacy_token = "legacy_secret_plaintext_token"
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agent_tasks (id, session_id, user_request, status, approval_status, approval_token, approval_token_hash, approval_expires_at)
            VALUES ($1, $2, 'Legacy job', $3, $4, $5, NULL, NOW() + INTERVAL '10 minutes')
            """,
            task_id_legacy,
            test_session,
            TaskStatus.AWAITING_APPROVAL.value,
            ApprovalStatus.PENDING.value,
            legacy_token
        )
    leg_ok, leg_err = await validate_and_consume_approval(task_id_legacy, test_session, legacy_token)
    assert leg_ok is False, "Legacy unhashed token must NOT be consumable"
    assert "missing or legacy" in leg_err.lower() or "invalidated" in leg_err.lower()
    print("  [✓] Approval state transitions validated; unhashed legacy tokens strictly rejected.")

    # =========================================================================
    # TEST 12: Audit Log Immutability Trigger
    # =========================================================================
    print("\n--- [TEST 12] Audit Log Immutability Trigger ---")
    async with pool.acquire() as conn:
        # Create a sample task and audit log
        audit_task_id = uuid.uuid4()
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
            VALUES ($1, $2, 'test_tool', 'succeeded', 'Audit event 1')
            """,
            audit_task_id,
            test_session
        )

        log_row = await conn.fetchrow("SELECT id FROM agent_execution_logs WHERE task_id = $1 LIMIT 1", audit_task_id)
        assert log_row is not None
        log_id = log_row["id"]

        # Attempt to modify audit log record
        try:
            await conn.execute("UPDATE agent_execution_logs SET result_summary = 'tampered' WHERE id = $1", log_id)
            assert False, "UPDATE on agent_execution_logs must be rejected by PostgreSQL trigger"
        except Exception as e:
            assert "append-only" in str(e).lower() or "forbidden" in str(e).lower(), f"Unexpected error: {e}"
        print("  [✓] Database trigger blocked unauthorized UPDATE on agent_execution_logs.")

        # Attempt to delete audit log from a production/non-test session
        prod_session_id = "prod-corp-client"
        prod_task_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO agent_tasks (id, session_id, user_request, status)
            VALUES ($1, $2, 'Prod task', 'succeeded')
            """,
            prod_task_id,
            prod_session_id
        )
        await conn.execute(
            """
            INSERT INTO agent_execution_logs (task_id, session_id, tool_name, status)
            VALUES ($1, $2, 'tool', 'succeeded')
            """,
            prod_task_id,
            prod_session_id
        )
        try:
            await conn.execute("DELETE FROM agent_execution_logs WHERE session_id = $1", prod_session_id)
            assert False, "DELETE on production audit log must be rejected by trigger"
        except Exception as e:
            assert "append-only" in str(e).lower() or "forbidden" in str(e).lower(), f"Unexpected error: {e}"
        print("  [✓] Database trigger blocked unauthorized DELETE on production audit logs.")

        # Day 7.2 Strict check: Even a test-prefixed session cannot bypass trigger without session setting
        try:
            await conn.execute("DELETE FROM agent_execution_logs WHERE session_id = $1", test_session)
            assert False, "DELETE on test session audit log must be rejected without allow_audit_cleanup"
        except Exception as e:
            assert "append-only" in str(e).lower() or "forbidden" in str(e).lower(), f"Unexpected error: {e}"
        print("  [✓] Database trigger blocked unauthorized DELETE even on test-prefixed session.")

        # Clean up temporary test fixtures within explicit transaction using SET LOCAL
        async with conn.transaction():
            await conn.execute("SET LOCAL memora.allow_audit_cleanup = 'on'")
            await conn.execute("DELETE FROM agent_execution_logs WHERE session_id IN ($1, $2)", prod_session_id, test_session)
            await conn.execute("DELETE FROM agent_tasks WHERE id IN ($1, $2)", prod_task_id, audit_task_id)

    # Clean up test session notes
    await note_service.delete_all_notes(test_session)
    await close_db_pool()

    print("\n" + "=" * 80)
    print("ALL 12 DAY 7 & 7.1 PRODUCTION HARDENING, SECURITY & INTEGRITY TESTS PASSED!")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(run_day7_hardening_tests())
