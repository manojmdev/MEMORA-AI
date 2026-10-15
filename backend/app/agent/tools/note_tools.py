"""
MEMORA AI — Persistent Note Creation Tool
Requires explicit user approval before execution. Persists to the dedicated notes table.
"""
from typing import Dict, Any
from app.agent.models import ToolPermission
from app.agent.tools.base import BaseTool
from app.services.note_service import create_note

class CreateNoteTool(BaseTool):
    name = "create_note"
    description = (
        "Create and save a persistent note in database. "
        "Requires explicit user authorization before writing. "
        "Arguments: 'title' (string, required), 'content' (string, required)."
    )
    permission = ToolPermission.APPROVAL_REQUIRED

    async def execute(self, session_id: str, **kwargs) -> Dict[str, Any]:
        title = kwargs.get("title")
        if not title or not isinstance(title, str) or not title.strip():
            raise ValueError("create_note requires a non-empty 'title' string.")

        content = kwargs.get("content")
        if not content or not isinstance(content, str) or not content.strip():
            raise ValueError("create_note requires a non-empty 'content' string.")

        clean_title = title.strip()
        clean_content = content.strip()

        if len(clean_title) > 255:
            raise ValueError("Note title cannot exceed 255 characters.")
        if len(clean_content) > 20000:
            raise ValueError("Note content cannot exceed 20,000 characters.")

        # Persist to database
        saved_note = await create_note(
            session_id=session_id,
            title=clean_title,
            content=clean_content
        )

        return {
            "success": True,
            "note_id": str(saved_note["id"]),
            "title": saved_note["title"],
            "created_at": saved_note["created_at"].isoformat() if hasattr(saved_note["created_at"], "isoformat") else str(saved_note["created_at"]),
            "message": f"Successfully created persistent note '{clean_title}'."
        }
