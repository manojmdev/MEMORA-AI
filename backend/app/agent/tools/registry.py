"""
MEMORA AI — Central Tool Registry
Provides explicit allowlist-based tool resolution, metadata indexing, and unknown tool blocking.
"""
import logging
from typing import Dict, Optional, List, Any
from app.agent.tools.base import BaseTool
from app.agent.tools.calculator import CalculatorTool
from app.agent.tools.memory_tools import SearchMemoriesTool, ListMemoriesTool
from app.agent.tools.study_tools import GenerateStudyPlanTool
from app.agent.tools.note_tools import CreateNoteTool

logger = logging.getLogger(__name__)

class ToolRegistry:
    """Central registry of all allowlisted execution tools."""

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        # Pre-register default 5 safe tools
        self.register(CalculatorTool())
        self.register(SearchMemoriesTool())
        self.register(ListMemoriesTool())
        self.register(GenerateStudyPlanTool())
        self.register(CreateNoteTool())

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance by its unique name."""
        self._tools[tool.name] = tool
        logger.info(f"Registered tool: '{tool.name}' (permission={tool.permission.value})")

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Resolve a tool by name, returning None if not registered."""
        return self._tools.get(name)

    def has_tool(self, name: str) -> bool:
        """Check whether a tool exists in the allowlist."""
        return name in self._tools

    def list_tools(self) -> List[Dict[str, Any]]:
        """Return list of metadata for all registered allowlist tools."""
        return [tool.get_metadata() for tool in self._tools.values()]

# Global registry instance
tool_registry = ToolRegistry()
