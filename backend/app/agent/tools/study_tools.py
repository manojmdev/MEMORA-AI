"""
MEMORA AI — Study Plan Generator Tool
Produces structured personalized study schedules utilizing user memory context and learning preferences.
"""
import json
import logging
import re
from typing import Dict, Any, Optional, List
from app.config import settings
from app.agent.models import ToolPermission
from app.agent.tools.base import BaseTool
from app.services.llm_service import client
from app.services.hybrid_retriever import retrieve_hybrid_memories

logger = logging.getLogger(__name__)

STUDY_PLAN_SYSTEM_PROMPT = """You are the Academic and Skill Curriculum Specialist for MEMORA AI.
Given a subject, duration in days, daily study hours, and relevant personal memories (learning style, skills),
generate a practical, step-by-step study curriculum formatted strictly as raw JSON.

OUTPUT JSON SCHEMA:
{
  "subject": "string",
  "total_days": int,
  "daily_hours": float,
  "overall_objective": "string",
  "schedule": [
    {
      "day": int,
      "topic": "string",
      "activities": ["string"],
      "learning_milestone": "string"
    }
  ],
  "recommended_resources": ["string"],
  "memory_alignments": ["string"]
}
Keep each day's topic and activities concise and brief (1-2 bullet points per day).
Respond ONLY with valid JSON. No conversational fluff or markdown fences.
"""

class GenerateStudyPlanTool(BaseTool):
    name = "generate_study_plan"
    description = (
        "Generate a structured, personalized multi-day curriculum or revision plan. "
        "Arguments: 'subject' (string, required), 'duration_days' (int, default 7), "
        "'hours_per_day' (float, default 2.0), 'focus_areas' (list of strings, optional)."
    )
    permission = ToolPermission.AUTOMATIC
    timeout_seconds = 60.0

    async def execute(self, session_id: str, **kwargs) -> Dict[str, Any]:
        subject = (
            kwargs.get("subject")
            or kwargs.get("topic")
            or kwargs.get("query")
            or kwargs.get("course")
            or kwargs.get("title")
            or ""
        )
        if not subject or not isinstance(subject, str) or not subject.strip():
            subject = "Personalized Learning Curriculum"
        else:
            clean_subj = re.sub(
                r"^(check\s+my\s+memories\s+(and\s+)?|generate\s+(a\s+)?study\s+plan\s+for\s+|create\s+(a\s+)?study\s+plan\s+for\s+|study\s+plan\s+for\s+)",
                "",
                subject,
                flags=re.IGNORECASE
            ).strip()
            if clean_subj:
                subject = clean_subj


        duration_days = kwargs.get("duration_days", 7)
        try:
            duration_days = max(1, min(int(duration_days), 30))
        except (ValueError, TypeError):
            duration_days = 7

        hours_per_day = kwargs.get("hours_per_day", 2.0)
        try:
            hours_per_day = max(0.5, min(float(hours_per_day), 12.0))
        except (ValueError, TypeError):
            hours_per_day = 2.0

        focus_areas = kwargs.get("focus_areas", [])
        if not isinstance(focus_areas, list):
            focus_areas = [str(focus_areas)]

        # Retrieve relevant user memories about this subject and user's learning style
        recalled_memories = await retrieve_hybrid_memories(
            session_id=session_id,
            query=f"learning style preferences for {subject}",
            limit=4
        )

        memory_hints = []
        for m in recalled_memories:
            memory_hints.append(f"- [{m.category}] {m.memory_key}: {m.content}")

        user_prompt = (
            f"Generate a {duration_days}-day study plan for '{subject}'.\n"
            f"Daily study commitment: {hours_per_day} hours/day.\n"
        )
        if focus_areas:
            user_prompt += f"Specific focus areas: {', '.join(focus_areas)}.\n"
        if memory_hints:
            user_prompt += "Known user background & preferences:\n" + "\n".join(memory_hints) + "\n"

        try:
            response = await client.chat.completions.create(
                model=settings.NEBIUS_MODEL,
                messages=[
                    {"role": "system", "content": STUDY_PLAN_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2,
            )
            raw = response.choices[0].message.content or "{}"
            raw_clean = re.sub(r"<thought>[\s\S]*?</thought>", "", raw, flags=re.IGNORECASE).strip()
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw_clean)
            if match:
                raw_clean = match.group(1).strip()
            
            start = raw_clean.find("{")
            if start != -1:
                depth = 0
                in_string = False
                escape = False
                for i in range(start, len(raw_clean)):
                    ch = raw_clean[i]
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
                                raw_clean = raw_clean[start:i+1]
                                break

            raw_clean = re.sub(r',\s*([}\]])', r'\1', raw_clean)
            parsed = json.loads(raw_clean)
            return parsed
        except Exception as e:
            logger.warning(f"Study plan JSON parse failed: {e}. Falling back to structured envelope.")
            return {
                "subject": subject,
                "total_days": duration_days,
                "daily_hours": hours_per_day,
                "overall_objective": f"Comprehensive masterplan for {subject}",
                "schedule": [
                    {
                        "day": day,
                        "topic": f"Module {day}: Core concepts of {subject}",
                        "activities": ["Review documentation", "Hands-on coding exercise"],
                        "learning_milestone": f"Completed Day {day} fundamentals"
                    }
                    for day in range(1, duration_days + 1)
                ],
                "recommended_resources": ["Official Documentation", "Practical Code Samples"],
                "memory_alignments": [m.content for m in recalled_memories]
            }
