import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.schemas import ChatRequest, ChatResponse
from app.services.llm_service import generate_response
from app.database import init_db_pool, close_db_pool, check_db_health

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting MEMORA AI API...")
    try:
        await init_db_pool()
    except Exception as e:
        logger.error(f"Database pool initialization warning: {e}")
    yield
    logger.info("Shutting down MEMORA AI API...")
    await close_db_pool()

app = FastAPI(
    title="MEMORA AI API",
    description="Private AI Memory and Agent Intelligence Platform",
    version="0.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN, "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {
        "message": "Welcome to MEMORA AI API",
        "status": "running"
    }

@app.get("/health")
async def health():
    db_health = await check_db_health()
    is_healthy = db_health.get("status") == "healthy"
    return {
        "status": "healthy" if is_healthy else "degraded",
        "database": db_health
    }

@app.post("/api/chat", response_model=ChatResponse)
@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        reply = await generate_response(request.message)
        return ChatResponse(reply=reply, model=settings.NEBIUS_MODEL)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
