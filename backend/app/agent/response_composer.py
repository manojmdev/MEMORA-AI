"""
MEMORA AI — Agent Response Composer
Composes clear, transparent task summaries explaining executed steps, results, and memory provenance.
"""
from typing import Dict, Any, List, Optional
from app.agent.models import AgentTask, TaskStatus, StepStatus
from app.schemas import ScoredMemoryRecord

def compose_agent_response(
    task: AgentTask,
    recalled_memories: Optional[List[ScoredMemoryRecord]] = None
) -> str:
    """
    Format a transparent human-readable response summarizing the task outcome.
    Mentions tools executed and memories actually used.
    """
    plan = task.plan
    if not plan:
        return task.result_summary or "Task concluded."

    lines = []

    # If task is awaiting approval
    if task.status == TaskStatus.AWAITING_APPROVAL and task.pending_approval:
        lines.append(f"### ⏸️ Action Requires Your Approval: **{task.pending_approval.title}**")
        lines.append(f"**Operation:** `{task.pending_approval.operation}`")
        lines.append(f"**Reason:** {task.pending_approval.reason}")
        lines.append(f"**Proposed Content:**\n```\n{task.pending_approval.content}\n```")
        lines.append(f"👉 *Please approve or reject this operation to proceed.*")
        return "\n\n".join(lines)

    # If task was cancelled
    if task.status == TaskStatus.CANCELLED:
        return f"🚫 **Task Cancelled**: {task.result_summary or 'Operation was declined or aborted.'}"

    # If task failed
    if task.status == TaskStatus.FAILED:
        return f"❌ **Task Failed**: {task.result_summary or 'An error occurred during execution.'}"

    # If task succeeded
    lines.append(f"### ✅ **{plan.title}**")
    lines.append(f"*{plan.objective}*")

    # Step execution summaries
    step_summaries = []
    tools_used = set()
    for s in plan.steps:
        if s.tool_name:
            tools_used.add(s.tool_name)
        status_icon = "✅" if s.status == StepStatus.SUCCEEDED else "⏳"
        if s.tool_name == "calculator" and s.result:
            step_summaries.append(f"- {status_icon} **Calculation:** `{s.result.get('expression')}` = **{s.result.get('result')}**")
        elif s.tool_name == "create_note" and s.result:
            step_summaries.append(f"- {status_icon} **Saved Note:** '{s.result.get('title')}'")
        elif s.tool_name == "generate_study_plan" and s.result:
            subj = s.result.get('subject', 'Study Plan')
            days = s.result.get('total_days', '')
            step_summaries.append(f"- {status_icon} **Curriculum:** Generated {days}-day plan for *{subj}*.")
        elif s.tool_name == "search_memories" and s.result:
            step_summaries.append(f"- {status_icon} **Memory Search:** Found {s.result.get('count', 0)} matching memories.")
        else:
            step_summaries.append(f"- {status_icon} {s.description}")

    if step_summaries:
        lines.append("\n**Execution Steps:**\n" + "\n".join(step_summaries))

    # Relevant memories used provenance
    if recalled_memories:
        mem_bullets = [f"- [{m.category}] *{m.memory_key}*: {m.content}" for m in recalled_memories[:3]]
        lines.append("\n**Context from Your Memory:**\n" + "\n".join(mem_bullets))

    if task.result_summary:
        lines.append(f"\n**Summary:** {task.result_summary}")

    return "\n".join(lines)
