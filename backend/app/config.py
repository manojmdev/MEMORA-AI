import os
from pathlib import Path
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
    EMBEDDING_DIMENSION: int = 1024
    EMBEDDING_API_BASE_URL: str = "https://api.tokenfactory.nebius.com/v1"
    SIMILARITY_THRESHOLD: float = 0.58
    KEYWORD_WEIGHT: float = 0.50
    SEMANTIC_WEIGHT: float = 0.50
    HYBRID_LIMIT: int = 5

    model_config = SettingsConfigDict(
        env_file=(str(ENV_FILE), ".env", str(Path(__file__).resolve().parent.parent.parent / ".env.local")),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
