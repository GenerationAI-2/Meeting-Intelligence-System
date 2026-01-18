"""Meeting Intelligence MCP Server - Meeting Tools"""

from datetime import datetime
from typing import Optional
from ..database import get_db, row_to_dict, rows_to_list


def list_meetings(limit: int = 20, days_back: int = 30) -> dict:
    """
    List recent meetings.
    
    Args:
        limit: Maximum results (default 20, max 100)
        days_back: How far back to search (default 30)
    
    Returns:
        Array of meetings with: id, title, date, attendees, source
    """
    # Validate inputs
    if limit < 1:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "Limit must be at least 1"}
    if limit > 100:
        limit = 100
    if days_back < 1:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "days_back must be at least 1"}
    
    try:
        with get_db() as cursor:
            cursor.execute("""
                SELECT MeetingId, Title, MeetingDate, Attendees, Source
                FROM Meeting
                WHERE MeetingDate >= DATEADD(day, -?, GETUTCDATE())
                ORDER BY MeetingDate DESC
                OFFSET 0 ROWS FETCH NEXT ? ROWS ONLY
            """, (days_back, limit))
            
            rows = cursor.fetchall()
            meetings = []
            for row in rows:
                meetings.append({
                    "id": row[0],
                    "title": row[1],
                    "date": row[2].isoformat() if row[2] else None,
                    "attendees": row[3],
                    "source": row[4]
                })
            
            return {"meetings": meetings, "count": len(meetings)}
    except Exception as e:
        return {"error": True, "code": "DATABASE_ERROR", "message": str(e)}


def get_meeting(meeting_id: int) -> dict:
    """
    Get full details of a specific meeting.
    
    Args:
        meeting_id: The meeting ID
    
    Returns:
        Full meeting record including summary and transcript
    """
    if not isinstance(meeting_id, int) or meeting_id < 1:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "meeting_id must be a positive integer"}
    
    try:
        with get_db() as cursor:
            cursor.execute("""
                SELECT MeetingId, Title, MeetingDate, RawTranscript, Summary,
                       Attendees, Source, SourceMeetingId, CreatedAt, CreatedBy,
                       UpdatedAt, UpdatedBy
                FROM Meeting
                WHERE MeetingId = ?
            """, (meeting_id,))
            
            row = cursor.fetchone()
            if not row:
                return {"error": True, "code": "NOT_FOUND", "message": f"Meeting with ID {meeting_id} not found"}
            
            return {
                "id": row[0],
                "title": row[1],
                "date": row[2].isoformat() if row[2] else None,
                "transcript": row[3],
                "summary": row[4],
                "attendees": row[5],
                "source": row[6],
                "source_meeting_id": row[7],
                "created_at": row[8].isoformat() if row[8] else None,
                "created_by": row[9],
                "updated_at": row[10].isoformat() if row[10] else None,
                "updated_by": row[11]
            }
    except Exception as e:
        return {"error": True, "code": "DATABASE_ERROR", "message": str(e)}


def search_meetings(query: str, limit: int = 10) -> dict:
    """
    Search meetings by keyword.
    
    Args:
        query: Search terms (min 2 chars)
        limit: Maximum results (default 10, max 50)
    
    Returns:
        Array of matching meetings with snippet showing match context
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
                SELECT MeetingId, Title, MeetingDate,
                       CASE 
                           WHEN Title LIKE ? THEN LEFT(Title, 100)
                           WHEN RawTranscript LIKE ? THEN 
                               SUBSTRING(RawTranscript, 
                                   GREATEST(CHARINDEX(?, RawTranscript) - 50, 1),
                                   150)
                           ELSE ''
                       END as Snippet
                FROM Meeting
                WHERE Title LIKE ? OR RawTranscript LIKE ?
                ORDER BY MeetingDate DESC
                OFFSET 0 ROWS FETCH NEXT ? ROWS ONLY
            """, (search_pattern, search_pattern, query, search_pattern, search_pattern, limit))
            
            rows = cursor.fetchall()
            results = []
            for row in rows:
                results.append({
                    "id": row[0],
                    "title": row[1],
                    "date": row[2].isoformat() if row[2] else None,
                    "snippet": row[3] or ""
                })
            
            return {"results": results, "count": len(results)}
    except Exception as e:
        return {"error": True, "code": "DATABASE_ERROR", "message": str(e)}


def create_meeting(
    title: str,
    meeting_date: str,
    user_email: str,
    attendees: Optional[str] = None,
    summary: Optional[str] = None,
    transcript: Optional[str] = None,
    source: str = "Manual",
    source_meeting_id: Optional[str] = None
) -> dict:
    """
    Create a new meeting record.
    
    Args:
        title: Meeting title
        meeting_date: ISO date format
        user_email: Email of user creating the record
        attendees: Comma-separated names (optional)
        summary: Meeting summary (optional)
        transcript: Raw transcript (optional)
        source: Source system (default "Manual")
        source_meeting_id: External ID (optional)
    
    Returns:
        Created meeting with ID
    """
    if not title or len(title.strip()) == 0:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "Title is required"}
    if not meeting_date:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "Meeting date is required"}
    
    try:
        parsed_date = datetime.fromisoformat(meeting_date.replace('Z', '+00:00'))
    except ValueError:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "Invalid date format. Use ISO format."}
    
    now = datetime.utcnow()
    
    try:
        with get_db() as cursor:
            cursor.execute("""
                INSERT INTO Meeting (Title, MeetingDate, RawTranscript, Summary, 
                                     Attendees, Source, SourceMeetingId,
                                     CreatedAt, CreatedBy, UpdatedAt, UpdatedBy)
                OUTPUT INSERTED.MeetingId
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (title, parsed_date, transcript, summary, attendees, 
                  source, source_meeting_id, now, user_email, now, user_email))
            
            row = cursor.fetchone()
            meeting_id = row[0]
            
            return {
                "id": meeting_id,
                "title": title,
                "date": parsed_date.isoformat(),
                "source": source,
                "message": "Meeting created successfully"
            }
    except Exception as e:
        return {"error": True, "code": "DATABASE_ERROR", "message": str(e)}


def update_meeting(
    meeting_id: int,
    user_email: str,
    title: Optional[str] = None,
    summary: Optional[str] = None,
    attendees: Optional[str] = None
) -> dict:
    """
    Update an existing meeting.
    
    Args:
        meeting_id: The meeting ID
        user_email: Email of user updating the record
        title: New title (optional)
        summary: New/updated summary (optional)
        attendees: Updated attendees (optional)
    
    Returns:
        Updated meeting record
    """
    if not isinstance(meeting_id, int) or meeting_id < 1:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "meeting_id must be a positive integer"}
    
    # Build dynamic update
    updates = []
    params = []
    
    if title is not None:
        if len(title.strip()) == 0:
            return {"error": True, "code": "VALIDATION_ERROR", "message": "Title cannot be empty"}
        updates.append("Title = ?")
        params.append(title)
    
    if summary is not None:
        updates.append("Summary = ?")
        params.append(summary)
    
    if attendees is not None:
        updates.append("Attendees = ?")
        params.append(attendees)
    
    if not updates:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "No fields to update"}
    
    updates.append("UpdatedAt = ?")
    params.append(datetime.utcnow())
    updates.append("UpdatedBy = ?")
    params.append(user_email)
    
    params.append(meeting_id)
    
    try:
        with get_db() as cursor:
            # Check exists
            cursor.execute("SELECT MeetingId FROM Meeting WHERE MeetingId = ?", (meeting_id,))
            if not cursor.fetchone():
                return {"error": True, "code": "NOT_FOUND", "message": f"Meeting with ID {meeting_id} not found"}
            
            # Update
            cursor.execute(f"""
                UPDATE Meeting
                SET {', '.join(updates)}
                WHERE MeetingId = ?
            """, tuple(params))
            
        # Return updated meeting (new transaction)
        return get_meeting(meeting_id)
    except Exception as e:
        return {"error": True, "code": "DATABASE_ERROR", "message": str(e)}
