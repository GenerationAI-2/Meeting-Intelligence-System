"""Meeting Intelligence — Decision Tools

All functions receive cursor + ctx as first two params.
Caller manages connection lifecycle and retry logic via call_with_retry().
"""

import pyodbc
from datetime import datetime
from typing import Optional
from ..workspace_context import WorkspaceContext
from ..permissions import check_permission


def list_decisions(
    cursor: pyodbc.Cursor,
    ctx: WorkspaceContext,
    meeting_id: Optional[int] = None,
    limit: int = 50
) -> dict:
    """List decisions from meetings, sorted by most recent first."""
    check_permission(ctx, "read")

    if limit < 1:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "Limit must be at least 1"}
    if limit > 200:
        limit = 200

    if meeting_id is not None and (not isinstance(meeting_id, int) or meeting_id < 1):
        return {"error": True, "code": "VALIDATION_ERROR", "message": "meeting_id must be a positive integer"}

    if meeting_id:
        cursor.execute("""
            SELECT d.DecisionId, d.DecisionText, d.Context, d.MeetingId,
                   m.Title, d.CreatedAt
            FROM Decision d
            JOIN Meeting m ON d.MeetingId = m.MeetingId
            WHERE d.MeetingId = ?
            ORDER BY d.CreatedAt DESC
            OFFSET 0 ROWS FETCH NEXT ? ROWS ONLY
        """, (meeting_id, limit))
    else:
        cursor.execute("""
            SELECT d.DecisionId, d.DecisionText, d.Context, d.MeetingId,
                   m.Title, d.CreatedAt
            FROM Decision d
            JOIN Meeting m ON d.MeetingId = m.MeetingId
            ORDER BY d.CreatedAt DESC
            OFFSET 0 ROWS FETCH NEXT ? ROWS ONLY
        """, (limit,))

    rows = cursor.fetchall()
    decisions = []
    for row in rows:
        decisions.append({
            "id": row[0],
            "text": row[1],
            "context": row[2],
            "meeting_id": row[3],
            "meeting_title": row[4],
            "created_at": row[5].isoformat() if row[5] else None
        })

    return {"decisions": decisions, "count": len(decisions)}


def get_decision(
    cursor: pyodbc.Cursor,
    ctx: WorkspaceContext,
    decision_id: int
) -> dict:
    """Get full details of a specific decision."""
    check_permission(ctx, "read")

    if not isinstance(decision_id, int) or decision_id < 1:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "decision_id must be a positive integer"}

    cursor.execute("""
        SELECT d.DecisionId, d.DecisionText, d.Context, d.MeetingId,
               m.Title, d.CreatedAt, d.CreatedBy
        FROM Decision d
        JOIN Meeting m ON d.MeetingId = m.MeetingId
        WHERE d.DecisionId = ?
    """, (decision_id,))

    row = cursor.fetchone()
    if not row:
        return {"error": True, "code": "NOT_FOUND", "message": f"Decision with ID {decision_id} not found"}

    return {
        "id": row[0],
        "text": row[1],
        "context": row[2],
        "meeting_id": row[3],
        "meeting_title": row[4],
        "created_at": row[5].isoformat() if row[5] else None,
        "created_by": row[6]
    }


def search_decisions(
    cursor: pyodbc.Cursor,
    ctx: WorkspaceContext,
    query: str,
    limit: int = 10
) -> dict:
    """Search decisions by keyword in decision text or context."""
    check_permission(ctx, "read")

    if not query or len(query) < 2:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "Query must be at least 2 characters"}
    if limit < 1:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "Limit must be at least 1"}
    if limit > 50:
        limit = 50

    search_pattern = f"%{query}%"
    cursor.execute("""
        SELECT d.DecisionId, d.DecisionText, d.Context, d.MeetingId, m.Title,
               CASE
                   WHEN d.DecisionText LIKE ? THEN LEFT(d.DecisionText, 100)
                   WHEN d.Context LIKE ? THEN
                       SUBSTRING(d.Context,
                           GREATEST(CHARINDEX(?, d.Context) - 50, 1),
                           150)
                   ELSE ''
               END as Snippet
        FROM Decision d
        JOIN Meeting m ON d.MeetingId = m.MeetingId
        WHERE d.DecisionText LIKE ? OR d.Context LIKE ?
        ORDER BY d.CreatedAt DESC
        OFFSET 0 ROWS FETCH NEXT ? ROWS ONLY
    """, (search_pattern, search_pattern, query, search_pattern, search_pattern, limit))

    rows = cursor.fetchall()
    results = []
    for row in rows:
        results.append({
            "id": row[0],
            "text": row[1],
            "context": row[2],
            "meeting_id": row[3],
            "meeting_title": row[4],
            "snippet": row[5] or ""
        })

    return {"results": results, "count": len(results)}


def create_decision(
    cursor: pyodbc.Cursor,
    ctx: WorkspaceContext,
    meeting_id: int,
    decision_text: str,
    context: Optional[str] = None
) -> dict:
    """Record a decision made in a meeting."""
    check_permission(ctx, "create")

    if not isinstance(meeting_id, int) or meeting_id < 1:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "meeting_id must be a positive integer"}

    if not decision_text or len(decision_text.strip()) == 0:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "decision_text is required"}

    now = datetime.utcnow()

    # Validate meeting exists
    cursor.execute("SELECT MeetingId, Title FROM Meeting WHERE MeetingId = ?", (meeting_id,))
    meeting_row = cursor.fetchone()
    if not meeting_row:
        return {"error": True, "code": "NOT_FOUND", "message": f"Meeting with ID {meeting_id} not found"}

    cursor.execute("""
        INSERT INTO Decision (MeetingId, DecisionText, Context, CreatedAt, CreatedBy)
        OUTPUT INSERTED.DecisionId
        VALUES (?, ?, ?, ?, ?)
    """, (meeting_id, decision_text, context, now, ctx.user_email))

    row = cursor.fetchone()
    decision_id = row[0]

    return {
        "id": decision_id,
        "text": decision_text,
        "context": context,
        "meeting_id": meeting_id,
        "meeting_title": meeting_row[1],
        "message": "Decision recorded successfully"
    }


def delete_decision(
    cursor: pyodbc.Cursor,
    ctx: WorkspaceContext,
    decision_id: int
) -> dict:
    """Permanently delete a decision."""
    check_permission(ctx, "delete")

    if not isinstance(decision_id, int) or decision_id < 1:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "decision_id must be a positive integer"}

    cursor.execute("SELECT DecisionId FROM Decision WHERE DecisionId = ?", (decision_id,))
    if not cursor.fetchone():
        return {"error": True, "code": "NOT_FOUND", "message": f"Decision with ID {decision_id} not found"}

    cursor.execute("DELETE FROM Decision WHERE DecisionId = ?", (decision_id,))

    return {"success": True, "message": f"Decision {decision_id} deleted"}
