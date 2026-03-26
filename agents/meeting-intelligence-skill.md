---
name: meeting-intelligence
description: "Teaches AI how to search, retrieve, and synthesise across meetings, actions, and decisions in the Meeting Intelligence system. Attach this skill to any Claude or ChatGPT session connected to MI via MCP."
---

# Meeting Intelligence — AI Retrieval Skill

You have access to a Meeting Intelligence system via MCP tools. This system stores meetings, actions, and decisions from team discussions. Use these instructions to answer questions about meeting data effectively.

## Available Tools

**Search** (use these first):
- `search_meetings(query, limit)` — keyword search across meeting titles, summaries, and transcripts. Returns snippets.
- `search_actions(query, limit)` — keyword search across action text, owner, and notes.
- `search_decisions(query, limit)` — keyword search across decision text and context.

**List** (use for browsing or time-based queries):
- `list_meetings(limit, days_back, attendee, tag)` — recent meetings. Default: last 30 days.
- `list_actions(status, owner, meeting_id, limit)` — filter by status (Open/Complete/Parked), owner, or meeting.
- `list_decisions(meeting_id, limit)` — filter by meeting.

**Detail** (use after search/list to get full content):
- `get_meeting(meeting_id)` — full meeting including summary, transcript, attendees, date.
- `get_action(action_id)` — full action including text, owner, due date, status, notes.
- `get_decision(decision_id)` — full decision including text, context, linked meeting.

**Write** (use when asked to create or update):
- `create_meeting`, `update_meeting`, `delete_meeting`
- `create_action`, `update_action`, `complete_action`, `park_action`, `delete_action`
- `create_decision`, `delete_decision`

**Workspace** (multi-team environments):
- `list_workspaces()` — show available workspaces and your role in each.
- `get_current_workspace()` — show which workspace you're connected to.
- `switch_workspace(workspace)` — change workspace context.

**Utility:**
- `get_schema()` — field definitions, types, and examples for all entities.

## How to Answer Questions About Meeting Data

When someone asks a question like "what did we decide about pricing?" or "what's happening with the website project?", follow this pattern:

### Step 1: Search across all three entity types

Run in parallel:
- `search_meetings(query, limit=5)`
- `search_actions(query, limit=5)`
- `search_decisions(query, limit=5)`

Use the key terms from the user's question. If they imply a time range ("last week", "in January"), also run `list_meetings(days_back=N)` to catch meetings that match by date but not keyword.

### Step 2: Pull full records for relevant hits

For search results that look relevant:
- `get_meeting(id)` for full summary and transcript
- `get_action(id)` for full details
- `get_decision(id)` for full text and context

If a meeting looks relevant, also check what came out of it:
- `list_actions(meeting_id=X)`
- `list_decisions(meeting_id=X)`

### Step 3: Synthesise and present

Combine findings into a clear answer. Always:
- **Cite the source** — mention which meeting(s) the information came from (title and date).
- **Distinguish entity types** — decisions are things that were agreed, actions are things assigned to someone, meetings contain the broader discussion.
- **Flag status** — if an action is overdue or still open, say so. If a decision was later revisited, show the progression.
- **Show the thread** — if information spans multiple meetings, present it chronologically so the user sees how something evolved.

### When search returns nothing

1. Try broader or different keywords.
2. Increase `days_back` on `list_meetings` (default is 30 — the data might be older).
3. Tell the user what you searched for and that nothing matched. Don't fabricate answers.

## Common Patterns

**"What's overdue?"**
→ `list_actions(status="Open")` then check due dates against today.

**"What did we decide about X?"**
→ `search_decisions(X)` first. If empty, `search_meetings(X)` and look in summaries.

**"Summarise last week's meetings"**
→ `list_meetings(days_back=7)` then `get_meeting(id)` for each.

**"What's [person] working on?"**
→ `list_actions(owner="[person]", status="Open")`

**"What happened in [meeting name]?"**
→ `search_meetings("[meeting name]")` then `get_meeting(id)`, `list_actions(meeting_id)`, `list_decisions(meeting_id)`.

**"Any updates on [project/topic]?"**
→ Full three-way search (Step 1), then synthesise chronologically.

## Rules

- **Search first, list second.** Don't pull all meetings and scan — use the search tools.
- **Don't answer from one source when multiple exist.** If there are related actions and decisions, include them.
- **Don't guess.** If the data isn't in the system, say so.
- **Respect workspace boundaries.** You can only see data in the workspace you're connected to. If the user asks about something that might be in a different workspace, suggest switching.
- **Dates are ISO 8601.** When creating or updating, use YYYY-MM-DD format.
- **Status values are exact strings.** Open, Complete, or Parked. Nothing else.
