# MEMORA AI

> **Private Long-Term Memory & Proactive Agent Intelligence Platform**

MEMORA AI is an enterprise-grade personal AI assistant combining self-evolving long-term memory, reciprocal rank fusion hybrid retrieval, typed knowledge graphs, and a resilient DAG-based autonomous agent execution engine.

---

## 🌟 Key Capabilities

### 🧠 Dynamic Long-Term Memory Engine
- **Automatic Extraction**: Continuously extracts semantic user preferences, technical skills, habits, and profile facts during chat conversations.
- **1024-Dimensional Vector Embeddings**: Utilizes Nebius-hosted `Qwen/Qwen3-Embedding-8B` normalized to 1024 dimensions, persisted via Neon Serverless `pgvector`.
- **Reciprocal Rank Fusion (RRF) Hybrid Search**: Merges cosine vector similarity with PostgreSQL full-text keyword ranking (`ts_rank_cd`) for zero-loss contextual recall.
- **Self-Evolving Lifecycle**: Features exponential confidence decay over inactive intervals, access-based reinforcement, and automatic contradiction detection that marks superseded memories.
- **Typed Relationship Graph**: Builds a semantic graph of interconnected memories with explicit relationship types (`SUPPORTS`, `CONTRADICTS`, `EXTENDS`, `RELATION`).
- **Memory Consolidation**: Clusters episodic memory fragments into stable semantic reflections and high-level user profiles.

### 🤖 Resilient Agent Subsystem
- **Goal-Backward DAG Planning**: Natural language objectives are decomposed into strictly sequenced, dependency-aware execution steps.
- **Wave-Based Concurrency**: Independent steps execute concurrently in parallel waves (`asyncio.gather`), maximizing throughput.
- **Cryptographic Human Approval**: Sensitive actions (e.g., persistent note writes, external side effects) halt in `AWAITING_APPROVAL` and issue HMAC-SHA256 one-time approval tokens. Replay attacks are strictly prevented.
- **Durable Checkpoints & Crash Recovery**: Every step transition and state snapshot is durably committed to PostgreSQL. Interrupted tasks automatically resume from the last valid checkpoint.
- **Worker Lease Fencing**: Distributed workers maintain heartbeat leases in PostgreSQL. Stale or unresponsive workers are fenced out to eliminate split-brain execution risks.
- **Immutable Audit Trail**: Step history and state transitions are recorded in `agent_execution_logs` protected by PostgreSQL database triggers that reject raw modifications.

### 🖥️ Eight Interactive Workspaces
1. **Chat Workspace**: Conversational interface with live memory grounding and real-time candidate preview.
2. **Memory Explorer**: Search, filter, inspect, edit, and delete persistent memory records.
3. **Agent Workspace**: Create goals, monitor multi-step DAG progress, review execution checkpoints, and grant approvals.
4. **Intelligence Graph**: Interactive node-link visualization of typed memory relationships and clusters.
5. **Notes Workspace**: Markdown note editor and storage for human notes and agent-generated study artifacts.
6. **Lifecycle Management**: Real-time decay scoring, access frequency meters, and memory evolution chains.
7. **Consolidation**: Clustering episodic memories into consolidated reflections and semantic profiles.
8. **System Dashboard**: Cluster statistics, database health metrics, token usage, and audit trail inspector.

---

## 🏗️ Repository Architecture

```text
MEMORA-AI/
├── backend/
│   ├── app/
│   │   ├── main.py                     # FastAPI application entry point, routes, CORS & lifespan
│   │   ├── config.py                   # Pydantic v2 settings & environment loading
│   │   ├── database.py                 # Neon PostgreSQL connection pool management (asyncpg)
│   │   ├── schemas.py                  # Pydantic data schemas & API models
│   │   ├── agent/                      # Autonomous agent execution subsystem
│   │   │   ├── models.py               # Task status, DAG step models, checkpoint schemas
│   │   │   ├── orchestrator.py         # Multi-step DAG orchestrator & wave concurrency
│   │   │   ├── planner.py              # LLM goal-backward planner & fallback engine
│   │   │   ├── plan_validator.py       # DAG cycle detection & structural validator
│   │   │   ├── policy_engine.py        # Tool permissions & safety rules
│   │   │   ├── approval_manager.py     # HMAC-SHA256 cryptographic approval token manager
│   │   │   ├── checkpoint_manager.py   # Durable state checkpoint persistence & recovery
│   │   │   ├── worker_identity.py      # Distributed worker lease acquisition & fencing
│   │   │   ├── intent_analyzer.py      # Goal ambiguity detection & role routing
│   │   │   ├── response_composer.py    # Multi-step execution synthesis
│   │   │   └── tools/                  # Registered tool execution plugins
│   │   │       ├── registry.py         # Tool registry & dispatcher
│   │   │       ├── calculator.py       # Deterministic arithmetic calculator
│   │   │       ├── memory_tools.py     # Memory search, list & graph tools
│   │   │       ├── note_tools.py       # Persistent database note tools
│   │   │       └── study_tools.py      # Curriculum & study plan generators
│   │   └── services/                   # Memory and intelligence services
│   │       ├── llm_service.py          # Nebius TokenFactory OpenAI client
│   │       ├── embedding_service.py    # 1024-dim embedding generator with LRU cache
│   │       ├── hybrid_retriever.py     # Reciprocal Rank Fusion retrieval
│   │       ├── memory_service.py       # Memory persistence & CRUD operations
│   │       ├── lifecycle_service.py    # Confidence decay & contradiction resolution
│   │       ├── consolidation_service.py# Semantic clustering & memory consolidation
│   │       ├── context_retriever.py    # Multi-factor context ranking & graph boost
│   │       ├── dashboard_service.py    # System metrics & cluster statistics
│   │       ├── explainability_service.py# Memory recall explainability generator
│   │       └── note_service.py         # Persistent note storage
│   ├── run_all_tests.py                # Unified test suite runner & orchestrator
│   ├── test_*.py                       # 15 automated regression & verification suites
│   ├── Dockerfile                      # Production container build manifest
│   ├── requirements.txt                # Python backend dependencies
│   └── .env.example                    # Backend environment configuration template
├── frontend/
│   ├── src/
│   │   ├── App.jsx                     # Single Page Application router & workspace switcher
│   │   ├── api/client.js               # Unified backend API HTTP client
│   │   ├── components/                 # Workspace views & UI modules
│   │   │   ├── chat/                   # ChatArea, MessageItem, MemoryCard
│   │   │   ├── explorer/               # MemoryExplorer, FilterBar, DetailModal
│   │   │   ├── agent/                  # AgentWorkspaceView, TaskTimeline, ApprovalModal
│   │   │   ├── graph/                  # IntelligenceGraph, RelationshipInspector
│   │   │   ├── notes/                  # NotesView, NoteEditor
│   │   │   ├── lifecycle/              # LifecycleView, DecayMeters
│   │   │   ├── consolidation/          # ConsolidationView, ClusterDetails
│   │   │   └── dashboard/              # DashboardView, AuditLogTable
│   │   └── styles/                     # Layout, animations, and workspace stylesheets
│   ├── package.json                    # Frontend dependencies (React 19, Vite 6)
│   ├── vercel.json                     # Vercel SPA routing & build configuration
│   └── .env.example                    # Frontend environment template
├── docs/
│   ├── ARCHITECTURE.md                 # In-depth system architecture & data flow
│   ├── TESTING.md                      # Complete testing guide & suite inventory
│   ├── DEPLOYMENT.md                   # Render & Vercel deployment instructions
│   └── ENVIRONMENT_VARIABLES.md        # Comprehensive variable definitions & security
├── render.yaml                         # Production Render Blueprint manifest
├── .gitignore                          # Root Git hygiene & credential protection
└── README.md                           # Project documentation (this file)
```

---

## 🚀 Quickstart Guide

### 1. Prerequisites
- **Python**: 3.11 or 3.13
- **Node.js**: 18.x or 20.x
- **PostgreSQL**: Neon PostgreSQL with `pgvector` extension enabled
- **Nebius API Key**: Access to Nebius TokenFactory API

---

### 2. Backend Setup

```powershell
# Navigate to backend directory
cd backend

# Create and activate a Python virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1   # On Windows
# source .venv/bin/activate  # On Linux/macOS

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
Copy-Item .env.example .env
# Edit .env with your actual credentials
```

#### Required Variables in `backend/.env`:
```env
DATABASE_URL=postgresql://user:password@ep-xyz-pooler.aws-us-east-2.neon.tech/neondb?sslmode=require
NEBIUS_API_KEY=your_actual_nebius_api_key
NEBIUS_BASE_URL=https://api.tokenfactory.nebius.com/v1
NEBIUS_MODEL=nvidia/Nemotron-3_5-Lightning
EMBEDDING_MODEL=Qwen/Qwen3-Embedding-8B
EMBEDDING_DIMENSION=1024
FRONTEND_ORIGIN=http://localhost:5173
ENVIRONMENT=development
AUTH_SECRET_KEY=generate_a_secure_32_character_random_key
```

#### Start the Backend API:
```powershell
uvicorn app.main:app --reload --port 8000
```
- Interactive API Swagger Docs: `http://localhost:8000/docs`
- Health Endpoint: `http://localhost:8000/health`

---

### 3. Frontend Setup

```powershell
# In a new terminal, navigate to frontend directory
cd frontend

# Install Node modules
npm install

# Configure environment variables
Copy-Item .env.example .env

# Start the Vite development server
npm run dev
```
Open your browser at `http://localhost:5173`.

---

## 🧪 Testing & Verification

MEMORA AI includes 15 automated test suites. Execute them using the unified test runner:

```powershell
# List all 15 registered test suites
python backend/run_all_tests.py --list

# Run all test suites
python backend/run_all_tests.py --all

# Run standard suites without live LLM calls (deterministic offline mode)
python backend/run_all_tests.py --skip-live

# Run a specific suite
python backend/run_all_tests.py --suite test_day7_hardening.py

# Verify frontend production build and linting
cd frontend
npm run build
npm run lint
```

Refer to [`docs/TESTING.md`](docs/TESTING.md) for detailed test documentation.

---

## 🌐 Deployment Architecture

MEMORA AI is deployed across two specialized cloud providers:

| Tier | Hosting Service | Configuration File | Purpose |
|---|---|---|---|
| **Frontend** | **Vercel** Static Site | `frontend/vercel.json` | High-speed global edge CDN hosting the React 19 SPA |
| **Backend** | **Render** Web Service | `render.yaml` & `backend/Dockerfile` | Persistent Docker container hosting FastAPI, ASGI connection pooling, and agent DAG execution |
| **Database** | **Neon** Serverless | — | PostgreSQL 16+ with `vector(1024)` |

> [!NOTE]
> **Serverless Backend Compatibility**: The backend is hosted as a persistent container on Render rather than Vercel Serverless because multi-step agent DAG execution, worker lease heartbeats, and crash-resilient checkpoints require long-lived execution contexts that exceed serverless execution limits.

Refer to [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for step-by-step deployment instructions.

---

## 📚 Documentation Index

- [System Architecture Specification](docs/ARCHITECTURE.md)
- [Testing Strategy & Test Suite Guide](docs/TESTING.md)
- [Deployment & Infrastructure Guide](docs/DEPLOYMENT.md)
- [Environment Variables Reference](docs/ENVIRONMENT_VARIABLES.md)

---

## ⚠️ Current Limitations

1. **Vector Dimension Fixed at 1024**: The existing Neon database column `memories.embedding` is `vector(1024)`. Upgrading to 4096 dimensions requires an explicit schema migration and full memory re-embedding.
2. **External LLM Latency**: End-to-end tests calling the external Nebius TokenFactory API are subject to remote upstream provider latency and occasional gateway timeouts. The application incorporates deterministic fallbacks to guarantee uninterrupted operation.

---

## 📄 License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
