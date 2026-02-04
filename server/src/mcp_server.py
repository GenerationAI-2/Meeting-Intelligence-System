"""Meeting Intelligence MCP Server - FastMCP Implementation"""

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from .tools import meetings, actions, decisions

# Configure transport security - disable DNS rebinding protection
# (we use token-based auth instead)
transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=False
)

# Create stateless MCP server (required for Copilot)
mcp = FastMCP(
    "meeting-intelligence",
    stateless_http=True,
    transport_security=transport_security
)

# System user for MCP calls (TODO: extract from auth in future)
SYSTEM_USER = "system@generationai.co.nz"


# ============================================================================
# MEETING TOOLS
# ============================================================================

@mcp.tool(description="List recent meetings. Returns id, title, date, attendees, source, tags. Can filter by attendee or tag.")
def list_meetings(
    limit: int = 20,
    days_back: int = 30,
    attendee: str = None,
    tag: str = None
) -> dict:
    return meetings.list_meetings(limit=limit, days_back=days_back, attendee=attendee, tag=tag)


@mcp.tool(description="Get full details of a specific meeting including summary and transcript.")
def get_meeting(meeting_id: int) -> dict:
    return meetings.get_meeting(meeting_id)


@mcp.tool(description="Search meetings by keyword in title and transcript. Returns matching meetings with context snippet.")
def search_meetings(query: str, limit: int = 10) -> dict:
    return meetings.search_meetings(query=query, limit=limit)


@mcp.tool(description="Create a new meeting record.")
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
    return meetings.create_meeting(
        title=title,
        meeting_date=meeting_date,
        user_email=SYSTEM_USER,
        attendees=attendees,
        summary=summary,
        transcript=transcript,
        source=source,
        source_meeting_id=source_meeting_id,
        tags=tags
    )


@mcp.tool(description="Update an existing meeting. Can update title, summary, attendees, transcript, or tags.")
def update_meeting(
    meeting_id: int,
    title: str = None,
    summary: str = None,
    attendees: str = None,
    transcript: str = None,
    tags: str = None
) -> dict:
    return meetings.update_meeting(
        meeting_id=meeting_id,
        user_email=SYSTEM_USER,
        title=title,
        summary=summary,
        attendees=attendees,
        transcript=transcript,
        tags=tags
    )


@mcp.tool(description="Permanently delete a meeting and all its linked actions and decisions. Cannot be undone. Confirm with user before calling.")
def delete_meeting(meeting_id: int) -> dict:
    return meetings.delete_meeting(meeting_id)


# ============================================================================
# ACTION TOOLS
# ============================================================================

@mcp.tool(description="List action items. Default returns Open actions only, sorted by due date.")
def list_actions(
    status: str = None,
    owner: str = None,
    meeting_id: int = None,
    limit: int = 50
) -> dict:
    return actions.list_actions(status=status, owner=owner, meeting_id=meeting_id, limit=limit)


@mcp.tool(description="Get full details of a specific action including notes and timestamps.")
def get_action(action_id: int) -> dict:
    return actions.get_action(action_id)


@mcp.tool(description="Create a new action item. Status defaults to 'Open'.")
def create_action(
    action_text: str,
    owner: str,
    due_date: str = None,
    meeting_id: int = None,
    notes: str = None
) -> dict:
    return actions.create_action(
        action_text=action_text,
        owner=owner,
        user_email=SYSTEM_USER,
        due_date=due_date,
        meeting_id=meeting_id,
        notes=notes
    )


@mcp.tool(description="Update an existing action. Cannot change status (use complete_action or park_action).")
def update_action(
    action_id: int,
    action_text: str = None,
    owner: str = None,
    due_date: str = None,
    notes: str = None
) -> dict:
    return actions.update_action(
        action_id=action_id,
        user_email=SYSTEM_USER,
        action_text=action_text,
        owner=owner,
        due_date=due_date,
        notes=notes
    )


@mcp.tool(description="Mark an action as complete. Idempotent - completing an already-complete action is not an error.")
def complete_action(action_id: int) -> dict:
    return actions.complete_action(action_id, SYSTEM_USER)


@mcp.tool(description="Park an action (put on hold). Parked actions can be reopened via update_action.")
def park_action(action_id: int) -> dict:
    return actions.park_action(action_id, SYSTEM_USER)


@mcp.tool(description="Permanently delete an action. Cannot be undone. Confirm with user before calling.")
def delete_action(action_id: int) -> dict:
    return actions.delete_action(action_id)


# ============================================================================
# DECISION TOOLS
# ============================================================================

@mcp.tool(description="List decisions from meetings. Sorted by created date, most recent first.")
def list_decisions(meeting_id: int = None, limit: int = 50) -> dict:
    return decisions.list_decisions(meeting_id=meeting_id, limit=limit)


@mcp.tool(description="Record a decision made in a meeting.")
def create_decision(
    meeting_id: int,
    decision_text: str,
    context: str = None
) -> dict:
    return decisions.create_decision(
        meeting_id=meeting_id,
        decision_text=decision_text,
        user_email=SYSTEM_USER,
        context=context
    )


@mcp.tool(description="Permanently delete a decision. Cannot be undone. Confirm with user before calling.")
def delete_decision(decision_id: int) -> dict:
    return decisions.delete_decision(decision_id)
