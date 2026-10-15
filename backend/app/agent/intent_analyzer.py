"""
MEMORA AI — Agent Intent Analyzer
Classifies incoming user messages into actionable task archetypes using Nemotron + heuristics.
"""
import json
import logging
import re
from typing import Dict, Any
from app.config import settings
from app.services.llm_service import client

logger = logging.getLogger(__name__)

INTENT_SYSTEM_PROMPT = """You are the Intent Analyzer for MEMORA AI.
Analyze the user request and classify its primary intent into exactly ONE category:
- conversational: simple greeting, chit-chat, or direct conceptual question needing no tools.
- memory_lookup: query about what is remembered about the user (preferences, skills, goals, projects).
- calculation: numerical or arithmetic calculations.
- study_plan: request to produce a learning schedule, curriculum, or revision plan.
- persistent_write: request to create, write, or save a persistent note or document.
- multi_step_task: complex task combining multiple actions (e.g. check memories then plan and save).
- disallowed: requests for shell, bash, SQL, arbitrary code execution, or security violations.

Respond ONLY with raw JSON:
{
  "intent": "conversational" | "memory_lookup" | "calculation" | "study_plan" | "persistent_write" | "multi_step_task" | "disallowed",
  "confidence": float,
  "summary": "string",
  "suggested_tools": ["string"]
}
"""

async def analyze_intent(user_message: str) -> Dict[str, Any]:
    """Analyze and classify user intent using Nemotron with fallback heuristics."""
    clean_msg = user_message.strip()
    msg_lower = clean_msg.lower()

    # Fast heuristic checks for obvious security violations
    if any(term in msg_lower for term in ["bash", "shell", "eval(", "exec(", "drop table", "select * from"]):
        return {
            "intent": "disallowed",
            "confidence": 1.0,
            "summary": "Attempted execution of disallowed command or code injection.",
            "suggested_tools": []
        }

    try:
        response = await client.chat.completions.create(
            model=settings.NEBIUS_MODEL,
            messages=[
                {"role": "system", "content": INTENT_SYSTEM_PROMPT},
                {"role": "user", "content": clean_msg}
            ],
            temperature=0.1,
            max_tokens=1024
        )
        content = response.choices[0].message.content or "{}"
        
        # Remove reasoning tags if present
        cleaned_content = re.sub(r"<thought>[\s\S]*?</thought>", "", content, flags=re.IGNORECASE).strip()

        # Try regex markdown block
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned_content)
        candidate = match.group(1).strip() if match else cleaned_content

        # Extract balanced JSON object
        start = candidate.find("{")
        if start != -1:
            depth = 0
            in_string = False
            escape = False
            for i in range(start, len(candidate)):
                ch = candidate[i]
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
                            candidate = candidate[start:i+1]
                            break

        parsed = json.loads(candidate)
        logger.info(f"Analyzed intent: {parsed.get('intent')} (confidence={parsed.get('confidence')})")
        return parsed

    except Exception as e:
        logger.warning(f"Intent analysis LLM call failed ({e}). Using rule-based fallback.")
        # Rule-based fallback
        if any(w in msg_lower for w in ["calculate", "math", "+", "-", "*", "/", "sum", "divided", "times"]):
            return {"intent": "calculation", "confidence": 0.85, "summary": "Mathematical calculation", "suggested_tools": ["calculator"]}
        if any(w in msg_lower for w in ["study plan", "curriculum", "syllabus", "revision plan", "schedule"]):
            return {"intent": "study_plan", "confidence": 0.85, "summary": "Study curriculum generation", "suggested_tools": ["generate_study_plan"]}
        if any(w in msg_lower for w in ["save note", "create note", "write note", "take note", "save this as note"]):
            return {"intent": "persistent_write", "confidence": 0.90, "summary": "Persistent note write", "suggested_tools": ["create_note"]}
        if any(w in msg_lower for w in ["remember", "what do you know", "my skills", "my preferences", "stored memory"]):
            return {"intent": "memory_lookup", "confidence": 0.85, "summary": "Memory retrieval", "suggested_tools": ["search_memories"]}

        return {"intent": "conversational", "confidence": 0.70, "summary": "General conversational query", "suggested_tools": []}
