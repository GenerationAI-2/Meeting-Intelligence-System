"""Meeting Intelligence MCP Server - Server Instance"""

from mcp.server import Server
from .tools import meetings, actions, decisions

# Create MCP server instance to be shared
mcp_server = Server("meeting-intelligence")

# Add tools to the server instance
@mcp_server.list_tools()
async def list_tools() -> list:
    # Re-use logic from main.py, but since we're splitting files, 
    # we need to ensure this is the source of truth.
    # We will import this mcp_server instance in both main.py (stdio) and api.py (sse)
    from mcp.types import Tool
    return [
        # Meeting Tools
        Tool(
            name="list_meetings",
            description="List recent meetings. Returns id, title, date, attendees, source. Can filter by attendee email.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Maximum results (default 20, max 100)", "default": 20},
                    "days_back": {"type": "integer", "description": "How far back to search (default 30)", "default": 30},
                    "attendee": {"type": "string", "description": "Filter by attendee email (partial match)"}
                }
            }
        ),
        Tool(
            name="get_meeting",
            description="Get full details of a specific meeting including summary and transcript.",
            inputSchema={
                "type": "object",
                "properties": {
                    "meeting_id": {"type": "integer", "description": "The meeting ID"}
                },
                "required": ["meeting_id"]
            }
        ),
        Tool(
            name="search_meetings",
            description="Search meetings by keyword in title and transcript. Returns matching meetings with context snippet.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search terms (min 2 chars)"},
                    "limit": {"type": "integer", "description": "Maximum results (default 10, max 50)", "default": 10}
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="create_meeting",
            description="Create a new meeting record.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Meeting title"},
                    "meeting_date": {"type": "string", "description": "ISO date format"},
                    "attendees": {"type": "string", "description": "Comma-separated names"},
                    "summary": {"type": "string", "description": "Meeting summary"},
                    "transcript": {"type": "string", "description": "Raw transcript"},
                    "source": {"type": "string", "description": "Source system (default 'Manual')", "default": "Manual"},
                    "source_meeting_id": {"type": "string", "description": "External ID"}
                },
                "required": ["title", "meeting_date"]
            }
        ),
        Tool(
            name="update_meeting",
            description="Update an existing meeting. Can update title, summary, attendees, or transcript.",
            inputSchema={
                "type": "object",
                "properties": {
                    "meeting_id": {"type": "integer", "description": "The meeting ID"},
                    "title": {"type": "string", "description": "New title"},
                    "summary": {"type": "string", "description": "New/updated summary"},
                    "attendees": {"type": "string", "description": "Updated attendees"},
                    "transcript": {"type": "string", "description": "Updated raw transcript"}
                },
                "required": ["meeting_id"]
            }
        ),
        
        # Action Tools
        Tool(
            name="list_actions",
            description="List action items. Default returns Open actions only, sorted by due date.",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "Filter by 'Open', 'Complete', or 'Parked'", "enum": ["Open", "Complete", "Parked"]},
                    "owner": {"type": "string", "description": "Filter by owner name"},
                    "meeting_id": {"type": "integer", "description": "Filter by source meeting"},
                    "limit": {"type": "integer", "description": "Maximum results (default 50, max 200)", "default": 50}
                }
            }
        ),
        Tool(
            name="get_action",
            description="Get full details of a specific action including notes and timestamps.",
            inputSchema={
                "type": "object",
                "properties": {
                    "action_id": {"type": "integer", "description": "The action ID"}
                },
                "required": ["action_id"]
            }
        ),
        Tool(
            name="create_action",
            description="Create a new action item. Status defaults to 'Open'.",
            inputSchema={
                "type": "object",
                "properties": {
                    "action_text": {"type": "string", "description": "What needs to be done"},
                    "owner": {"type": "string", "description": "Person responsible"},
                    "due_date": {"type": "string", "description": "ISO date format"},
                    "meeting_id": {"type": "integer", "description": "Link to source meeting"},
                    "notes": {"type": "string", "description": "Additional context"}
                },
                "required": ["action_text", "owner"]
            }
        ),
        Tool(
            name="update_action",
            description="Update an existing action. Cannot change status (use complete_action or park_action).",
            inputSchema={
                "type": "object",
                "properties": {
                    "action_id": {"type": "integer", "description": "The action ID"},
                    "action_text": {"type": "string", "description": "Updated description"},
                    "owner": {"type": "string", "description": "New owner"},
                    "due_date": {"type": "string", "description": "New due date"},
                    "notes": {"type": "string", "description": "Updated notes"}
                },
                "required": ["action_id"]
            }
        ),
        Tool(
            name="complete_action",
            description="Mark an action as complete. Idempotent - completing an already-complete action is not an error.",
            inputSchema={
                "type": "object",
                "properties": {
                    "action_id": {"type": "integer", "description": "The action ID"}
                },
                "required": ["action_id"]
            }
        ),
        Tool(
            name="park_action",
            description="Park an action (put on hold). Parked actions can be reopened via update_action.",
            inputSchema={
                "type": "object",
                "properties": {
                    "action_id": {"type": "integer", "description": "The action ID"}
                },
                "required": ["action_id"]
            }
        ),
        Tool(
            name="delete_action",
            description="Permanently delete an action. Cannot be undone. Confirm with user before calling.",
            inputSchema={
                "type": "object",
                "properties": {
                    "action_id": {"type": "integer", "description": "The action ID"}
                },
                "required": ["action_id"]
            }
        ),
        
        # Decision Tools
        Tool(
            name="list_decisions",
            description="List decisions from meetings. Sorted by created date, most recent first.",
            inputSchema={
                "type": "object",
                "properties": {
                    "meeting_id": {"type": "integer", "description": "Filter by source meeting"},
                    "limit": {"type": "integer", "description": "Maximum results (default 50, max 200)", "default": 50}
                }
            }
        ),
        Tool(
            name="create_decision",
            description="Record a decision made in a meeting.",
            inputSchema={
                "type": "object",
                "properties": {
                    "meeting_id": {"type": "integer", "description": "The meeting where decision was made"},
                    "decision_text": {"type": "string", "description": "The decision"},
                    "context": {"type": "string", "description": "Background/reasoning"}
                },
                "required": ["meeting_id", "decision_text"]
            }
        ),
    ]

@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict) -> list:
    from mcp.types import TextContent
    # This logic matches what was in main.py, now centralized
    
    # We need a user_email provider. 
    # For stdio/sse, we'll use a default for V1 or could extract from headers in SSE.
    # For simplicity in V1, we hardcode system user
    user_email = "system@generationai.co.nz"
    
    try:
        # Meeting Tools
        if name == "list_meetings":
            result = meetings.list_meetings(
                limit=arguments.get("limit", 20),
                days_back=arguments.get("days_back", 30),
                attendee=arguments.get("attendee")
            )
        elif name == "get_meeting":
            result = meetings.get_meeting(arguments["meeting_id"])
        elif name == "search_meetings":
            result = meetings.search_meetings(
                query=arguments["query"],
                limit=arguments.get("limit", 10)
            )
        elif name == "create_meeting":
            result = meetings.create_meeting(
                title=arguments["title"],
                meeting_date=arguments["meeting_date"],
                user_email=user_email,
                attendees=arguments.get("attendees"),
                summary=arguments.get("summary"),
                transcript=arguments.get("transcript"),
                source=arguments.get("source", "Manual"),
                source_meeting_id=arguments.get("source_meeting_id")
            )
        elif name == "update_meeting":
            result = meetings.update_meeting(
                meeting_id=arguments["meeting_id"],
                user_email=user_email,
                title=arguments.get("title"),
                summary=arguments.get("summary"),
                attendees=arguments.get("attendees"),
                transcript=arguments.get("transcript")
            )
        
        # Action Tools
        elif name == "list_actions":
            result = actions.list_actions(
                status=arguments.get("status"),
                owner=arguments.get("owner"),
                meeting_id=arguments.get("meeting_id"),
                limit=arguments.get("limit", 50)
            )
        elif name == "get_action":
            result = actions.get_action(arguments["action_id"])
        elif name == "create_action":
            result = actions.create_action(
                action_text=arguments["action_text"],
                owner=arguments["owner"],
                user_email=user_email,
                due_date=arguments.get("due_date"),
                meeting_id=arguments.get("meeting_id"),
                notes=arguments.get("notes")
            )
        elif name == "update_action":
            result = actions.update_action(
                action_id=arguments["action_id"],
                user_email=user_email,
                action_text=arguments.get("action_text"),
                owner=arguments.get("owner"),
                due_date=arguments.get("due_date"),
                notes=arguments.get("notes")
            )
        elif name == "complete_action":
            result = actions.complete_action(arguments["action_id"], user_email)
        elif name == "park_action":
            result = actions.park_action(arguments["action_id"], user_email)
        elif name == "delete_action":
            result = actions.delete_action(arguments["action_id"])
        
        # Decision Tools
        elif name == "list_decisions":
            result = decisions.list_decisions(
                meeting_id=arguments.get("meeting_id"),
                limit=arguments.get("limit", 50)
            )
        elif name == "create_decision":
            result = decisions.create_decision(
                meeting_id=arguments["meeting_id"],
                decision_text=arguments["decision_text"],
                user_email=user_email,
                context=arguments.get("context")
            )

        else:
            result = {"error": True, "code": "UNKNOWN_TOOL", "message": f"Unknown tool: {name}"}
        
        import json
        return [TextContent(type="text", text=json.dumps(result, default=str, indent=2))]
    
    except Exception as e:
        import json
        error_result = {"error": True, "code": "INTERNAL_ERROR", "message": str(e)}
        return [TextContent(type="text", text=json.dumps(error_result))]
