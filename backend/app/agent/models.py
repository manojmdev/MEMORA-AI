"""
MEMORA AI — Agent Data Models & State Machine Contracts
Defines strictly typed Pydantic models for tasks, plans, steps, tools, approvals, and events.
"""
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field

class TaskStatus(str, Enum):
    PROPOSED = "proposed"
    AWAITING_APPROVAL = "awaiting_approval"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"

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

class AgentPlan(BaseModel):
    title: str = Field(..., description="Short plan title")
    objective: str = Field(..., description="Clear task goal")
    steps: List[AgentPlanStep] = Field(default_factory=list)
    requires_approval: bool = False
    estimated_tools: List[str] = Field(default_factory=list)

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
    session_id: str
    approval_token: Optional[str] = None

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

class AgentTask(BaseModel):
    id: UUID
    session_id: str
    user_request: str
    task_type: str = "general"
    plan: Optional[AgentPlan] = None
    status: TaskStatus = TaskStatus.PROPOSED
    result_summary: Optional[str] = None
    approval_token: Optional[str] = None
    approval_status: Optional[str] = None
    approval_expires_at: Optional[datetime] = None
    pending_approval: Optional[ApprovalRequest] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None

class AgentTaskResponse(BaseModel):
    task: AgentTask
    reply: str
    memories_used: List[Dict[str, Any]] = Field(default_factory=list)
    tools_executed: List[str] = Field(default_factory=list)
    execution_timeline: List[Dict[str, Any]] = Field(default_factory=list)

class AgentRunRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000, description="User instruction for the agent")
    session_id: str = Field(default="default-session", min_length=1, max_length=255, description="Session identifier")

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

