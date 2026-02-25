"""Meeting Intelligence — Action Tools

All functions receive cursor + ctx as first two params.
Caller manages connection lifecycle and retry logic via call_with_retry().
"""

import pyodbc
from datetime import datetime, date
from typing import Optional
from ..workspace_context import WorkspaceContext
from ..permissions import check_permission


def list_actions(
    cursor: pyodbc.Cursor,
    ctx: WorkspaceContext,
    status: Optional[str] = None,
    owner: Optional[str] = None,
    meeting_id: Optional[int] = None,
    limit: int = 50
) -> dict:
    """List action items with optional filters."""
    check_permission(ctx, "read")

    valid_statuses = ["Open", "Complete", "Parked"]
    if status and status not in valid_statuses:
        return {"error": True, "code": "VALIDATION_ERROR",
                "message": f"Invalid status. Must be one of: {', '.join(valid_statuses)}"}

    if limit < 1:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "Limit must be at least 1"}
    if limit > 200:
        limit = 200

    if meeting_id is not None and (not isinstance(meeting_id, int) or meeting_id < 1):
        return {"error": True, "code": "VALIDATION_ERROR", "message": "meeting_id must be a positive integer"}

    conditions = []
    params = []

    if status:
        conditions.append("Status = ?")
        params.append(status)

    if owner:
        conditions.append("Owner LIKE ?")
        params.append(f"%{owner}%")

    if meeting_id:
        conditions.append("MeetingId = ?")
        params.append(meeting_id)

    where_clause = " AND ".join(conditions) if conditions else "1=1"
    params.append(limit)

    cursor.execute(f"""
        SELECT ActionId, ActionText, Owner, DueDate, Status, MeetingId
        FROM Action
        WHERE {where_clause}
        ORDER BY
            CASE WHEN DueDate IS NULL THEN 1 ELSE 0 END,
            DueDate ASC,
            CreatedAt ASC
        OFFSET 0 ROWS FETCH NEXT ? ROWS ONLY
    """, tuple(params))

    rows = cursor.fetchall()
    actions = []
    for row in rows:
        actions.append({
            "id": row[0],
            "text": row[1],
            "owner": row[2],
            "due_date": row[3].isoformat() if row[3] else None,
            "status": row[4],
            "meeting_id": row[5]
        })

    return {"actions": actions, "count": len(actions)}


def get_distinct_owners(
    cursor: pyodbc.Cursor,
    ctx: WorkspaceContext,
) -> dict:
    """Get distinct owner values from the Action table."""
    check_permission(ctx, "read")

    cursor.execute(
        "SELECT DISTINCT Owner FROM Action WHERE Owner IS NOT NULL ORDER BY Owner"
    )
    owners = [row[0] for row in cursor.fetchall()]
    return {"owners": owners}


def get_action(
    cursor: pyodbc.Cursor,
    ctx: WorkspaceContext,
    action_id: int
) -> dict:
    """Get full details of a specific action."""
    check_permission(ctx, "read")

    if not isinstance(action_id, int) or action_id < 1:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "action_id must be a positive integer"}

    cursor.execute("""
        SELECT ActionId, ActionText, Owner, DueDate, Status, MeetingId,
               Notes, CreatedAt, CreatedBy, UpdatedAt, UpdatedBy
        FROM Action
        WHERE ActionId = ?
    """, (action_id,))

    row = cursor.fetchone()
    if not row:
        return {"error": True, "code": "NOT_FOUND", "message": f"Action with ID {action_id} not found"}

    return {
        "id": row[0],
        "text": row[1],
        "owner": row[2],
        "due_date": row[3].isoformat() if row[3] else None,
        "status": row[4],
        "meeting_id": row[5],
        "notes": row[6],
        "created_at": row[7].isoformat() if row[7] else None,
        "created_by": row[8],
        "updated_at": row[9].isoformat() if row[9] else None,
        "updated_by": row[10]
    }


def search_actions(
    cursor: pyodbc.Cursor,
    ctx: WorkspaceContext,
    query: str,
    limit: int = 10
) -> dict:
    """Search actions by keyword in action text, owner, or notes."""
    check_permission(ctx, "read")

    if not query or len(query) < 2:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "Query must be at least 2 characters"}
    if limit < 1:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "Limit must be at least 1"}
    if limit > 50:
        limit = 50

    search_pattern = f"%{query}%"
    cursor.execute("""
        SELECT ActionId, ActionText, Owner, DueDate, Status, MeetingId,
               CASE
                   WHEN ActionText LIKE ? THEN LEFT(ActionText, 100)
                   WHEN Owner LIKE ? THEN LEFT(Owner, 100)
                   WHEN Notes LIKE ? THEN
                       SUBSTRING(Notes,
                           GREATEST(CHARINDEX(?, Notes) - 50, 1),
                           150)
                   ELSE ''
               END as Snippet
        FROM Action
        WHERE ActionText LIKE ? OR Owner LIKE ? OR Notes LIKE ?
        ORDER BY CreatedAt DESC
        OFFSET 0 ROWS FETCH NEXT ? ROWS ONLY
    """, (search_pattern, search_pattern, search_pattern, query, search_pattern, search_pattern, search_pattern, limit))

    rows = cursor.fetchall()
    results = []
    for row in rows:
        results.append({
            "id": row[0],
            "text": row[1],
            "owner": row[2],
            "due_date": row[3].isoformat() if row[3] else None,
            "status": row[4],
            "meeting_id": row[5],
            "snippet": row[6] or ""
        })

    return {"results": results, "count": len(results)}


def create_action(
    cursor: pyodbc.Cursor,
    ctx: WorkspaceContext,
    action_text: str,
    owner: str,
    due_date: Optional[str] = None,
    meeting_id: Optional[int] = None,
    notes: Optional[str] = None
) -> dict:
    """Create a new action item. Status defaults to 'Open'."""
    check_permission(ctx, "create")

    if not action_text or len(action_text.strip()) == 0:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "action_text is required"}
    if not owner or len(owner.strip()) == 0:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "owner is required"}

    parsed_due_date = None
    if due_date:
        try:
            parsed_due_date = datetime.fromisoformat(due_date.replace('Z', '+00:00')).date()
        except ValueError:
            return {"error": True, "code": "VALIDATION_ERROR", "message": "Invalid due_date format. Use ISO format."}

    now = datetime.utcnow()

    # Validate meeting_id if provided
    if meeting_id:
        cursor.execute("SELECT MeetingId FROM Meeting WHERE MeetingId = ?", (meeting_id,))
        if not cursor.fetchone():
            return {"error": True, "code": "NOT_FOUND", "message": f"Meeting with ID {meeting_id} not found"}

    cursor.execute("""
        INSERT INTO Action (ActionText, Owner, DueDate, Status, MeetingId,
                            Notes, CreatedAt, CreatedBy, UpdatedAt, UpdatedBy)
        OUTPUT INSERTED.ActionId
        VALUES (?, ?, ?, 'Open', ?, ?, ?, ?, ?, ?)
    """, (action_text, owner, parsed_due_date, meeting_id,
          notes, now, ctx.user_email, now, ctx.user_email))

    row = cursor.fetchone()
    action_id = row[0]

    return {
        "id": action_id,
        "text": action_text,
        "owner": owner,
        "due_date": parsed_due_date.isoformat() if parsed_due_date else None,
        "status": "Open",
        "message": "Action created successfully"
    }


def update_action(
    cursor: pyodbc.Cursor,
    ctx: WorkspaceContext,
    action_id: int,
    action_text: Optional[str] = None,
    owner: Optional[str] = None,
    due_date: Optional[str] = None,
    notes: Optional[str] = None
) -> dict:
    """Update an existing action. Only provided fields are updated."""
    if not isinstance(action_id, int) or action_id < 1:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "action_id must be a positive integer"}

    # Fetch for existence + ownership check
    cursor.execute("SELECT ActionId, CreatedBy FROM Action WHERE ActionId = ?", (action_id,))
    row = cursor.fetchone()
    if not row:
        return {"error": True, "code": "NOT_FOUND", "message": f"Action with ID {action_id} not found"}

    check_permission(ctx, "update", {"created_by": row[1]})

    # Build dynamic update
    updates = []
    params = []

    if action_text is not None:
        if len(action_text.strip()) == 0:
            return {"error": True, "code": "VALIDATION_ERROR", "message": "action_text cannot be empty"}
        updates.append("ActionText = ?")
        params.append(action_text)

    if owner is not None:
        if len(owner.strip()) == 0:
            return {"error": True, "code": "VALIDATION_ERROR", "message": "owner cannot be empty"}
        updates.append("Owner = ?")
        params.append(owner)

    if due_date is not None:
        try:
            parsed_date = datetime.fromisoformat(due_date.replace('Z', '+00:00')).date()
            updates.append("DueDate = ?")
            params.append(parsed_date)
        except ValueError:
            return {"error": True, "code": "VALIDATION_ERROR", "message": "Invalid due_date format"}

    if notes is not None:
        updates.append("Notes = ?")
        params.append(notes)

    if not updates:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "No fields to update"}

    updates.append("UpdatedAt = ?")
    params.append(datetime.utcnow())
    updates.append("UpdatedBy = ?")
    params.append(ctx.user_email)

    params.append(action_id)

    cursor.execute(f"""
        UPDATE Action
        SET {', '.join(updates)}
        WHERE ActionId = ?
    """, tuple(params))

    # Return updated action using same cursor
    return get_action(cursor, ctx, action_id)


def complete_action(
    cursor: pyodbc.Cursor,
    ctx: WorkspaceContext,
    action_id: int
) -> dict:
    """Mark an action as complete."""
    if not isinstance(action_id, int) or action_id < 1:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "action_id must be a positive integer"}

    # Fetch for existence + ownership check
    cursor.execute("SELECT ActionId, CreatedBy FROM Action WHERE ActionId = ?", (action_id,))
    row = cursor.fetchone()
    if not row:
        return {"error": True, "code": "NOT_FOUND", "message": f"Action with ID {action_id} not found"}

    check_permission(ctx, "update", {"created_by": row[1]})

    cursor.execute("""
        UPDATE Action
        SET Status = 'Complete', UpdatedAt = ?, UpdatedBy = ?
        WHERE ActionId = ?
    """, (datetime.utcnow(), ctx.user_email, action_id))

    return get_action(cursor, ctx, action_id)


def park_action(
    cursor: pyodbc.Cursor,
    ctx: WorkspaceContext,
    action_id: int
) -> dict:
    """Park an action (put on hold)."""
    if not isinstance(action_id, int) or action_id < 1:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "action_id must be a positive integer"}

    # Fetch for existence + ownership check
    cursor.execute("SELECT ActionId, CreatedBy FROM Action WHERE ActionId = ?", (action_id,))
    row = cursor.fetchone()
    if not row:
        return {"error": True, "code": "NOT_FOUND", "message": f"Action with ID {action_id} not found"}

    check_permission(ctx, "update", {"created_by": row[1]})

    cursor.execute("""
        UPDATE Action
        SET Status = 'Parked', UpdatedAt = ?, UpdatedBy = ?
        WHERE ActionId = ?
    """, (datetime.utcnow(), ctx.user_email, action_id))

    return get_action(cursor, ctx, action_id)


def reopen_action(
    cursor: pyodbc.Cursor,
    ctx: WorkspaceContext,
    action_id: int
) -> dict:
    """Set action status back to Open."""
    if not isinstance(action_id, int) or action_id < 1:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "action_id must be a positive integer"}

    # Fetch for existence + ownership check
    cursor.execute("SELECT ActionId, CreatedBy FROM Action WHERE ActionId = ?", (action_id,))
    row = cursor.fetchone()
    if not row:
        return {"error": True, "code": "NOT_FOUND", "message": f"Action with ID {action_id} not found"}

    check_permission(ctx, "update", {"created_by": row[1]})

    cursor.execute("""
        UPDATE Action SET Status = 'Open', UpdatedAt = ?, UpdatedBy = ?
        WHERE ActionId = ?
    """, (datetime.utcnow(), ctx.user_email, action_id))

    return get_action(cursor, ctx, action_id)


def delete_action(
    cursor: pyodbc.Cursor,
    ctx: WorkspaceContext,
    action_id: int
) -> dict:
    """Permanently delete an action."""
    check_permission(ctx, "delete")

    if not isinstance(action_id, int) or action_id < 1:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "action_id must be a positive integer"}

    cursor.execute("SELECT ActionId FROM Action WHERE ActionId = ?", (action_id,))
    if not cursor.fetchone():
        return {"error": True, "code": "NOT_FOUND", "message": f"Action with ID {action_id} not found"}

    cursor.execute("DELETE FROM Action WHERE ActionId = ?", (action_id,))

    return {"message": f"Action {action_id} deleted successfully", "deleted": True}
