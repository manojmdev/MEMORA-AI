import logging
import urllib.parse
from typing import Optional, Dict, Any
import asyncpg
from app.config import settings

logger = logging.getLogger(__name__)

# Global connection pool instance and schema state
_pool: Optional[asyncpg.Pool] = None
_schema_initialized: bool = False

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

-- Sprint 2: Advanced Memory Intelligence 2.0 schema additions
ALTER TABLE memories ADD COLUMN IF NOT EXISTS is_archived BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS access_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS last_accessed_at TIMESTAMPTZ;

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

-- Sprint 2: Typed Memory Relationship Graph
CREATE TABLE IF NOT EXISTS memory_relationships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR(255) NOT NULL,
    source_memory_id UUID NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    target_memory_id UUID NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    relationship_type VARCHAR(100) NOT NULL,
    strength DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    metadata_json JSONB DEFAULT '{{}}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_no_self_relationship CHECK (source_memory_id != target_memory_id)
);

CREATE INDEX IF NOT EXISTS idx_mem_rel_session ON memory_relationships (session_id);
CREATE INDEX IF NOT EXISTS idx_mem_rel_source ON memory_relationships (source_memory_id);
CREATE INDEX IF NOT EXISTS idx_mem_rel_target ON memory_relationships (target_memory_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_mem_rel_pair ON memory_relationships (session_id, source_memory_id, target_memory_id, relationship_type);

-- Sprint 2: Memory Consolidation History
CREATE TABLE IF NOT EXISTS memory_consolidations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR(255) NOT NULL,
    consolidated_memory_id UUID REFERENCES memories(id) ON DELETE SET NULL,
    source_memory_ids UUID[] NOT NULL,
    rationale TEXT NOT NULL,
    cluster_topic VARCHAR(255),
    status VARCHAR(50) NOT NULL DEFAULT 'applied',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mem_cons_session ON memory_consolidations (session_id);

-- Sprint 2: Memory Lifecycle Governance & Explainability Audit
CREATE TABLE IF NOT EXISTS memory_lifecycle_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR(255) NOT NULL,
    memory_id UUID NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    reason TEXT,
    actor VARCHAR(100) DEFAULT 'user',
    metadata_json JSONB DEFAULT '{{}}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mem_life_session ON memory_lifecycle_events (session_id);
CREATE INDEX IF NOT EXISTS idx_mem_life_memory ON memory_lifecycle_events (memory_id);

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

-- Day 7.1: Safe task execution leasing & heartbeat columns
ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS worker_id VARCHAR(100);
ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS last_heartbeat_at TIMESTAMPTZ;
ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS execution_lease_expires_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_agent_tasks_session_id ON agent_tasks (session_id);
CREATE INDEX IF NOT EXISTS idx_agent_tasks_status ON agent_tasks (status);
CREATE INDEX IF NOT EXISTS idx_agent_tasks_token_hash ON agent_tasks (approval_token_hash) WHERE approval_token_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_agent_tasks_lease ON agent_tasks (execution_lease_expires_at) WHERE status = 'running';

-- Invalidate legacy pending approvals that lack token hash
UPDATE agent_tasks 
SET approval_status = 'expired', 
    status = 'failed', 
    result_summary = 'Invalidated legacy unhashed approval token on startup migration.' 
WHERE approval_token_hash IS NULL AND approval_status = 'pending';

-- Redact/purge any remaining plaintext tokens from previous versions
UPDATE agent_tasks 
SET approval_token = NULL 
WHERE approval_token IS NOT NULL;

-- Sprint 3: Agent Intelligence 2.0 Task Enhancements & Checkpoints
ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS estimated_complexity VARCHAR(50);
ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS estimated_cost_tier VARCHAR(50);
ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS requires_clarification BOOLEAN DEFAULT FALSE;
ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS clarification_prompt TEXT;

CREATE TABLE IF NOT EXISTS agent_task_checkpoints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES agent_tasks(id) ON DELETE CASCADE,
    session_id VARCHAR(255) NOT NULL,
    step_id VARCHAR(100) NOT NULL,
    tool_name VARCHAR(100),
    arguments_json JSONB DEFAULT '{{}}',
    dependencies TEXT[] DEFAULT '{{}}',
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    error_classification VARCHAR(50),
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 2,
    idempotency_key VARCHAR(128) NOT NULL,
    result_json JSONB,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_task_step_checkpoint UNIQUE (task_id, step_id)
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_task_id ON agent_task_checkpoints (task_id);
CREATE INDEX IF NOT EXISTS idx_checkpoints_session_id ON agent_task_checkpoints (session_id);
CREATE INDEX IF NOT EXISTS idx_checkpoints_status ON agent_task_checkpoints (status);
CREATE INDEX IF NOT EXISTS idx_checkpoints_idempotency ON agent_task_checkpoints (session_id, idempotency_key);

-- Sprint 3.1: Execution Integrity, Worker Fencing & Downstream Reconciliation
ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS lease_generation INTEGER NOT NULL DEFAULT 1;
ALTER TABLE agent_task_checkpoints ADD COLUMN IF NOT EXISTS external_operation_id VARCHAR(255);
ALTER TABLE agent_task_checkpoints ADD COLUMN IF NOT EXISTS lease_generation INTEGER NOT NULL DEFAULT 1;
ALTER TABLE agent_task_checkpoints ADD COLUMN IF NOT EXISTS worker_id VARCHAR(100);
ALTER TABLE agent_task_checkpoints ADD COLUMN IF NOT EXISTS execution_intent_persisted_at TIMESTAMPTZ;
ALTER TABLE notes ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(128);
CREATE INDEX IF NOT EXISTS idx_notes_idempotency ON notes (session_id, idempotency_key);

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

-- Day 7.2: Strict append-only immutability for agent_execution_logs (zero session backdoor)
CREATE OR REPLACE FUNCTION prevent_audit_log_modification()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' AND current_setting('memora.allow_audit_cleanup', true) = 'on' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'agent_execution_logs is an append-only audit table; % operations are forbidden.', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_prevent_audit_modification ON agent_execution_logs;
CREATE TRIGGER trg_prevent_audit_modification
BEFORE UPDATE OR DELETE ON agent_execution_logs
FOR EACH ROW
EXECUTE FUNCTION prevent_audit_log_modification();
"""

def get_clean_dsn(raw_url: str) -> str:
    """Strip query parameters like ?sslmode=... from DSN for asyncpg compatibility."""
    parsed = urllib.parse.urlparse(raw_url)
    return urllib.parse.urlunparse(parsed._replace(query=""))

async def init_db_pool() -> Optional[asyncpg.Pool]:
    """Initialize the asynchronous PostgreSQL connection pool with serverless-safe sizing."""
    global _pool
    if _pool is not None and not _pool._closed:
        return _pool

    if not settings.DATABASE_URL:
        logger.warning("DATABASE_URL is not configured. Database operations will not be available.")
        return None

    clean_dsn = get_clean_dsn(settings.DATABASE_URL)
    min_size = max(1, settings.DB_POOL_MIN_SIZE)
    max_size = max(min_size, settings.DB_POOL_MAX_SIZE)
    cmd_timeout = max(5.0, settings.DB_COMMAND_TIMEOUT)
    logger.info(f"Initializing Neon PostgreSQL connection pool (SSL required, min={min_size}, max={max_size}, timeout={cmd_timeout}s)...")

    try:
        _pool = await asyncpg.create_pool(
            clean_dsn,
            ssl="require",
            min_size=min_size,
            max_size=max_size,
            command_timeout=cmd_timeout,
        )
        logger.info("Neon PostgreSQL connection pool created successfully.")
        
        # Initialize schema if not explicitly skipped
        if not settings.SKIP_SCHEMA_MIGRATIONS:
            await init_db_schema()
        return _pool
    except Exception as e:
        logger.error(f"Failed to create Neon PostgreSQL connection pool: {e}")
        raise

async def init_db_schema() -> None:
    """
    Ensure required database schema and tables exist.
    Uses a PostgreSQL transaction-level advisory lock (pg_advisory_xact_lock) to ensure
    safe distributed concurrency across multiple serverless cold-starts, while releasing
    the lock automatically at transaction end for PgBouncer/Neon compatibility.
    """
    global _schema_initialized
    if _schema_initialized:
        return

    pool = await get_db_pool()
    if pool is None:
        return

    # Unique 64-bit advisory lock key for MEMORA AI schema initialization
    MIGRATION_ADVISORY_LOCK_ID = 84729104

    async with pool.acquire() as conn:
        logger.info("Acquiring distributed PostgreSQL advisory lock for schema initialization...")
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock($1);", MIGRATION_ADVISORY_LOCK_ID)
            logger.info("Executing initial schema migrations with distributed lock held...")
            await conn.execute(CREATE_MEMORIES_TABLE_SQL)
        _schema_initialized = True
        logger.info("Schema migrations applied and distributed lock released.")

async def close_db_pool() -> None:
    """Gracefully close the PostgreSQL connection pool."""
    global _pool, _schema_initialized
    if _pool is not None:
        logger.info("Closing Neon PostgreSQL connection pool...")
        await _pool.close()
        _pool = None
        _schema_initialized = False
        logger.info("Neon PostgreSQL connection pool closed.")

async def get_db_pool() -> Optional[asyncpg.Pool]:
    """Get the active connection pool, initializing or reconnecting it if needed."""
    global _pool
    if (_pool is None or _pool._closed) and settings.DATABASE_URL:
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

async def recover_interrupted_tasks(stale_threshold_minutes: int = 10) -> int:
    """
    Day 7.1: Sweep tasks left in 'running' status across restarts or abnormal termination.
    Uses a safe lease/heartbeat expiration model:
    Only recovers tasks where:
      - status = 'running' AND
      - (execution_lease_expires_at < NOW() OR (execution_lease_expires_at IS NULL AND updated_at < NOW() - INTERVAL '10 minutes'))
    Preserves actively executing tasks owned by live workers with valid leases.
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
                    result_summary = 'Task execution interrupted: worker lease expired or unexpected shutdown.',
                    execution_lease_expires_at = NULL,
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE status = 'running'
                  AND (
                    (execution_lease_expires_at IS NOT NULL AND execution_lease_expires_at < NOW())
                    OR
                    (execution_lease_expires_at IS NULL AND updated_at < NOW() - ($1 || ' minutes')::INTERVAL)
                  )
                """,
                str(stale_threshold_minutes),
            )
            count = int(result.split()[-1]) if result else 0
            if count > 0:
                logger.info(f"Recovered {count} stale interrupted agent tasks with expired leases.")
            return count
    except Exception as e:
        logger.error(f"Failed to recover interrupted tasks: {e}")
        return 0
