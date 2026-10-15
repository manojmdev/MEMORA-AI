"""
MEMORA AI — Base Tool Interface & Contract
Defines the abstract BaseTool class with execution timeout, output limits, and permission classification.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from app.agent.models import ToolPermission

class BaseTool(ABC):
    """Abstract contract for registered tools in MEMORA AI."""
    name: str
    description: str
    permission: ToolPermission = ToolPermission.AUTOMATIC
    timeout_seconds: float = 15.0
    max_output_bytes: int = 8192

    @abstractmethod
    async def execute(self, session_id: str, **kwargs) -> Any:
        """
        Execute the tool with validated arguments.
        Strictly enforces session_id on the backend.
        """
        pass

    def get_metadata(self) -> Dict[str, Any]:
        """Returns JSON-serializable tool metadata for planning prompts."""
        return {
            "name": self.name,
            "description": self.description,
            "permission": self.permission.value,
            "timeout_seconds": self.timeout_seconds,
        }
