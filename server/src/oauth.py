"""OAuth 2.1 implementation for ChatGPT MCP support.

Implements:
- Dynamic Client Registration (RFC 7591)
- Authorization Code Flow with PKCE (RFC 7636)
- Well-known metadata endpoints (RFC 8414)

Client registrations are persisted to database and cached in-memory.
Authorization codes and access tokens remain in-memory (short-lived).
"""

import html as html_mod
import logging
import secrets
import hashlib
import base64
import uuid
import jwt
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlparse, urlencode

from fastapi import APIRouter, HTTPException, Form, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from pydantic import BaseModel

from .config import get_settings
from .database import save_oauth_client, load_all_oauth_clients, validate_client_token, consume_refresh_token

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory cache for OAuth clients (loaded from DB on startup, updated on register)
_oauth_clients_cache: dict[str, dict] = {}

# Authorization codes stay in-memory (short-lived, lost on restart is fine)
pending_auth_codes: dict[str, dict] = {}


def init_oauth_clients():
    """Load OAuth clients from database into memory cache. Call on app startup."""
    global _oauth_clients_cache
    try:
        result = load_all_oauth_clients()
        if isinstance(result, dict) and not result.get("error"):
            _oauth_clients_cache = result
            logger.info("Loaded %d OAuth clients from database", len(_oauth_clients_cache))
        elif isinstance(result, dict) and result.get("error"):
            logger.warning("Failed to load OAuth clients from database: %s", result.get("message"))
            _oauth_clients_cache = {}
        else:
            _oauth_clients_cache = result or {}
            logger.info("Loaded %d OAuth clients from database", len(_oauth_clients_cache))
    except Exception as e:
        logger.warning("Could not load OAuth clients from database: %s", e)
        _oauth_clients_cache = {}


def _get_client(client_id: str) -> dict | None:
    """Get OAuth client from in-memory cache."""
    return _oauth_clients_cache.get(client_id)


def get_base_url() -> str:
    """Get the OAuth base URL from settings or default."""
    settings = get_settings()
    if settings.oauth_base_url:
        return settings.oauth_base_url.rstrip("/")
    # Fallback for local dev
    return f"http://{settings.host}:{settings.port}"


def get_jwt_secret() -> str:
    """Get current JWT secret for signing new tokens."""
    settings = get_settings()
    if settings.jwt_secret:
        return settings.jwt_secret
    # For local dev, use a random secret (tokens won't survive restart)
    return secrets.token_urlsafe(32)


def _decode_jwt_with_rotation(token: str, **kwargs) -> dict:
    """Decode a JWT, trying the current secret first, then the previous.

    During key rotation, tokens signed with the old key remain valid for
    the rotation window (30 days to cover refresh token lifetime).
    Raises jwt.InvalidTokenError if neither key works.
    """
    current_secret = get_jwt_secret()
    settings = get_settings()
    previous_secret = settings.jwt_secret_previous or None

    try:
        return jwt.decode(token, current_secret, algorithms=["HS256"], **kwargs)
    except jwt.InvalidTokenError:
        if previous_secret:
            # Fall back to previous key during rotation window
            return jwt.decode(token, previous_secret, algorithms=["HS256"], **kwargs)
        raise


# ============================================================================
# REDIRECT URI ALLOWLIST
# ============================================================================

# Default allowed domains for OAuth redirect URIs.
# Override via OAUTH_ALLOWED_REDIRECT_DOMAINS env var (comma-separated).
_DEFAULT_ALLOWED_REDIRECT_DOMAINS = [
    "claude.ai",
    "claude.com",
    "chatgpt.com",
    "openai.com",
    "localhost",
    "127.0.0.1",
]


def _get_allowed_redirect_domains() -> list[str]:
    """Get allowed redirect URI domains from config or defaults."""
    settings = get_settings()
    if settings.oauth_allowed_redirect_domains:
        return [d.strip() for d in settings.oauth_allowed_redirect_domains.split(",") if d.strip()]
    return _DEFAULT_ALLOWED_REDIRECT_DOMAINS


def _validate_redirect_uri(uri: str) -> bool:
    """Check if a redirect URI belongs to an allowed domain."""
    try:
        parsed = urlparse(uri)
        hostname = parsed.hostname or ""
        allowed = _get_allowed_redirect_domains()
        return any(
            hostname == domain or hostname.endswith(f".{domain}")
            for domain in allowed
        )
    except Exception:
        return False


# ============================================================================
# MCP TOKEN VALIDATION (reuses DB-backed ClientToken lookup)
# ============================================================================

def _validate_mcp_token(token: str) -> str | None:
    """Validate an MCP client token. Returns client email if valid, None if not.

    Uses the same SHA256 hash → ClientToken table lookup as the auth middleware.
    """
    if not token:
        return None
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    result = validate_client_token(token_hash)
    if isinstance(result, dict) and not result.get("error") and result.get("client_email"):
        return result["client_email"]
    return None


# ============================================================================
# CONSENT PAGE HTML
# ============================================================================

def _render_consent_page(
    app_name: str,
    error: str = "",
    **oauth_params,
) -> str:
    """Render the OAuth consent HTML page."""
    safe_name = html_mod.escape(app_name or "Unknown application")

    error_html = ""
    if error:
        error_html = f'<div class="error">{html_mod.escape(error)}</div>'

    hidden = ""
    for key, value in oauth_params.items():
        hidden += f'<input type="hidden" name="{html_mod.escape(key)}" value="{html_mod.escape(str(value))}">'

    return f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Connect to Meeting Intelligence</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f5f5f5;display:flex;justify-content:center;align-items:center;min-height:100vh;padding:20px}}
.card{{background:#fff;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,.1);padding:32px;max-width:420px;width:100%}}
h1{{font-size:20px;margin-bottom:8px;color:#1a1a1a}}
.subtitle{{color:#666;font-size:14px;margin-bottom:24px}}
.app-name{{font-weight:600;color:#333;background:#f0f0f0;padding:2px 8px;border-radius:4px}}
label{{display:block;font-size:14px;font-weight:500;color:#333;margin-bottom:6px}}
input[type="password"]{{width:100%;padding:10px 12px;border:1px solid #ddd;border-radius:8px;font-size:14px;outline:none;transition:border-color .2s}}
input:focus{{border-color:#0066cc}}
.error{{background:#fef2f2;border:1px solid #fecaca;color:#dc2626;padding:10px 12px;border-radius:8px;font-size:13px;margin-bottom:16px}}
button{{width:100%;padding:10px;background:#0066cc;color:#fff;border:none;border-radius:8px;font-size:14px;font-weight:500;cursor:pointer;margin-top:16px;transition:background .2s}}
button:hover{{background:#0052a3}}
</style>
</head><body>
<div class="card">
<h1>Connect to Meeting Intelligence</h1>
<p class="subtitle"><span class="app-name">{safe_name}</span> wants to access your meeting data.</p>
{error_html}
<form method="post" action="/oauth/authorize">
<label for="token">Enter your access token</label>
<input type="password" id="token" name="token" placeholder="Paste your MCP client token" required autocomplete="off">
{hidden}
<button type="submit">Connect</button>
</form>
</div>
</body></html>"""


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
        "revocation_endpoint": f"{base_url}/oauth/revoke",
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
    """Register a new OAuth client (used by ChatGPT/Claude).

    ChatGPT and Claude call this automatically to register before starting OAuth flow.
    Validates redirect_uris against allowed domains, then persists to database.
    """
    # Validate all redirect URIs against allowed domains
    rejected = [uri for uri in request.redirect_uris if not _validate_redirect_uri(uri)]
    if rejected:
        raise HTTPException(400, {
            "error": "invalid_redirect_uri",
            "error_description": "redirect_uri must be from an approved AI platform domain",
        })

    client_id = str(uuid.uuid4())
    client_secret = secrets.token_urlsafe(32)
    client_secret_hash = hashlib.sha256(client_secret.encode()).hexdigest()

    client_data = {
        "client_id": client_id,
        "client_secret": client_secret_hash,
        "redirect_uris": request.redirect_uris,
        "client_name": request.client_name or "ChatGPT",
        "scope": request.scope or "mcp:read mcp:write",
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "client_secret_post",
    }

    # Persist to database
    save_oauth_client(client_data)

    # Update in-memory cache
    _oauth_clients_cache[client_id] = client_data
    logger.info("Registered OAuth client: %s", client_id)

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

def _validate_authorize_params(
    response_type: str,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    code_challenge_method: str,
) -> dict:
    """Validate OAuth authorize parameters. Returns the client dict or raises HTTPException."""
    client = _get_client(client_id)
    if not client:
        raise HTTPException(400, f"Invalid client_id: {client_id}")

    if redirect_uri not in client["redirect_uris"]:
        raise HTTPException(400, f"Invalid redirect_uri: {redirect_uri}")

    if response_type != "code":
        raise HTTPException(400, "Only response_type=code is supported")

    if code_challenge_method != "S256":
        raise HTTPException(400, "Only S256 code_challenge_method is supported")

    if not code_challenge:
        raise HTTPException(400, "code_challenge is required")

    return client


@router.get("/oauth/authorize")
async def authorize_get(
    response_type: str,
    client_id: str,
    redirect_uri: str,
    scope: str = "mcp:read mcp:write",
    state: str = "",
    code_challenge: str = "",
    code_challenge_method: str = "S256",
):
    """Authorization endpoint — renders consent page requiring MCP token."""
    client = _validate_authorize_params(
        response_type, client_id, redirect_uri, code_challenge, code_challenge_method
    )

    return HTMLResponse(_render_consent_page(
        app_name=client.get("client_name", "Unknown application"),
        response_type=response_type,
        client_id=client_id,
        redirect_uri=redirect_uri,
        scope=scope,
        state=state,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
    ))


@router.post("/oauth/authorize")
async def authorize_post(
    response_type: str = Form(...),
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    scope: str = Form("mcp:read mcp:write"),
    state: str = Form(""),
    code_challenge: str = Form(""),
    code_challenge_method: str = Form("S256"),
    token: str = Form(...),
):
    """Authorization endpoint — validates MCP token, then issues auth code."""
    client = _validate_authorize_params(
        response_type, client_id, redirect_uri, code_challenge, code_challenge_method
    )

    # Validate the MCP client token
    client_email = _validate_mcp_token(token)
    if not client_email:
        return HTMLResponse(_render_consent_page(
            app_name=client.get("client_name", "Unknown application"),
            error="Invalid token. Please check your access token and try again.",
            response_type=response_type,
            client_id=client_id,
            redirect_uri=redirect_uri,
            scope=scope,
            state=state,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
        ))

    # Token valid — generate authorization code
    auth_code = secrets.token_urlsafe(32)

    pending_auth_codes[auth_code] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(minutes=10),
    }

    logger.info("OAuth authorized for client %s by %s", client_id, client_email)

    params = {"code": auth_code}
    if state:
        params["state"] = state
    redirect_url = f"{redirect_uri}?{urlencode(params)}"

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
    client = _get_client(client_id)
    if not client:
        raise HTTPException(401, "Invalid client_id")

    if client.get("client_secret") != hashlib.sha256(client_secret.encode()).hexdigest():
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

        token_family = str(uuid.uuid4())
        refresh = jwt.encode({
            "iss": base_url,
            "sub": client_id,
            "type": "refresh",
            "family": token_family,
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
            payload = _decode_jwt_with_rotation(refresh_token)

            # Validate this is actually a refresh token
            if payload.get("type") != "refresh":
                raise HTTPException(400, "Invalid refresh token")

            # Validate client_id matches
            if payload.get("sub") != client_id:
                raise HTTPException(400, "client_id mismatch")

            # Refresh token rotation: mark this token as consumed.
            # If already consumed, this is a replay (possible token theft).
            token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
            family_id = payload.get("family", "legacy")
            if not consume_refresh_token(token_hash, family_id, client_id):
                logger.warning("Refresh token replay detected for client %s, family %s", client_id, family_id)
                raise HTTPException(401, "Refresh token has already been used")

            # Issue new access token + rotated refresh token
            now = datetime.utcnow()
            access_token = jwt.encode({
                "iss": base_url,
                "sub": client_id,
                "aud": base_url,
                "scope": "mcp:read mcp:write",
                "iat": now,
                "exp": now + timedelta(hours=1)
            }, jwt_secret, algorithm="HS256")

            new_refresh = jwt.encode({
                "iss": base_url,
                "sub": client_id,
                "type": "refresh",
                "family": family_id,
                "iat": now,
                "exp": now + timedelta(days=30)
            }, jwt_secret, algorithm="HS256")

            return {
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_in": 3600,
                "refresh_token": new_refresh
            }

        except jwt.ExpiredSignatureError:
            raise HTTPException(401, "Refresh token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(401, "Invalid refresh token")

    else:
        raise HTTPException(400, f"Unsupported grant_type: {grant_type}")


# ============================================================================
# TOKEN REVOCATION (RFC 7009)
# ============================================================================

@router.post("/oauth/revoke")
async def revoke_token(
    token: str = Form(...),
    token_type_hint: Optional[str] = Form(None),
):
    """Revoke an OAuth token per RFC 7009.

    For refresh tokens: marks as consumed so it cannot be reused.
    For access tokens: accepted but no action (stateless, expires in 1hr).
    Always returns 200 per RFC 7009 (even if token is invalid).
    """
    # Try to decode as refresh token and consume it
    try:
        payload = _decode_jwt_with_rotation(token)
        if payload.get("type") == "refresh":
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            family_id = payload.get("family", "legacy")
            client_id = payload.get("sub", "unknown")
            consume_refresh_token(token_hash, family_id, client_id)
            logger.info("Revoked refresh token for client %s", client_id)
    except jwt.InvalidTokenError:
        pass  # Per RFC 7009, invalid tokens get 200 too

    return {"status": "revoked"}


# ============================================================================
# TOKEN VALIDATION (for use by MCP auth middleware)
# ============================================================================

def validate_oauth_token(token: str) -> Optional[dict]:
    """Validate an OAuth access token and return claims.

    Returns None if token is invalid, otherwise returns the token payload.
    Used by MCP auth middleware to validate Bearer tokens from ChatGPT.
    Supports dual-key rotation — tries current key first, then previous.
    """
    try:
        base_url = get_base_url()
        payload = _decode_jwt_with_rotation(token, audience=base_url, issuer=base_url)

        # Ensure this is an access token (not refresh)
        if payload.get("type") == "refresh":
            return None

        return payload
    except jwt.InvalidTokenError:
        return None
