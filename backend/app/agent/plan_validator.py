import hashlib
import json
import logging
from typing import Tuple, Optional, Set, Dict, List
from app.agent.models import AgentPlan, ToolPermission
from app.agent.policy_engine import policy_engine
from app.agent.tools.registry import tool_registry

logger = logging.getLogger(__name__)

MAX_PLAN_STEPS = 6

def generate_step_idempotency_key(step_id: str, tool_name: Optional[str], arguments: Dict) -> str:
    """Generate deterministic SHA-256 idempotency key for a step."""
    payload = f"{step_id}:{tool_name or 'none'}:{json.dumps(arguments or {}, sort_keys=True)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def validate_plan(plan: AgentPlan) -> Tuple[bool, AgentPlan, Optional[str]]:
    """
    Validates proposed AgentPlan:
    1. Step count must be between 1 and MAX_PLAN_STEPS.
    2. Step IDs must be unique.
    3. Tool names must be in the allowlist or null.
    4. Blocked operations trigger immediate plan invalidation.
    5. Permissions are authoritatively assigned by backend policy engine.
    6. Tool arguments are strictly validated against registered Pydantic schemas.
    7. Dependencies must form a valid Directed Acyclic Graph (DAG) without cycles.
    8. Idempotency keys and retry limits are authoritatively configured.
    """
    if plan and plan.requires_clarification:
        return True, plan, None

    if not plan or not plan.steps:
        return False, plan, "Plan must contain at least one step."

    if len(plan.steps) > MAX_PLAN_STEPS:
        return False, plan, f"Plan exceeds maximum limit of {MAX_PLAN_STEPS} steps."

    seen_step_ids: Set[str] = set()
    step_id_order: List[str] = []
    requires_approval = False
    dag_edges: List[List[str]] = []

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

            tool = tool_registry.get_tool(tool_name)
            if not tool:
                return False, plan, f"Tool '{tool_name}' is not registered in the system allowlist."

            # Strict tool argument schema validation
            is_valid_args, validated_args, arg_err = tool.validate_arguments(step.arguments)
            if not is_valid_args:
                return False, plan, f"Step '{sid}' ({tool_name}) argument validation error: {arg_err}"
            step.arguments = validated_args
            step.is_idempotent = tool.is_idempotent
            step.max_retries = 2 if tool.is_idempotent else 0
        else:
            step.permission = ToolPermission.AUTOMATIC
            step.is_idempotent = True
            step.max_retries = 1

        # Assign deterministic idempotency key
        step.idempotency_key = generate_step_idempotency_key(step.step_id, step.tool_name, step.arguments)

    # Validate dependencies & build graph for Kahn's topological cycle detection
    adj: Dict[str, List[str]] = {sid: [] for sid in seen_step_ids}
    in_degree: Dict[str, int] = {sid: 0 for sid in seen_step_ids}

    for step in plan.steps:
        for dep in step.dependencies:
            if dep == step.step_id:
                return False, plan, f"Step '{step.step_id}' cannot depend on itself (dependency cycle)."
            if dep not in seen_step_ids:
                return False, plan, f"Step '{step.step_id}' references unknown dependency '{dep}'."

            adj[dep].append(step.step_id)
            in_degree[step.step_id] += 1
            dag_edges.append([dep, step.step_id])

    # Kahn's algorithm for authoritative cycle detection & topological ordering
    queue = [sid for sid, deg in in_degree.items() if deg == 0]
    topological_order: List[str] = []
    while queue:
        curr = queue.pop(0)
        topological_order.append(curr)
        for neighbor in adj[curr]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(topological_order) != len(seen_step_ids):
        return False, plan, "Dependency cycle detected in execution plan."

    # Validate dependency order (steps must reference preceding steps in sequence)
    for i, step in enumerate(plan.steps):
        preceding_steps = set(step_id_order[:i])
        for dep in step.dependencies:
            if dep not in preceding_steps:
                return False, plan, f"Step '{step.step_id}' depends on forward or concurrent step '{dep}'."

    plan.requires_approval = requires_approval
    plan.dag_edges = dag_edges
    return True, plan, None

validate_and_govern_plan = validate_plan

