"""Meeting Intelligence MCP Server - FastMCP Implementation"""

import contextvars
from typing import Optional

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import ValidationError
from .workspace_context import WorkspaceContext, make_legacy_context
from . import database as _db_module
from .database import _get_engine, call_with_retry, get_db_for
from .tools import meetings, actions, decisions, workspaces
from .audit import audit_data_operation
from .schemas import (
    MeetingCreate, MeetingUpdate, MeetingId, MeetingSearch, MeetingListFilter,
    ActionCreate, ActionUpdate, ActionId, ActionListFilter,
    DecisionCreate, DecisionId, DecisionListFilter,
)

# Tool annotations for ChatGPT compatibility
# ChatGPT requires these hints to properly classify tools
READ_ONLY = ToolAnnotations(readOnlyHint=True)
WRITE = ToolAnnotations(readOnlyHint=False)
DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True)

# DNS rebinding protection is disabled in the SDK because we enforce
# Origin validation ourselves in main.py (mcp_auth_middleware). The SDK's
# allowed_hosts check requires a static FQDN which varies per environment.
transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=False
)

# Create stateless MCP server (required for Copilot)
mcp = FastMCP(
    "meeting-intelligence",
    stateless_http=True,
    transport_security=transport_security
)

# Contextvar set by auth middleware in main.py — carries the authenticated
# user email through to MCP tool handlers without explicit parameter passing.
_mcp_user_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "mcp_user", default="system@generationai.co.nz"
)


def set_mcp_user(email: str) -> None:
    """Set the authenticated MCP user for the current request."""
    _mcp_user_var.set(email)


def get_mcp_user() -> str:
    """Get the authenticated MCP user. Falls back to system@ for stdio/unauthenticated."""
    return _mcp_user_var.get()


# Workspace context — set by auth middleware when control DB is configured
_mcp_workspace_ctx_var: contextvars.ContextVar[Optional[WorkspaceContext]] = contextvars.ContextVar(
    "mcp_workspace_ctx", default=None
)


def set_mcp_workspace_context(ctx: WorkspaceContext) -> None:
    """Set the resolved workspace context for the current MCP request."""
    _mcp_workspace_ctx_var.set(ctx)


def get_mcp_workspace_context() -> Optional[WorkspaceContext]:
    """Get the workspace context for the current MCP request. None if not resolved."""
    return _mcp_workspace_ctx_var.get()


# ============================================================================
# HELPERS
# ============================================================================

def _resolve_ctx(workspace_override: str | None = None) -> WorkspaceContext | dict:
    """Get workspace context for current MCP request, with optional workspace override.

    Returns WorkspaceContext on success, or error dict on failure.
    """
    from .config import get_settings
    ctx = get_mcp_workspace_context()
    if ctx is None:
        settings = get_settings()
        if settings.control_db_name:
            # Workspace mode: context should have been set by auth middleware.
            # If it wasn't, fail closed — do NOT grant admin access.
            return {"error": True, "code": "AUTH_ERROR",
                    "message": "Workspace context not resolved — access denied"}
        # Genuine legacy/stdio mode: no control DB configured
        ctx = make_legacy_context(get_mcp_user())

    if workspace_override:
        # Find the requested workspace in user's memberships
        for m in ctx.memberships:
            if m.workspace_name == workspace_override or str(m.workspace_id) == workspace_override:
                return WorkspaceContext(
                    user_email=ctx.user_email,
                    is_org_admin=ctx.is_org_admin,
                    memberships=ctx.memberships,
                    active=m,
                )
        return {"error": True, "code": "FORBIDDEN",
                "message": f"Not a member of workspace '{workspace_override}'"}

    return ctx


def _mcp_tool_call(func, ctx, *, _audit=None, **kwargs):
    """Execute a tool function with retry and cursor management.

    _audit: Optional tuple of (operation, entity_type, id_key) for audit logging.
            id_key is the key in the result dict that holds the entity ID.
            Only logs on success (no error in result).
    """
    if isinstance(ctx, dict) and ctx.get("error"):
        return ctx  # Workspace resolution failed
    if _db_module.engine_registry:
        eng = _db_module.engine_registry.get_engine(ctx.db_name)
    else:
        eng = _get_engine()
    result = call_with_retry(eng, func, ctx, **kwargs)

    # Audit write operations on success
    if _audit and not (isinstance(result, dict) and result.get("error")):
        operation, entity_type, id_key = _audit
        entity_id = result.get(id_key) if isinstance(result, dict) and id_key else None
        audit_data_operation(ctx, operation, entity_type, entity_id, auth_method="mcp")

    return result


def _validation_error_response(e: ValidationError) -> dict:
    """Convert Pydantic ValidationError to user-friendly MCP response."""
    errors = e.errors()
    if len(errors) == 1:
        field = errors[0].get('loc', ['unknown'])[-1]
        msg = errors[0].get('msg', 'Invalid input')
        return {"error": True, "code": "VALIDATION_ERROR", "message": f"Invalid {field}: {msg}"}
    messages = [f"{err.get('loc', ['unknown'])[-1]}: {err.get('msg', '')}" for err in errors]
    return {"error": True, "code": "VALIDATION_ERROR", "message": f"Validation errors: {'; '.join(messages)}"}


# ============================================================================
# MEETING TOOLS
# ============================================================================

@mcp.tool(description="List recent meetings. Returns id, title, date, attendees, source, tags. Can filter by attendee or tag.", annotations=READ_ONLY)
def list_meetings(
    limit: int = 20,
    days_back: int = 30,
    attendee: str = None,
    tag: str = None,
    workspace: str = None
) -> dict:
    try:
        validated = MeetingListFilter(limit=limit, days_back=days_back, attendee=attendee, tag=tag)
    except ValidationError as e:
        return _validation_error_response(e)
    ctx = _resolve_ctx(workspace)
    return _mcp_tool_call(meetings.list_meetings, ctx,
                          limit=validated.limit, days_back=validated.days_back or 30,
                          attendee=validated.attendee, tag=validated.tag)


@mcp.tool(description="Get full details of a specific meeting including summary and transcript.", annotations=READ_ONLY)
def get_meeting(meeting_id: int, workspace: str = None) -> dict:
    try:
        validated = MeetingId(meeting_id=meeting_id)
    except ValidationError as e:
        return _validation_error_response(e)
    ctx = _resolve_ctx(workspace)
    return _mcp_tool_call(meetings.get_meeting, ctx, meeting_id=validated.meeting_id)


@mcp.tool(description="Search meetings by keyword in title and transcript. Returns matching meetings with context snippet.", annotations=READ_ONLY)
def search_meetings(query: str, limit: int = 10, workspace: str = None) -> dict:
    try:
        validated = MeetingSearch(query=query, limit=limit)
    except ValidationError as e:
        return _validation_error_response(e)
    ctx = _resolve_ctx(workspace)
    return _mcp_tool_call(meetings.search_meetings, ctx,
                          query=validated.query, limit=validated.limit)


@mcp.tool(description="Create a new meeting record. Format the summary field as markdown: use ## headings for sections (e.g. ## Key Discussion Points, ## Decisions, ## Next Steps), bullet points for lists, and **bold** for key items. This ensures the summary renders well in the web UI.", annotations=WRITE)
def create_meeting(
    title: str,
    meeting_date: str,
    attendees: str = None,
    summary: str = None,
    transcript: str = None,
    source: str = "Manual",
    source_meeting_id: str = None,
    tags: str = None,
    workspace: str = None
) -> dict:
    try:
        validated = MeetingCreate(
            title=title, meeting_date=meeting_date, attendees=attendees,
            summary=summary, transcript=transcript, source=source,
            source_meeting_id=source_meeting_id, tags=tags
        )
    except ValidationError as e:
        return _validation_error_response(e)
    ctx = _resolve_ctx(workspace)
    return _mcp_tool_call(meetings.create_meeting, ctx,
                          _audit=("create", "meeting", "id"),
                          title=validated.title,
                          meeting_date=validated.meeting_date,
                          attendees=validated.attendees,
                          summary=validated.summary,
                          transcript=validated.transcript,
                          source=validated.source,
                          source_meeting_id=validated.source_meeting_id,
                          tags=validated.tags)


@mcp.tool(description="Update an existing meeting. Can update title, summary, attendees, transcript, or tags.", annotations=WRITE)
def update_meeting(
    meeting_id: int,
    title: str = None,
    summary: str = None,
    attendees: str = None,
    transcript: str = None,
    tags: str = None,
    workspace: str = None
) -> dict:
    try:
        MeetingId(meeting_id=meeting_id)
        validated = MeetingUpdate(
            title=title, summary=summary, attendees=attendees,
            transcript=transcript, tags=tags
        )
    except ValidationError as e:
        return _validation_error_response(e)
    ctx = _resolve_ctx(workspace)
    return _mcp_tool_call(meetings.update_meeting, ctx,
                          _audit=("update", "meeting", "id"),
                          meeting_id=meeting_id,
                          title=validated.title,
                          summary=validated.summary,
                          attendees=validated.attendees,
                          transcript=validated.transcript,
                          tags=validated.tags)


@mcp.tool(description="Permanently delete a meeting and all its linked actions and decisions. Cannot be undone. Confirm with user before calling.", annotations=DESTRUCTIVE)
def delete_meeting(meeting_id: int, workspace: str = None) -> dict:
    try:
        validated = MeetingId(meeting_id=meeting_id)
    except ValidationError as e:
        return _validation_error_response(e)
    ctx = _resolve_ctx(workspace)
    return _mcp_tool_call(meetings.delete_meeting, ctx,
                          _audit=("delete", "meeting", None),
                          meeting_id=validated.meeting_id)


# ============================================================================
# ACTION TOOLS
# ============================================================================

@mcp.tool(description="List action items. Default returns Open actions only, sorted by due date.", annotations=READ_ONLY)
def list_actions(
    status: str = None,
    owner: str = None,
    meeting_id: int = None,
    limit: int = 50,
    workspace: str = None
) -> dict:
    try:
        validated = ActionListFilter(status=status, owner=owner, meeting_id=meeting_id, limit=limit)
    except ValidationError as e:
        return _validation_error_response(e)
    ctx = _resolve_ctx(workspace)
    return _mcp_tool_call(actions.list_actions, ctx,
                          status=validated.status, owner=validated.owner,
                          meeting_id=validated.meeting_id, limit=validated.limit)


@mcp.tool(description="Get full details of a specific action including notes and timestamps.", annotations=READ_ONLY)
def get_action(action_id: int, workspace: str = None) -> dict:
    try:
        validated = ActionId(action_id=action_id)
    except ValidationError as e:
        return _validation_error_response(e)
    ctx = _resolve_ctx(workspace)
    return _mcp_tool_call(actions.get_action, ctx, action_id=validated.action_id)


@mcp.tool(description="Create a new action item. Status defaults to 'Open'. IMPORTANT: Always extract and include the due_date if a deadline, timeframe, or date is mentioned in the meeting context (e.g. 'by Friday', 'next week', 'end of sprint'). Use ISO 8601 format (YYYY-MM-DD). If no date is mentioned, omit due_date.", annotations=WRITE)
def create_action(
    action_text: str,
    owner: str,
    due_date: str = None,
    meeting_id: int = None,
    notes: str = None,
    workspace: str = None
) -> dict:
    try:
        validated = ActionCreate(
            action_text=action_text, owner=owner,
            due_date=due_date, meeting_id=meeting_id, notes=notes
        )
    except ValidationError as e:
        return _validation_error_response(e)
    ctx = _resolve_ctx(workspace)
    return _mcp_tool_call(actions.create_action, ctx,
                          _audit=("create", "action", "id"),
                          action_text=validated.action_text,
                          owner=validated.owner,
                          due_date=validated.due_date,
                          meeting_id=validated.meeting_id,
                          notes=validated.notes)


@mcp.tool(description="Update an existing action. Cannot change status (use complete_action or park_action).", annotations=WRITE)
def update_action(
    action_id: int,
    action_text: str = None,
    owner: str = None,
    due_date: str = None,
    notes: str = None,
    workspace: str = None
) -> dict:
    try:
        ActionId(action_id=action_id)
        validated = ActionUpdate(
            action_text=action_text, owner=owner,
            due_date=due_date, notes=notes
        )
    except ValidationError as e:
        return _validation_error_response(e)
    ctx = _resolve_ctx(workspace)
    return _mcp_tool_call(actions.update_action, ctx,
                          _audit=("update", "action", "id"),
                          action_id=action_id,
                          action_text=validated.action_text,
                          owner=validated.owner,
                          due_date=validated.due_date,
                          notes=validated.notes)


@mcp.tool(description="Mark an action as complete. Idempotent - completing an already-complete action is not an error.", annotations=WRITE)
def complete_action(action_id: int, workspace: str = None) -> dict:
    try:
        validated = ActionId(action_id=action_id)
    except ValidationError as e:
        return _validation_error_response(e)
    ctx = _resolve_ctx(workspace)
    return _mcp_tool_call(actions.complete_action, ctx,
                          _audit=("update", "action", "id"),
                          action_id=validated.action_id)


@mcp.tool(description="Park an action (put on hold). Parked actions can be reopened via update_action.", annotations=WRITE)
def park_action(action_id: int, workspace: str = None) -> dict:
    try:
        validated = ActionId(action_id=action_id)
    except ValidationError as e:
        return _validation_error_response(e)
    ctx = _resolve_ctx(workspace)
    return _mcp_tool_call(actions.park_action, ctx,
                          _audit=("update", "action", "id"),
                          action_id=validated.action_id)


@mcp.tool(description="Permanently delete an action. Cannot be undone. Confirm with user before calling.", annotations=DESTRUCTIVE)
def delete_action(action_id: int, workspace: str = None) -> dict:
    try:
        validated = ActionId(action_id=action_id)
    except ValidationError as e:
        return _validation_error_response(e)
    ctx = _resolve_ctx(workspace)
    return _mcp_tool_call(actions.delete_action, ctx,
                          _audit=("delete", "action", None),
                          action_id=validated.action_id)


@mcp.tool(description="Search actions by keyword in action text, owner, or notes. Returns matching actions with context snippet. Use this to find specific action items across all meetings.", annotations=READ_ONLY)
def search_actions(query: str, limit: int = 10, workspace: str = None) -> dict:
    ctx = _resolve_ctx(workspace)
    return _mcp_tool_call(actions.search_actions, ctx, query=query, limit=limit)


# ============================================================================
# DECISION TOOLS
# ============================================================================

@mcp.tool(description="List decisions from meetings. Sorted by created date, most recent first.", annotations=READ_ONLY)
def list_decisions(meeting_id: int = None, limit: int = 50, workspace: str = None) -> dict:
    try:
        validated = DecisionListFilter(meeting_id=meeting_id, limit=limit)
    except ValidationError as e:
        return _validation_error_response(e)
    ctx = _resolve_ctx(workspace)
    return _mcp_tool_call(decisions.list_decisions, ctx,
                          meeting_id=validated.meeting_id, limit=validated.limit)


@mcp.tool(description="Record a decision made in a meeting.", annotations=WRITE)
def create_decision(
    meeting_id: int,
    decision_text: str,
    context: str = None,
    workspace: str = None
) -> dict:
    try:
        validated = DecisionCreate(
            meeting_id=meeting_id, decision_text=decision_text, context=context
        )
    except ValidationError as e:
        return _validation_error_response(e)
    ctx = _resolve_ctx(workspace)
    return _mcp_tool_call(decisions.create_decision, ctx,
                          _audit=("create", "decision", "id"),
                          meeting_id=validated.meeting_id,
                          decision_text=validated.decision_text,
                          context=validated.context)


@mcp.tool(description="Permanently delete a decision. Cannot be undone. Confirm with user before calling.", annotations=DESTRUCTIVE)
def delete_decision(decision_id: int, workspace: str = None) -> dict:
    try:
        validated = DecisionId(decision_id=decision_id)
    except ValidationError as e:
        return _validation_error_response(e)
    ctx = _resolve_ctx(workspace)
    return _mcp_tool_call(decisions.delete_decision, ctx,
                          _audit=("delete", "decision", None),
                          decision_id=validated.decision_id)


@mcp.tool(description="Get full details of a specific decision including context and creator.", annotations=READ_ONLY)
def get_decision(decision_id: int, workspace: str = None) -> dict:
    try:
        validated = DecisionId(decision_id=decision_id)
    except ValidationError as e:
        return _validation_error_response(e)
    ctx = _resolve_ctx(workspace)
    return _mcp_tool_call(decisions.get_decision, ctx, decision_id=validated.decision_id)


@mcp.tool(description="Search decisions by keyword in decision text or context. Returns matching decisions with meeting title and context snippet. Use this to find specific decisions across all meetings.", annotations=READ_ONLY)
def search_decisions(query: str, limit: int = 10, workspace: str = None) -> dict:
    ctx = _resolve_ctx(workspace)
    return _mcp_tool_call(decisions.search_decisions, ctx, query=query, limit=limit)


# ============================================================================
# SCHEMA TOOL
# ============================================================================

@mcp.tool(description="Get field definitions, types, constraints, formats, and examples for all entities (Meeting, Action, Decision). Call this before creating or updating records to understand required fields and formats.", annotations=READ_ONLY)
def get_schema() -> dict:
    from .api import get_entity_schema
    return get_entity_schema()


# ============================================================================
# WORKSPACE TOOLS
# ============================================================================

@mcp.tool(description="List workspaces the user has access to. Shows name, role, and which is active.", annotations=READ_ONLY)
def list_workspaces() -> dict:
    ctx = _resolve_ctx()
    if isinstance(ctx, dict):
        return ctx
    return workspaces.list_workspaces(ctx)


@mcp.tool(description="Get details about the currently active workspace including user's role and permissions.", annotations=READ_ONLY)
def get_current_workspace() -> dict:
    ctx = _resolve_ctx()
    if isinstance(ctx, dict):
        return ctx
    return workspaces.get_current_workspace(ctx)


@mcp.tool(description="Switch to a different workspace by name or ID. Subsequent tool calls will operate in the new workspace.", annotations=WRITE)
def switch_workspace(workspace: str) -> dict:
    ctx = _resolve_ctx(workspace)
    if isinstance(ctx, dict):
        return ctx
    # Update the contextvar so subsequent calls in this session use the new workspace
    set_mcp_workspace_context(ctx)
    return {
        "message": f"Switched to workspace '{ctx.active.workspace_display_name}'",
        "workspace": workspaces.get_current_workspace(ctx),
    }
