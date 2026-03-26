"""Meeting Intelligence MCP Server - Entry Point"""

import hashlib
import sys
import asyncio
import contextlib
import time as _time
import uuid
from contextvars import ContextVar

# Request correlation — set per-request, accessible from any async code path
request_id_var: ContextVar[str] = ContextVar("request_id", default="")

from .logging_config import configure_logging, get_logger
from .mcp_server import mcp, set_mcp_user, set_mcp_workspace_context
from .workspace_context import make_legacy_context
from . import database as _db_module
from .database import EngineRegistry

# Configure logging at module load (before any other imports that might log)
configure_logging()
logger = get_logger(__name__)

# Cache invalidation callback — set by run_http(), callable from admin.py
# Signature: invalidate_user_cache(email: str) -> None
_invalidate_user_cache_fn = None

def invalidate_user_cache(email: str) -> None:
    """Evict a user's workspace context from the in-memory cache.

    Called from admin.py after role/membership changes so the new
    permissions take effect immediately instead of waiting for cache TTL.
    No-op if not running in HTTP mode or if no callback is registered.
    """
    if _invalidate_user_cache_fn:
        _invalidate_user_cache_fn(email)


async def run_stdio():
    """Run MCP server over stdio (for local/Claude Desktop)."""
    await mcp.run(transport="stdio")


def run_http():
    """Run MCP server over Streamable HTTP + REST API."""
    import uvicorn
    import os
    from fastapi import Depends, FastAPI
    from fastapi.staticfiles import StaticFiles
    from starlette.responses import FileResponse, Response
    from starlette.middleware.cors import CORSMiddleware

    from starlette.responses import JSONResponse as StarletteJSONResponse

    from .api import app as api_app  # REST API endpoints
    from .admin import admin_router
    from .config import get_settings
    from .database import validate_client_token, validate_token_from_control_db
    from .dependencies import authenticate_and_store, resolve_workspace
    from .permissions import check_permission
    from .workspace_context import WorkspaceContext

    settings = get_settings()

    # ── OAuth 2.1 Provider (B17 — per-user MCP auth) ──────────────────
    import jwt as pyjwt
    from pydantic import AnyHttpUrl
    from starlette.responses import HTMLResponse

    _oauth_provider = None
    if settings.jwt_secret and settings.oauth_base_url:
        from .oauth_provider import MIOAuthProvider
        _oauth_provider = MIOAuthProvider(
            jwt_secret=settings.jwt_secret,
            oauth_base_url=settings.oauth_base_url,
        )
        logger.info("OAuth 2.1 provider enabled (base URL: %s)", settings.oauth_base_url)
    # ──────────────────────────────────────────────────────────────────

    # In-memory token cache — avoids DB hit on every MCP request
    # Trade-off: revoked tokens may still work for up to TOKEN_CACHE_TTL seconds
    _token_cache: dict[str, dict] = {}  # {hash: {"email": str, "expires_cache": float}}
    _token_cache_lock = asyncio.Lock()
    TOKEN_CACHE_TTL = 300  # 5 minutes
    TOKEN_CACHE_MAX_SIZE = 1000

    # Workspace context cache — avoids control DB hit on every MCP request
    # Keyed by email, same TTL as token cache
    _workspace_cache: dict[str, dict] = {}  # {email: {"ctx": WorkspaceContext, "expires": float}}

    # Register cache invalidation callback for use by admin.py
    global _invalidate_user_cache_fn
    def _do_invalidate_user_cache(email: str) -> None:
        email = email.strip().lower()
        removed = _workspace_cache.pop(email, None)
        if removed:
            logger.info("Workspace cache evicted for %s (role/membership change)", email)
    _invalidate_user_cache_fn = _do_invalidate_user_cache

    def _resolve_workspace_for_mcp(email: str) -> None:
        """Resolve workspace context for MCP requests and set on contextvar.

        Uses in-memory cache with same TTL as token cache.
        In legacy mode (no control_db_name), always uses make_legacy_context.
        """
        now = _time.time()

        # Check cache first
        cached = _workspace_cache.get(email)
        if cached and cached["expires"] > now:
            set_mcp_workspace_context(cached["ctx"])
            return

        # Resolve workspace context
        if settings.control_db_name and _db_module.engine_registry:
            try:
                from .dependencies import _get_user_memberships, _resolve_active_workspace
                from .workspace_context import WorkspaceContext
                from .database import get_control_db
                with get_control_db() as cursor:
                    is_org_admin, default_ws_id, memberships = _get_user_memberships(cursor, email)
                if memberships:
                    active = _resolve_active_workspace(memberships, None, default_ws_id)
                    ctx = WorkspaceContext(
                        user_email=email,
                        is_org_admin=is_org_admin,
                        memberships=memberships,
                        active=active,
                    )
                else:
                    logger.warning("MCP user %s has no workspace memberships — denying access", email)
                    ctx = None  # Will cause _resolve_ctx to return error
            except Exception as e:
                logger.error("Failed to resolve workspace for MCP user %s — failing closed: %s", email, e)
                ctx = None  # Fail closed — do not grant admin on transient errors
        else:
            ctx = make_legacy_context(email)

        # Cache and set context (only if successfully resolved)
        if ctx is not None:
            _workspace_cache[email] = {"ctx": ctx, "expires": _time.time() + TOKEN_CACHE_TTL}
            # Enforce max size
            if len(_workspace_cache) > TOKEN_CACHE_MAX_SIZE:
                oldest_key = min(_workspace_cache, key=lambda k: _workspace_cache[k]["expires"])
                del _workspace_cache[oldest_key]
            set_mcp_workspace_context(ctx)
        # else: ctx stays None — _resolve_ctx will return error dict in workspace mode

    async def validate_mcp_token(token: str) -> str | None:
        """Validate MCP token. Returns client email if valid, None if not.

        When control_db_name is configured, validates against control DB tokens table
        and pre-caches the full WorkspaceContext (avoids double control DB query).
        Falls back to legacy ClientToken validation when control DB is not configured.
        """
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        now = _time.time()

        async with _token_cache_lock:
            # Check cache first
            cached = _token_cache.get(token_hash)
            if cached and cached["expires_cache"] > now:
                return cached["email"]

            # Evict expired entries while we hold the lock
            expired = [k for k, v in _token_cache.items() if v["expires_cache"] <= now]
            for k in expired:
                del _token_cache[k]

        # Cache miss — try control DB first when configured
        email = None
        if settings.control_db_name and _db_module.engine_registry:
            try:
                result = validate_token_from_control_db(token_hash)
            except Exception as e:
                # Control DB unreachable — fail closed (deny access).
                # Do NOT fall through to legacy validation.
                logger.error("Token validation failed — control DB error: %s", e)
                return None
            if result and result.get("user_email"):
                email = result["user_email"]
                # Build and cache WorkspaceContext from token result
                from .workspace_context import WorkspaceMembership, WorkspaceContext
                from .dependencies import _resolve_active_workspace
                memberships = [
                    WorkspaceMembership(
                        workspace_id=m["workspace_id"],
                        workspace_name=m["workspace_name"],
                        workspace_display_name=m["workspace_display_name"],
                        db_name=m["db_name"],
                        role=m["role"],
                        is_default=m["is_default"],
                        is_archived=m["is_archived"],
                    )
                    for m in result.get("memberships", [])
                ]
                if memberships:
                    active = _resolve_active_workspace(
                        memberships, None, result.get("default_workspace_id"),
                    )
                    ctx = WorkspaceContext(
                        user_email=email,
                        is_org_admin=result.get("is_org_admin", False),
                        memberships=memberships,
                        active=active,
                    )
                else:
                    logger.warning("Token user %s has no workspace memberships — denying access", email)
                    ctx = None  # Fail closed — no admin escalation
                # Pre-cache workspace context (avoids second control DB query)
                if ctx is not None:
                    _workspace_cache[email] = {
                        "ctx": ctx,
                        "expires": _time.time() + TOKEN_CACHE_TTL,
                    }

        # Fallback: legacy workspace DB ClientToken table
        # Only use legacy validation when control DB is NOT configured.
        # When control DB is active (control_db_name set), all tokens must be
        # in the control DB — never fall through to legacy, even if engine_registry is None.
        if not email and not settings.control_db_name:
            result = validate_client_token(token_hash)
            if isinstance(result, dict) and not result.get("error") and result.get("client_email"):
                email = result["client_email"]

        async with _token_cache_lock:
            if email:
                if len(_token_cache) >= TOKEN_CACHE_MAX_SIZE:
                    oldest_key = min(_token_cache, key=lambda k: _token_cache[k]["expires_cache"])
                    del _token_cache[oldest_key]
                _token_cache[token_hash] = {
                    "email": email,
                    "expires_cache": _time.time() + TOKEN_CACHE_TTL,
                }
                return email

            # Invalid — remove from cache if present
            _token_cache.pop(token_hash, None)
        return None

    # Create MCP transport app (this creates the session manager)
    streamable_http_app = mcp.streamable_http_app()

    # Lifespan for MCP session management
    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        # Initialize engine registry for multi-database support
        if settings.azure_sql_server:
            _db_module.engine_registry = EngineRegistry(settings.azure_sql_server)
            logger.info("Engine registry initialized for server: %s", settings.azure_sql_server)

            # Startup validation: verify control DB is reachable before accepting traffic
            if settings.control_db_name:
                try:
                    from .database import get_control_db
                    with get_control_db() as cursor:
                        cursor.execute("SELECT 1")
                    logger.info("Startup check: control DB '%s' is reachable", settings.control_db_name)
                except Exception as e:
                    logger.error("Startup check FAILED: control DB '%s' unreachable: %s", settings.control_db_name, e)

        async with mcp.session_manager.run():
            yield

        # Cleanup engine registry on shutdown
        if _db_module.engine_registry:
            _db_module.engine_registry.dispose_all()
            logger.info("Engine registry disposed")

    # Create main app with lifespan
    app = FastAPI(title="Meeting Intelligence", lifespan=lifespan)

    # Payload size limit (1MB) — reject oversized requests before processing
    # Pure ASGI middleware (not BaseHTTPMiddleware) to avoid breaking streaming
    MAX_PAYLOAD_BYTES = 1 * 1024 * 1024

    class PayloadSizeLimitMiddleware:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] != "http":
                await self.app(scope, receive, send)
                return
            headers = dict(scope.get("headers", []))
            content_length = headers.get(b"content-length")
            if content_length and int(content_length) > MAX_PAYLOAD_BYTES:
                response = StarletteJSONResponse(
                    status_code=413,
                    content={
                        "error": True,
                        "code": "PAYLOAD_TOO_LARGE",
                        "message": f"Payload too large. Maximum size is {MAX_PAYLOAD_BYTES // 1024}KB."
                    }
                )
                await response(scope, receive, send)
                return
            await self.app(scope, receive, send)

    app.add_middleware(PayloadSizeLimitMiddleware)

    # Rate limiting middleware — tiered per endpoint category
    # MCP: 120/min per-token (rapid tool calls), API: 60/min per-IP,
    # health/well-known: exempt
    # Pure ASGI middleware (not BaseHTTPMiddleware) to avoid breaking streaming
    class RateLimitMiddleware:
        TIERS = {
            "mcp":   (120, 60),  # 120 req/min — MCP tool calls
            "api":   (60, 60),   # 60 req/min — REST API
        }
        EXEMPT_PREFIXES = ("/health", "/.well-known")

        def __init__(self, app):
            self.app = app
            self._windows: dict[str, list[float]] = {}
            self._last_cleanup = _time.monotonic()
            self._lock = asyncio.Lock()

        def _classify(self, path: str):
            if any(path.startswith(p) for p in self.EXEMPT_PREFIXES):
                return None
            if path.startswith("/mcp"):
                return "mcp"
            if path.startswith("/api"):
                return "api"
            return None

        def _get_client_key(self, scope, headers_dict: dict, tier: str) -> str:
            if tier == "mcp":
                # Extract token from headers for per-token rate limiting
                token = headers_dict.get(b"x-api-key", b"").decode() or ""
                if not token:
                    auth_header = headers_dict.get(b"authorization", b"").decode()
                    if auth_header.startswith("Bearer "):
                        token = auth_header[7:]
                if token:
                    return f"mcp:{hashlib.sha256(token.encode()).hexdigest()[:16]}"
            client = scope.get("client")
            client_ip = client[0] if client else "unknown"
            return f"{tier}:{client_ip}"

        async def __call__(self, scope, receive, send):
            if scope["type"] != "http":
                await self.app(scope, receive, send)
                return

            path = scope.get("path", "")
            tier = self._classify(path)
            if tier is None:
                await self.app(scope, receive, send)
                return

            headers_dict = dict(scope.get("headers", []))
            max_requests, window_seconds = self.TIERS[tier]
            client_key = self._get_client_key(scope, headers_dict, tier)
            now = _time.monotonic()

            async with self._lock:
                if client_key not in self._windows:
                    self._windows[client_key] = []
                timestamps = self._windows[client_key]

                cutoff = now - window_seconds
                while timestamps and timestamps[0] < cutoff:
                    timestamps.pop(0)

                if len(timestamps) >= max_requests:
                    retry_after = int(timestamps[0] - cutoff) + 1
                    logger.warning("Rate limit hit: %s (%d/%d in %ds)", client_key, len(timestamps), max_requests, window_seconds)
                    response = StarletteJSONResponse(
                        status_code=429,
                        content={
                            "error": True,
                            "code": "RATE_LIMITED",
                            "message": f"Rate limit exceeded. Try again in {retry_after}s.",
                        },
                        headers={
                            "Retry-After": str(retry_after),
                            "X-RateLimit-Limit": str(max_requests),
                            "X-RateLimit-Remaining": "0",
                        }
                    )
                    await response(scope, receive, send)
                    return

                timestamps.append(now)
                remaining = max_requests - len(timestamps)

                # Periodic cleanup of stale entries (every 5 minutes)
                if now - self._last_cleanup > 300:
                    self._last_cleanup = now
                    max_window = max(w for _, w in self.TIERS.values())
                    stale = [k for k, v in self._windows.items() if not v or v[-1] < now - max_window]
                    for k in stale:
                        del self._windows[k]

            # Inject rate limit headers into response
            async def send_with_rate_headers(message):
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers", []))
                    headers.append((b"x-ratelimit-limit", str(max_requests).encode()))
                    headers.append((b"x-ratelimit-remaining", str(remaining).encode()))
                    message["headers"] = headers
                await send(message)

            await self.app(scope, receive, send_with_rate_headers)

    app.add_middleware(RateLimitMiddleware)

    # Security headers middleware
    # Pure ASGI middleware (not BaseHTTPMiddleware) to avoid breaking streaming
    _SECURITY_HEADERS = [
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"referrer-policy", b"strict-origin-when-cross-origin"),
        (b"strict-transport-security", b"max-age=31536000; includeSubDomains"),
        (b"content-security-policy", (
            b"default-src 'self'; "
            b"script-src 'self'; "
            b"style-src 'self' 'unsafe-inline'; "
            b"img-src 'self' data:; "
            b"font-src 'self'; "
            b"connect-src 'self' https://login.microsoftonline.com https://*.microsoftonline.com; "
            b"frame-ancestors 'none'"
        )),
    ]

    class SecurityHeadersMiddleware:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] != "http":
                await self.app(scope, receive, send)
                return

            async def send_with_security_headers(message):
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers", []))
                    headers.extend(_SECURITY_HEADERS)
                    message["headers"] = headers
                await send(message)

            await self.app(scope, receive, send_with_security_headers)

    app.add_middleware(SecurityHeadersMiddleware)

    # Request ID correlation — generates a unique ID per request, sets it on a
    # contextvar for log access, and returns it in the X-Request-ID response header.
    class RequestIdMiddleware:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] != "http":
                await self.app(scope, receive, send)
                return

            rid = uuid.uuid4().hex[:12]
            token = request_id_var.set(rid)

            async def send_with_request_id(message):
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers", []))
                    headers.append((b"x-request-id", rid.encode()))
                    message["headers"] = headers
                await send(message)

            try:
                await self.app(scope, receive, send_with_request_id)
            finally:
                request_id_var.reset(token)

    app.add_middleware(RequestIdMiddleware)

    # CORS — mcp-session-id for Streamable HTTP session management
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.get_cors_origins_list(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS", "PATCH"],
        allow_headers=["Authorization", "Content-Type", "Accept", "X-API-Key", "X-Workspace-ID", "mcp-protocol-version", "mcp-session-id"],
        expose_headers=["mcp-session-id"],
    )

    # Allowed origins for MCP Origin header validation (MCP spec 2025-11-25).
    # The SDK's DNS rebinding middleware is bypassed when routes are mounted
    # onto a parent app, so we enforce Origin validation here.
    _allowed_origins = set(settings.get_cors_origins_list())

    # Token auth middleware for MCP endpoints
    # Uses DB-backed token validation with in-memory cache (5-min TTL)
    @app.middleware("http")
    async def mcp_auth_middleware(request, call_next):
        path = request.url.path

        # Only check auth for MCP endpoint
        if not path.startswith("/mcp"):
            return await call_next(request)

        # Origin header validation per MCP spec 2025-11-25.
        # Reject requests with an Origin that isn't in our allowed list.
        # Requests without Origin are allowed (server-to-server, CLI tools).
        origin = request.headers.get("origin")
        if origin and origin not in _allowed_origins:
            logger.warning("Rejected MCP request with invalid Origin: %s", origin)
            return Response("Forbidden", status_code=403)

        # MCP-Protocol-Version header validation (Streamable HTTP only).
        # The spec requires clients to include this header on POST requests.
        _SUPPORTED_MCP_VERSIONS = {"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"}
        if path.startswith("/mcp") and request.method == "POST":
            proto_version = request.headers.get("mcp-protocol-version")
            if proto_version and proto_version not in _SUPPORTED_MCP_VERSIONS:
                return StarletteJSONResponse(
                    status_code=400,
                    content={
                        "error": "unsupported_protocol_version",
                        "supported_versions": sorted(_SUPPORTED_MCP_VERSIONS),
                    }
                )

        # Extract token from headers (Bearer or X-API-Key) or query param
        token = None
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
        if not token:
            token = request.headers.get("X-API-Key")
        if not token:
            token = request.query_params.get("token")

        if not token:
            return Response("Unauthorized", status_code=401)

        email = None

        # OAuth JWT validation (B17) — try first if provider is configured
        # JWTs contain dots; PATs are base64url without dots.
        if _oauth_provider and "." in token:
            try:
                payload = pyjwt.decode(
                    token, settings.jwt_secret, algorithms=["HS256"]
                )
                if payload.get("type") == "access":
                    email = payload.get("sub")
                    if email:
                        logger.debug("OAuth JWT auth: %s (client: %s)", email, payload.get("client_id"))
            except pyjwt.InvalidTokenError:
                pass  # Not a valid JWT — fall through to PAT validation

        # PAT validation (existing path)
        if not email:
            email = await validate_mcp_token(token)

        if not email:
            return Response("Unauthorized", status_code=401)
        set_mcp_user(email)
        await asyncio.to_thread(_resolve_workspace_for_mcp, email)

        return await call_next(request)

    # Mount MCP transport (Streamable HTTP only — /mcp endpoint)
    for route in streamable_http_app.routes:
        app.routes.append(route)

    # ── OAuth 2.1 Routes (B17) ────────────────────────────────────────
    if _oauth_provider:
        from mcp.server.auth.routes import create_auth_routes, create_protected_resource_routes
        from mcp.server.auth.settings import (
            ClientRegistrationOptions,
            RevocationOptions,
        )

        # SDK creates Starlette routes for /.well-known/*, /authorize, /token, /register, /revoke
        oauth_routes = create_auth_routes(
            provider=_oauth_provider,
            issuer_url=AnyHttpUrl(settings.oauth_base_url),
            client_registration_options=ClientRegistrationOptions(
                enabled=True,
                valid_scopes=["mcp"],
                default_scopes=["mcp"],
            ),
            revocation_options=RevocationOptions(enabled=True),
        )
        # Protected Resource Metadata (RFC 9728) — tells clients where our AS is
        prm_routes = create_protected_resource_routes(
            resource_url=AnyHttpUrl(settings.oauth_base_url),
            authorization_servers=[AnyHttpUrl(settings.oauth_base_url)],
            scopes_supported=["mcp"],
        )

        # Mount as a Starlette sub-app so these take priority over the SPA catch-all.
        # Raw route insertion (app.routes.insert) loses to @app.get decorator routes.
        # Insert OAuth routes into the FastAPI router's route list at position 0.
        # This ensures they're checked before the SPA catch-all ({full_path:path}).
        # app.router.routes is the actual dispatch list FastAPI uses internally.
        for _route in reversed([*oauth_routes, *prm_routes]):
            app.router.routes.insert(0, _route)

        # ── Consent Page (PAT-based identity proof) ───────────────────
        @app.get("/oauth/consent")
        async def oauth_consent_page(session: str = ""):
            """Render consent page where user pastes their MI PAT."""
            if not _oauth_provider:
                return Response("OAuth not configured", status_code=503)
            pending = _oauth_provider.get_pending_auth(session)
            if not pending:
                return HTMLResponse(
                    "<html><body><h2>Invalid or expired authorization session.</h2>"
                    "<p>Please try connecting again from your AI client.</p></body></html>",
                    status_code=400,
                )
            client = pending["client"]
            return HTMLResponse(f"""<!DOCTYPE html>
<html>
<head><title>Authorize MCP Connection</title>
<style>
  body {{ font-family: -apple-system, sans-serif; max-width: 480px; margin: 60px auto; padding: 0 20px; }}
  h2 {{ color: #1a1a1a; }}
  .client-name {{ background: #f0f0f0; padding: 4px 8px; border-radius: 4px; font-weight: 600; }}
  input[type=password] {{ width: 100%; padding: 10px; margin: 12px 0; border: 1px solid #ccc; border-radius: 6px; font-size: 14px; }}
  button {{ background: #2563eb; color: white; border: none; padding: 12px 24px; border-radius: 6px; font-size: 16px; cursor: pointer; width: 100%; }}
  button:hover {{ background: #1d4ed8; }}
  .info {{ color: #666; font-size: 13px; margin-top: 16px; }}
</style>
</head>
<body>
  <h2>Authorize MCP Connection</h2>
  <p><span class="client-name">{client.client_name or client.client_id}</span> wants to connect to Meeting Intelligence.</p>
  <p>Enter your Personal Access Token to authorize this connection. Each team member must authorize individually.</p>
  <form method="POST" action="/oauth/consent">
    <input type="hidden" name="session" value="{session}">
    <input type="password" name="pat" placeholder="Paste your MI Personal Access Token" required>
    <button type="submit">Authorize Connection</button>
  </form>
  <p class="info">Your PAT is used to verify your identity. The connecting application will receive a separate OAuth token.</p>
</body>
</html>""")

        @app.post("/oauth/consent")
        async def oauth_consent_submit(request):
            """Process consent form — validate PAT, issue auth code, redirect."""
            from starlette.responses import RedirectResponse as StarletteRedirect
            form = await request.form()
            session_id = form.get("session", "")
            pat = form.get("pat", "")

            if not session_id or not pat:
                return HTMLResponse(
                    "<html><body><h2>Missing session or token.</h2></body></html>",
                    status_code=400,
                )

            # Validate the PAT using existing infrastructure
            email = await validate_mcp_token(pat)
            if not email:
                # Re-render consent page with error
                pending = _oauth_provider.get_pending_auth(session_id)
                if not pending:
                    return HTMLResponse(
                        "<html><body><h2>Session expired. Please try connecting again.</h2></body></html>",
                        status_code=400,
                    )
                client = pending["client"]
                return HTMLResponse(f"""<!DOCTYPE html>
<html>
<head><title>Authorization Failed</title>
<style>
  body {{ font-family: -apple-system, sans-serif; max-width: 480px; margin: 60px auto; padding: 0 20px; }}
  .error {{ color: #dc2626; background: #fef2f2; padding: 12px; border-radius: 6px; margin-bottom: 16px; }}
  input[type=password] {{ width: 100%; padding: 10px; margin: 12px 0; border: 1px solid #ccc; border-radius: 6px; font-size: 14px; }}
  button {{ background: #2563eb; color: white; border: none; padding: 12px 24px; border-radius: 6px; font-size: 16px; cursor: pointer; width: 100%; }}
</style>
</head>
<body>
  <h2>Authorize MCP Connection</h2>
  <div class="error">Invalid token. Please check your Personal Access Token and try again.</div>
  <p><strong>{client.client_name or client.client_id}</strong> wants to connect.</p>
  <form method="POST" action="/oauth/consent">
    <input type="hidden" name="session" value="{session_id}">
    <input type="password" name="pat" placeholder="Paste your MI Personal Access Token" required>
    <button type="submit">Authorize Connection</button>
  </form>
</body>
</html>""", status_code=401)

            # PAT valid — complete the OAuth authorization
            try:
                redirect_uri = _oauth_provider.complete_authorization(session_id, email)
            except ValueError as e:
                return HTMLResponse(
                    f"<html><body><h2>Authorization failed: {e}</h2></body></html>",
                    status_code=400,
                )

            logger.info("OAuth consent completed: user=%s, session=%s", email, session_id[:8])
            return StarletteRedirect(url=redirect_uri, status_code=302)

        logger.info("OAuth 2.1 routes mounted (DCR, PKCE, consent page)")
    # ──────────────────────────────────────────────────────────────────

    # Mount Admin API (workspace CRUD + member management)
    app.include_router(admin_router, prefix="/api/admin")

    # Mount REST API - api_app routes are /api/*, so include directly
    # Since api_app already has /api prefix, we add its routes to main app
    for route in api_app.routes:
        app.routes.append(route)

    # Cache invalidation endpoints (org_admin only)
    @app.post("/api/admin/cache/invalidate")
    async def invalidate_all_caches(
        user: str = Depends(authenticate_and_store),
        ctx: WorkspaceContext = Depends(resolve_workspace),
    ):
        """Clear all in-memory token and workspace caches. Org Admin only."""
        check_permission(ctx, "manage_workspace")
        token_count = len(_token_cache)
        workspace_count = len(_workspace_cache)
        _token_cache.clear()
        _workspace_cache.clear()
        logger.info("Cache invalidated by %s: %d tokens, %d workspaces cleared",
                     ctx.user_email, token_count, workspace_count)
        return {
            "message": "All caches invalidated",
            "tokens_cleared": token_count,
            "workspaces_cleared": workspace_count,
        }

    @app.delete("/api/admin/cache/tokens/{email}")
    async def invalidate_user_cache(
        email: str,
        user: str = Depends(authenticate_and_store),
        ctx: WorkspaceContext = Depends(resolve_workspace),
    ):
        """Invalidate cached tokens and workspace context for a specific user. Org Admin only."""
        check_permission(ctx, "manage_workspace")
        email = email.strip().lower()
        # Remove from workspace cache
        ws_removed = _workspace_cache.pop(email, None) is not None
        # Remove matching token cache entries (keyed by hash, value contains email)
        token_keys = [k for k, v in _token_cache.items() if v.get("email", "").lower() == email]
        for k in token_keys:
            del _token_cache[k]
        logger.info("Cache invalidated for %s by %s: %d tokens, workspace=%s",
                     email, ctx.user_email, len(token_keys), ws_removed)
        return {
            "message": f"Cache invalidated for {email}",
            "tokens_cleared": len(token_keys),
            "workspace_cleared": ws_removed,
        }

    # Health probes (defined after route appends to ensure proper ordering)
    @app.get("/health")
    def health():
        return {"status": "healthy", "transports": ["streamable-http"]}

    @app.get("/health/live")
    def health_live():
        """Liveness probe — process is running."""
        return {"status": "alive"}

    @app.get("/health/ready")
    def health_ready():
        """Readiness probe — checks control DB in workspace mode, legacy DB otherwise."""
        from starlette.responses import JSONResponse
        from .database import get_control_db, test_connection
        try:
            if settings.control_db_name and _db_module.engine_registry:
                with get_control_db() as cursor:
                    cursor.execute("SELECT 1")
                return {"status": "ready", "database": "connected", "mode": "workspace"}
            else:
                test_connection()
                return {"status": "ready", "database": "connected", "mode": "legacy"}
        except Exception as e:
            logger.warning("Readiness check failed: %s", e)
            return JSONResponse(
                status_code=503,
                content={"status": "not ready", "database": "unavailable"}
            )

    # Static files for web UI
    static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
    if os.path.exists(static_dir):
        app.mount("/assets", StaticFiles(directory=os.path.join(static_dir, "assets")), name="assets")

        # Favicon — per-client branding via FAVICON_PATH env var
        # If FAVICON_PATH is set and the file exists, serve it as the favicon.
        # This allows each deployed instance to show its own client logo (used by
        # browser tabs and claude.ai MCP connector thumbnails).
        # Falls back to the default favicon.svg if FAVICON_PATH is unset or missing.
        _custom_favicon = settings.favicon_path if settings.favicon_path and os.path.isfile(settings.favicon_path) else None
        if _custom_favicon:
            logger.info("Custom favicon configured: %s", _custom_favicon)

        @app.get("/favicon.svg")
        async def serve_favicon_svg():
            if _custom_favicon:
                # Serve the custom PNG favicon even on the .svg path — browsers handle
                # content-type correctly regardless of URL extension.
                return FileResponse(_custom_favicon, media_type="image/png")
            return FileResponse(os.path.join(static_dir, "favicon.svg"), media_type="image/svg+xml")

        @app.get("/favicon.ico")
        async def serve_favicon_ico():
            if _custom_favicon:
                return FileResponse(_custom_favicon, media_type="image/png")
            return FileResponse(os.path.join(static_dir, "favicon.svg"), media_type="image/svg+xml")

        @app.get("/favicon.png")
        async def serve_favicon_png():
            if _custom_favicon:
                return FileResponse(_custom_favicon, media_type="image/png")
            return FileResponse(os.path.join(static_dir, "favicon.svg"), media_type="image/svg+xml")

        @app.get("/")
        async def serve_root():
            return FileResponse(os.path.join(static_dir, "index.html"))

        # SPA catch-all - must be defined LAST
        # OAuth/well-known paths are Starlette routes (not @app.get decorators),
        # so the catch-all would match first. Explicitly skip them here.
        _NON_SPA_PREFIXES = ("/api", "/mcp", "/health", "/.well-known", "/authorize", "/token", "/register", "/revoke", "/oauth")

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            if any(f"/{full_path}".startswith(p) for p in _NON_SPA_PREFIXES):
                return Response("Not Found", status_code=404)
            return FileResponse(os.path.join(static_dir, "index.html"))

    logger.info("Starting Meeting Intelligence Server")
    logger.info("Endpoints: MCP=/mcp, API=/api/*, UI=/")

    uvicorn.run(app, host="0.0.0.0", port=8000)


def main():
    if "--http" in sys.argv:
        run_http()
    else:
        asyncio.run(run_stdio())


if __name__ == "__main__":
    main()
