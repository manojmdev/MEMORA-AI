# MEMORA AI — Vercel-Only Deployment & Infrastructure Guide

## 1. Production Architecture Overview

MEMORA AI is deployed exclusively on **Vercel** with a serverless architecture designed for high availability, zero persistent server costs, and global edge distribution:

```mermaid
flowchart LR
    Client([User Browser]) -->|Static Assets & SPA| VercelFE[Vercel Static Edge - Frontend SPA]
    Client -->|REST & Slices API| VercelBE[Vercel Serverless Functions - Python ASGI]
    VercelBE -->|Pooled Wire Protocol| Neon[(Neon Serverless PostgreSQL + pgvector)]
    VercelBE -->|HTTPS API| Nebius[Nebius TokenFactory LLM & Embeddings]
```

- **Frontend**: Hosted on **Vercel** as a high-performance static Single Page Application (React 19 + Vite 8).
- **Backend**: Hosted on **Vercel Serverless Functions** (`api/index.py` exporting the FastAPI ASGI application).
- **Database & Vectors**: Hosted on **Neon Serverless PostgreSQL** with `pgvector` (`vector(1024)`).
- **Inference**: Hosted on **Nebius TokenFactory** (`nvidia/Nemotron-3_5-Lightning` and `Qwen/Qwen3-Embedding-8B`).
- **Scheduling**: Automated stale task recovery driven by **Vercel Cron Jobs** (`/api/agent/cron/recover`).

---

## 2. Serverless Architecture & Execution Model

In traditional persistent servers (such as Render or Docker containers), background worker threads run indefinitely. In Vercel serverless functions, execution halts immediately when an HTTP response is delivered.

To guarantee rock-solid execution without paid external queue services, MEMORA AI implements **Bounded Agent Execution Slices**:

1. **Durable State in PostgreSQL**: All agent tasks, plans, and step-level checkpoints are committed to Neon PostgreSQL as the single source of truth.
2. **Durable Task Creation (`POST /api/agent/tasks`)**: Intent analysis, memory retrieval, plan generation, and policy validation run synchronously. The task and its initial step checkpoints are persisted in PostgreSQL. A durable task ID is returned immediately.
3. **Bounded Execution Slices (`POST /api/agent/tasks/{task_id}/step`)**: The client or scheduler invokes step execution slices. Each invocation:
   - Claims an atomic lease with a monotonic fencing generation (`lease_generation`).
   - Executes ready step(s) within a strict time budget (< 20 seconds, well within Vercel timeout limits).
   - Checkpoints step results transactionally in Neon PostgreSQL before returning.
4. **Client-Driven Slicing Loop**: The frontend drives sequential execution slices while the task is active, updating the UI in real time.
5. **Idempotency & Crash Resilience**: If a slice is interrupted by a network blip or cold start, the next invocation inspects PostgreSQL checkpoints and skips already-completed steps idempotently.

---

## 3. Step-by-Step Vercel Deployment Guide

### 3.1 GitHub Repository Connection
1. Log into your [Vercel Dashboard](https://vercel.com/dashboard).
2. Click **Add New...** → **Project**.
3. Import your GitHub repository: `https://github.com/manojmdev/MEMORA AI` (or your repository fork).

### 3.2 Vercel Project Root Selection
MEMORA AI supports two deployment configurations:

#### Option A: Unified Full-Stack Project (Recommended)
- **Root Directory**: Select repository root (`.`).
- **Framework Preset**: Select `Vite` or `Other`.
- **Build Command**: `npm --prefix frontend run build` (configured in root `vercel.json`).
- **Output Directory**: `frontend/dist` (configured in root `vercel.json`).
- Both the frontend SPA and the Python backend (`api/index.py`) deploy together in a single Vercel project sharing the same domain.

#### Option B: Decoupled Multi-Project
- **Frontend Project**: Root directory `frontend`. Framework preset `Vite`. Set `VITE_API_BASE_URL` to the backend Vercel project URL.
- **Backend Project**: Root directory `.`. Deploys the Python serverless function at `/api`.

### 3.3 Backend Environment Variables (Vercel Project Settings)
In the Vercel Project Settings, navigate to **Settings** → **Environment Variables** and configure:

| Variable | Required | Value / Format | Description |
|---|---|---|---|
| `DATABASE_URL` | **Yes** | `postgresql://user:pass@ep-xyz-pooler.region.neon.tech/neondb?sslmode=require` | Neon pooled connection string (PgBouncer `-pooler` endpoint). |
| `NEBIUS_API_KEY` | **Yes** | `your_nebius_api_key` | Nebius TokenFactory API Key. |
| `NEBIUS_BASE_URL` | No | `https://api.tokenfactory.nebius.com/v1` | Nebius API endpoint. |
| `NEBIUS_MODEL` | No | `nvidia/Nemotron-3_5-Lightning` | Primary LLM for chat & planning. |
| `NEBIUS_EMBEDDING_MODEL`| No | `Qwen/Qwen3-Embedding-8B` | Embedding model name. |
| `EMBEDDING_DIMENSION` | **Yes** | `1024` | Must match Neon `vector(1024)` column. |
| `EMBEDDING_DIM` | No | `1024` | Alias for `EMBEDDING_DIMENSION`. |
| `ENVIRONMENT` | **Yes** | `production` | Production mode lock. |
| `FRONTEND_ORIGIN` | No | `https://your-project.vercel.app` | Allowed CORS origin (Vercel previews are auto-matched via regex). |
| `AUTH_SECRET_KEY` | **Yes** | 64-char hex string | HMAC authentication & approval signature secret. |
| `CRON_SECRET` | Recommended | Random secret string | Authorizes Vercel Cron on `/api/agent/cron/recover`. |
| `DB_POOL_MIN_SIZE` | No | `1` | Serverless connection pool minimum. |
| `DB_POOL_MAX_SIZE` | No | `3` | Serverless connection pool maximum. |
| `ENABLE_BACKGROUND_EMBEDDING_BACKFILL` | No | `false` | Disabled on serverless to prevent dangling background tasks. |

> [!IMPORTANT]
> **Neon Connection String**: Always use the Neon **Pooled** connection string (containing `-pooler` in the host). This routes connections through Neon's PgBouncer proxy, preventing ephemeral serverless functions from exhausting database connection limits.

### 3.4 Frontend Environment Variables
| Variable | Required | Value |
|---|---|---|
| `VITE_API_BASE_URL` | Conditional | Leave blank or unset for Unified deployment (`/` relative requests). Set to backend URL (e.g. `https://memora-ai-api.vercel.app`) if using decoupled projects. |

> [!WARNING]
> **No Secrets in Frontend**: Never place `NEBIUS_API_KEY`, `DATABASE_URL`, or `AUTH_SECRET_KEY` in frontend environment variables.

### 3.5 Neon PostgreSQL Connectivity
- The database schema is fully provisioned in Neon with `pgvector(1024)`.
- SSL is required (`?sslmode=require`).
- `asyncpg` manages connections using adaptive connection pooling with connection timeouts.

### 3.6 Nebius TokenFactory Connectivity
- Validates model availability for `nvidia/Nemotron-3_5-Lightning` and `Qwen/Qwen3-Embedding-8B`.
- Exponential backoff retry logic is built into all client requests.

### 3.7 CORS Configuration
- `backend/app/main.py` enforces CORS with origin matching and preview-branch regex:
  `allow_origin_regex=r"^https:\/\/.*\.vercel\.app$"`
- All preview and production deployments on `*.vercel.app` are allowed out-of-the-box.

### 3.8 Health Verification
Verify deployment health:
```bash
curl -f https://your-project.vercel.app/health
```
Expected response:
```json
{
  "status": "healthy",
  "database": {
    "status": "healthy",
    "connected": true,
    "provider": "Neon Lakebase Postgres"
  }
}
```

### 3.9 Agent Task Execution Verification
Test task initialization and stepwise execution:
```bash
# 1. Create a task
curl -X POST https://your-project.vercel.app/api/agent/tasks \
  -H "Content-Type: application/json" \
  -d '{"session_id": "verify-session", "instruction": "Calculate 50 * 20"}'

# 2. Step the task slice
curl -X POST "https://your-project.vercel.app/api/agent/tasks/<TASK_ID>/step?session_id=verify-session"
```

### 3.10 Known Vercel Execution & Scheduling Limitations

> [!CAUTION]
> **Unattended Execution Limitation**:
> Because Vercel serverless functions terminate execution when an HTTP response is delivered, agent tasks require either:
> 1. An active connected client driving execution slices (the default user experience when the browser is open), OR
> 2. Scheduled Vercel Cron invocations (`GET /api/agent/cron/recover`) to sweep and advance tasks.
>
> **If the user closes their browser and disconnects**, the task will safely pause at its latest committed checkpoint in Neon PostgreSQL. It will **not** continue executing in the background unattended until the user returns or a cron trigger fires.

---

## 4. Local Development with Docker

The containerized Docker development environment is preserved for local development:
```bash
docker build -t memora-backend -f backend/Dockerfile .
docker run -p 8000:8000 --env-file backend/.env memora-backend
```
Render deployment configuration (`render.yaml`) is maintained in the repository for historical continuity.
