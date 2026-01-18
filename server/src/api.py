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

async def get_current_user(
    request: Request,
    x_ms_client_principal_name: str | None = Header(None, alias="X-MS-CLIENT-PRINCIPAL-NAME")
):
    # 1. Try Easy Auth Header (Injected by Azure)
    if x_ms_client_principal_name:
        user_email = x_ms_client_principal_name
    else:
        # 2. Try Standard Bearer Token (Injected by React App)
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
             raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="Authentication required"
            )
        
        token = auth_header.split(" ")[1]
        try:
            # Decode token (verify_signature=False for now to handle standard Entra ID tokens 
            # without fetching JWKS keys manually. In production, we should configure 
            # Azure Container Apps to enforce auth or implement full validation)
            payload = jwt.decode(token, options={"verify_signature": False})
            
            # Extract email from claims
            user_email = payload.get("preferred_username") or payload.get("upn") or payload.get("email")
            
            if not user_email:
                raise HTTPException(status_code=401, detail="Token missing email claim")
                
        except Exception as e:
            print(f"Token decode error: {e}")
            raise HTTPException(status_code=401, detail="Invalid token")

    # Whitelist Check
    allowed_users = ["caleb.lucas@myadvisor.co.nz", "mark.lucas@myadvisor.co.nz"]
    if user_email.lower() not in allowed_users:
         raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail=f"Access denied for user: {user_email}"
        )
    
    return user_email


app = FastAPI(title="Meeting Intelligence API", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "https://claude.ai"],
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
    result = meetings.list_meetings(limit=limit, days_back=days_back)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["message"])
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


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "meeting-intelligence"}
