"""Meeting Intelligence - REST API (Web UI) + MCP SSE Endpoint (Claude)"""

from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from mcp.server.sse import SseServerTransport
from starlette.responses import Response

from .database import get_db
from .tools import meetings, actions, decisions
from .mcp_server import mcp_server
from fastapi import Depends, Header, status

import jwt
from fastapi_azure_auth import SingleTenantAzureAuthorizationCodeBearer
from .config import get_settings

settings = get_settings()

# Startup diagnostics - log config values (redacted)
print(f"[STARTUP] Azure Tenant ID: {settings.azure_tenant_id[:8]}..." if settings.azure_tenant_id else "[STARTUP] Azure Tenant ID: NOT SET")
print(f"[STARTUP] Azure Client ID: {settings.azure_client_id[:8]}..." if settings.azure_client_id else "[STARTUP] Azure Client ID: NOT SET")
print(f"[STARTUP] Allowed Users: {settings.allowed_users[:30]}..." if settings.allowed_users else "[STARTUP] Allowed Users: NOT SET")
print(f"[STARTUP] CORS Origins: {settings.cors_origins[:50]}..." if settings.cors_origins else "[STARTUP] CORS Origins: NOT SET")

azure_scheme = SingleTenantAzureAuthorizationCodeBearer(
    app_client_id=settings.azure_client_id,
    tenant_id=settings.azure_tenant_id,
    allow_guest_users=True,
    scopes={
        f"api://{settings.azure_client_id}/access_as_user": "Access Meeting Intelligence API",
    }
)

async def get_current_user(request: Request):
    # 1. MCP / Internal Bearer Token (for Claude)
    # Check manual Authorization header for MCP token
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        # Look up user from token mapping
        mcp_user = settings.get_mcp_user(token)
        if mcp_user:
            return mcp_user

    # 2. Azure Entra ID Token (for React Users)
    try:
        from fastapi.security import SecurityScopes
        print(f"[AUTH] Attempting Azure AD validation...")
        # Validates signature, audience, issuer, and expiration
        # Throws HTTPException if invalid
        # Fix: Must pass SecurityScopes when calling manually
        token_payload = await azure_scheme(request, SecurityScopes(scopes=[]))
        print(f"[AUTH] Token validated successfully. Payload type: {type(token_payload)}")
        # Fix: token_payload can be a User object or dict. Use a safe helper.
        def get_val(obj, key):
            # Try dict access
            try:
                if isinstance(obj, dict):
                    return obj.get(key)
                # Try attribute access
                return getattr(obj, key, None)
            except Exception:
                return None

        user_email = get_val(token_payload, "preferred_username") or get_val(token_payload, "upn") or get_val(token_payload, "email")
    except Exception as e:
        # Map Azure Auth errors to 401
        print(f"[AUTH ERROR] Type: {type(e).__name__}, Detail: {e}")
        # If it's an HTTPException, check the status code
        if hasattr(e, 'status_code'):
            print(f"[AUTH ERROR] HTTP Status: {e.status_code}, Detail: {getattr(e, 'detail', 'N/A')}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Whitelist Check
    allowed_users = settings.get_allowed_users_list()
    
    if not user_email:
        print("Auth Error: No email found in token payload")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing email/upn claim"
        )

    if user_email.lower() not in allowed_users:
         raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail=f"Access denied for user: {user_email}"
        )
    
    return user_email


app = FastAPI(title="Meeting Intelligence API", version="1.0.0", swagger_ui_oauth2_redirect_url="/oauth2-redirect")

# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    auth_header = request.headers.get("Authorization", "")
    auth_preview = f"{auth_header[:20]}..." if len(auth_header) > 20 else auth_header
    print(f"[REQUEST] {request.method} {request.url.path} | Auth: {auth_preview}")
    response = await call_next(request)
    print(f"[RESPONSE] {request.method} {request.url.path} -> {response.status_code}")
    return response

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# MCP SSE ENDPOINT (For Claude.ai)
# ============================================================================

# SSE Endpoints are handled in main.py when running with --http
# This ensures separation of concerns: api.py is REST, main.py adds MCP transport.


# ============================================================================
# REST ENDPOINTS (Web UI)
# ============================================================================

@app.get("/api/meetings")
async def list_meetings_endpoint(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    days_back: int = Query(30, ge=1),
    user: str = Depends(get_current_user)
):
    """List meetings with pagination."""
    print(f"[ENDPOINT] /api/meetings called by user: {user}")
    result = meetings.list_meetings(limit=limit, days_back=days_back)
    if result.get("error"):
        print(f"[ENDPOINT ERROR] /api/meetings: {result.get('code')} - {result.get('message')}")
        raise HTTPException(status_code=400, detail=result["message"])
    print(f"[ENDPOINT] /api/meetings returned {result.get('count', 0)} meetings")
    return result


@app.get("/api/meetings/{meeting_id}")
async def get_meeting_endpoint(meeting_id: int, user: str = Depends(get_current_user)):
    """Get meeting details including linked actions and decisions."""
    result = meetings.get_meeting(meeting_id)
    if result.get("error"):
        if result["code"] == "NOT_FOUND":
            raise HTTPException(status_code=404, detail=result["message"])
        raise HTTPException(status_code=400, detail=result["message"])
    
    try:
        with get_db() as cursor:
            cursor.execute("""
                SELECT DecisionId, DecisionText, Context
                FROM Decision WHERE MeetingId = ?
            """, (meeting_id,))
            result["decisions"] = [
                {"id": r[0], "text": r[1], "context": r[2]}
                for r in cursor.fetchall()
            ]
            
            cursor.execute("""
                SELECT ActionId, ActionText, Owner, DueDate, Status
                FROM Action WHERE MeetingId = ?
            """, (meeting_id,))
            result["actions"] = [
                {"id": r[0], "text": r[1], "owner": r[2], 
                 "due_date": r[3].isoformat() if r[3] else None, "status": r[4]}
                for r in cursor.fetchall()
            ]
    except Exception:
        pass
    
    return result


@app.get("/api/meetings/search")
async def search_meetings_endpoint(
    query: str = Query(..., min_length=2),
    limit: int = Query(10, ge=1, le=50),
    user: str = Depends(get_current_user)
):
    """Search meetings by keyword."""
    result = meetings.search_meetings(query=query, limit=limit)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@app.get("/api/actions")
async def list_actions_endpoint(
    status: Optional[str] = Query(None),
    owner: Optional[str] = Query(None),
    meeting_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: str = Depends(get_current_user)
):
    """List actions with filters."""
    result = actions.list_actions(
        status=status,
        owner=owner,
        meeting_id=meeting_id,
        limit=limit
    )
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@app.get("/api/actions/{action_id}")
async def get_action_endpoint(action_id: int, user: str = Depends(get_current_user)):
    """Get action details."""
    result = actions.get_action(action_id)
    if result.get("error"):
        if result["code"] == "NOT_FOUND":
            raise HTTPException(status_code=404, detail=result["message"])
        raise HTTPException(status_code=400, detail=result["message"])
    return result


class StatusUpdate(BaseModel):
    status: str


@app.patch("/api/actions/{action_id}/status")
async def update_action_status_endpoint(action_id: int, update: StatusUpdate, user: str = Depends(get_current_user)):
    """Update action status."""
    """Update action status."""
    user_email = user # Use the authenticated user's email
    
    if update.status == "Complete":
        result = actions.complete_action(action_id, user_email)
    elif update.status == "Parked":
        result = actions.park_action(action_id, user_email)
    elif update.status == "Open":
        try:
            with get_db() as cursor:
                cursor.execute("""
                    UPDATE Action SET Status = 'Open', UpdatedAt = ?, UpdatedBy = ?
                    WHERE ActionId = ?
                """, (datetime.utcnow(), user_email, action_id))
            result = actions.get_action(action_id)
        except Exception as e:
            result = {"error": True, "code": "DATABASE_ERROR", "message": str(e)}
    else:
        raise HTTPException(status_code=400, detail="Invalid status")
    
    if result.get("error"):
        if result["code"] == "NOT_FOUND":
            raise HTTPException(status_code=404, detail=result["message"])
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@app.get("/api/decisions")
async def list_decisions_endpoint(
    meeting_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: str = Depends(get_current_user)
):
    """List decisions."""
    result = decisions.list_decisions(meeting_id=meeting_id, limit=limit)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@app.get("/api/decisions/{decision_id}")
async def get_decision_endpoint(decision_id: int, user: str = Depends(get_current_user)):
    """Get decision details."""
    result = decisions.get_decision(decision_id)
    if result.get("error"):
        if result.get("code") == "NOT_FOUND":
            raise HTTPException(status_code=404, detail=result["message"])
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@app.delete("/api/meetings/{meeting_id}")
async def delete_meeting_endpoint(meeting_id: int, user: str = Depends(get_current_user)):
    """Delete a meeting and its associated decisions and actions."""
    try:
        with get_db() as cursor:
            # Check if meeting exists
            cursor.execute("SELECT MeetingId FROM Meeting WHERE MeetingId = ?", (meeting_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail=f"Meeting {meeting_id} not found")

            # Delete in order due to foreign keys
            cursor.execute("DELETE FROM Decision WHERE MeetingId = ?", (meeting_id,))
            cursor.execute("DELETE FROM Action WHERE MeetingId = ?", (meeting_id,))
            cursor.execute("DELETE FROM Meeting WHERE MeetingId = ?", (meeting_id,))

        return {"success": True, "message": f"Meeting {meeting_id} deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/actions/{action_id}")
async def delete_action_endpoint(action_id: int, user: str = Depends(get_current_user)):
    """Delete an action."""
    try:
        with get_db() as cursor:
            cursor.execute("SELECT ActionId FROM Action WHERE ActionId = ?", (action_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail=f"Action {action_id} not found")

            cursor.execute("DELETE FROM Action WHERE ActionId = ?", (action_id,))

        return {"success": True, "message": f"Action {action_id} deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/decisions/{decision_id}")
async def delete_decision_endpoint(decision_id: int, user: str = Depends(get_current_user)):
    """Delete a decision."""
    try:
        with get_db() as cursor:
            cursor.execute("SELECT DecisionId FROM Decision WHERE DecisionId = ?", (decision_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail=f"Decision {decision_id} not found")

            cursor.execute("DELETE FROM Decision WHERE DecisionId = ?", (decision_id,))

        return {"success": True, "message": f"Decision {decision_id} deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "meeting-intelligence"}
