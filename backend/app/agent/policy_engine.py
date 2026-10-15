"""
MEMORA AI — Backend Execution Policy Engine
Enforces backend-controlled permissions independently of model-generated claims.
"""
import logging
from typing import Set, Optional
from app.agent.models import ToolPermission
from app.agent.tools.registry import tool_registry

logger = logging.getLogger(__name__)

# Explicitly blocked operations (security perimeter)
BLOCKED_OPERATIONS: Set[str] = {
    "eval",
    "exec",
    "shell",
    "bash",
    "powershell",
    "cmd",
    "sql",
    "query_db",
    "raw_sql",
    "python",
    "python_exec",
    "delete_memory",
    "update_memory",
    "clear_memories",
}

class PolicyEngine:
    """Backend-enforced tool permission and security validator."""

    @staticmethod
    def get_permission(tool_name: Optional[str]) -> ToolPermission:
        """
        Determines the authoritative permission for an operation.
        Never relies on LLM-generated permission values.
        """
        if not tool_name:
            return ToolPermission.AUTOMATIC

        normalized = tool_name.strip().lower()

        # Hard-blocked dangerous or unexposed operations
        if normalized in BLOCKED_OPERATIONS:
            logger.warning(f"Policy Engine blocked attempt to invoke forbidden operation '{normalized}'.")
            return ToolPermission.BLOCKED

        # Resolve against tool registry allowlist
        tool = tool_registry.get_tool(normalized)
        if not tool:
            logger.warning(f"Policy Engine blocked unknown tool '{normalized}'.")
            return ToolPermission.BLOCKED

        return tool.permission

    @staticmethod
    def is_executable(tool_name: Optional[str]) -> bool:
        """Returns True if the tool is permitted to execute automatically or with approval."""
        perm = PolicyEngine.get_permission(tool_name)
        return perm != ToolPermission.BLOCKED

    @staticmethod
    def requires_approval(tool_name: Optional[str]) -> bool:
        """Returns True if the tool requires explicit user sign-off before running."""
        return PolicyEngine.get_permission(tool_name) == ToolPermission.APPROVAL_REQUIRED

    @staticmethod
    def get_tool_permission(tool_name: Optional[str]) -> ToolPermission:
        """Alias for get_permission."""
        return PolicyEngine.get_permission(tool_name)

    @staticmethod
    def authorize_tool_execution(tool_name: Optional[str], arguments: dict = None):
        """Authorize tool execution against policy engine."""
        perm = PolicyEngine.get_permission(tool_name)
        if perm == ToolPermission.BLOCKED:
            return False, perm, f"Tool '{tool_name}' is blocked by policy engine."
        return True, perm, ""

policy_engine = PolicyEngine()
