import logging
import urllib.parse
from typing import Optional, Dict, Any
import asyncpg
from app.config import settings

logger = logging.getLogger(__name__)

# Global connection pool instance
_pool: Optional[asyncpg.Pool] = None

CREATE_MEMORIES_TABLE_SQL = f"""
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR(255) NOT NULL,
    category VARCHAR(100) NOT NULL DEFAULT 'general',
    memory_key VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    confidence_score DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    source_message TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Safe idempotent column addition for pgvector
ALTER TABLE memories ADD COLUMN IF NOT EXISTS embedding vector({settings.EMBEDDING_DIMENSION});

-- Safe idempotent column additions for Day 5: Temporal memory and explainability
ALTER TABLE memories ADD COLUMN IF NOT EXISTS valid_from TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE memories ADD COLUMN IF NOT EXISTS valid_until TIMESTAMPTZ;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS last_confirmed_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE memories ADD COLUMN IF NOT EXISTS persistence_type VARCHAR(50) DEFAULT 'persistent';
ALTER TABLE memories ADD COLUMN IF NOT EXISTS memory_status VARCHAR(50) DEFAULT 'active';
ALTER TABLE memories ADD COLUMN IF NOT EXISTS memory_type VARCHAR(50) DEFAULT 'general_fact';
ALTER TABLE memories ADD COLUMN IF NOT EXISTS information_source VARCHAR(50) DEFAULT 'explicit_statement';
ALTER TABLE memories ADD COLUMN IF NOT EXISTS importance_score DOUBLE PRECISION DEFAULT 0.70;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS reason_for_storage TEXT;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS superseded_by UUID;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS superseded_reason TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_session_active_memory_key 
ON memories (session_id, memory_key) 
WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_memories_session_id ON memories (session_id);
CREATE INDEX IF NOT EXISTS idx_memories_category ON memories (category);
CREATE INDEX IF NOT EXISTS idx_memories_session_active ON memories (session_id, is_active);
CREATE INDEX IF NOT EXISTS idx_memories_status_valid ON memories (session_id, memory_status, is_active);

-- HNSW cosine distance index for sub-millisecond semantic similarity search
CREATE INDEX IF NOT EXISTS idx_memories_embedding 
ON memories USING hnsw (embedding vector_cosine_ops) 
WHERE is_active = TRUE;

-- Day 6: Agentic Task Execution & Notes Storage
CREATE TABLE IF NOT EXISTS notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR(255) NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notes_session_id ON notes (session_id);
-- Day 7: Idempotent uniqueness index for notes using MD5 hash of text to prevent B-tree row limit issues
CREATE UNIQUE INDEX IF NOT EXISTS uq_notes_session_title_content 
ON notes (session_id, md5(title), md5(content));

CREATE TABLE IF NOT EXISTS agent_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR(255) NOT NULL,
    user_request TEXT NOT NULL,
    task_type VARCHAR(100),
    plan_json JSONB,
    status VARCHAR(50) NOT NULL DEFAULT 'proposed',
    result_summary TEXT,
    approval_token VARCHAR(255),
    approval_status VARCHAR(50),
    approval_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- Day 7: Idempotent column addition for secure approval token hashing
ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS approval_token_hash VARCHAR(64);

CREATE INDEX IF NOT EXISTS idx_agent_tasks_session_id ON agent_tasks (session_id);
CREATE INDEX IF NOT EXISTS idx_agent_tasks_status ON agent_tasks (status);
CREATE INDEX IF NOT EXISTS idx_agent_tasks_token_hash ON agent_tasks (approval_token_hash) WHERE approval_token_hash IS NOT NULL;

CREATE TABLE IF NOT EXISTS agent_execution_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES agent_tasks(id) ON DELETE CASCADE,
    session_id VARCHAR(255) NOT NULL,
    step_id VARCHAR(100),
    tool_name VARCHAR(100) NOT NULL,
    arguments_json JSONB,
    status VARCHAR(50) NOT NULL,
    approval_status VARCHAR(50),
    result_summary TEXT,
    error_code VARCHAR(100),
    duration_ms INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_logs_task_id ON agent_execution_logs (task_id);
CREATE INDEX IF NOT EXISTS idx_agent_logs_session_id ON agent_execution_logs (session_id);
"""

def get_clean_dsn(raw_url: str) -> str:
    """Strip query parameters like ?sslmode=... from DSN for asyncpg compatibility."""
    parsed = urllib.parse.urlparse(raw_url)
    return urllib.parse.urlunparse(parsed._replace(query=""))

async def init_db_pool() -> Optional[asyncpg.Pool]:
    """Initialize the asynchronous PostgreSQL connection pool."""
    global _pool
    if _pool is not None:
        return _pool

    if not settings.DATABASE_URL:
        logger.warning("DATABASE_URL is not configured. Database operations will not be available.")
        return None

    clean_dsn = get_clean_dsn(settings.DATABASE_URL)
    logger.info("Initializing Neon PostgreSQL connection pool (SSL required)...")

    try:
        _pool = await asyncpg.create_pool(
            clean_dsn,
            ssl="require",
            min_size=1,
            max_size=10,
            command_timeout=30.0,
        )
        logger.info("Neon PostgreSQL connection pool created successfully.")
        
        # Initialize schema
        await init_db_schema()
        return _pool
    except Exception as e:
        logger.error(f"Failed to create Neon PostgreSQL connection pool: {e}")
        raise

async def init_db_schema() -> None:
    """Ensure required database schema and tables exist."""
    pool = await get_db_pool()
    if pool is None:
        return

    async with pool.acquire() as conn:
        logger.info("Executing initial schema migrations (memories table)...")
        await conn.execute(CREATE_MEMORIES_TABLE_SQL)
        logger.info("Schema migrations applied successfully.")

async def close_db_pool() -> None:
    """Gracefully close the PostgreSQL connection pool."""
    global _pool
    if _pool is not None:
        logger.info("Closing Neon PostgreSQL connection pool...")
        await _pool.close()
        _pool = None
        logger.info("Neon PostgreSQL connection pool closed.")

async def get_db_pool() -> Optional[asyncpg.Pool]:
    """Get the active connection pool, initializing it if needed."""
    global _pool
    if _pool is None and settings.DATABASE_URL:
        await init_db_pool()
    return _pool

async def check_db_health() -> Dict[str, Any]:
    """Perform a database health check and return connectivity metrics."""
    pool = await get_db_pool()
    if pool is None:
        return {
            "status": "unavailable",
            "reason": "DATABASE_URL not configured or pool not initialized"
        }

    try:
        async with pool.acquire() as conn:
            val = await conn.fetchval("SELECT 1")
            return {
                "status": "healthy",
                "connected": val == 1,
                "provider": "Neon Lakebase Postgres",
                "pool_size": pool.get_size(),
                "free_connections": pool.get_idle_size()
            }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": "Database connectivity check failed"
        }

async def recover_interrupted_tasks() -> int:
    """
    Day 7: Sweep tasks left in 'running' status across restarts or abnormal termination.
    Transitions stale running tasks to 'failed' to prevent hanging states.
    """
    pool = await get_db_pool()
    if pool is None:
        return 0

    try:
        async with pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE agent_tasks
                SET status = 'failed',
                    result_summary = 'Task execution interrupted by server restart or unexpected shutdown.',
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE status = 'running'
                """
            )
            count = int(result.split()[-1]) if result else 0
            if count > 0:
                logger.info(f"Recovered {count} interrupted agent tasks on startup.")
            return count
    except Exception as e:
        logger.error(f"Failed to recover interrupted tasks: {e}")
        return 0
