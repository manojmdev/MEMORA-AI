import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.schemas import ChatRequest, ChatResponse
from app.services.llm_service import generate_response

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="MEMORA AI API",
    description="Private AI Memory and Agent Intelligence Platform",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

@app.get("/")
async def root():
    return {
        "message": "Welcome to MEMORA AI API",
        "status": "running"
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy"
    }

@app.post("/api/chat", response_model=ChatResponse)
@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        reply = await generate_response(request.message)
        return ChatResponse(reply=reply, model=settings.NEBIUS_MODEL)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

