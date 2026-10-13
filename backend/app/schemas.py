from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, field_validator

class MemoryCategory(str, Enum):
    PREFERENCES = "preferences"
    SKILLS = "skills"
    GOALS = "goals"
    PROJECTS = "projects"
    PERSONAL_CONTEXT = "personal_context"
    LEARNING_STYLE = "learning_style"
    GENERAL = "general"

class MemoryCandidate(BaseModel):
    category: str = Field(
        default=MemoryCategory.GENERAL.value,
        description="Category classification for this memory"
    )
    memory_key: str = Field(
        min_length=1,
        max_length=255,
        description="Normalized key/slug identifying the fact (e.g. preferred_language, active_project)"
    )
    content: str = Field(
        min_length=1,
        max_length=5000,
        description="Factual, concise description of the memory"
    )
    confidence_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0 (explicit statements >= 0.9, inferences 0.5-0.85)"
    )
    source_message: Optional[str] = Field(
        default=None,
        description="The source user message segment that gave rise to this memory"
    )

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        valid_cats = {cat.value for cat in MemoryCategory}
        normalized = v.strip().lower()
        if normalized in valid_cats:
            return normalized
        return MemoryCategory.GENERAL.value

    @field_validator("memory_key")
    @classmethod
    def normalize_key(cls, v: str) -> str:
        normalized = v.strip().lower().replace(" ", "_").replace("-", "_")
        # Strip non-alphanumeric except underscores
        clean_key = "".join(c for c in normalized if c.isalnum() or c == "_")
        return clean_key or "general_fact"

class ExtractionResult(BaseModel):
    candidates: List[MemoryCandidate] = Field(
        default_factory=list,
        description="List of candidate memories extracted from the interaction"
    )

class MemoryRecord(BaseModel):
    id: UUID
    session_id: str
    category: str
    memory_key: str
    content: str
    confidence_score: float
    source_message: Optional[str] = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

class UpdateMemoryRequest(BaseModel):
    content: Optional[str] = Field(default=None, min_length=1, max_length=5000)
    confidence_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    category: Optional[str] = None
    is_active: Optional[bool] = None

class MemoryListResponse(BaseModel):
    session_id: str
    count: int
    memories: List[MemoryRecord]

class DeleteResponse(BaseModel):
    session_id: str
    message: str
    deleted_count: int

class ChatRequest(BaseModel):
    message: str = Field(
        min_length=1,
        max_length=10000
    )
    session_id: str = Field(
        default="default-session",
        min_length=1,
        max_length=255,
        description="Session identifier to isolate memories across users"
    )

class ChatResponse(BaseModel):
    reply: str
    model: str
    session_id: str
    memories_recalled: List[Dict[str, Any]] = Field(default_factory=list)
    memories_extracted: List[Dict[str, Any]] = Field(default_factory=list)
