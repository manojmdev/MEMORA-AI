"""
MEMORA AI — Independent Plan Validator
Validates proposed plan structure, step limits, dependency DAGs, and tool allowlists.
"""
import logging
from typing import Tuple, Optional, Set, Dict, List
from app.agent.models import AgentPlan, ToolPermission
from app.agent.policy_engine import policy_engine
from app.agent.tools.registry import tool_registry

logger = logging.getLogger(__name__)

MAX_PLAN_STEPS = 6

def validate_plan(plan: AgentPlan) -> Tuple[bool, AgentPlan, Optional[str]]:
    """
    Validates proposed AgentPlan:
    1. Step count must be between 1 and MAX_PLAN_STEPS.
    2. Step IDs must be unique.
    3. Tool names must be in the allowlist or null.
    4. Blocked operations trigger immediate plan invalidation.
    5. Permissions are authoritatively assigned by backend policy engine.
    6. Dependencies must be valid preceding steps without cycles.
    """
    if not plan or not plan.steps:
        return False, plan, "Plan must contain at least one step."

    if len(plan.steps) > MAX_PLAN_STEPS:
        return False, plan, f"Plan exceeds maximum limit of {MAX_PLAN_STEPS} steps."

    seen_step_ids: Set[str] = set()
    step_id_order: List[str] = []
    requires_approval = False

    for step in plan.steps:
        sid = step.step_id.strip()
        if not sid:
            return False, plan, "Step ID cannot be empty."

        if sid in seen_step_ids:
            return False, plan, f"Duplicate step ID '{sid}' found in plan."

        seen_step_ids.add(sid)
        step_id_order.append(sid)

        # Validate tool
        if step.tool_name:
            tool_name = step.tool_name.strip()
            # Authoritative policy assignment
            permission = policy_engine.get_permission(tool_name)
            step.permission = permission

            if permission == ToolPermission.BLOCKED:
                return False, plan, f"Step '{sid}' references disallowed or unregistered tool '{tool_name}'."

            if permission == ToolPermission.APPROVAL_REQUIRED:
                requires_approval = True

            if not tool_registry.has_tool(tool_name):
                return False, plan, f"Tool '{tool_name}' is not registered in the system allowlist."
        else:
            step.permission = ToolPermission.AUTOMATIC

    # Validate dependencies (must reference preceding steps only, preventing cycles)
    for i, step in enumerate(plan.steps):
        preceding_steps = set(step_id_order[:i])
        for dep in step.dependencies:
            if dep == step.step_id:
                return False, plan, f"Step '{step.step_id}' cannot depend on itself."
            if dep not in seen_step_ids:
                return False, plan, f"Step '{step.step_id}' references unknown dependency '{dep}'."
            if dep not in preceding_steps:
                return False, plan, f"Step '{step.step_id}' depends on forward or concurrent step '{dep}'."

    plan.requires_approval = requires_approval
    return True, plan, None

validate_and_govern_plan = validate_plan

