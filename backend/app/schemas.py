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
    is_archived: bool = False
    archived_at: Optional[datetime] = None
    access_count: int = 0
    last_accessed_at: Optional[datetime] = None
    has_embedding: bool = False
    created_at: datetime
    updated_at: datetime

class RetrievalMethod(str, Enum):
    SEMANTIC = "semantic"
    KEYWORD = "keyword"
    HYBRID = "hybrid"
    GRAPH_ASSISTED = "graph_assisted"

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
    is_archived: bool = False
    created_at: datetime
    updated_at: datetime
    retrieval_method: str = "keyword"  # 'semantic' | 'keyword' | 'hybrid' | 'graph_assisted'
    similarity_score: float = 1.0       # Raw similarity (e.g. cosine similarity)
    relevance_score: float = 1.0        # Combined normalized relevance score
    retrieval_reason: str = ""          # Human-readable explainability rationale
    graph_boost: float = 0.0            # Contextual relationship graph proximity boost
    recency_score: float = 1.0          # Time-decay recency multiplier
    score_breakdown: Dict[str, float] = Field(default_factory=dict) # Explicit breakdown of score components

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

# ============================================================================
# SPRINT 2: ADVANCED MEMORY INTELLIGENCE 2.0 SCHEMAS
# ============================================================================

class RelationshipType(str, Enum):
    USES = "uses"
    PREFERS = "prefers"
    BELONGS_TO = "belongs_to"
    APPLIED_IN = "applied_in"
    SUPERSEDES = "supersedes"
    RELATES_TO = "relates_to"
    DEPENDS_ON = "depends_on"
    CONTRADICTS = "contradicts"
    DERIVED_FROM = "derived_from"
    CONSOLIDATED_INTO = "consolidated_into"

class MemoryRelationshipRecord(BaseModel):
    id: UUID
    session_id: str
    source_memory_id: UUID
    target_memory_id: UUID
    relationship_type: str
    strength: float = 1.0
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

class CreateRelationshipRequest(BaseModel):
    source_memory_id: UUID
    target_memory_id: UUID
    relationship_type: str = Field(
        default=RelationshipType.RELATES_TO.value,
        description="Type of relationship: uses, prefers, belongs_to, applied_in, supersedes, relates_to, depends_on, contradicts, derived_from, consolidated_into"
    )
    strength: float = Field(default=1.0, ge=0.0, le=1.0, description="Strength of connection between 0.0 and 1.0")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)

class ConnectedMemoryNode(BaseModel):
    memory: MemoryRecord
    relationship: MemoryRelationshipRecord
    direction: str  # 'outgoing' | 'incoming'
    relationship_type: Optional[str] = None
    strength: Optional[float] = None

    def model_post_init(self, __context: Any) -> None:
        if self.relationship_type is None and self.relationship:
            self.relationship_type = self.relationship.relationship_type
        if self.strength is None and self.relationship:
            self.strength = self.relationship.strength

class MemoryGraphResponse(BaseModel):
    session_id: str
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]

# Consolidation
class ConsolidationCandidateGroup(BaseModel):
    cluster_id: str
    topic: str
    source_memory_ids: List[UUID]
    source_memories: List[MemoryRecord]
    proposed_content: str
    proposed_key: str
    proposed_category: str
    rationale: str
    preserved_facts: List[str] = Field(default_factory=list)
    confidence_score: float = 0.90
    is_contradictory: bool = False
    cluster_topic: Optional[str] = None
    proposed_consolidated_content: Optional[str] = None
    consolidation_rationale: Optional[str] = None
    avg_similarity: float = 0.85

    def model_post_init(self, __context: Any) -> None:
        if self.cluster_topic is None:
            self.cluster_topic = self.topic
        if self.proposed_consolidated_content is None:
            self.proposed_consolidated_content = self.proposed_content
        if self.consolidation_rationale is None:
            self.consolidation_rationale = self.rationale

class ConsolidationPreviewResponse(BaseModel):
    session_id: str
    total_active_memories: int
    proposed_clusters: List[ConsolidationCandidateGroup] = Field(default_factory=list)
    candidate_groups: List[ConsolidationCandidateGroup] = Field(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        if not self.candidate_groups and self.proposed_clusters:
            self.candidate_groups = self.proposed_clusters
        elif not self.proposed_clusters and self.candidate_groups:
            self.proposed_clusters = self.candidate_groups

class ApplyConsolidationRequest(BaseModel):
    source_memory_ids: List[UUID]
    consolidated_content: str
    consolidated_key: Optional[str] = None
    consolidated_category: Optional[str] = None
    rationale: Optional[str] = None
    session_id: Optional[str] = None
    cluster_topic: Optional[str] = None

class ApplyConsolidationResponse(BaseModel):
    session_id: str
    consolidation_id: UUID
    new_memory: MemoryRecord
    consolidated_memory_ids: List[UUID]
    message: str

# Lifecycle
class LifecycleEventType(str, Enum):
    CREATED = "created"
    UPDATED = "updated"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"
    ARCHIVED = "archived"
    RESTORED = "restored"
    FORGOTTEN = "forgotten"
    CONSOLIDATED = "consolidated"

class MemoryLifecycleEventRecord(BaseModel):
    id: UUID
    session_id: str
    memory_id: UUID
    event_type: str
    reason: Optional[str] = None
    actor: str = "user"
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

class MemoryLifecycleStats(BaseModel):
    session_id: str
    total_memories: int
    active_memories: int
    archived_memories: int
    expired_memories: int
    superseded_memories: int
    forgotten_memories: int
    persistent_count: int
    temporary_count: int

# Explainability
class MemoryExplanationResponse(BaseModel):
    memory_id: UUID
    session_id: str
    memory_key: str
    content: str
    category: str
    memory_status: str
    why_extracted: str
    why_retained: str
    is_inferred: bool
    source_message: Optional[str] = None
    lineage: Dict[str, Any] = Field(default_factory=dict)
    connected_relationships: List[Dict[str, Any]] = Field(default_factory=list)
    lifecycle_events: List[Dict[str, Any]] = Field(default_factory=list)

# Dashboard
class MemoryDashboardStats(BaseModel):
    session_id: str
    total_memories: int
    active_memories: int
    archived_memories: int
    expired_memories: int
    superseded_memories: int
    forgotten_memories: int
    persistent_count: int
    temporary_count: int
    category_counts: Dict[str, int] = Field(default_factory=dict)
    relationship_count: int = 0
    consolidation_count: int = 0
    recent_evolutions: List[Dict[str, Any]] = Field(default_factory=list)
    retrieval_metrics: Dict[str, Any] = Field(default_factory=dict)

