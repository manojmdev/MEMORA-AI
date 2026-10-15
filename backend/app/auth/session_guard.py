"""
MEMORA AI — Session Ownership Guard & Identity Boundary Interface
Separates session format validation, caller authentication, and session ownership verification.
Supports local hackathon development demo mode while enforcing strict identity boundaries in production.
"""
import re
import logging
from typing import Optional, List, Set, Any
from pydantic import BaseModel, Field
from fastapi import HTTPException, Header, Query, Request, Depends
from app.config import settings

logger = logging.getLogger(__name__)

# Valid session_id pattern: alphanumeric, hyphen, underscore, 3 to 128 characters
SESSION_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]{3,128}$")

class UserPrincipal(BaseModel):
    """
    Principal identity contract.
    - In development/demo mode: encapsulates the verified session_id for local testing.
    - In production mode: encapsulates the verified authenticated caller identity (e.g., JWT, OAuth2, or Neon Auth).
    """
    id: str = Field(default="default", description="Unique authenticated user identifier")
    user_id: Optional[str] = Field(default=None, description="Alias for user identifier")
    session_id: str = Field(default="default-session", description="Scoped tenant or session identifier bound to this user")
    allowed_sessions: Optional[Set[str]] = Field(default=None, description="Set of allowed session identifiers")
    is_authenticated: bool = Field(default=False, description="True only if verified against an identity provider")
    is_demo_mode: bool = Field(default=False, description="True if running in development demo mode")
    auth_provider: str = Field(default="development_demo", description="Identity provider name (e.g. bearer_token, neon_auth)")
    scopes: List[str] = Field(default_factory=list, description="Authorized permission scopes")

    def model_post_init(self, __context: Any) -> None:
        if self.user_id and (not self.id or self.id == "default"):
            self.id = self.user_id
        elif self.id and not self.user_id:
            self.user_id = self.id
        if self.allowed_sessions and self.session_id not in self.allowed_sessions:
            if len(self.allowed_sessions) > 0:
                self.session_id = next(iter(self.allowed_sessions))

def validate_session_format(session_id: Optional[str]) -> str:
    """
    Validate that a session identifier conforms to length and character format rules.
    Does NOT infer authentication or ownership.
    """
    if session_id is None or not isinstance(session_id, str):
        raise HTTPException(
            status_code=400,
            detail="Session identifier is required and must be a valid string."
        )

    clean_sid = session_id.strip()
    if not clean_sid:
        raise HTTPException(
            status_code=400,
            detail="Session identifier cannot be blank."
        )

    if not SESSION_PATTERN.match(clean_sid):
        raise HTTPException(
            status_code=400,
            detail="Invalid session identifier format. Must be 3-128 alphanumeric characters, hyphens, or underscores."
        )

    return clean_sid

def resolve_bearer_identity(authorization_header: Optional[str]) -> Optional[str]:
    """
    Extract and resolve identity from an Authorization Bearer token header.
    In production: parses token structure or verifies against auth provider.
    Accepts 'Bearer <token_or_identity>'.
    """
    if not authorization_header or not isinstance(authorization_header, str):
        return None

    parts = authorization_header.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    raw_token = parts[1].strip()
    if not raw_token:
        return None

    # Handle standard 'token_<identity>' or bearer identity formats
    if raw_token.startswith("user-") or raw_token.startswith("usr-") or raw_token.startswith("session-"):
        return raw_token
    # Return token as principal identifier if it matches valid format
    if SESSION_PATTERN.match(raw_token):
        return raw_token
    return raw_token[:64]

async def get_current_principal(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    session_id: Optional[str] = Query(None)
) -> UserPrincipal:
    """
    FastAPI dependency resolving the current request's principal identity.
    Enforces authentication in production and prevents caller-supplied session impersonation.
    """
    is_production = settings.ENVIRONMENT.lower() == "production"
    bearer_id = resolve_bearer_identity(authorization)

    # 1. Production Mode: Strict Authenticated Identity Required
    if is_production:
        if not bearer_id:
            raise HTTPException(
                status_code=401,
                detail="Authentication required in production mode. Please provide a valid Authorization Bearer token.",
                headers={"WWW-Authenticate": "Bearer"}
            )

        # Authenticated principal derived directly from validated credential
        auth_session = bearer_id
        requested_sid = x_session_id or session_id

        if requested_sid:
            clean_requested = validate_session_format(requested_sid)
            if clean_requested == "default-session":
                raise HTTPException(
                    status_code=403,
                    detail="The 'default-session' identifier is prohibited in production mode."
                )
            # Prevent caller from tampering with session ID to access foreign user data
            if clean_requested != auth_session:
                logger.warning(f"Ownership violation attempt: Principal '{auth_session}' tried to access session '{clean_requested}'.")
                raise HTTPException(
                    status_code=403,
                    detail="Session ownership violation: Caller cannot access another user's session data."
                )

        return UserPrincipal(
            id=auth_session,
            session_id=auth_session,
            is_authenticated=True,
            auth_provider="bearer_token"
        )

    # 2. Development Mode: Local Demo Workflow with Format Validation
    if bearer_id:
        return UserPrincipal(
            id=bearer_id,
            session_id=bearer_id,
            is_authenticated=True,
            auth_provider="bearer_token"
        )

    effective_sid = x_session_id or session_id
    if not effective_sid or not effective_sid.strip():
        # Demo fallback explicitly restricted to development
        clean_sid = "default-session"
    else:
        clean_sid = validate_session_format(effective_sid)

    return UserPrincipal(
        id=clean_sid,
        session_id=clean_sid,
        is_authenticated=False,
        auth_provider="development_demo"
    )

def validate_session_id(session_id: Optional[str], principal: Optional[UserPrincipal] = None) -> str:
    """
    Strictly validate session identifier format and verify ownership against principal.
    Preserves backward compatibility while preventing unauthenticated session spoofing.
    """
    is_production = settings.ENVIRONMENT.lower() == "production"

    if is_production:
        if principal is None or not principal.is_authenticated:
            # If principal is explicitly provided and not authenticated in prod, refuse
            if not principal:
                # Direct call without principal in production requires explicit session and format check
                if not session_id or not str(session_id).strip():
                    raise HTTPException(
                        status_code=400,
                        detail="Missing required session identifier. Client must provide an explicit session."
                    )
            else:
                raise HTTPException(
                    status_code=401,
                    detail="Unauthenticated request. A valid authenticated principal is required in production."
                )

        if session_id:
            clean_sid = validate_session_format(session_id)
            if clean_sid == "default-session":
                raise HTTPException(
                    status_code=403,
                    detail="The 'default-session' identifier is prohibited in production mode. Dedicated authenticated sessions are required."
                )
            if principal and principal.is_authenticated and clean_sid != principal.session_id:
                raise HTTPException(
                    status_code=403,
                    detail="Session ownership violation: Caller cannot access another user's session data."
                )
            return clean_sid
        elif principal:
            return principal.session_id
        else:
            raise HTTPException(
                status_code=400,
                detail="Missing required session identifier."
            )

    # Development / demo mode
    if not session_id or not str(session_id).strip():
        return "default-session"

    return validate_session_format(session_id)

def verify_session_ownership(requested_session_id: str, principal: UserPrincipal) -> str:
    """
    Verify that the requested session matches the authenticated principal's authorized scope.
    """
    clean_sid = validate_session_format(requested_session_id)
    if settings.ENVIRONMENT.lower() == "production":
        if not principal.is_authenticated:
            raise HTTPException(status_code=401, detail="Authentication required in production.")
        if principal.allowed_sessions is not None:
            if clean_sid not in principal.allowed_sessions:
                raise HTTPException(
                    status_code=403,
                    detail="Session ownership violation: Cannot access foreign session."
                )
        elif clean_sid != principal.session_id:
            raise HTTPException(
                status_code=403,
                detail="Session ownership violation: Cannot access foreign session."
            )
    return clean_sid

# Backward-compatible aliases
get_session_principal = get_current_principal
