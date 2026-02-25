"""Meeting Intelligence - REST API (Web UI)"""

import hashlib
from typing import Optional
from fastapi import FastAPI, HTTPException, Query, Request, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response
from .schemas import StatusUpdate

from .database import engine_registry, _get_engine, call_with_retry, validate_client_token, validate_token_from_control_db
from .dependencies import authenticate_and_store, resolve_workspace
from .workspace_context import WorkspaceContext
from .tools import meetings, actions, decisions
from fastapi_azure_auth import SingleTenantAzureAuthorizationCodeBearer
from .config import get_settings
from .logging_config import get_logger

logger = get_logger(__name__)
settings = get_settings()

# Startup diagnostics - log config values (redacted)
logger.info("API startup", extra={
    "tenant_id": settings.azure_tenant_id[:8] + "..." if settings.azure_tenant_id else "NOT SET",
    "client_id": settings.azure_client_id[:8] + "..." if settings.azure_client_id else "NOT SET",
    "allowed_users": settings.allowed_users[:30] + "..." if settings.allowed_users else "NOT SET",
    "cors_origins": settings.cors_origins[:50] + "..." if settings.cors_origins else "NOT SET",
})

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
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        # Try control DB first when configured
        if settings.control_db_name and engine_registry:
            result = validate_token_from_control_db(token_hash)
            if result and result.get("user_email"):
                return result["user_email"]
        # Fallback: legacy workspace DB ClientToken table
        result = validate_client_token(token_hash)
        if result and not result.get("error") and result.get("client_email"):
            return result["client_email"]

    # 2. Azure Entra ID Token (for React Users)
    try:
        from fastapi.security import SecurityScopes
        logger.debug("Attempting Azure AD validation")
        # Validates signature, audience, issuer, and expiration
        # Throws HTTPException if invalid
        # Fix: Must pass SecurityScopes when calling manually
        token_payload = await azure_scheme(request, SecurityScopes(scopes=[]))
        logger.debug("Token validated successfully", extra={"payload_type": str(type(token_payload))})
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
        logger.warning("Auth failed", extra={
            "error_type": type(e).__name__,
            "detail": str(e),
            "status_code": getattr(e, 'status_code', None),
        })
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Whitelist Check
    allowed_users = settings.get_allowed_users_list()

    if not user_email:
        logger.warning("Auth failed: no email in token payload")
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
    logger.debug("Request", extra={
        "method": request.method,
        "path": request.url.path,
    })
    response = await call_next(request)
    logger.debug("Response", extra={
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
    })
    return response

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _get_engine_for_ctx(ctx: WorkspaceContext):
    """Get the SQLAlchemy engine for the active workspace."""
    if engine_registry:
        return engine_registry.get_engine(ctx.db_name)
    return _get_engine()


# ============================================================================
# MCP SSE ENDPOINT (For Claude.ai)
# ============================================================================

# SSE Endpoints are handled in main.py when running with --http
# This ensures separation of concerns: api.py is REST, main.py adds MCP transport.


# ============================================================================
# REST ENDPOINTS (Web UI)
# ============================================================================

@app.get("/api/me")
async def get_me(
    user: str = Depends(authenticate_and_store),
    ctx: WorkspaceContext = Depends(resolve_workspace),
):
    """Return authenticated user's profile, workspace memberships, and permissions."""
    return {
        "email": ctx.user_email,
        "is_org_admin": ctx.is_org_admin,
        "active_workspace": {
            "id": ctx.active.workspace_id,
            "name": ctx.active.workspace_name,
            "display_name": ctx.active.workspace_display_name,
            "role": ctx.active.role,
            "is_archived": ctx.active.is_archived,
        },
        "permissions": {
            "can_write": ctx.can_write(),
            "is_chair_or_admin": ctx.is_chair_or_admin(),
        },
        "workspaces": [
            {
                "id": m.workspace_id,
                "name": m.workspace_name,
                "display_name": m.workspace_display_name,
                "role": m.role,
                "is_default": m.is_default,
                "is_archived": m.is_archived,
            }
            for m in ctx.memberships
        ],
    }


@app.get("/api/meetings")
async def list_meetings_endpoint(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    days_back: int = Query(30, ge=1),
    user: str = Depends(authenticate_and_store),
    ctx: WorkspaceContext = Depends(resolve_workspace),
):
    """List meetings with pagination."""
    logger.info("List meetings", extra={"user": user, "limit": limit, "days_back": days_back})
    result = call_with_retry(_get_engine_for_ctx(ctx), meetings.list_meetings, ctx,
                             limit=limit, days_back=days_back)
    if result.get("error"):
        logger.error("List meetings failed", extra={"code": result.get("code"), "message": result.get("message")})
        raise HTTPException(status_code=400, detail=result["message"])
    logger.info("List meetings success", extra={"count": result.get("count", 0)})
    return result


@app.get("/api/meetings/search")
async def search_meetings_endpoint(
    query: str = Query(..., min_length=2),
    limit: int = Query(10, ge=1, le=50),
    user: str = Depends(authenticate_and_store),
    ctx: WorkspaceContext = Depends(resolve_workspace),
):
    """Search meetings by keyword."""
    result = call_with_retry(_get_engine_for_ctx(ctx), meetings.search_meetings, ctx,
                             query=query, limit=limit)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@app.get("/api/meetings/{meeting_id}")
async def get_meeting_endpoint(
    meeting_id: int,
    user: str = Depends(authenticate_and_store),
    ctx: WorkspaceContext = Depends(resolve_workspace),
):
    """Get meeting details including linked actions and decisions."""
    result = call_with_retry(_get_engine_for_ctx(ctx), meetings.get_meeting_detail, ctx,
                             meeting_id=meeting_id)
    if result.get("error"):
        if result["code"] == "NOT_FOUND":
            raise HTTPException(status_code=404, detail=result["message"])
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@app.get("/api/actions")
async def list_actions_endpoint(
    status: Optional[str] = Query(None),
    owner: Optional[str] = Query(None),
    meeting_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: str = Depends(authenticate_and_store),
    ctx: WorkspaceContext = Depends(resolve_workspace),
):
    """List actions with filters."""
    result = call_with_retry(_get_engine_for_ctx(ctx), actions.list_actions, ctx,
                             status=status, owner=owner,
                             meeting_id=meeting_id, limit=limit)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@app.get("/api/actions/owners")
async def list_action_owners_endpoint(
    user: str = Depends(authenticate_and_store),
    ctx: WorkspaceContext = Depends(resolve_workspace),
):
    """Get distinct action owners for filter dropdown."""
    result = call_with_retry(_get_engine_for_ctx(ctx), actions.get_distinct_owners, ctx)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@app.get("/api/actions/{action_id}")
async def get_action_endpoint(
    action_id: int,
    user: str = Depends(authenticate_and_store),
    ctx: WorkspaceContext = Depends(resolve_workspace),
):
    """Get action details."""
    result = call_with_retry(_get_engine_for_ctx(ctx), actions.get_action, ctx,
                             action_id=action_id)
    if result.get("error"):
        if result["code"] == "NOT_FOUND":
            raise HTTPException(status_code=404, detail=result["message"])
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@app.patch("/api/actions/{action_id}/status")
async def update_action_status_endpoint(
    action_id: int,
    update: StatusUpdate,
    user: str = Depends(authenticate_and_store),
    ctx: WorkspaceContext = Depends(resolve_workspace),
):
    """Update action status."""
    eng = _get_engine_for_ctx(ctx)

    if update.status == "Complete":
        result = call_with_retry(eng, actions.complete_action, ctx, action_id=action_id)
    elif update.status == "Parked":
        result = call_with_retry(eng, actions.park_action, ctx, action_id=action_id)
    elif update.status == "Open":
        result = call_with_retry(eng, actions.reopen_action, ctx, action_id=action_id)
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status: '{update.status}'. Must be one of: Open, Complete, Parked"
        )
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
    user: str = Depends(authenticate_and_store),
    ctx: WorkspaceContext = Depends(resolve_workspace),
):
    """List decisions."""
    result = call_with_retry(_get_engine_for_ctx(ctx), decisions.list_decisions, ctx,
                             meeting_id=meeting_id, limit=limit)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@app.get("/api/decisions/{decision_id}")
async def get_decision_endpoint(
    decision_id: int,
    user: str = Depends(authenticate_and_store),
    ctx: WorkspaceContext = Depends(resolve_workspace),
):
    """Get decision details."""
    result = call_with_retry(_get_engine_for_ctx(ctx), decisions.get_decision, ctx,
                             decision_id=decision_id)
    if result.get("error"):
        if result.get("code") == "NOT_FOUND":
            raise HTTPException(status_code=404, detail=result["message"])
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@app.delete("/api/meetings/{meeting_id}")
async def delete_meeting_endpoint(
    meeting_id: int,
    user: str = Depends(authenticate_and_store),
    ctx: WorkspaceContext = Depends(resolve_workspace),
):
    """Delete a meeting and its associated decisions and actions."""
    result = call_with_retry(_get_engine_for_ctx(ctx), meetings.delete_meeting, ctx,
                             meeting_id=meeting_id)
    if result.get("error"):
        if result.get("code") == "NOT_FOUND":
            raise HTTPException(status_code=404, detail=result["message"])
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@app.delete("/api/actions/{action_id}")
async def delete_action_endpoint(
    action_id: int,
    user: str = Depends(authenticate_and_store),
    ctx: WorkspaceContext = Depends(resolve_workspace),
):
    """Delete an action."""
    result = call_with_retry(_get_engine_for_ctx(ctx), actions.delete_action, ctx,
                             action_id=action_id)
    if result.get("error"):
        if result.get("code") == "NOT_FOUND":
            raise HTTPException(status_code=404, detail=result["message"])
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@app.delete("/api/decisions/{decision_id}")
async def delete_decision_endpoint(
    decision_id: int,
    user: str = Depends(authenticate_and_store),
    ctx: WorkspaceContext = Depends(resolve_workspace),
):
    """Delete a decision."""
    result = call_with_retry(_get_engine_for_ctx(ctx), decisions.delete_decision, ctx,
                             decision_id=decision_id)
    if result.get("error"):
        if result.get("code") == "NOT_FOUND":
            raise HTTPException(status_code=404, detail=result["message"])
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@app.get("/api/schema")
async def schema_endpoint():
    """Return field definitions, constraints, and formats for all entities."""
    return get_entity_schema()


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "meeting-intelligence"}


def get_entity_schema() -> dict:
    """Return structured schema describing all entities, fields, types, constraints, and examples.

    Used by both the REST endpoint and the MCP get_schema tool. One source of truth.
    """
    return {
        "version": "1.0",
        "entities": {
            "meeting": {
                "description": "A meeting record with optional transcript and summary",
                "fields": {
                    "title": {
                        "type": "string",
                        "required": True,
                        "max_length": 255,
                        "description": "Meeting title. Include the date in the title for clarity.",
                        "example": "Weekly Team Standup — 24 Feb 2026",
                    },
                    "meeting_date": {
                        "type": "string",
                        "required": True,
                        "format": "ISO 8601 (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)",
                        "description": "Date and time of the meeting. Include the actual time if known — do not default to midnight.",
                        "example": "2026-02-24T09:30:00",
                    },
                    "summary": {
                        "type": "string",
                        "required": False,
                        "max_length": 50000,
                        "format": "markdown",
                        "description": "Meeting summary. Use markdown formatting: ## headings for sections, bullet points (- or *) for items, **bold** for emphasis. Summaries over 500 characters without any markdown formatting will be rejected. Structure improves readability in the web UI.",
                        "example": "## Key Discussion\n\n- **Budget approved** for Q2 marketing campaign\n- Timeline confirmed: launch by 15 March\n\n## Next Steps\n\n- Sarah to draft creative brief by Friday",
                    },
                    "transcript": {
                        "type": "string",
                        "required": False,
                        "max_length": 500000,
                        "format": "plain text",
                        "description": "Raw transcript text.",
                        "example": "Speaker 1: Let's start with the budget update...",
                    },
                    "attendees": {
                        "type": "string",
                        "required": False,
                        "max_length": 5000,
                        "format": "comma-separated names",
                        "description": "Attendees as comma-separated full names, not email addresses.",
                        "example": "Sarah Chen, James Wilson, Maria Lopez",
                    },
                    "source": {
                        "type": "string",
                        "required": False,
                        "max_length": 50,
                        "description": "Where the meeting was captured. Default 'Manual'. Use 'Fireflies' for Fireflies imports.",
                        "example": "Manual",
                    },
                    "source_meeting_id": {
                        "type": "string",
                        "required": False,
                        "max_length": 255,
                        "description": "External system's meeting ID, used for deduplication.",
                        "example": "ff_abc123",
                    },
                    "tags": {
                        "type": "string",
                        "required": False,
                        "max_length": 1000,
                        "format": "comma-separated, lowercase",
                        "description": "Tags for categorisation. Comma-separated, lowercase.",
                        "example": "strategy, quarterly-review",
                    },
                },
            },
            "action": {
                "description": "An action item assigned to a person, optionally linked to a meeting",
                "fields": {
                    "action_text": {
                        "type": "string",
                        "required": True,
                        "max_length": 10000,
                        "description": "Clear, actionable description of what needs to be done.",
                        "example": "Draft the Q2 marketing budget proposal",
                    },
                    "owner": {
                        "type": "string",
                        "required": True,
                        "max_length": 128,
                        "description": "Person responsible. Use their display name, not email address.",
                        "example": "Sarah Chen",
                    },
                    "due_date": {
                        "type": "string",
                        "required": False,
                        "format": "YYYY-MM-DD",
                        "description": "Due date in ISO 8601 format. ALWAYS extract and include a due date if one is mentioned or can be inferred from context (e.g. 'by Friday', 'next week', 'end of sprint'). Convert relative dates to absolute. Non-ISO formats will be rejected.",
                        "example": "2026-03-01",
                    },
                    "meeting_id": {
                        "type": "integer",
                        "required": False,
                        "description": "Link to the meeting this action came from. References Meeting.id.",
                        "example": 42,
                    },
                    "notes": {
                        "type": "string",
                        "required": False,
                        "max_length": 10000,
                        "description": "Additional context or details about the action.",
                        "example": "Include comparison with Q1 actuals",
                    },
                },
                "status_values": ["Open", "Complete", "Parked"],
            },
            "decision": {
                "description": "A decision recorded during a meeting",
                "fields": {
                    "decision_text": {
                        "type": "string",
                        "required": True,
                        "max_length": 10000,
                        "description": "The decision that was made.",
                        "example": "Approved Q2 marketing budget of $50,000",
                    },
                    "meeting_id": {
                        "type": "integer",
                        "required": True,
                        "description": "The meeting where this decision was made. Must reference a valid meeting.",
                        "example": 42,
                    },
                    "context": {
                        "type": "string",
                        "required": False,
                        "max_length": 10000,
                        "description": "Why this decision was made — the reasoning or discussion that led to it.",
                        "example": "Team agreed after reviewing Q1 results showing 20% ROI on marketing spend",
                    },
                },
            },
        },
        "relationships": [
            {
                "from": "action.meeting_id",
                "to": "meeting",
                "type": "many-to-one",
                "required": False,
                "description": "An action can optionally be linked to the meeting it came from.",
            },
            {
                "from": "decision.meeting_id",
                "to": "meeting",
                "type": "many-to-one",
                "required": True,
                "description": "A decision must be linked to the meeting where it was made.",
            },
        ],
        "cascade_deletes": "Deleting a meeting deletes all its linked actions and decisions.",
    }
