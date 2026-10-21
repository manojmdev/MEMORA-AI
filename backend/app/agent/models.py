"""
MEMORA AI — Agent Data Models & State Machine Contracts
Defines strictly typed Pydantic models for tasks, plans, steps, tools, approvals, and events.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field

class TaskStatus(str, Enum):
    CREATED = "created"
    PLANNING = "planning"
    PROPOSED = "proposed"
    AWAITING_CLARIFICATION = "awaiting_clarification"
    AWAITING_APPROVAL = "awaiting_approval"
    RUNNING = "running"
    RETRYING = "retrying"
    CANCEL_REQUESTED = "cancel_requested"
    NEEDS_RECONCILIATION = "needs_reconciliation"
    SUCCEEDED = "succeeded"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

# Strict State Machine Transition Rules
VALID_TASK_TRANSITIONS = {
    TaskStatus.CREATED: {TaskStatus.PLANNING, TaskStatus.RUNNING, TaskStatus.AWAITING_CLARIFICATION, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.PROPOSED: {TaskStatus.PLANNING, TaskStatus.RUNNING, TaskStatus.AWAITING_APPROVAL, TaskStatus.AWAITING_CLARIFICATION, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.PLANNING: {TaskStatus.RUNNING, TaskStatus.AWAITING_APPROVAL, TaskStatus.AWAITING_CLARIFICATION, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.AWAITING_CLARIFICATION: {TaskStatus.PLANNING, TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.AWAITING_APPROVAL: {TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.AWAITING_APPROVAL},
    TaskStatus.RUNNING: {TaskStatus.SUCCEEDED, TaskStatus.COMPLETED, TaskStatus.AWAITING_APPROVAL, TaskStatus.FAILED, TaskStatus.NEEDS_RECONCILIATION, TaskStatus.CANCEL_REQUESTED, TaskStatus.CANCELLED, TaskStatus.RETRYING},
    TaskStatus.RETRYING: {TaskStatus.RUNNING, TaskStatus.SUCCEEDED, TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.NEEDS_RECONCILIATION, TaskStatus.CANCELLED},
    TaskStatus.CANCEL_REQUESTED: {TaskStatus.CANCELLED, TaskStatus.SUCCEEDED, TaskStatus.COMPLETED, TaskStatus.NEEDS_RECONCILIATION, TaskStatus.FAILED},
    TaskStatus.NEEDS_RECONCILIATION: {TaskStatus.RETRYING, TaskStatus.RUNNING, TaskStatus.CANCELLED, TaskStatus.FAILED, TaskStatus.SUCCEEDED, TaskStatus.COMPLETED},
    TaskStatus.FAILED: {TaskStatus.RETRYING, TaskStatus.RUNNING},  # Allowed strictly on authorized retry
    TaskStatus.SUCCEEDED: set(),  # Terminal
    TaskStatus.COMPLETED: set(),  # Terminal
    TaskStatus.CANCELLED: set(),  # Terminal
}

class InvalidStateTransitionError(ValueError):
    """Raised when an illegal task state machine transition is attempted."""
    pass

def validate_task_transition(current_status: TaskStatus, next_status: TaskStatus) -> bool:
    """Validate whether transitioning from current_status to next_status is permitted."""
    if current_status == next_status:
        return True
    allowed = VALID_TASK_TRANSITIONS.get(current_status, set())
    if next_status not in allowed:
        raise InvalidStateTransitionError(
            f"Cannot transition task from '{current_status.value}' to '{next_status.value}'. Permitted: {[s.value for s in allowed]}"
        )
    return True

class StepStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    DISPATCHED = "dispatched"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    CANCEL_REQUESTED = "cancel_requested"
    SUCCEEDED = "succeeded"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    NEEDS_RECONCILIATION = "needs_reconciliation"

class ErrorClassification(str, Enum):
    TRANSIENT = "transient"
    PERMANENT = "permanent"
    VALIDATION_FAILURE = "validation_failure"
    AUTHORIZATION_FAILURE = "authorization_failure"
    TOOL_UNAVAILABLE = "tool_unavailable"
    TIMEOUT = "timeout"
    UNKNOWN_OUTCOME = "unknown_outcome"

class ToolPermission(str, Enum):
    AUTOMATIC = "automatic"
    APPROVAL_REQUIRED = "approval_required"
    BLOCKED = "blocked"

class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"

class ToolCall(BaseModel):
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)

class ToolResult(BaseModel):
    tool_name: str
    success: bool
    result: Any = None
    error: Optional[str] = None
    duration_ms: Optional[int] = None
    error_classification: Optional[ErrorClassification] = None
    external_operation_id: Optional[str] = None

class AgentPlanStep(BaseModel):
    step_id: str = Field(..., description="Unique step identifier like 'step_1'")
    description: str = Field(..., description="Human-readable step objective")
    tool_name: Optional[str] = Field(default=None, description="Registered allowlist tool name")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Arguments to pass to tool")
    dependencies: List[str] = Field(default_factory=list, description="List of step_ids this step depends on")
    permission: ToolPermission = Field(default=ToolPermission.AUTOMATIC)
    status: StepStatus = Field(default=StepStatus.PENDING)
    result: Optional[Any] = None
    error: Optional[str] = None
    estimated_cost: Optional[str] = "minimal"
    is_idempotent: bool = True
    retry_count: int = 0
    max_retries: int = 2
    idempotency_key: Optional[str] = None
    error_classification: Optional[ErrorClassification] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    external_operation_id: Optional[str] = None
    execution_intent_persisted_at: Optional[datetime] = None
    lease_generation: int = 1

class AgentPlan(BaseModel):
    title: str = Field(default="Agent Execution Plan", description="Short plan title")
    objective: str = Field(default="Execute task", description="Clear task goal")
    goal: Optional[str] = None
    steps: List[AgentPlanStep] = Field(default_factory=list)
    requires_approval: bool = False
    estimated_tools: List[str] = Field(default_factory=list)
    estimated_complexity: str = Field(default="low", description="low, medium, high")
    estimated_cost_tier: str = Field(default="standard", description="minimal, standard, intensive")
    requires_clarification: bool = False
    clarification_prompt: Optional[str] = None
    memory_influences: List[Dict[str, Any]] = Field(default_factory=list)
    dag_edges: List[List[str]] = Field(default_factory=list)

class ApprovalRequest(BaseModel):
    task_id: UUID
    step_id: str
    approval_token: str
    operation: str
    title: str
    content: str
    reason: str
    consequences: str
    expires_at: datetime

class ApprovalActionRequest(BaseModel):
    session_id: Optional[str] = Field(default="default-session", description="Session identifier")
    approval_token: Optional[str] = None
    reason: Optional[str] = None
    feedback: Optional[str] = None

class ClarificationActionRequest(BaseModel):
    session_id: Optional[str] = Field(default="default-session", description="Session identifier")
    clarification: str = Field(..., min_length=1, max_length=5000, description="User clarification text")

class ApprovalResponse(BaseModel):
    task_id: UUID
    status: str
    message: str
    task: Optional[Dict[str, Any]] = None

class AgentExecutionEvent(BaseModel):
    id: UUID
    task_id: UUID
    session_id: str
    step_id: Optional[str] = None
    tool_name: str
    arguments_json: Optional[Dict[str, Any]] = None
    status: str
    approval_status: Optional[str] = None
    result_summary: Optional[str] = None
    error_code: Optional[str] = None
    duration_ms: Optional[int] = None
    created_at: datetime

class AgentTaskCheckpoint(BaseModel):
    id: UUID
    task_id: UUID
    session_id: str
    step_id: str
    tool_name: Optional[str] = None
    arguments: Dict[str, Any] = Field(default_factory=dict)
    dependencies: List[str] = Field(default_factory=list)
    status: StepStatus = StepStatus.PENDING
    error_classification: Optional[ErrorClassification] = None
    retry_count: int = 0
    max_retries: int = 2
    idempotency_key: str
    result: Optional[Any] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    external_operation_id: Optional[str] = None
    execution_intent_persisted_at: Optional[datetime] = None
    lease_generation: int = 1
    worker_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class StaleWorkerError(Exception):
    """Raised when worker lease expires or lease generation token is superseded."""
    pass

class TaskFailureDetails(BaseModel):
    error_category: Optional[str] = None
    failed_step_id: Optional[str] = None
    tool_name: Optional[str] = None
    failure_timestamp: Optional[datetime] = None
    is_retryable: bool = False
    attempt_count: int = 1
    safe_error_message: Optional[str] = None
    correlation_id: Optional[str] = None

class AgentTask(BaseModel):
    id: UUID
    session_id: str
    user_request: str
    task_type: str = "general"
    plan: Optional[AgentPlan] = None
    status: TaskStatus = TaskStatus.PROPOSED
    result_summary: Optional[str] = None
    error_message: Optional[str] = None
    failure_details: Optional[TaskFailureDetails] = None
    approval_token: Optional[str] = None
    approval_status: Optional[str] = None
    approval_expires_at: Optional[datetime] = None
    pending_approval: Optional[ApprovalRequest] = None
    estimated_complexity: Optional[str] = "low"
    estimated_cost_tier: Optional[str] = "standard"
    requires_clarification: bool = False
    clarification_prompt: Optional[str] = None
    lease_generation: int = 1
    worker_id: Optional[str] = None
    last_heartbeat_at: Optional[datetime] = None
    execution_lease_expires_at: Optional[datetime] = None
    checkpoints: List[AgentTaskCheckpoint] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None

class AgentTaskResponse(BaseModel):
    task: AgentTask
    reply: str
    memories_used: List[Dict[str, Any]] = Field(default_factory=list)
    tools_executed: List[str] = Field(default_factory=list)
    execution_timeline: List[Dict[str, Any]] = Field(default_factory=list)
    checkpoints: List[AgentTaskCheckpoint] = Field(default_factory=list)

class AgentRunRequest(BaseModel):
    message: Optional[str] = Field(default=None, max_length=10000, description="User instruction for the agent")
    instruction: Optional[str] = Field(default=None, max_length=10000, description="Alias for message")
    session_id: str = Field(default="default-session", min_length=1, max_length=255, description="Session identifier")
    require_approval: Optional[bool] = Field(default=None, description="Require manual approval for side-effect operations")
    max_steps: int = Field(default=6, description="Maximum execution steps allowed")

    @property
    def effective_instruction(self) -> str:
        return (self.message or self.instruction or "").strip()

class NoteRecord(BaseModel):
    id: UUID
    session_id: str
    title: str
    content: str
    created_at: datetime
    updated_at: datetime

class NoteListResponse(BaseModel):
    session_id: str
    count: int
    notes: List[NoteRecord]

