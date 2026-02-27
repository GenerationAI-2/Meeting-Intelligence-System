"""Meeting Intelligence MCP Server - Entry Point"""

import hashlib
import sys
import asyncio
import contextlib
import time as _time

from .logging_config import configure_logging, get_logger
from .mcp_server import mcp, set_mcp_user, set_mcp_workspace_context
from .workspace_context import make_legacy_context
from . import database as _db_module
from .database import EngineRegistry

# Configure logging at module load (before any other imports that might log)
configure_logging()
logger = get_logger(__name__)


async def run_stdio():
    """Run MCP server over stdio (for local/Claude Desktop)."""
    await mcp.run(transport="stdio")


def run_http():
    """Run MCP server over SSE + Streamable HTTP + REST API."""
    import uvicorn
    import os
    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles
    from starlette.responses import FileResponse, Response
    from starlette.middleware.cors import CORSMiddleware

    from starlette.responses import JSONResponse as StarletteJSONResponse

    from .api import app as api_app  # REST API endpoints
    from .admin import admin_router
    from .config import get_settings
    from .database import validate_client_token, validate_token_from_control_db
    from .oauth import router as oauth_router, validate_oauth_token, init_oauth_clients

    settings = get_settings()

    # In-memory token cache — avoids DB hit on every MCP request
    # Trade-off: revoked tokens may still work for up to TOKEN_CACHE_TTL seconds
    _token_cache: dict[str, dict] = {}  # {hash: {"email": str, "expires_cache": float}}
    _token_cache_lock = asyncio.Lock()
    TOKEN_CACHE_TTL = 300  # 5 minutes
    TOKEN_CACHE_MAX_SIZE = 1000

    # Workspace context cache — avoids control DB hit on every MCP request
    # Keyed by email, same TTL as token cache
    _workspace_cache: dict[str, dict] = {}  # {email: {"ctx": WorkspaceContext, "expires": float}}

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

    # Create MCP transport apps first (this creates the session manager)
    streamable_http_app = mcp.streamable_http_app()
    sse_app = mcp.sse_app()

    # Lifespan for MCP session management
    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        # Fail fast if JWT_SECRET is not configured
        from .oauth import get_jwt_secret
        get_jwt_secret()

        # Initialize engine registry for multi-database support
        if settings.azure_sql_server:
            _db_module.engine_registry = EngineRegistry(settings.azure_sql_server)
            logger.info("Engine registry initialized for server: %s", settings.azure_sql_server)

        # Load OAuth clients from database into memory on startup
        init_oauth_clients()
        async with mcp.session_manager.run():
            yield

        # Cleanup engine registry on shutdown
        if _db_module.engine_registry:
            _db_module.engine_registry.dispose_all()
            logger.info("Engine registry disposed")

    # Create main app with lifespan
    app = FastAPI(title="Meeting Intelligence", lifespan=lifespan)

    # Payload size limit (1MB) — reject oversized requests before processing
    # Pure ASGI middleware (not BaseHTTPMiddleware) to avoid breaking SSE/streaming
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
    # MCP: 120/min per-token (rapid tool calls), OAuth: 20/min per-IP,
    # API: 60/min per-IP, health/well-known: exempt
    # Pure ASGI middleware (not BaseHTTPMiddleware) to avoid breaking SSE/streaming
    class RateLimitMiddleware:
        TIERS = {
            "mcp":   (120, 60),  # 120 req/min — MCP tool calls
            "oauth": (20, 60),   # 20 req/min — auth endpoints
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
            if path.startswith("/mcp") or path.startswith("/sse") or path.startswith("/messages"):
                return "mcp"
            if path.startswith("/oauth"):
                return "oauth"
            if path.startswith("/api"):
                return "api"
            return None

        def _get_client_key(self, scope, headers_dict: dict, tier: str) -> str:
            if tier == "mcp":
                # Extract token from query string
                from urllib.parse import parse_qs
                qs = parse_qs(scope.get("query_string", b"").decode())
                token = (qs.get("token", [""])[0]
                         or headers_dict.get(b"x-api-key", b"").decode()
                         or "")
                auth_header = headers_dict.get(b"authorization", b"").decode()
                if not token and auth_header.startswith("Bearer "):
                    token = auth_header[7:]
                path = scope.get("path", "")
                if not token and path.startswith("/mcp/"):
                    token = path[5:]
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
    # Pure ASGI middleware (not BaseHTTPMiddleware) to avoid breaking SSE/streaming
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

    # CORS - include mcp-session-id header
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

        # Only check auth for MCP endpoints
        if not (path.startswith("/sse") or path.startswith("/mcp")):
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

        token = None

        # Check for path-based token: /mcp/{token} (for Copilot)
        if path.startswith("/mcp/") and len(path) > 5:
            path_token = path[5:]  # Extract token from path
            email = await validate_mcp_token(path_token)
            if email:
                token = path_token
                set_mcp_user(email)
                # Rewrite path to /mcp for the route handler
                request.scope["path"] = "/mcp"

        # Check token in query param
        if not token:
            token = request.query_params.get("token")

        # Check X-API-Key header
        if not token:
            token = request.headers.get("X-API-Key")

        # Check Authorization header (Bearer token)
        if not token:
            auth = request.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                bearer_token = auth[7:]
                # First check if it's an MCP client token
                email = await validate_mcp_token(bearer_token)
                if email:
                    token = bearer_token
                    set_mcp_user(email)
                else:
                    # Try validating as OAuth token (for ChatGPT)
                    oauth_payload = validate_oauth_token(bearer_token)
                    if oauth_payload:
                        # Valid OAuth token — attribute to OAuth client_id
                        oauth_email = f"oauth:{oauth_payload.get('sub', 'unknown')}"
                        set_mcp_user(oauth_email)
                        _resolve_workspace_for_mcp(oauth_email)
                        return await call_next(request)

        if not token:
            return Response("Unauthorized", status_code=401)

        # For query param / X-API-Key tokens, resolve email if not already set
        email = await validate_mcp_token(token)
        if not email:
            return Response("Unauthorized", status_code=401)
        set_mcp_user(email)
        _resolve_workspace_for_mcp(email)

        return await call_next(request)

    # Mount MCP transports
    # FastMCP apps have their own routes (/mcp for HTTP, /sse+/messages for SSE)
    # Include routes from both apps directly
    for route in streamable_http_app.routes:
        app.routes.append(route)
    for route in sse_app.routes:
        app.routes.append(route)

    # Mount OAuth endpoints (for ChatGPT support)
    app.include_router(oauth_router)

    # Mount Admin API (workspace CRUD + member management)
    app.include_router(admin_router, prefix="/api/admin")

    # Mount REST API - api_app routes are /api/*, so include directly
    # Since api_app already has /api prefix, we add its routes to main app
    for route in api_app.routes:
        app.routes.append(route)

    # Health probes (defined after route appends to ensure proper ordering)
    @app.get("/health")
    def health():
        return {"status": "healthy", "transports": ["sse", "streamable-http"], "oauth": True}

    @app.get("/health/live")
    def health_live():
        """Liveness probe — process is running."""
        return {"status": "alive"}

    @app.get("/health/ready")
    def health_ready():
        """Readiness probe — verifies database is accessible."""
        from starlette.responses import JSONResponse
        from .database import test_connection
        try:
            test_connection()
            return {"status": "ready", "database": "connected"}
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

        @app.get("/favicon.svg")
        async def serve_favicon():
            return FileResponse(os.path.join(static_dir, "favicon.svg"), media_type="image/svg+xml")

        @app.get("/")
        async def serve_root():
            return FileResponse(os.path.join(static_dir, "index.html"))

        # SPA catch-all - must be defined LAST
        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            # Let API, MCP, and health routes pass through (they should be matched first)
            return FileResponse(os.path.join(static_dir, "index.html"))

    logger.info("Starting Meeting Intelligence Server")
    logger.info("Endpoints: MCP=/mcp (Copilot), SSE=/sse (Claude), OAuth=/oauth/*, API=/api/*, UI=/")

    uvicorn.run(app, host="0.0.0.0", port=8000)


def main():
    if "--http" in sys.argv:
        run_http()
    else:
        asyncio.run(run_stdio())


if __name__ == "__main__":
    main()
