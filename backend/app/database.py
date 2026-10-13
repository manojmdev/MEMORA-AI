import logging
import urllib.parse
from typing import Optional, Dict, Any
import asyncpg
from app.config import settings

logger = logging.getLogger(__name__)

# Global connection pool instance
_pool: Optional[asyncpg.Pool] = None

CREATE_MEMORIES_TABLE_SQL = """
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
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_session_memory_key UNIQUE (session_id, memory_key)
);

CREATE INDEX IF NOT EXISTS idx_memories_session_id ON memories (session_id);
CREATE INDEX IF NOT EXISTS idx_memories_category ON memories (category);
CREATE INDEX IF NOT EXISTS idx_memories_session_active ON memories (session_id, is_active);
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
            "error": str(e)
        }
