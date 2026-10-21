# MEMORA AI — Environment Variables Reference

This document provides a comprehensive, production-audited catalog of all environment variables supported by the MEMORA AI backend and frontend applications.

---

## 1. Backend Environment Variables (`backend/.env`)

| Variable | Type | Required | Default | Security | Description |
|---|---|---|---|---|---|
| `DATABASE_URL` | string | **Yes** | — | **Secret** | Pooled PostgreSQL connection string for application runtime (e.g., Neon pooled endpoint). |
| `DATABASE_URL_UNPOOLED` | string | No | `""` | **Secret** | Direct unpooled PostgreSQL connection string for migrations and DDL commands. |
| `NEBIUS_API_KEY` | string | **Yes** | — | **Secret** | API key for Nebius TokenFactory LLM and embedding inference services. |
| `NEBIUS_BASE_URL` | string | No | `https://api.tokenfactory.nebius.com/v1` | Public | Base endpoint URL for Nebius OpenAI-compatible API. |
| `NEBIUS_MODEL` | string | No | `nvidia/Nemotron-3_5-Lightning` | Public | Main language model for chat reasoning, memory extraction, and agent planning. |
| `EMBEDDING_MODEL` | string | No | `Qwen/Qwen3-Embedding-8B` | Public | Model name for vector embedding generation. |
| `NEBIUS_EMBEDDING_MODEL` | string | No | `None` | Public | Optional alias for embedding model name. |
| `EMBEDDING_DIMENSION` | integer | No | `1024` | Public | Vector embedding dimensionality. Must strictly match Neon `vector(1024)` column. |
| `EMBEDDING_DIM` | integer | No | `None` | Public | Deployment alias for `EMBEDDING_DIMENSION`. |
| `EMBEDDING_API_BASE_URL` | string | No | `https://api.tokenfactory.nebius.com/v1` | Public | Dedicated endpoint for embedding inference requests. |
| `SIMILARITY_THRESHOLD` | float | No | `0.58` | Public | Minimum cosine similarity cutoff for vector memory retrieval. |
| `KEYWORD_WEIGHT` | float | No | `0.50` | Public | Weight multiplier for full-text search BM25 score in hybrid RRF fusion. |
| `SEMANTIC_WEIGHT` | float | No | `0.50` | Public | Weight multiplier for vector similarity score in hybrid RRF fusion. |
| `HYBRID_LIMIT` | integer | No | `5` | Public | Maximum number of memories retrieved per hybrid search query. |
| `FRONTEND_ORIGIN` | string | No | `http://localhost:5173` | Sensitive | Allowed origin for FastAPI CORS middleware (e.g. `https://memora-ai.vercel.app`). |
| `ENVIRONMENT` | string | No | `development` | Public | Environment gate (`development`, `staging`, `production`). In production, docs & debug details are locked. |
| `ENABLE_EVALUATION_ENDPOINT`| boolean| No | `false` | Sensitive | Controls whether `/api/evaluate` benchmark endpoint is accessible. Must be `false` in production. |
| `AUTH_SECRET_KEY` | string | Recommended| `None` | **Secret** | 32+ character random secret used for HMAC-SHA256 signature generation and approval tokens. |
| `API_AUTH_TOKENS` | string | No | `None` | **Secret** | Static pre-shared token map format: `"token:user_id:session_id,..."`. |
| `WORKER_LEASE_MINUTES` | integer | No | `5` | Public | Duration in minutes of distributed agent worker lease before being marked stale and reclaimable. |

---

## 2. Frontend Environment Variables (`frontend/.env`)

| Variable | Type | Required | Default | Security | Description |
|---|---|---|---|---|---|
| `VITE_API_BASE_URL` | string | **Yes** | `http://localhost:8000` | Public | Base HTTP URL of the backend API. Note: Vite bundles this into client-side JS; **never place API keys or secrets in VITE_ variables**. |

---

## 3. Security Best Practices

> [!WARNING]
> **Zero Secrets in Frontend**: `VITE_` variables are baked into browser-downloaded JavaScript bundles. Never expose `NEBIUS_API_KEY`, `DATABASE_URL`, or `AUTH_SECRET_KEY` in frontend environment variables.

> [!IMPORTANT]
> **Production Vector Dimension Constraint**: The database column `memories.embedding` was provisioned as `vector(1024)`. All deployment manifests (`render.yaml`, Docker, local `.env`) must set `EMBEDDING_DIMENSION=1024`. Setting `4096` will cause runtime database insertion rejections.

> [!TIP]
> **Generating AUTH_SECRET_KEY**:
> You can generate a secure random secret key with:
> ```powershell
> python -c "import secrets; print(secrets.token_hex(32))"
> ```
