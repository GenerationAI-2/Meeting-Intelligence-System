"""Meeting Intelligence MCP Server - Decision Tools"""

from datetime import datetime
from typing import Optional
from ..database import get_db


def list_decisions(
    meeting_id: Optional[int] = None,
    limit: int = 50
) -> dict:
    """
    List decisions from meetings.
    
    Args:
        meeting_id: Filter by source meeting (optional)
        limit: Maximum results (default 50, max 200)
    
    Returns:
        Array of decisions with: id, text, context, meeting_id, meeting_title, created_at
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
        return {"error": True, "code": "DATABASE_ERROR", "message": str(e)}


def create_decision(
    meeting_id: int,
    decision_text: str,
    user_email: str,
    context: Optional[str] = None
) -> dict:
    """
    Record a decision.
    
    Args:
        meeting_id: The meeting where decision was made
        decision_text: The decision
        user_email: Email of user creating the record
        context: Background/reasoning (optional)
    
    Returns:
        Created decision with ID
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
        return {"error": True, "code": "DATABASE_ERROR", "message": str(e)}
