"""Meeting Intelligence MCP Server - Entry Point"""

import hashlib
import sys
import asyncio
import contextlib
import time as _time

from .logging_config import configure_logging, get_logger
from .mcp_server import mcp, set_mcp_user

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

    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse as StarletteJSONResponse

    from .api import app as api_app  # REST API endpoints
    from .config import get_settings
    from .database import validate_client_token
    from .oauth import router as oauth_router, validate_oauth_token, init_oauth_clients

    settings = get_settings()

    # In-memory token cache — avoids DB hit on every MCP request
    # Trade-off: revoked tokens may still work for up to TOKEN_CACHE_TTL seconds
    _token_cache: dict[str, dict] = {}  # {hash: {"email": str, "expires_cache": float}}
    _token_cache_lock = asyncio.Lock()
    TOKEN_CACHE_TTL = 300  # 5 minutes
    TOKEN_CACHE_MAX_SIZE = 1000

    async def validate_mcp_token(token: str) -> str | None:
        """Validate MCP token. Returns client email if valid, None if not.

        Uses in-memory cache with 5-minute TTL and max size to reduce DB load.
        Protected by asyncio.Lock for concurrent access safety.
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

        # Cache miss — check database (outside lock to avoid holding it during I/O)
        result = validate_client_token(token_hash)

        async with _token_cache_lock:
            if isinstance(result, dict) and not result.get("error") and result.get("client_email"):
                # Enforce max cache size — evict oldest entries if full
                if len(_token_cache) >= TOKEN_CACHE_MAX_SIZE:
                    oldest_key = min(_token_cache, key=lambda k: _token_cache[k]["expires_cache"])
                    del _token_cache[oldest_key]
                _token_cache[token_hash] = {
                    "email": result["client_email"],
                    "expires_cache": _time.time() + TOKEN_CACHE_TTL,
                }
                return result["client_email"]

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

        # Load OAuth clients from database into memory on startup
        init_oauth_clients()
        async with mcp.session_manager.run():
            yield

    # Create main app with lifespan
    app = FastAPI(title="Meeting Intelligence", lifespan=lifespan)

    # Payload size limit (1MB) — reject oversized requests before processing
    MAX_PAYLOAD_BYTES = 1 * 1024 * 1024

    class PayloadSizeLimitMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            content_length = request.headers.get('content-length')
            if content_length and int(content_length) > MAX_PAYLOAD_BYTES:
                return StarletteJSONResponse(
                    status_code=413,
                    content={
                        "error": True,
                        "code": "PAYLOAD_TOO_LARGE",
                        "message": f"Payload too large. Maximum size is {MAX_PAYLOAD_BYTES // 1024}KB."
                    }
                )
            return await call_next(request)

    app.add_middleware(PayloadSizeLimitMiddleware)

    # Rate limiting middleware — tiered per endpoint category
    # MCP: 120/min per-token (rapid tool calls), OAuth: 20/min per-IP,
    # API: 60/min per-IP, health/well-known: exempt
    class RateLimitMiddleware(BaseHTTPMiddleware):
        TIERS = {
            "mcp":   (120, 60),  # 120 req/min — MCP tool calls
            "oauth": (20, 60),   # 20 req/min — auth endpoints
            "api":   (60, 60),   # 60 req/min — REST API
        }
        EXEMPT_PREFIXES = ("/health", "/.well-known")

        def __init__(self, app):
            super().__init__(app)
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

        def _get_client_key(self, request, tier: str) -> str:
            if tier == "mcp":
                token = (
                    request.query_params.get("token")
                    or request.headers.get("X-API-Key")
                    or ""
                )
                auth_header = request.headers.get("Authorization", "")
                if not token and auth_header.startswith("Bearer "):
                    token = auth_header[7:]
                if not token and request.url.path.startswith("/mcp/"):
                    token = request.url.path[5:]
                if token:
                    return f"mcp:{hashlib.sha256(token.encode()).hexdigest()[:16]}"
            client_ip = request.client.host if request.client else "unknown"
            return f"{tier}:{client_ip}"

        async def dispatch(self, request, call_next):
            tier = self._classify(request.url.path)
            if tier is None:
                return await call_next(request)

            max_requests, window_seconds = self.TIERS[tier]
            client_key = self._get_client_key(request, tier)
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
                    return StarletteJSONResponse(
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

                timestamps.append(now)
                remaining = max_requests - len(timestamps)

                # Periodic cleanup of stale entries (every 5 minutes)
                if now - self._last_cleanup > 300:
                    self._last_cleanup = now
                    max_window = max(w for _, w in self.TIERS.values())
                    stale = [k for k, v in self._windows.items() if not v or v[-1] < now - max_window]
                    for k in stale:
                        del self._windows[k]

            response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(max_requests)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            return response

    app.add_middleware(RateLimitMiddleware)

    # Security headers middleware
    class SecurityHeadersMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            response = await call_next(request)
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; "
                "font-src 'self'; "
                "connect-src 'self' https://login.microsoftonline.com https://*.microsoftonline.com; "
                "frame-ancestors 'none'"
            )
            return response

    app.add_middleware(SecurityHeadersMiddleware)

    # CORS - include mcp-session-id header
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.get_cors_origins_list(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS", "PATCH"],
        allow_headers=["Authorization", "Content-Type", "Accept", "X-API-Key", "mcp-protocol-version", "mcp-session-id"],
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
                        set_mcp_user(f"oauth:{oauth_payload.get('sub', 'unknown')}")
                        return await call_next(request)

        if not token:
            return Response("Unauthorized", status_code=401)

        # For query param / X-API-Key tokens, resolve email if not already set
        email = await validate_mcp_token(token)
        if not email:
            return Response("Unauthorized", status_code=401)
        set_mcp_user(email)

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
