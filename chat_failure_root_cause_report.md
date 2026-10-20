# MEMORA AI — AI Chat Failure Root Cause & Resolution Report

**Investigation Reference ID:** `1f264bf81fb647e4b1a5d6a0df078328`  
**Date:** October 21, 2026  
**Status:** Resolved & Verified Across All Regression & Live Acceptance Suites  

---

## 1. Executive Summary & Root Cause Analysis

### Observed Failure
During an end-to-end AI Chat interaction, sending the user message:
> *"I'm a computer science student specializing in AI and machine learning. I prefer Python over Java and C. I enjoy building practical AI applications rather than spending too much time on theory."*

resulted in the frontend displaying:
> `Error: An internal error occurred while processing your request. (Reference ID: 1f264bf81fb647e4b1a5d6a0df078328)`

### Trace of Request Flow
The request was traced through the entire stack:
1. **Frontend (`ChatView.jsx` / `api.js`):** `POST /api/chat` sent with user message and session ID.
2. **FastAPI Route (`main.py` -> `/api/chat`):** Authentication principal and session ID validated.
3. **Hybrid Memory Retrieval (`hybrid_retriever.py`):** Embedding generation via Nebius `Qwen/Qwen3-Embedding-8B` + pgvector cosine similarity search + keyword matching.
4. **Context Construction & Nemotron Chat Completion (`memory_context.py`):** Formatted memory context block and dispatched chat completion request to `nvidia/Nemotron-3_5-Lightning` via Token Factory.
5. **Memory Extraction (`memory_extractor.py`):** Secondary LLM call extracting structured JSON memory candidates.
6. **Pydantic Validation & Persistence (`memory_service.py`):** Insertion into Neon PostgreSQL `memories` table with 1024-dimensional pgvector embeddings.
7. **Response Serialization (`schemas.py` / `main.py`):** Returning `ChatResponse` payload to client.

### Precise Root Cause & Failure Points Identified

1. **Unprotected LLM Provider Network & Timeout Failures:**
   In `backend/app/services/memory_context.py`, the call to `client.chat.completions.create` had no try/except block. Any transient socket reset, provider timeout (Nemotron or Nebius gateway latency), HTTP 429 rate limit, or network disconnection bubbled directly to `safe_internal_error(e, ...)` in `main.py`. This caught the uncaught exception, generated a reference ID, and converted what should have been a structured 504 Gateway Timeout or 503 Service Unavailable into an opaque internal 500 error.

2. **Silent Failure & Missing Persistence Status Contract:**
   If the chat completion succeeded but memory extraction or PostgreSQL persistence failed (e.g., database lock timeout, embedding timeout, or malformed JSON), `memory_context.py` swallowed the extraction error, leaving `extracted_candidates = []` without any status flag. The frontend was unable to tell whether zero memories existed or if persistence had failed, violating the requirement: *"Do not silently report memory persistence if it failed. Do not mark a failed chat as successful."*

3. **Brittle Markdown & Preamble Extraction Parsing:**
   In `backend/app/services/memory_extractor.py`, `clean_json_string` relied on strict regex matching of ````json ... ```` fences. When Nemotron output conversational text, explanations, or analysis before/after the JSON array (or omitted markdown code blocks entirely), JSON decoding threw `json.decoder.JSONDecodeError`.

4. **Missing End-to-End Correlation ID in Backend Logs:**
   The `X-Request-ID` header sent by the client or generated at the FastAPI middleware was not propagated through Python standard logging (`logger.info`/`logger.error`) in service modules (`memory_context`, `memory_extractor`, `memory_service`). Backend logs could not be deterministically correlated with client reference IDs.

5. **Cross-Session Authorization Guard Hole in Development:**
   In `backend/app/auth/session_guard.py`, `validate_session_id` previously skipped `verify_session_ownership` if `ENVIRONMENT != "production"`. When an authenticated user supplied an authorization token in testing/development and attempted to access a session belonging to another user, the server did not reject the unauthorized cross-tenant request with HTTP 403 Forbidden.

---

## 2. Changes Implemented

### Backend Core
- **`backend/app/services/memory_context.py`:**
  - Wrapped `client.chat.completions.create` with explicit exception handlers for `openai.APITimeoutError` (HTTP 504), `openai.APIConnectionError` / `httpx.ConnectError` (HTTP 503), `openai.RateLimitError` (HTTP 429), and `openai.APIError` (HTTP 502).
  - Preserved assistant reply when extraction or database persistence fails.
  - Returned a 5-tuple: `(reply, recalled_memories, extracted_candidates, persistence_status, persistence_error)` where `persistence_status` is `"success" | "partial" | "failed"`.
  - Added request ID logging context so all LLM steps are correlated.

- **`backend/app/services/memory_extractor.py`:**
  - Enhanced `clean_json_string` with bracket-matching fallback (`[` to `]`) to reliably parse JSON arrays even when surrounded by arbitrary conversational preamble or unclosed markdown fences.
  - Introduced `extract_memories_with_status()` returning `(candidates, error_str)` so parse errors are preserved for upstream reporting.

- **`backend/app/schemas.py`:**
  - Added `memory_persistence_status: Optional[str] = "success"` and `memory_persistence_error: Optional[str] = None` to `ChatResponse`.

- **`backend/app/services/embedding_service.py`:**
  - Added timeout handling for `APITimeoutError` and `httpx.TimeoutException`, gracefully falling back to keyword retrieval and ensuring embedding locks are always released.

- **`backend/app/services/memory_retriever.py`:**
  - Hardened asyncpg connection pool acquisition in keyword search with error catching to ensure clean empty-result degradation on temporary DB disconnections.

- **`backend/app/auth/session_guard.py`:**
  - Enforced session ownership checks whenever `principal.is_authenticated` is True regardless of environment mode, properly blocking cross-session tampering with HTTP 403 Forbidden.
  - Hardened token signature verification to reject forged/tampered bearer tokens with HTTP 401 Unauthorized.

- **`backend/app/main.py`:**
  - Implemented `ContextVar` request correlation filter (`[%(correlation_id)s]`) in logging format.
  - Updated `/api/chat` route to propagate `memory_persistence_status` and `memory_persistence_error` to the client.
  - Enhanced `safe_internal_error` to preserve HTTP 504/503/429 status codes.

### Frontend
- **`frontend/src/App.jsx`:**
  - Handled `memory_persistence_status === "failed"` or `"partial"` by surfacing non-blocking warning toasts to the user while preserving the assistant's response.
- **`frontend/src/components/chat/ChatView.jsx`:**
  - Added visual badges indicating newly extracted memories when persistence succeeds, and warning pills with retry advice when persistence fails or is degraded.

---

## 3. Regression Test Results

### Suite 1: AI Chat Regression Suite (Scenarios A through J)
*Executed with live Neon PostgreSQL & Nebius Token Factory (`test_chat_regression_suite.py`)*

| Scenario | Description | Target Behavior | Result |
|:---|:---|:---|:---:|
| **Test A** | First user message with 3 preferences | Extracts 3 preferences; persists in Neon DB; returns 200 OK | **PASS** |
| **Test B** | Second message retrieving preferences | Recalls preferences via hybrid search; personalizes response | **PASS** |
| **Test C** | Paraphrased semantic retrieval | Matches query via pgvector cosine distance (threshold 0.58) | **PASS** |
| **Test D** | Updating existing preference | Evolves memory; supersedes old fact; updates active state | **PASS** |
| **Test E** | Embedding provider timeout | Gracefully degrades to keyword search without failing request | **PASS** |
| **Test F** | Nemotron provider timeout | Cleanly returns HTTP 504 Gateway Timeout with correlation ID | **PASS** |
| **Test G** | Malformed extraction JSON | Preserves assistant reply; reports `memory_persistence_status: failed` | **PASS** |
| **Test H** | Database unavailable | Preserves assistant reply; reports persistence error | **PASS** |
| **Test I** | Invalid authentication token | Cleanly rejects with HTTP 401 Unauthorized | **PASS** |
| **Test J** | Cross-session access attempt | Strictly blocks cross-tenant access with HTTP 403 Forbidden | **PASS** |

**Summary: 10/10 Scenarios Passed (100% Success)**

---

### Suite 2: Existing Regression Suites

1. **`backend/test_db_and_api.py`**
   - Database Pool & Schema Verification (26 columns): **PASS**
   - Database CRUD Operations: **PASS**
   - FastAPI Endpoints & Nemotron Live Verification: **PASS**
   - **Result: PASSED (100%)**

2. **`backend/test_day5_intelligence.py`**
   - Schema validation, noise filtering, explicit statement calibration, temporal invalidation, contradiction resolution, explainability, session isolation, concurrency locks, and quantitative retrieval benchmark (12 queries, MRR 1.0, 100% pass rate): **PASS**
   - **Result: 11/11 PASSED (100%)**

3. **`backend/test_day7_2_hardening.py`**
   - Cryptographic HMAC-SHA256 signatures, API ownership enforcement, worker identity & renewable heartbeats, lease recovery, append-only triggers, and approval state machine: **PASS**
   - **Result: 6/6 PASSED (100%)**

4. **`backend/test_sprint4_4_acceptance.py`**
   - Parallel wave execution, serial dependency order, skipped downstream steps, branch isolation, cryptotoken approvals, recovery post-crash, idempotency reconciliation, atomic worker race resolution, cancellation rejection, synthesis fallback, and cyclic DAG rejection: **PASS**
   - **Result: 12/12 PASSED (100%)**

5. **Frontend Production Build (`npm --prefix frontend run build`)**
   - Vite 8.3.4 client production build: **PASS (1.45s, 0 errors)**

---

## 4. Final Live End-to-End Verification

Tested with the exact user message:
> *"I'm a computer science student specializing in AI and machine learning. I prefer Python over Java and C. I enjoy building practical AI applications rather than spending too much time on theory."*

- **HTTP Request:** Returned HTTP 200 OK (Request ID: `live-req-9c63cb6b1957`).
- **Assistant Response:** Generated a comprehensive, personalized response acknowledging AI/ML specialization, Python preference, and practical application focus.
- **Memory Extraction:** Successfully extracted 3 structured memory candidates:
  1. `[personal_context]` `academic_focus`: *"The user is a computer science student specializing in AI and machine learning."*
  2. `[preferences]` `preferred_language`: *"The user prefers Python over Java and C."*
  3. `[learning_style]` `preferred_learning_approach`: *"The user prefers building practical AI applications over theoretical study."*
- **Database Persistence:** Persisted 3 active records in Neon PostgreSQL table `memories` with 1024-dimensional embeddings (verified in DB with IDs `7df12d1e-801d-4c9f-a52b-0a542629e9fd`, `090cb317-40b8-4949-bb74-7c0959531c26`, `b90083b4-6f2c-40d4-8dd9-aa37a30de084`).
- **Memory Explorer:** `GET /api/memories?session_id=live_verify_e4ae58fe` returned all 3 active memories with importance scores (0.75 - 0.85) and categories.
- **Subsequent Query Retrieval:** Sent *"What language and focus would you recommend for my next machine learning portfolio project?"*. The hybrid retriever recalled the user's `academic_focus` and `preferred_language`, and the assistant personalized the response to recommend Python and practical AI portfolio architectures.

---

## 5. Remaining Considerations & Monitoring

- **External Provider Latency:** Nebius Token Factory response latency can occasionally spike to 20-30 seconds during peak times. The 45-second timeout configuration is appropriate for interactive chat while guarding against infinite client hangs.
- **Embedding Cache:** If repeated identical memory candidates are extracted across long multi-turn sessions, an LRU cache on memory candidate embeddings will further reduce Token Factory API round-trips.
- **Git State:** In accordance with instructions, no commits or pushes have been made.
