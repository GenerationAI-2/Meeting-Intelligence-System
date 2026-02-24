"""Meeting Intelligence MCP Server - FastMCP Implementation"""

import contextvars

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import ValidationError
from .tools import meetings, actions, decisions
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
    tag: str = None
) -> dict:
    try:
        validated = MeetingListFilter(limit=limit, days_back=days_back, attendee=attendee, tag=tag)
    except ValidationError as e:
        return _validation_error_response(e)
    return meetings.list_meetings(
        limit=validated.limit, days_back=validated.days_back or 30,
        attendee=validated.attendee, tag=validated.tag
    )


@mcp.tool(description="Get full details of a specific meeting including summary and transcript.", annotations=READ_ONLY)
def get_meeting(meeting_id: int) -> dict:
    try:
        validated = MeetingId(meeting_id=meeting_id)
    except ValidationError as e:
        return _validation_error_response(e)
    return meetings.get_meeting(validated.meeting_id)


@mcp.tool(description="Search meetings by keyword in title and transcript. Returns matching meetings with context snippet.", annotations=READ_ONLY)
def search_meetings(query: str, limit: int = 10) -> dict:
    try:
        validated = MeetingSearch(query=query, limit=limit)
    except ValidationError as e:
        return _validation_error_response(e)
    return meetings.search_meetings(query=validated.query, limit=validated.limit)


@mcp.tool(description="Create a new meeting record. Format the summary field as markdown: use ## headings for sections (e.g. ## Key Discussion Points, ## Decisions, ## Next Steps), bullet points for lists, and **bold** for key items. This ensures the summary renders well in the web UI.", annotations=WRITE)
def create_meeting(
    title: str,
    meeting_date: str,
    attendees: str = None,
    summary: str = None,
    transcript: str = None,
    source: str = "Manual",
    source_meeting_id: str = None,
    tags: str = None
) -> dict:
    try:
        validated = MeetingCreate(
            title=title, meeting_date=meeting_date, attendees=attendees,
            summary=summary, transcript=transcript, source=source,
            source_meeting_id=source_meeting_id, tags=tags
        )
    except ValidationError as e:
        return _validation_error_response(e)
    return meetings.create_meeting(
        title=validated.title,
        meeting_date=validated.meeting_date,
        user_email=get_mcp_user(),
        attendees=validated.attendees,
        summary=validated.summary,
        transcript=validated.transcript,
        source=validated.source,
        source_meeting_id=validated.source_meeting_id,
        tags=validated.tags
    )


@mcp.tool(description="Update an existing meeting. Can update title, summary, attendees, transcript, or tags.", annotations=WRITE)
def update_meeting(
    meeting_id: int,
    title: str = None,
    summary: str = None,
    attendees: str = None,
    transcript: str = None,
    tags: str = None
) -> dict:
    try:
        MeetingId(meeting_id=meeting_id)
        validated = MeetingUpdate(
            title=title, summary=summary, attendees=attendees,
            transcript=transcript, tags=tags
        )
    except ValidationError as e:
        return _validation_error_response(e)
    return meetings.update_meeting(
        meeting_id=meeting_id,
        user_email=get_mcp_user(),
        title=validated.title,
        summary=validated.summary,
        attendees=validated.attendees,
        transcript=validated.transcript,
        tags=validated.tags
    )


@mcp.tool(description="Permanently delete a meeting and all its linked actions and decisions. Cannot be undone. Confirm with user before calling.", annotations=DESTRUCTIVE)
def delete_meeting(meeting_id: int) -> dict:
    try:
        validated = MeetingId(meeting_id=meeting_id)
    except ValidationError as e:
        return _validation_error_response(e)
    return meetings.delete_meeting(validated.meeting_id)


# ============================================================================
# ACTION TOOLS
# ============================================================================

@mcp.tool(description="List action items. Default returns Open actions only, sorted by due date.", annotations=READ_ONLY)
def list_actions(
    status: str = None,
    owner: str = None,
    meeting_id: int = None,
    limit: int = 50
) -> dict:
    try:
        validated = ActionListFilter(status=status, owner=owner, meeting_id=meeting_id, limit=limit)
    except ValidationError as e:
        return _validation_error_response(e)
    return actions.list_actions(
        status=validated.status, owner=validated.owner,
        meeting_id=validated.meeting_id, limit=validated.limit
    )


@mcp.tool(description="Get full details of a specific action including notes and timestamps.", annotations=READ_ONLY)
def get_action(action_id: int) -> dict:
    try:
        validated = ActionId(action_id=action_id)
    except ValidationError as e:
        return _validation_error_response(e)
    return actions.get_action(validated.action_id)


@mcp.tool(description="Create a new action item. Status defaults to 'Open'. IMPORTANT: Always extract and include the due_date if a deadline, timeframe, or date is mentioned in the meeting context (e.g. 'by Friday', 'next week', 'end of sprint'). Use ISO 8601 format (YYYY-MM-DD). If no date is mentioned, omit due_date.", annotations=WRITE)
def create_action(
    action_text: str,
    owner: str,
    due_date: str = None,
    meeting_id: int = None,
    notes: str = None
) -> dict:
    try:
        validated = ActionCreate(
            action_text=action_text, owner=owner,
            due_date=due_date, meeting_id=meeting_id, notes=notes
        )
    except ValidationError as e:
        return _validation_error_response(e)
    return actions.create_action(
        action_text=validated.action_text,
        owner=validated.owner,
        user_email=get_mcp_user(),
        due_date=validated.due_date,
        meeting_id=validated.meeting_id,
        notes=validated.notes
    )


@mcp.tool(description="Update an existing action. Cannot change status (use complete_action or park_action).", annotations=WRITE)
def update_action(
    action_id: int,
    action_text: str = None,
    owner: str = None,
    due_date: str = None,
    notes: str = None
) -> dict:
    try:
        ActionId(action_id=action_id)
        validated = ActionUpdate(
            action_text=action_text, owner=owner,
            due_date=due_date, notes=notes
        )
    except ValidationError as e:
        return _validation_error_response(e)
    return actions.update_action(
        action_id=action_id,
        user_email=get_mcp_user(),
        action_text=validated.action_text,
        owner=validated.owner,
        due_date=validated.due_date,
        notes=validated.notes
    )


@mcp.tool(description="Mark an action as complete. Idempotent - completing an already-complete action is not an error.", annotations=WRITE)
def complete_action(action_id: int) -> dict:
    try:
        validated = ActionId(action_id=action_id)
    except ValidationError as e:
        return _validation_error_response(e)
    return actions.complete_action(validated.action_id, get_mcp_user())


@mcp.tool(description="Park an action (put on hold). Parked actions can be reopened via update_action.", annotations=WRITE)
def park_action(action_id: int) -> dict:
    try:
        validated = ActionId(action_id=action_id)
    except ValidationError as e:
        return _validation_error_response(e)
    return actions.park_action(validated.action_id, get_mcp_user())


@mcp.tool(description="Permanently delete an action. Cannot be undone. Confirm with user before calling.", annotations=DESTRUCTIVE)
def delete_action(action_id: int) -> dict:
    try:
        validated = ActionId(action_id=action_id)
    except ValidationError as e:
        return _validation_error_response(e)
    return actions.delete_action(validated.action_id)


@mcp.tool(description="Search actions by keyword in action text, owner, or notes. Returns matching actions with context snippet. Use this to find specific action items across all meetings.", annotations=READ_ONLY)
def search_actions(query: str, limit: int = 10) -> dict:
    return actions.search_actions(query=query, limit=limit)


# ============================================================================
# DECISION TOOLS
# ============================================================================

@mcp.tool(description="List decisions from meetings. Sorted by created date, most recent first.", annotations=READ_ONLY)
def list_decisions(meeting_id: int = None, limit: int = 50) -> dict:
    try:
        validated = DecisionListFilter(meeting_id=meeting_id, limit=limit)
    except ValidationError as e:
        return _validation_error_response(e)
    return decisions.list_decisions(meeting_id=validated.meeting_id, limit=validated.limit)


@mcp.tool(description="Record a decision made in a meeting.", annotations=WRITE)
def create_decision(
    meeting_id: int,
    decision_text: str,
    context: str = None
) -> dict:
    try:
        validated = DecisionCreate(
            meeting_id=meeting_id, decision_text=decision_text, context=context
        )
    except ValidationError as e:
        return _validation_error_response(e)
    return decisions.create_decision(
        meeting_id=validated.meeting_id,
        decision_text=validated.decision_text,
        user_email=get_mcp_user(),
        context=validated.context
    )


@mcp.tool(description="Permanently delete a decision. Cannot be undone. Confirm with user before calling.", annotations=DESTRUCTIVE)
def delete_decision(decision_id: int) -> dict:
    try:
        validated = DecisionId(decision_id=decision_id)
    except ValidationError as e:
        return _validation_error_response(e)
    return decisions.delete_decision(validated.decision_id)


@mcp.tool(description="Get full details of a specific decision including context and creator.", annotations=READ_ONLY)
def get_decision(decision_id: int) -> dict:
    try:
        validated = DecisionId(decision_id=decision_id)
    except ValidationError as e:
        return _validation_error_response(e)
    return decisions.get_decision(validated.decision_id)


@mcp.tool(description="Search decisions by keyword in decision text or context. Returns matching decisions with meeting title and context snippet. Use this to find specific decisions across all meetings.", annotations=READ_ONLY)
def search_decisions(query: str, limit: int = 10) -> dict:
    return decisions.search_decisions(query=query, limit=limit)


# ============================================================================
# SCHEMA TOOL
# ============================================================================

@mcp.tool(description="Get field definitions, types, constraints, formats, and examples for all entities (Meeting, Action, Decision). Call this before creating or updating records to understand required fields and formats.", annotations=READ_ONLY)
def get_schema() -> dict:
    from .api import get_entity_schema
    return get_entity_schema()
