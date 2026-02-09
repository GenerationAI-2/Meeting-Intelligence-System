"""OAuth 2.1 implementation for ChatGPT MCP support.

Implements:
- Dynamic Client Registration (RFC 7591)
- Authorization Code Flow with PKCE (RFC 7636)
- Well-known metadata endpoints (RFC 8414)

This is an MVP in-memory implementation. For production, store clients and
auth codes in a database.
"""

import secrets
import hashlib
import base64
import uuid
import jwt
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Form, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from pydantic import BaseModel

from .config import get_settings

router = APIRouter()

# In-memory storage (MVP - lost on restart)
# For production, use database tables
registered_clients: dict[str, dict] = {}
pending_auth_codes: dict[str, dict] = {}


def get_base_url() -> str:
    """Get the OAuth base URL from settings or default."""
    settings = get_settings()
    if settings.oauth_base_url:
        return settings.oauth_base_url.rstrip("/")
    # Fallback for local dev
    return f"http://{settings.host}:{settings.port}"


def get_jwt_secret() -> str:
    """Get JWT secret, generating one if not configured (dev only)."""
    settings = get_settings()
    if settings.jwt_secret:
        return settings.jwt_secret
    # For local dev, use a random secret (tokens won't survive restart)
    return secrets.token_urlsafe(32)


# ============================================================================
# WELL-KNOWN METADATA ENDPOINTS
# ============================================================================

@router.get("/.well-known/oauth-protected-resource")
async def oauth_protected_resource():
    """RFC 8414 - Protected Resource Metadata.

    ChatGPT uses this to discover which authorization server protects this resource.
    """
    base_url = get_base_url()
    return {
        "resource": base_url,
        "authorization_servers": [base_url],
        "scopes_supported": ["mcp:read", "mcp:write"],
        "bearer_methods_supported": ["header"]
    }


@router.get("/.well-known/oauth-authorization-server")
async def oauth_authorization_server():
    """RFC 8414 - Authorization Server Metadata.

    ChatGPT uses this to discover OAuth endpoints and capabilities.
    """
    base_url = get_base_url()
    return {
        "issuer": base_url,
        "authorization_endpoint": f"{base_url}/oauth/authorize",
        "token_endpoint": f"{base_url}/oauth/token",
        "registration_endpoint": f"{base_url}/oauth/register",
        "scopes_supported": ["mcp:read", "mcp:write"],
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["client_secret_post"]
    }


# ============================================================================
# DYNAMIC CLIENT REGISTRATION (RFC 7591)
# ============================================================================

class ClientRegistrationRequest(BaseModel):
    """Request body for client registration."""
    redirect_uris: list[str]
    client_name: Optional[str] = None
    scope: Optional[str] = None


@router.post("/oauth/register")
async def register_client(request: ClientRegistrationRequest):
    """Register a new OAuth client (used by ChatGPT).

    ChatGPT calls this automatically to register itself before starting OAuth flow.
    """
    client_id = str(uuid.uuid4())
    client_secret = secrets.token_urlsafe(32)

    registered_clients[client_id] = {
        "client_secret": client_secret,
        "redirect_uris": request.redirect_uris,
        "client_name": request.client_name or "ChatGPT",
        "scope": request.scope or "mcp:read mcp:write",
        "created_at": datetime.utcnow().isoformat()
    }

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uris": request.redirect_uris,
        "client_name": request.client_name or "ChatGPT",
        "token_endpoint_auth_method": "client_secret_post"
    }


# ============================================================================
# AUTHORIZATION ENDPOINT (with PKCE)
# ============================================================================

@router.get("/oauth/authorize")
async def authorize(
    response_type: str,
    client_id: str,
    redirect_uri: str,
    scope: str = "mcp:read mcp:write",
    state: str = "",
    code_challenge: str = "",
    code_challenge_method: str = "S256"
):
    """Authorization endpoint with PKCE support.

    For MVP: auto-approves all requests (no consent screen).
    Production: would show a consent screen asking user to approve.
    """
    # Validate client exists
    if client_id not in registered_clients:
        raise HTTPException(400, f"Invalid client_id: {client_id}")

    client = registered_clients[client_id]

    # Validate redirect_uri
    if redirect_uri not in client["redirect_uris"]:
        raise HTTPException(400, f"Invalid redirect_uri: {redirect_uri}")

    # Validate response_type
    if response_type != "code":
        raise HTTPException(400, "Only response_type=code is supported")

    # Validate PKCE (required for ChatGPT)
    if code_challenge_method != "S256":
        raise HTTPException(400, "Only S256 code_challenge_method is supported")

    if not code_challenge:
        raise HTTPException(400, "code_challenge is required")

    # Generate authorization code
    auth_code = secrets.token_urlsafe(32)

    # Store pending auth code with PKCE challenge
    pending_auth_codes[auth_code] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(minutes=10)
    }

    # For MVP: auto-approve and redirect back with code
    # Build redirect URL with code and state
    redirect_url = f"{redirect_uri}?code={auth_code}"
    if state:
        redirect_url += f"&state={state}"

    return RedirectResponse(redirect_url, status_code=302)


# ============================================================================
# TOKEN ENDPOINT
# ============================================================================

@router.post("/oauth/token")
async def token(
    grant_type: str = Form(...),
    code: Optional[str] = Form(None),
    redirect_uri: Optional[str] = Form(None),
    client_id: str = Form(...),
    client_secret: str = Form(...),
    code_verifier: Optional[str] = Form(None),
    refresh_token: Optional[str] = Form(None)
):
    """Token endpoint - exchanges auth code for tokens or refreshes tokens.

    Supports:
    - authorization_code grant (with PKCE validation)
    - refresh_token grant
    """
    jwt_secret = get_jwt_secret()
    base_url = get_base_url()

    # Validate client credentials
    if client_id not in registered_clients:
        raise HTTPException(401, "Invalid client_id")

    client = registered_clients[client_id]
    if client["client_secret"] != client_secret:
        raise HTTPException(401, "Invalid client_secret")

    if grant_type == "authorization_code":
        # Validate auth code exists
        if not code or code not in pending_auth_codes:
            raise HTTPException(400, "Invalid or expired authorization code")

        auth = pending_auth_codes[code]

        # Validate auth code hasn't expired
        if datetime.utcnow() > auth["expires_at"]:
            del pending_auth_codes[code]
            raise HTTPException(400, "Authorization code expired")

        # Validate client_id matches
        if auth["client_id"] != client_id:
            raise HTTPException(400, "client_id mismatch")

        # Validate redirect_uri matches
        if redirect_uri and auth["redirect_uri"] != redirect_uri:
            raise HTTPException(400, "redirect_uri mismatch")

        # Validate PKCE code_verifier
        if not code_verifier:
            raise HTTPException(400, "code_verifier is required")

        # S256: BASE64URL(SHA256(code_verifier)) == code_challenge
        verifier_hash = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).decode().rstrip("=")

        if verifier_hash != auth["code_challenge"]:
            raise HTTPException(400, "Invalid code_verifier")

        # Clean up used auth code
        del pending_auth_codes[code]

        # Generate tokens
        now = datetime.utcnow()
        access_token = jwt.encode({
            "iss": base_url,
            "sub": client_id,
            "aud": base_url,
            "scope": auth["scope"],
            "iat": now,
            "exp": now + timedelta(hours=1)
        }, jwt_secret, algorithm="HS256")

        refresh = jwt.encode({
            "iss": base_url,
            "sub": client_id,
            "type": "refresh",
            "iat": now,
            "exp": now + timedelta(days=30)
        }, jwt_secret, algorithm="HS256")

        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": 3600,
            "refresh_token": refresh,
            "scope": auth["scope"]
        }

    elif grant_type == "refresh_token":
        if not refresh_token:
            raise HTTPException(400, "refresh_token is required")

        try:
            payload = jwt.decode(refresh_token, jwt_secret, algorithms=["HS256"])

            # Validate this is actually a refresh token
            if payload.get("type") != "refresh":
                raise HTTPException(400, "Invalid refresh token")

            # Validate client_id matches
            if payload.get("sub") != client_id:
                raise HTTPException(400, "client_id mismatch")

            # Issue new access token
            now = datetime.utcnow()
            access_token = jwt.encode({
                "iss": base_url,
                "sub": client_id,
                "aud": base_url,
                "scope": "mcp:read mcp:write",
                "iat": now,
                "exp": now + timedelta(hours=1)
            }, jwt_secret, algorithm="HS256")

            return {
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_in": 3600
            }

        except jwt.ExpiredSignatureError:
            raise HTTPException(401, "Refresh token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(401, "Invalid refresh token")

    else:
        raise HTTPException(400, f"Unsupported grant_type: {grant_type}")


# ============================================================================
# TOKEN VALIDATION (for use by MCP auth middleware)
# ============================================================================

def validate_oauth_token(token: str) -> Optional[dict]:
    """Validate an OAuth access token and return claims.

    Returns None if token is invalid, otherwise returns the token payload.
    Used by MCP auth middleware to validate Bearer tokens from ChatGPT.
    """
    try:
        jwt_secret = get_jwt_secret()
        base_url = get_base_url()

        # Decode with audience validation
        payload = jwt.decode(
            token,
            jwt_secret,
            algorithms=["HS256"],
            audience=base_url,
            issuer=base_url
        )

        # Ensure this is an access token (not refresh)
        if payload.get("type") == "refresh":
            return None

        return payload
    except jwt.InvalidTokenError:
        return None
