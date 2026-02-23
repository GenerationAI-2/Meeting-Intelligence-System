"""Meeting Intelligence MCP Server - Decision Tools"""

from datetime import datetime
from typing import Optional
from ..database import get_db, is_transient_error, retry_on_transient


@retry_on_transient()
def list_decisions(
    meeting_id: Optional[int] = None,
    limit: int = 50
) -> dict:
    """
    List decisions from meetings, sorted by most recent first.

    Args:
        meeting_id: Optional. Filter by source meeting ID.
        limit: Maximum results to return. Default 50, max 200.

    Returns:
        {
            "decisions": [...],  # Array of decision objects
            "count": int         # Number of results returned
        }

        Each decision contains: id, text, context, meeting_id, meeting_title, created_at.
    """
    if limit < 1:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "Limit must be at least 1"}
    if limit > 200:
        limit = 200
    
    if meeting_id is not None and (not isinstance(meeting_id, int) or meeting_id < 1):
        return {"error": True, "code": "VALIDATION_ERROR", "message": "meeting_id must be a positive integer"}
    
    try:
        with get_db() as cursor:
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
    except Exception as e:
        if is_transient_error(e):
            raise
        return {"error": True, "code": "DATABASE_ERROR", "message": str(e)}


@retry_on_transient()
def get_decision(decision_id: int) -> dict:
    """
    Get full details of a specific decision.

    Args:
        decision_id: Required. The decision ID (positive integer).

    Returns:
        Full decision record with fields:
        - id: Decision ID
        - text: The decision text
        - context: Background/reasoning or null
        - meeting_id: Source meeting ID
        - meeting_title: Title of source meeting
        - created_at: ISO timestamp
        - created_by: Email of creator
    """
    if not isinstance(decision_id, int) or decision_id < 1:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "decision_id must be a positive integer"}

    try:
        with get_db() as cursor:
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
    except Exception as e:
        if is_transient_error(e):
            raise
        return {"error": True, "code": "DATABASE_ERROR", "message": str(e)}


@retry_on_transient()
def search_decisions(query: str, limit: int = 10) -> dict:
    """
    Search decisions by keyword in decision text or context.

    Args:
        query: Required. Search terms. Min 2 characters.
               Searches in decision text and context fields.
        limit: Maximum results to return. Default 10, max 50.

    Returns:
        {
            "results": [...],  # Array of matching decisions
            "count": int       # Number of results returned
        }

        Each result contains: id, text, context, meeting_id, meeting_title, snippet (context around match).
    """
    if not query or len(query) < 2:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "Query must be at least 2 characters"}
    if limit < 1:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "Limit must be at least 1"}
    if limit > 50:
        limit = 50

    try:
        with get_db() as cursor:
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
    except Exception as e:
        if is_transient_error(e):
            raise
        return {"error": True, "code": "DATABASE_ERROR", "message": str(e)}


@retry_on_transient()
def create_decision(
    meeting_id: int,
    decision_text: str,
    user_email: str,
    context: Optional[str] = None
) -> dict:
    """
    Record a decision made in a meeting.

    Args:
        meeting_id: Required. The meeting where decision was made.
                    Must be a valid meeting ID from list_meetings.
        decision_text: Required. The decision. Plain text, no limit.
        user_email: Required. Email of user creating (auto-set by system).
        context: Optional. Background/reasoning for the decision.
                 Plain text, no limit.

    Returns:
        Created decision with: id, text, context, meeting_id, meeting_title, message.
    """
    if not isinstance(meeting_id, int) or meeting_id < 1:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "meeting_id must be a positive integer"}
    
    if not decision_text or len(decision_text.strip()) == 0:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "decision_text is required"}
    
    now = datetime.utcnow()
    
    try:
        with get_db() as cursor:
            # Validate meeting exists
            cursor.execute("SELECT MeetingId, Title FROM Meeting WHERE MeetingId = ?", (meeting_id,))
            meeting_row = cursor.fetchone()
            if not meeting_row:
                return {"error": True, "code": "NOT_FOUND", "message": f"Meeting with ID {meeting_id} not found"}
            
            cursor.execute("""
                INSERT INTO Decision (MeetingId, DecisionText, Context, CreatedAt, CreatedBy)
                OUTPUT INSERTED.DecisionId
                VALUES (?, ?, ?, ?, ?)
            """, (meeting_id, decision_text, context, now, user_email))
            
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
    except Exception as e:
        if is_transient_error(e):
            raise
        return {"error": True, "code": "DATABASE_ERROR", "message": str(e)}


@retry_on_transient()
def delete_decision(decision_id: int) -> dict:
    """
    Permanently delete a decision.

    Args:
        decision_id: Required. The decision ID (positive integer).

    Returns:
        {"success": True, "message": "Decision deleted"} on success.

    Warning: This cannot be undone.
    """
    if not isinstance(decision_id, int) or decision_id < 1:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "decision_id must be a positive integer"}

    try:
        with get_db() as cursor:
            # Check exists
            cursor.execute("SELECT DecisionId FROM Decision WHERE DecisionId = ?", (decision_id,))
            if not cursor.fetchone():
                return {"error": True, "code": "NOT_FOUND", "message": f"Decision with ID {decision_id} not found"}

            cursor.execute("DELETE FROM Decision WHERE DecisionId = ?", (decision_id,))

            return {"success": True, "message": f"Decision {decision_id} deleted"}
    except Exception as e:
        if is_transient_error(e):
            raise
        return {"error": True, "code": "DATABASE_ERROR", "message": str(e)}
