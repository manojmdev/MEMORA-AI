# MEMORA AI — Testing Strategy & Test Suite Guide

## 1. Overview

MEMORA AI employs a multi-tiered regression and verification strategy. All 15 automated test suites are preserved at the root of `backend/` to guarantee Python import integrity and uninterrupted direct CLI script execution.

A unified test runner `backend/run_all_tests.py` orchestrates test discovery, environment capability checks, isolated execution, timeout enforcement, and standardized exit codes for CI/CD environments.

---

## 2. Test Suite Inventory

| # | Filename | Phase / Sprint | Category | Primary Focus & Verification Scope |
|---|---|---|---|---|
| 1 | `test_db_and_api.py` | Day 3 | `db` | Neon PostgreSQL connectivity, table schemas, and basic FastAPI CRUD endpoints |
| 2 | `test_memory_engine.py` | Day 3 | `live` | Memory extraction, vector embedding creation, and pgvector persistence |
| 3 | `test_hybrid_retrieval.py` | Day 4 | `live` | Reciprocal Rank Fusion (vector cosine similarity + full-text search) |
| 4 | `test_day5_intelligence.py` | Day 5 | `live` | Memory evolution, exponential confidence decay, contradiction handling |
| 5 | `test_day6_agent.py` | Day 6 | `db` | Task planner, policy rules, plan validator, step DAG execution, checkpoints |
| 6 | `test_day7_hardening.py` | Day 7 | `db` | Idempotency keys, concurrent race conditions, worker lease fencing, audit logs |
| 7 | `test_day7_2_hardening.py` | Day 7.2 | `db` | Security headers, SQL injection resistance, rate limits, payload size limits |
| 8 | `test_sprint2_intelligence.py` | Sprint 2 | `db` | Semantic clustering, typed relationship graph, memory consolidation |
| 9 | `test_sprint3_agent.py` | Sprint 3 | `db` | Dynamic DAG planning, multi-step rollback, human approval gates, leases |
| 10 | `test_sprint3_1_fault_injection.py` | Sprint 3.1 | `db` | Worker crashes, poisoned checkpoints, database disconnections, recovery |
| 11 | `test_sprint4_3_reliability.py` | Sprint 4.3 | `db` | Recovery policies, event streams, lease timeouts, stale worker fencing |
| 12 | `test_sprint4_4_acceptance.py` | Sprint 4.4 | `db` | Multi-turn approval flows, memory-context grounding, workspace operations |
| 13 | `test_sprint4_5_agent_e2e.py` | Sprint 4.5 | `db` | Multi-workspace agent workflows, parallel waves, cryptographic approvals |
| 14 | `test_chat_regression_suite.py` | Sprint 4 | `db` | 10 deterministic chat scenarios: context grounding, identity, safety |
| 15 | `test_live_chat_verification.py` | Sprint 4 | `live` | Live end-to-end conversation, real-time memory extraction and recall |

---

## 3. Running Tests

### 3.1 Using the Unified Test Runner

The centralized runner executes suites inside isolated Python subprocesses with clean environment propagation.

```powershell
# List all registered test suites with metadata
python backend/run_all_tests.py --list

# Run all test suites
python backend/run_all_tests.py --all

# Run standard test suites, skipping external live LLM API calls
python backend/run_all_tests.py --skip-live

# Run tests by category ('db', 'live', or 'offline')
python backend/run_all_tests.py --category db

# Run a specific test suite by name or substring
python backend/run_all_tests.py --suite test_day7_hardening.py
python backend/run_all_tests.py --suite sprint3
```

### 3.2 Direct Suite Execution

Each test script retains a standalone `if __name__ == '__main__':` block and can be executed directly:

```powershell
cd backend
python test_day7_hardening.py
python test_sprint3_agent.py
python test_chat_regression_suite.py
```

---

## 4. Test Categories & Environment Requirements

### Category: `db` (Database-Dependent)
- Requires `DATABASE_URL` pointing to an active Neon PostgreSQL database.
- Safe to run on development or staging databases; tests use UUID-isolated session identifiers (`s45_test_...`, `sprint3_test_...`).
- Does not modify or overwrite production user records.

### Category: `live` (Live Nebius LLM API)
- Requires both `DATABASE_URL` and `NEBIUS_API_KEY`.
- Makes real outbound network calls to `https://api.tokenfactory.nebius.com/v1`.
- When external provider latency or 504 timeouts occur, use `--skip-live` to test all system components deterministically.

---

## 5. Production Safety & Audit Integrity

1. **Session Isolation**: Every test run generates a unique session UUID. Test assertions operate exclusively within this isolated namespace.
2. **Audit Table Immutability**: The PostgreSQL table `agent_execution_logs` is guarded by a database trigger (`trg_prevent_audit_modification`). Tests do not attempt raw `DELETE` operations on audit tables; test cleanup scripts handle isolation gracefully.
3. **No Database Resets**: Tests never issue `DROP TABLE` or destructive truncation commands against shared database environments.

---

## 6. Frontend Verification

Frontend testing and code quality are verified via Vite and Oxlint:

```powershell
# Run production build
cd frontend
npm run build

# Run Oxlint
npm run lint
```
