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

    model_config = SettingsConfigDict(
        env_file=(str(ENV_FILE), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
