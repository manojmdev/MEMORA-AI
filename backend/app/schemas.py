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

class MemoryType(str, Enum):
    PERSONAL_PREFERENCE = "personal_preference"
    TECHNICAL_SKILL = "technical_skill"
    PROJECT_INFO = "project_info"
    GOAL = "goal"
    HABIT = "habit"
    IMPORTANT_EVENT = "important_event"
    TEMPORARY_ACTIVITY = "temporary_activity"
    FUTURE_INTENTION = "future_intention"
    GENERAL_FACT = "general_fact"

class InformationSource(str, Enum):
    EXPLICIT_STATEMENT = "explicit_statement"
    CONTEXTUAL_INFERENCE = "contextual_inference"

class PersistenceType(str, Enum):
    PERSISTENT = "persistent"
    TEMPORARY = "temporary"
    HISTORICAL = "historical"
    FUTURE_INTENTION = "future_intention"

class MemoryStatus(str, Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"
    TENTATIVE = "tentative"

class MemoryCandidate(BaseModel):
    category: str = Field(
        default=MemoryCategory.GENERAL.value,
        description="Category classification for this memory"
    )
    memory_type: str = Field(
        default=MemoryType.GENERAL_FACT.value,
        description="Semantic classification of the memory type"
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
    extraction_confidence: float = Field(
        default=0.90,
        ge=0.0,
        le=1.0,
        description="Confidence specifically in the accuracy of extraction"
    )
    importance_score: float = Field(
        default=0.70,
        ge=0.0,
        le=1.0,
        description="Subjective long-term utility score (low-value messages < 0.40 are discarded)"
    )
    information_source: str = Field(
        default=InformationSource.EXPLICIT_STATEMENT.value,
        description="'explicit_statement' vs 'contextual_inference'"
    )
    persistence_type: str = Field(
        default=PersistenceType.PERSISTENT.value,
        description="'persistent', 'temporary', 'historical', or 'future_intention'"
    )
    fact_status: str = Field(
        default="current",
        description="'current', 'tentative', or 'historical'"
    )
    reason_for_storage: str = Field(
        default="Direct user-provided background information.",
        description="Human-readable explanation of why this was captured"
    )
    valid_until: Optional[datetime] = Field(
        default=None,
        description="Optional expiration timestamp for temporary activities"
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
    memory_type: str = MemoryType.GENERAL_FACT.value
    memory_key: str
    content: str
    confidence_score: float
    importance_score: float = 0.70
    information_source: str = InformationSource.EXPLICIT_STATEMENT.value
    persistence_type: str = PersistenceType.PERSISTENT.value
    memory_status: str = MemoryStatus.ACTIVE.value
    reason_for_storage: Optional[str] = None
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    last_confirmed_at: Optional[datetime] = None
    superseded_by: Optional[UUID] = None
    superseded_reason: Optional[str] = None
    source_message: Optional[str] = None
    is_active: bool = True
    has_embedding: bool = False
    created_at: datetime
    updated_at: datetime

class RetrievalMethod(str, Enum):
    SEMANTIC = "semantic"
    KEYWORD = "keyword"
    HYBRID = "hybrid"

class ScoredMemoryRecord(BaseModel):
    id: UUID
    session_id: str
    category: str
    memory_type: str = MemoryType.GENERAL_FACT.value
    memory_key: str
    content: str
    confidence_score: float
    importance_score: float = 0.70
    information_source: str = InformationSource.EXPLICIT_STATEMENT.value
    persistence_type: str = PersistenceType.PERSISTENT.value
    memory_status: str = MemoryStatus.ACTIVE.value
    reason_for_storage: Optional[str] = None
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    last_confirmed_at: Optional[datetime] = None
    source_message: Optional[str] = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
    retrieval_method: str = "keyword"  # 'semantic' | 'keyword' | 'hybrid'
    similarity_score: float = 1.0       # Raw similarity (e.g. cosine similarity)
    relevance_score: float = 1.0        # Combined normalized relevance score
    retrieval_reason: str = ""          # Human-readable explainability rationale

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
