"""
MEMORA AI — Session Ownership Guard & Identity Boundary Interface
Validates session formats, prevents insecure default-session fallback in production,
and defines the principal authentication contract for multi-user deployment.
"""
import re
import logging
from typing import Optional
from pydantic import BaseModel
from fastapi import HTTPException, Header, Query, Request
from app.config import settings

logger = logging.getLogger(__name__)

# Valid session_id pattern: alphanumeric, hyphen, underscore, 3 to 128 characters
SESSION_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]{3,128}$")

class UserPrincipal(BaseModel):
    """
    Principal identity interface.
    In development/demo mode: encapsulates the verified session_id.
    In production mode: intended to bind to a verified JWT, OAuth2, or Neon Auth identity.
    """
    id: str
    session_id: str
    is_authenticated: bool = False
    auth_provider: str = "session_isolated"

def validate_session_id(session_id: Optional[str]) -> str:
    """
    Strictly validate a session identifier:
    - Must be non-empty and stripped of surrounding whitespace.
    - Must match regex (3-128 chars of letters, digits, hyphens, underscores).
    - In production mode, rejects 'default-session'.
    """
    if not session_id or not isinstance(session_id, str):
        if settings.ENVIRONMENT.lower() == "production":
            raise HTTPException(
                status_code=400,
                detail="Missing required session identifier. Client must provide an explicit session."
            )
        return "default-session"

    clean_sid = session_id.strip()

    if not clean_sid:
        if settings.ENVIRONMENT.lower() == "production":
            raise HTTPException(
                status_code=400,
                detail="Session identifier cannot be blank."
            )
        return "default-session"

    if clean_sid == "default-session" and settings.ENVIRONMENT.lower() == "production":
        raise HTTPException(
            status_code=403,
            detail="The 'default-session' identifier is prohibited in production mode. Dedicated authenticated sessions are required."
        )

    if not SESSION_PATTERN.match(clean_sid):
        raise HTTPException(
            status_code=400,
            detail="Invalid session identifier format. Must be 3-128 alphanumeric characters, hyphens, or underscores."
        )

    return clean_sid

async def get_session_principal(
    request: Request,
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    session_id: Optional[str] = Query(None)
) -> UserPrincipal:
    """
    FastAPI dependency resolving the current principal identity.
    Reads from X-Session-ID header first, then query parameter, validating format.
    """
    effective_sid = x_session_id or session_id
    valid_sid = validate_session_id(effective_sid)

    return UserPrincipal(
        id=valid_sid,
        session_id=valid_sid,
        is_authenticated=False,
        auth_provider="session_isolated"
    )
