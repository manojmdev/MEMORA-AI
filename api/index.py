"""
MEMORA AI — Vercel Serverless Entrypoint
Exposes the FastAPI ASGI application for Vercel Python Serverless Functions.
"""
import sys
import os
from pathlib import Path

# Add backend and repository root directories to sys.path
root_dir = Path(__file__).resolve().parent.parent
backend_dir = root_dir / "backend"

if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

# Configure serverless defaults if not already set in environment
os.environ.setdefault("DB_POOL_MIN_SIZE", "1")
os.environ.setdefault("DB_POOL_MAX_SIZE", "3")
os.environ.setdefault("ENABLE_BACKGROUND_EMBEDDING_BACKFILL", "false")

from app.main import app

# Export ASGI application for Vercel Python runtime
__all__ = ["app"]
