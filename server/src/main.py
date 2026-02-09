"""Meeting Intelligence MCP Server - Entry Point"""

import sys
import asyncio
import contextlib

from .logging_config import configure_logging, get_logger
from .mcp_server import mcp

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

    from .api import app as api_app  # REST API endpoints
    from .config import get_settings
    from .oauth import router as oauth_router, validate_oauth_token

    settings = get_settings()
    valid_tokens = settings.get_valid_mcp_tokens()

    # Create MCP transport apps first (this creates the session manager)
    streamable_http_app = mcp.streamable_http_app()
    sse_app = mcp.sse_app()

    # Lifespan for MCP session management
    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        async with mcp.session_manager.run():
            yield

    # Create main app with lifespan
    app = FastAPI(title="Meeting Intelligence", lifespan=lifespan)

    # CORS - include mcp-session-id header
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.get_cors_origins_list(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS", "PATCH"],
        allow_headers=["*", "mcp-protocol-version", "mcp-session-id", "Authorization", "X-API-Key"],
        expose_headers=["mcp-session-id"],
    )

    # Token auth middleware for MCP endpoints
    # Uses raw ASGI middleware to support path rewriting for Copilot
    @app.middleware("http")
    async def mcp_auth_middleware(request, call_next):
        path = request.url.path

        # Only check auth for MCP endpoints
        if not (path.startswith("/sse") or path.startswith("/mcp")):
            return await call_next(request)

        # Skip auth if no tokens configured
        if not valid_tokens:
            return await call_next(request)

        token = None

        # Check for path-based token: /mcp/{token} (for Copilot)
        if path.startswith("/mcp/") and len(path) > 5:
            path_token = path[5:]  # Extract token from path
            if path_token in valid_tokens:
                token = path_token
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
                # First check if it's an MCP static token
                if bearer_token in valid_tokens:
                    token = bearer_token
                else:
                    # Try validating as OAuth token (for ChatGPT)
                    oauth_payload = validate_oauth_token(bearer_token)
                    if oauth_payload:
                        # Valid OAuth token - allow request
                        return await call_next(request)

        if token not in valid_tokens:
            return Response("Unauthorized", status_code=401)

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

    # Health check (defined after route appends to ensure proper ordering)
    @app.get("/health")
    def health():
        return {"status": "healthy", "transports": ["sse", "streamable-http"], "oauth": True}

    # Static files for web UI
    static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
    if os.path.exists(static_dir):
        app.mount("/assets", StaticFiles(directory=os.path.join(static_dir, "assets")), name="assets")

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
