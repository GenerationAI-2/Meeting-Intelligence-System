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
    from starlette.responses import Response

    MCP_AUTH_TOKEN = os.getenv("MCP_AUTH_TOKEN")
    
    endpoint_path = "/messages"
    print(f"DEBUG: Initializing with Token Present: {bool(MCP_AUTH_TOKEN)}")
    
    if MCP_AUTH_TOKEN:
        # Bake token into the endpoint path so it survives the SSE roundtrip
        endpoint_path = f"/messages/token/{MCP_AUTH_TOKEN}"
        
    print(f"DEBUG: Selected SSE Endpoint Path: {endpoint_path}")
    
    sse = SseServerTransport(endpoint_path)

    async def verify_mcp_token(request):
        if not MCP_AUTH_TOKEN:
            return None # Auth disabled if no token configured
            
        # 1. Check Authorization Header (Standard)
        auth_header = request.headers.get("authorization")
        token = None
        
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
        
        # 2. Check Query Parameter (Initial SSE connection)
        if not token:
             token = request.query_params.get("token") or request.query_params.get("access_token")

        if token and token == MCP_AUTH_TOKEN:
            return None

        # 3. Check Path (For subsequent POSTs to /messages/token/...)
        # If the request path matches our expected tokenized endpoint, it's authorized.
        if request.url.path == endpoint_path:
            return None

        return Response("Unauthorized: Missing or Invalid Token", status_code=401)

    async def handle_sse(request):
        # Verify Auth
        auth_error = await verify_mcp_token(request)
        if auth_error:
            return auth_error

        # Establish SSE connection
        async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
            await mcp_server.run(streams[0], streams[1], mcp_server.create_initialization_options())
    
    async def handle_messages(request):
        # Verify Auth
        auth_error = await verify_mcp_token(request)
        if auth_error:
            return auth_error
            
        # Handle client messages (POST)
        await sse.handle_post_message(request.scope, request.receive, request._send)

    # Add routes to the FastAPI app
    fastapi_app.add_route("/sse", handle_sse, methods=["GET"])
    
    # Register the POST route (either /messages or /messages/token/XYZ)
    fastapi_app.add_route(endpoint_path, handle_messages, methods=["POST"])

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
