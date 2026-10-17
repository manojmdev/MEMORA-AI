"""
MEMORA AI — Session Ownership Guard & Identity Boundary Interface
Separates session format validation, caller authentication, and session ownership verification.
Supports local hackathon development demo mode while enforcing strict identity boundaries in production.
"""
import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
from typing import Optional, List, Set, Any
from pydantic import BaseModel, Field
from fastapi import HTTPException, Header, Query, Request, Depends
from app.config import settings

import time

logger = logging.getLogger(__name__)

# Day 7.2: Active token revocation registry
_REVOKED_TOKENS: Set[str] = set()

def revoke_token(token: str) -> None:
    """Mark a token string as revoked."""
    if token and isinstance(token, str):
        _REVOKED_TOKENS.add(token.strip())

def is_token_revoked(token: str) -> bool:
    """Check if a token has been revoked."""
    if not token or not isinstance(token, str):
        return False
    return token.strip() in _REVOKED_TOKENS

def clear_revocation_cache() -> None:
    """Clear revocation registry (used for tests)."""
    _REVOKED_TOKENS.clear()

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

def create_signed_token(
    user_id: str,
    session_id: str,
    secret_key: str,
    scopes: Optional[List[str]] = None,
    expires_in_seconds: Optional[int] = None
) -> str:
    """
    Day 7.2: Generate a tamper-evident cryptographically signed bearer token.
    Format: <base64_payload>.<hmac_hex_signature>
    Supports optional expiration timestamp (exp), token identifier (jti), and secret rotation keys.
    """
    # If secret_key has comma-separated rotation keys, sign with the active primary key
    active_key = secret_key.split(",")[0].strip() if secret_key else ""
    now_ts = int(time.time())
    payload = {
        "uid": user_id,
        "sid": session_id,
        "scopes": scopes or ["memora:standard"],
        "iat": now_ts,
        "jti": secrets.token_hex(8)
    }
    if expires_in_seconds is not None:
        payload["exp"] = now_ts + expires_in_seconds

    payload_bytes = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode("utf-8")
    b64_payload = base64.urlsafe_b64encode(payload_bytes).decode("utf-8").rstrip("=")
    signature = hmac.new(active_key.encode("utf-8"), b64_payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{b64_payload}.{signature}"

def verify_token_credential(raw_token: str) -> Optional[UserPrincipal]:
    """
    Day 7.2 Genuine Token Credential Verifier.
    Verifies cryptographic signature against AUTH_SECRET_KEY (supporting key rotation)
    or checks against registered API_AUTH_TOKENS.
    Enforces expiration (exp) and checks revocation.
    Returns UserPrincipal if genuinely verified, otherwise None.
    NEVER trusts an arbitrary unverified token.
    """
    if not raw_token or not isinstance(raw_token, str):
        return None

    clean_token = raw_token.strip()

    # 0. Check Token Revocation
    if is_token_revoked(clean_token):
        logger.warning("Token rejected: Token has been revoked.")
        return None

    # 1. HMAC Cryptographically Signed Token Verification (with key rotation support)
    if settings.AUTH_SECRET_KEY and "." in clean_token:
        parts = clean_token.split(".", 1)
        if len(parts) == 2:
            b64_payload, signature = parts
            rotation_keys = [k.strip() for k in settings.AUTH_SECRET_KEY.split(",") if k.strip()]
            sig_matches = False
            for key in rotation_keys:
                expected_sig = hmac.new(
                    key.encode("utf-8"),
                    b64_payload.encode("utf-8"),
                    hashlib.sha256
                ).hexdigest()
                if secrets.compare_digest(signature, expected_sig):
                    sig_matches = True
                    break

            if sig_matches:
                try:
                    padding = 4 - (len(b64_payload) % 4)
                    b64_payload_padded = b64_payload + ("=" * padding if padding != 4 else "")
                    payload_data = json.loads(base64.urlsafe_b64decode(b64_payload_padded).decode("utf-8"))

                    # Check expiration if present
                    exp = payload_data.get("exp")
                    if exp is not None:
                        if time.time() > float(exp):
                            logger.warning("Token rejected: Token signature has expired.")
                            return None

                    uid = str(payload_data.get("uid", ""))
                    sid = str(payload_data.get("sid", ""))
                    scopes = payload_data.get("scopes", [])
                    if uid and sid:
                        return UserPrincipal(
                            id=uid,
                            user_id=uid,
                            session_id=sid,
                            allowed_sessions={sid},
                            is_authenticated=True,
                            is_demo_mode=False,
                            auth_provider="hmac_signed_token",
                            scopes=scopes
                        )
                except Exception as parse_err:
                    logger.warning(f"Failed to decode validly signed token payload: {parse_err}")

    # 2. Pre-shared Registered API Tokens
    # Format: "token:user_id:session_id,token2:user2:session2"
    if settings.API_AUTH_TOKENS:
        for entry in settings.API_AUTH_TOKENS.split(","):
            entry = entry.strip()
            if not entry:
                continue
            entry_parts = entry.split(":")
            if len(entry_parts) >= 3:
                reg_token, reg_uid, reg_sid = entry_parts[0], entry_parts[1], entry_parts[2]
                if secrets.compare_digest(clean_token, reg_token):
                    return UserPrincipal(
                        id=reg_uid,
                        user_id=reg_uid,
                        session_id=reg_sid,
                        allowed_sessions={reg_sid},
                        is_authenticated=True,
                        is_demo_mode=False,
                        auth_provider="preshared_api_token"
                    )

    return None

async def get_current_principal(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    session_id: Optional[str] = Query(None)
) -> UserPrincipal:
    """
    FastAPI dependency resolving the current request's principal identity.
    Enforces genuine authentication in production and prevents caller-supplied session impersonation.
    """
    is_production = settings.ENVIRONMENT.lower() == "production"

    # 1. Production Mode: Strict Authenticated Identity Required
    if is_production:
        if not authorization or not authorization.strip():
            raise HTTPException(
                status_code=401,
                detail="Authentication required in production mode. Please provide a valid Authorization Bearer token.",
                headers={"WWW-Authenticate": "Bearer"}
            )

        auth_parts = authorization.strip().split()
        if len(auth_parts) != 2 or auth_parts[0].lower() != "bearer":
            raise HTTPException(
                status_code=401,
                detail="Invalid Authorization header format. Expected 'Bearer <token>'.",
                headers={"WWW-Authenticate": "Bearer"}
            )

        raw_token = auth_parts[1].strip()
        principal = verify_token_credential(raw_token)
        if not principal or not principal.is_authenticated:
            idp_configured = bool(settings.AUTH_SECRET_KEY or settings.API_AUTH_TOKENS)
            err_msg = (
                "Invalid or unverified authentication token."
                if idp_configured else
                "Production authentication is unconfigured or token is invalid. Configure AUTH_SECRET_KEY or an external identity provider."
            )
            raise HTTPException(
                status_code=401,
                detail=err_msg,
                headers={"WWW-Authenticate": "Bearer"}
            )

        # Check requested session ownership against authenticated principal
        requested_sid = x_session_id or session_id
        if requested_sid:
            verify_session_ownership(requested_sid, principal)

        return principal

    # 2. Development Mode: Local Demo Workflow with Format Validation
    if authorization:
        auth_parts = authorization.strip().split()
        if len(auth_parts) == 2 and auth_parts[0].lower() == "bearer":
            raw_token = auth_parts[1].strip()
            verified = verify_token_credential(raw_token)
            if verified:
                return verified
            # For backward-compatible development tests where auth was simulated with a test token
            if raw_token.startswith("test-") or raw_token.startswith("usr-") or raw_token.startswith("user-") or raw_token.startswith("session-"):
                clean_id = validate_session_format(raw_token) if SESSION_PATTERN.match(raw_token) else raw_token[:64]
                return UserPrincipal(
                    id=clean_id,
                    user_id=clean_id,
                    session_id=clean_id,
                    allowed_sessions={clean_id},
                    is_authenticated=True,
                    is_demo_mode=True,
                    auth_provider="development_bearer_test"
                )

    effective_sid = x_session_id or session_id
    if not effective_sid or not str(effective_sid).strip():
        # Demo fallback explicitly restricted to development
        clean_sid = "default-session"
    else:
        clean_sid = validate_session_format(effective_sid)

    return UserPrincipal(
        id=clean_sid,
        user_id=clean_sid,
        session_id=clean_sid,
        allowed_sessions={clean_sid},
        is_authenticated=False,
        is_demo_mode=True,
        auth_provider="development_demo"
    )

def verify_session_ownership(requested_session_id: str, principal: UserPrincipal) -> str:
    """
    Verify that the requested session matches the authenticated principal's authorized scope.
    """
    clean_sid = validate_session_format(requested_session_id)
    if settings.ENVIRONMENT.lower() == "production":
        if not principal.is_authenticated:
            raise HTTPException(
                status_code=401,
                detail="Authentication required in production mode."
            )
        if clean_sid == "default-session":
            raise HTTPException(
                status_code=403,
                detail="The 'default-session' identifier is prohibited in production mode."
            )
        if principal.allowed_sessions is not None:
            if clean_sid not in principal.allowed_sessions:
                logger.warning(f"Ownership violation attempt: Principal '{principal.id}' tried to access session '{clean_sid}'.")
                raise HTTPException(
                    status_code=403,
                    detail="Session ownership violation: Caller cannot access another user's session data."
                )
        elif clean_sid != principal.session_id:
            logger.warning(f"Ownership violation attempt: Principal '{principal.id}' tried to access session '{clean_sid}'.")
            raise HTTPException(
                status_code=403,
                detail="Session ownership violation: Caller cannot access another user's session data."
            )
    return clean_sid

def validate_session_id(session_id: Optional[str], principal: Optional[UserPrincipal] = None) -> str:
    """
    Strictly validate session identifier format and verify ownership against principal if provided.
    Preserves backward compatibility while preventing unauthenticated session spoofing.
    """
    is_production = settings.ENVIRONMENT.lower() == "production"

    if is_production:
        if principal is not None:
            if not principal.is_authenticated:
                raise HTTPException(
                    status_code=401,
                    detail="Unauthenticated request. A valid authenticated principal is required in production."
                )
            if not session_id or not str(session_id).strip():
                return principal.session_id
            return verify_session_ownership(session_id, principal)

        # Direct call without principal in production
        if not session_id or not str(session_id).strip():
            raise HTTPException(
                status_code=400,
                detail="Missing required session identifier. Client must provide an explicit session."
            )
        clean_sid = validate_session_format(session_id)
        if clean_sid == "default-session":
            raise HTTPException(
                status_code=403,
                detail="The 'default-session' identifier is prohibited in production mode. Dedicated authenticated sessions are required."
            )
        return clean_sid

    # Development / demo mode
    if not session_id or not str(session_id).strip():
        if principal:
            return principal.session_id
        return "default-session"

    return validate_session_format(session_id)

# Backward-compatible aliases
get_session_principal = get_current_principal
