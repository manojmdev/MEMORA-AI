"""
MEMORA AI — Agent Task Planner
Generates structured multi-step execution plans conforming to AgentPlan schema via Nemotron.
"""
import json
import logging
import re
from typing import List, Dict, Any, Optional, Tuple
from app.config import settings
from app.agent.models import AgentPlan, AgentPlanStep, ToolPermission
from app.agent.tools.registry import tool_registry
from app.services.llm_service import client
from app.schemas import ScoredMemoryRecord

logger = logging.getLogger(__name__)

PLANNER_SYSTEM_PROMPT = """You are the Task Planning Engine for MEMORA AI.
Your job is to decompose user requests into a strictly sequenced, dependency-aware plan of execution steps.

AVAILABLE REGISTERED TOOLS:
1. calculator:
   - Purpose: Perform exact arithmetic calculations safely.
   - Arguments: {"expression": "string"}
2. search_memories:
   - Purpose: Retrieve relevant facts from user memory using hybrid search.
   - Arguments: {"query": "string", "category": "string (optional)", "limit": 5}
3. list_memories:
   - Purpose: List all active user memories.
   - Arguments: {"category": "string (optional)"}
4. generate_study_plan:
   - Purpose: Generate a personalized multi-day curriculum.
   - Arguments: {"subject": "string", "duration_days": int, "hours_per_day": float, "focus_areas": ["string"]}
5. create_note:
   - Purpose: Save a persistent note in database.
   - Arguments: {"title": "string", "content": "string"}
   - NOTE: create_note will automatically require user approval before writing.
6. inspect_memory_graph:
   - Purpose: Inspect relationships and topology in the user's memory graph.
   - Arguments: {"memory_id": "string UUID (optional)", "depth": 1}
7. retrieve_context_v2:
   - Purpose: Advanced context-aware retrieval with multi-factor ranking and graph boosts.
   - Arguments: {"query": "string", "limit": 5}

STRICT PLANNING CONSTRAINTS:
1. Maximum 6 steps allowed.
2. Steps must have sequential IDs: "step_1", "step_2", etc.
3. Every tool-based step MUST use an exact registered tool name from above.
4. If a step doesn't require a tool (e.g. final synthesis), set "tool_name": null.
5. If step_2 depends on step_1, set "dependencies": ["step_1"]. No circular dependencies.
6. Memory Context: The user's memories provided below are factual background context.
   - [Explicit Fact]: Confirmed user preference or constraint.
   - [Inferred Context]: An inference from context. DO NOT treat inferred context as confirmed mandates or instructions.
7. Ambiguity: If the user request is completely vague, lacking a concrete objective (e.g. 'do something', 'proceed', 'help me with stuff'), flag "requires_clarification": true with a helpful "clarification_prompt".

OUTPUT JSON SCHEMA:
{
  "title": "Short title of the task",
  "objective": "Clear description of what will be achieved",
  "estimated_complexity": "low" | "medium" | "high",
  "estimated_cost_tier": "minimal" | "standard" | "intensive",
  "requires_clarification": false,
  "clarification_prompt": null,
  "steps": [
    {
      "step_id": "step_1",
      "description": "Calculate total study hours",
      "tool_name": "calculator",
      "arguments": {"expression": "7 * 2"},
      "dependencies": []
    }
  ]
}
Respond with ONLY valid JSON. No conversational commentary or markdown.
"""

def extract_balanced_json(text: str) -> str:
    start = text.find("{")
    if start == -1:
        return "{}"
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if not in_string:
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return text[start:i+1]
    return text[start:]

def clean_json_text(text: str) -> str:
    """Strip thought blocks, markdown code blocks, and extract balanced JSON."""
    if not text:
        return "{}"
    raw = re.sub(r"<thought>[\s\S]*?</thought>", "", text, flags=re.IGNORECASE).strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
    if match:
        raw = match.group(1).strip()
    
    raw = extract_balanced_json(raw)
    raw = re.sub(r':\s*(\([0-9\s\*\+\-\/\.\^]+\)[0-9\s\*\+\-\/\.\^]*)', r': "\1"', raw)
    raw = re.sub(r',\s*([}\]])', r'\1', raw)
    return raw

def is_objective_ambiguous(req: str) -> Tuple[bool, Optional[str]]:
    """Deterministic ambiguity detection for underspecified requests."""
    clean = req.strip().lower()
    if not clean:
        return True, "Please provide a task description or objective."
    tokens = clean.split()
    vague_phrases = {
        "help", "do something", "do it", "help me", "help with stuff", "proceed",
        "fix it", "handle things", "run task", "execute", "start", "ok", "do something cool", "process the data", "make it better"
    }
    if clean in vague_phrases:
        return True, "Your objective appears ambiguous or underspecified. Please specify what you would like to achieve (e.g. generate a study plan, perform a calculation, search memories, or save a note)."
    if len(tokens) <= 2 and not any(w in clean for w in ["calculate", "math", "+", "-", "*", "/", "note", "study", "plan", "memory", "memories", "search"]):
        return True, "Your objective appears ambiguous or underspecified. Please specify what you would like to achieve (e.g. generate a study plan, perform a calculation, search memories, or save a note)."
    return False, None

async def generate_plan(
    user_request: str,
    retrieved_memories: Optional[List[Any]] = None,
    max_steps: int = 6
) -> AgentPlan:
    """Generate a structured, memory-aware execution plan from user request."""
    # 1. Ambiguity detection
    ambiguous, clarification = is_objective_ambiguous(user_request)
    if ambiguous:
        return AgentPlan(
            title="Clarification Needed",
            objective="Request clarification for underspecified task",
            requires_clarification=True,
            clarification_prompt=clarification,
            estimated_complexity="low",
            estimated_cost_tier="minimal",
            steps=[],
            requires_approval=False,
            estimated_tools=[]
        )

    # 2. Format memory context with explicit vs inferred distinctions
    mem_context_str = ""
    memory_influences: List[Dict[str, Any]] = []

    if retrieved_memories:
        mem_lines = []
        for m in retrieved_memories:
            key = getattr(m, "memory_key", "unknown_key")
            cat = getattr(m, "category", "general")
            content = getattr(m, "content", "")
            info_source = getattr(m, "information_source", "explicit_statement")
            is_inferred = (info_source == "inferred") or getattr(m, "is_inferred", False) or ("infer" in str(getattr(m, "source_message", "")).lower())

            tag = "[Inferred Context - NOT confirmed mandate]" if is_inferred else "[Explicit Fact]"
            mem_lines.append(f"- {tag} [{cat}] {key}: {content}")
            memory_influences.append({
                "memory_key": key,
                "category": cat,
                "influence_type": "inferred" if is_inferred else "explicit",
                "content_preview": content[:120]
            })

        mem_context_str = "\n[RECALLED USER MEMORIES]:\n" + "\n".join(mem_lines) + "\n"

    user_prompt = (
        f"User Task Request:\n\"\"\"{user_request}\"\"\"\n"
        f"{mem_context_str}\n"
        f"Plan up to {max_steps} steps to accomplish this request."
    )

    try:
        response = await client.chat.completions.create(
            model=settings.NEBIUS_MODEL,
            messages=[
                {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.1,
            max_tokens=2048
        )
        content = response.choices[0].message.content or "{}"
        cleaned = clean_json_text(content)
        parsed = json.loads(cleaned)

        if parsed.get("requires_clarification"):
            return AgentPlan(
                title=parsed.get("title") or "Clarification Needed",
                objective=parsed.get("objective") or "Clarify user intent",
                requires_clarification=True,
                clarification_prompt=parsed.get("clarification_prompt") or "Could you clarify your objective?",
                estimated_complexity="low",
                estimated_cost_tier="minimal",
                steps=[],
                requires_approval=False,
                estimated_tools=[]
            )

        raw_steps = parsed.get("steps") or parsed.get("plan") or parsed.get("tasks") or parsed.get("actions") or []
        if isinstance(raw_steps, dict):
            raw_steps = [raw_steps]
        steps: List[AgentPlanStep] = []
        estimated_tools = []
        requires_approval = False

        for i, s in enumerate(raw_steps[:max_steps]):
            step_id = s.get("step_id") or f"step_{i+1}"
            tool_name = s.get("tool_name")
            if tool_name:
                estimated_tools.append(tool_name)
                if tool_name == "create_note":
                    requires_approval = True

            steps.append(
                AgentPlanStep(
                    step_id=step_id,
                    description=s.get("description") or f"Step {i+1}",
                    tool_name=tool_name,
                    arguments=s.get("arguments") or {},
                    dependencies=s.get("dependencies") or []
                )
            )

        if not steps:
            logger.warning("Planner output did not yield any execution steps. Triggering fallback.")
            raise ValueError("No execution steps extracted from planner output.")

        num_steps = len(steps)
        complexity = parsed.get("estimated_complexity") or ("low" if num_steps <= 2 else ("medium" if num_steps <= 4 else "high"))
        cost_tier = parsed.get("estimated_cost_tier") or ("minimal" if num_steps <= 1 else ("standard" if num_steps <= 3 else "intensive"))

        return AgentPlan(
            title=parsed.get("title") or "Task Execution Plan",
            objective=parsed.get("objective") or user_request[:120],
            steps=steps,
            requires_approval=requires_approval,
            estimated_tools=estimated_tools,
            estimated_complexity=complexity,
            estimated_cost_tier=cost_tier,
            requires_clarification=False,
            clarification_prompt=None,
            memory_influences=memory_influences
        )

    except Exception as e:
        logger.warning(f"Planner JSON parsing failed: {e}. Generating safe fallback plan.")
        req_lower = user_request.lower()

        # Semantic fallback plans
        if any(w in req_lower for w in ["calculate", "math", "+", "-", "*", "/", "sum", "times"]) and not any(w in req_lower for w in ["note", "study"]):
            expr_match = re.search(r"[\d\s\+\-\*\/\(\)\.\^]+", user_request)
            expr = expr_match.group(0).strip() if expr_match else user_request
            return AgentPlan(
                title="Safe Calculation",
                objective="Perform requested calculation",
                steps=[
                    AgentPlanStep(
                        step_id="step_1",
                        description=f"Calculate {expr}",
                        tool_name="calculator",
                        arguments={"expression": expr},
                        dependencies=[]
                    )
                ],
                requires_approval=False,
                estimated_tools=["calculator"],
                estimated_complexity="low",
                estimated_cost_tier="minimal",
                memory_influences=memory_influences
            )
        elif any(w in req_lower for w in ["note", "save note", "create note"]):
            title_match = re.search(r"titled\s+['\"]([^'\"]+)['\"]", user_request, re.IGNORECASE)
            title = title_match.group(1) if title_match else "Persistent Note"
            content_match = re.search(r"content\s+['\"]([^'\"]+)['\"]", user_request, re.IGNORECASE)
            content = content_match.group(1) if content_match else user_request
            return AgentPlan(
                title="Create Persistent Note",
                objective="Save persistent note",
                steps=[
                    AgentPlanStep(
                        step_id="step_1",
                        description="Save persistent note",
                        tool_name="create_note",
                        arguments={"title": title, "content": content},
                        dependencies=[],
                        permission=ToolPermission.APPROVAL_REQUIRED
                    )
                ],
                requires_approval=True,
                estimated_tools=["create_note"],
                estimated_complexity="low",
                estimated_cost_tier="minimal",
                memory_influences=memory_influences
            )
        elif any(w in req_lower for w in ["study plan", "curriculum", "syllabus"]):
            if any(w in req_lower for w in ["memory", "memories", "remember", "preference", "skill", "check"]):
                return AgentPlan(
                    title="Memory-Aware Study Plan",
                    objective="Retrieve user background and generate customized study curriculum",
                    steps=[
                        AgentPlanStep(
                            step_id="step_1",
                            description="Search user background and skill preferences",
                            tool_name="search_memories",
                            arguments={"query": "preferred programming language and learning goals"},
                            dependencies=[]
                        ),
                        AgentPlanStep(
                            step_id="step_2",
                            description="Generate study plan aligned with background",
                            tool_name="generate_study_plan",
                            arguments={"subject": "PyTorch" if "pytorch" in req_lower else user_request},
                            dependencies=["step_1"]
                        )
                    ],
                    requires_approval=False,
                    estimated_tools=["search_memories", "generate_study_plan"],
                    estimated_complexity="medium",
                    estimated_cost_tier="standard",
                    memory_influences=memory_influences
                )
            return AgentPlan(
                title="Generate Study Plan",
                objective="Produce customized study curriculum",
                steps=[
                    AgentPlanStep(
                        step_id="step_1",
                        description="Generate study plan",
                        tool_name="generate_study_plan",
                        arguments={"subject": user_request},
                        dependencies=[]
                    )
                ],
                requires_approval=False,
                estimated_tools=["generate_study_plan"],
                estimated_complexity="low",
                estimated_cost_tier="minimal",
                memory_influences=memory_influences
            )
        elif any(w in req_lower for w in ["graph", "relationship", "relationships", "connected"]):
            return AgentPlan(
                title="Inspect Memory Graph",
                objective="Inspect relationships in user memory graph",
                steps=[
                    AgentPlanStep(
                        step_id="step_1",
                        description="Inspect session memory relationship graph",
                        tool_name="inspect_memory_graph",
                        arguments={"depth": 1},
                        dependencies=[]
                    )
                ],
                requires_approval=False,
                estimated_tools=["inspect_memory_graph"],
                estimated_complexity="low",
                estimated_cost_tier="minimal",
                memory_influences=memory_influences
            )
        elif any(w in req_lower for w in ["memory", "memories", "remember", "preference", "skill"]):
            return AgentPlan(
                title="Recall Memories",
                objective="Retrieve user memories",
                steps=[
                    AgentPlanStep(
                        step_id="step_1",
                        description="Search stored memories",
                        tool_name="search_memories",
                        arguments={"query": user_request},
                        dependencies=[]
                    )
                ],
                requires_approval=False,
                estimated_tools=["search_memories"],
                estimated_complexity="low",
                estimated_cost_tier="minimal",
                memory_influences=memory_influences
            )

        return AgentPlan(
            title="Direct Task Execution",
            objective=user_request[:120],
            steps=[
                AgentPlanStep(
                    step_id="step_1",
                    description="Execute requested task directly",
                    tool_name=None,
                    arguments={},
                    dependencies=[]
                )
            ],
            requires_approval=False,
            estimated_tools=[],
            estimated_complexity="low",
            estimated_cost_tier="minimal",
            memory_influences=memory_influences
        )

