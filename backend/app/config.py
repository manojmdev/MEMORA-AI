import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

# Path to backend/.env
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

class Settings(BaseSettings):
    NEBIUS_API_KEY: str = ""
    NEBIUS_BASE_URL: str = "https://api.tokenfactory.nebius.com/v1"
    NEBIUS_MODEL: str = "nvidia/Nemotron-3_5-Lightning"
    FRONTEND_ORIGIN: str = "http://localhost:5173"
    DATABASE_URL: str = ""
    DATABASE_URL_UNPOOLED: str = ""

    # Day 4: Semantic and Hybrid Retrieval
    EMBEDDING_MODEL: str = "Qwen/Qwen3-Embedding-8B"
    NEBIUS_EMBEDDING_MODEL: Optional[str] = None
    EMBEDDING_DIMENSION: int = 1024
    EMBEDDING_DIM: Optional[int] = None
    EMBEDDING_API_BASE_URL: str = "https://api.tokenfactory.nebius.com/v1"
    SIMILARITY_THRESHOLD: float = 0.58
    KEYWORD_WEIGHT: float = 0.50
    SEMANTIC_WEIGHT: float = 0.50
    HYBRID_LIMIT: int = 5
    # Day 7: Environment & Production Safety Gates
    ENVIRONMENT: str = "development"
    ENABLE_EVALUATION_ENDPOINT: bool = False

    # Day 7.2: Genuine Authentication & Worker Lease Configuration
    AUTH_SECRET_KEY: Optional[str] = None
    API_AUTH_TOKENS: Optional[str] = None  # Format: "token:user_id:session_id,..."
    WORKER_LEASE_MINUTES: int = 5
    WORKER_LEASE_SECONDS: int = 60
    CRON_SECRET: Optional[str] = None

    # Serverless & Connection Pool Configuration
    DB_POOL_MIN_SIZE: int = 1
    DB_POOL_MAX_SIZE: int = 3
    DB_COMMAND_TIMEOUT: float = 30.0
    ENABLE_BACKGROUND_EMBEDDING_BACKFILL: bool = False
    SKIP_SCHEMA_MIGRATIONS: bool = False

    model_config = SettingsConfigDict(
        env_file=(str(ENV_FILE), ".env", str(Path(__file__).resolve().parent.parent.parent / ".env.local")),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
