"""
MEMORA AI — Persistent Note Creation Tool
Requires explicit user approval before execution. Persists to the dedicated notes table.
"""
from typing import Dict, Any, Optional
from app.agent.models import ToolPermission
from app.agent.tools.base import BaseTool
from app.services.note_service import create_note, find_note_by_idempotency_key

from pydantic import BaseModel, Field

class CreateNoteArgs(BaseModel):
    title: str = Field(..., min_length=1, max_length=255, description="Note title")
    content: str = Field(..., min_length=1, max_length=20000, description="Note body content")
    idempotency_key: Optional[str] = Field(default=None, description="Stable idempotency key")

class CreateNoteTool(BaseTool):
    name = "create_note"
    description = (
        "Create and save a persistent note in database. "
        "Requires explicit user authorization before writing. "
        "Arguments: 'title' (string, required), 'content' (string, required)."
    )
    permission = ToolPermission.APPROVAL_REQUIRED
    is_idempotent = False
    category = "storage"
    risk_level = "state_modifying"
    args_schema = CreateNoteArgs

    async def execute(self, session_id: str, **kwargs) -> Dict[str, Any]:
        title = kwargs.get("title")
        if not title or not isinstance(title, str) or not title.strip():
            raise ValueError("create_note requires a non-empty 'title' string.")

        content = kwargs.get("content")
        if not content or not isinstance(content, str) or not content.strip():
            raise ValueError("create_note requires a non-empty 'content' string.")

        clean_title = title.strip()
        clean_content = content.strip()
        idempotency_key = kwargs.get("idempotency_key")

        if len(clean_title) > 255:
            raise ValueError("Note title cannot exceed 255 characters.")
        if len(clean_content) > 20000:
            raise ValueError("Note content cannot exceed 20,000 characters.")

        # Persist to database with idempotency key
        saved_note = await create_note(
            session_id=session_id,
            title=clean_title,
            content=clean_content,
            idempotency_key=idempotency_key
        )

        return {
            "success": True,
            "note_id": str(saved_note["id"]),
            "title": saved_note["title"],
            "created_at": saved_note["created_at"].isoformat() if hasattr(saved_note["created_at"], "isoformat") else str(saved_note["created_at"]),
            "message": f"Successfully created persistent note '{clean_title}'."
        }

    async def reconcile(self, session_id: str, idempotency_key: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Reconcile note status by idempotency key before attempting any retry."""
        if not idempotency_key:
            return None
        existing = await find_note_by_idempotency_key(session_id, idempotency_key)
        if existing:
            return {
                "success": True,
                "note_id": str(existing["id"]),
                "title": existing["title"],
                "created_at": existing["created_at"].isoformat() if hasattr(existing["created_at"], "isoformat") else str(existing["created_at"]),
                "message": f"Reconciled existing persistent note '{existing['title']}'."
            }
        return None
