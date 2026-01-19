"""Meeting Intelligence MCP Server - Entry Point"""

import sys
import asyncio
from mcp.server.stdio import stdio_server
from .mcp_server import mcp_server


async def run_stdio():
    """Run MCP server over stdio (for local/Claude Desktop)."""
    async with stdio_server() as (read_stream, write_stream):
        await mcp_server.run(read_stream, write_stream, mcp_server.create_initialization_options())


def run_http():
    """Run MCP server over SSE AND REST API via Uvicorn."""
    import uvicorn
    from mcp.server.sse import SseServerTransport
    from starlette.middleware.cors import CORSMiddleware
    
    # Import the FastAPI app from api.py
    from .api import app as fastapi_app
    
    # Ensure CORS is permissive for Claude.ai development
    # Note: CORSMiddleware handles the OPTIONS preflight requests automatically
    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173", 
            "http://localhost:3000", 
            "https://claude.ai", 
            "https://preview.claude.ai"
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    
    import os
    import json
    from starlette.responses import Response
    from .config import get_settings

    settings = get_settings()
    valid_tokens = settings.get_valid_mcp_tokens()

    print(f"DEBUG: Initializing with {len(valid_tokens)} MCP token(s) configured")

    # Build endpoint paths for each token (for path-based auth on POST)
    token_endpoints = {f"/messages/token/{token}": token for token in valid_tokens}

    # We need one SSE transport per token endpoint for the POST routing
    # But for SSE connection, we use a single /sse endpoint and validate via query param
    # The SSE transport needs to know where to send POST messages - we'll use a dynamic approach
    sse_transports = {}
    for token in valid_tokens:
        endpoint = f"/messages/token/{token}"
        sse_transports[token] = SseServerTransport(endpoint)

    # Fallback for no tokens configured
    if not valid_tokens:
        sse_transports["default"] = SseServerTransport("/messages")

    def get_token_from_request(request):
        """Extract token from header, query param, or path."""
        # 1. Check Authorization Header
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header.split(" ")[1]

        # 2. Check Query Parameter
        token = request.query_params.get("token") or request.query_params.get("access_token")
        if token:
            return token

        # 3. Check Path
        path = request.url.path
        if path in token_endpoints:
            return token_endpoints[path]

        return None

    async def verify_mcp_token(request):
        if not valid_tokens:
            return None  # Auth disabled if no tokens configured

        token = get_token_from_request(request)
        if token and token in valid_tokens:
            return None

        return Response("Unauthorized: Missing or Invalid Token", status_code=401)

    async def handle_sse(request):
        # Verify Auth
        auth_error = await verify_mcp_token(request)
        if auth_error:
            return auth_error

        # Get the appropriate transport for this user's token
        token = get_token_from_request(request)
        sse = sse_transports.get(token) or sse_transports.get("default")

        # Establish SSE connection
        async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
            await mcp_server.run(streams[0], streams[1], mcp_server.create_initialization_options())

    async def handle_messages(request, token: str):
        # Verify Auth
        auth_error = await verify_mcp_token(request)
        if auth_error:
            return auth_error

        # Get the appropriate transport for this token
        sse = sse_transports.get(token) or sse_transports.get("default")

        # Handle client messages (POST)
        await sse.handle_post_message(request.scope, request.receive, request._send)

    # Add routes to the FastAPI app
    fastapi_app.add_route("/sse", handle_sse, methods=["GET"])

    # Register POST routes for each token endpoint
    for token in valid_tokens:
        endpoint = f"/messages/token/{token}"
        # Create a closure to capture the token value
        def make_handler(t):
            async def handler(request):
                return await handle_messages(request, t)
            return handler
        fastapi_app.add_route(endpoint, make_handler(token), methods=["POST"])

    # Fallback route if no tokens configured
    if not valid_tokens:
        async def handle_messages_default(request):
            return await handle_messages(request, "default")
        fastapi_app.add_route("/messages", handle_messages_default, methods=["POST"])

    print("Starting Meeting Intelligence Server (HTTP/SSE + REST)...")
    print("MCP SSE Endpoint: http://localhost:8000/sse")
    print("Web UI API: http://localhost:8000/api/...")
    
    from fastapi.staticfiles import StaticFiles
    from starlette.responses import FileResponse
    import os

    # 1. Mount assets (CSS/JS)
    # Check if static directory exists (it will in Docker)
    static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
    print(f"DEBUG: static_dir is {static_dir}, exists={os.path.exists(static_dir)}")
    
    if os.path.exists(static_dir):
        fastapi_app.mount("/assets", StaticFiles(directory=os.path.join(static_dir, "assets")), name="assets")

        async def serve_index():
            index_path = os.path.join(static_dir, "index.html")
            if os.path.exists(index_path):
                return FileResponse(index_path)
            return Response("Frontend not found (index.html missing)", status_code=404)

        # 2. explicit root route
        @fastapi_app.get("/")
        async def serve_root():
            return await serve_index()

        # 3. SPA Catch-all (Serve index.html for non-API routes)
        @fastapi_app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            # Allow API and SSE routes to pass through (handled by previous add_route/add_api_route)
            if full_path.startswith("api/") or full_path.startswith("sse") or full_path.startswith("messages"):
                # If we got here, it means no specific route matched for API, let it 404 naturally?
                # Actually, catch-all catches EVERYTHING that wasn't matched before.
                # If api/ endpoints are defined BEFORE this, they are matched first.
                # But if we access /api/foobar (undefined), it falls here?
                # Yes. We should 404.
                return Response("Not Found", status_code=404)
            
            return await serve_index()
    
    uvicorn.run(fastapi_app, host="0.0.0.0", port=8000)


def main():
    """Entry point detecting mode."""
    if "--http" in sys.argv:
        run_http()
    else:
         asyncio.run(run_stdio())


if __name__ == "__main__":
    main()
