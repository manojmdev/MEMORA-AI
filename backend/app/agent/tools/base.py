"""
MEMORA AI — Base Tool Interface & Contract
Defines the abstract BaseTool class with execution timeout, output limits, and permission classification.
"""
from abc import ABC, abstractmethod
import asyncio
from typing import Dict, Any, Optional, Tuple, Type
from pydantic import BaseModel, ValidationError
from app.agent.models import ToolPermission, ErrorClassification

class BaseTool(ABC):
    """Abstract contract for registered tools in MEMORA AI with strict argument validation and error normalization."""
    name: str
    description: str
    permission: ToolPermission = ToolPermission.AUTOMATIC
    timeout_seconds: float = 15.0
    max_output_bytes: int = 8192
    is_idempotent: bool = True
    category: str = "general"
    risk_level: str = "safe_readonly"
    args_schema: Optional[Type[BaseModel]] = None

    @abstractmethod
    async def execute(self, session_id: str, **kwargs) -> Any:
        """
        Execute the tool with validated arguments.
        Strictly enforces session_id on the backend.
        """
        pass

    def validate_arguments(self, raw_args: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """Validate raw arguments against args_schema if provided."""
        if not self.args_schema:
            return True, raw_args, None
        try:
            validated = self.args_schema(**raw_args)
            return True, validated.model_dump(), None
        except ValidationError as ve:
            return False, raw_args, f"Argument validation failed for tool '{self.name}': {ve}"
        except Exception as e:
            return False, raw_args, f"Argument error for tool '{self.name}': {e}"

    def normalize_error(self, exc: Exception) -> Tuple[str, ErrorClassification]:
        """Categorize an exception into user message and ErrorClassification."""
        if isinstance(exc, asyncio.TimeoutError):
            return f"Tool '{self.name}' timed out after {self.timeout_seconds}s.", ErrorClassification.TIMEOUT
        if isinstance(exc, (ValidationError, ValueError, TypeError)):
            return str(exc), ErrorClassification.VALIDATION_FAILURE
        if isinstance(exc, PermissionError):
            return str(exc), ErrorClassification.AUTHORIZATION_FAILURE
        msg = str(exc).lower()
        if any(w in msg for w in ["connect", "network", "socket", "pool", "rate limit", "503", "504"]):
            return str(exc), ErrorClassification.TRANSIENT
        return str(exc), ErrorClassification.PERMANENT

    def get_metadata(self) -> Dict[str, Any]:
        """Returns JSON-serializable tool metadata for planning prompts."""
        schema_props = {}
        if self.args_schema:
            try:
                schema_props = self.args_schema.model_json_schema()
            except Exception:
                schema_props = {}

        return {
            "name": self.name,
            "description": self.description,
            "permission": self.permission.value,
            "timeout_seconds": self.timeout_seconds,
            "is_idempotent": self.is_idempotent,
            "category": self.category,
            "risk_level": self.risk_level,
            "args_schema": schema_props,
        }

    async def reconcile(self, session_id: str, idempotency_key: str, **kwargs) -> Optional[Dict[str, Any]]:
        """
        Verify whether an external side effect was already performed for this idempotency key.
        Returns a dict of results if confirmed, or None if uncertain / not found.
        Override in non-idempotent or state-modifying tools.
        """
        return None
