"""Meeting Intelligence MCP Server - Fireflies Integration"""

from datetime import datetime
from typing import Optional
import httpx
from ..database import get_db
from ..config import get_settings


FIREFLIES_GRAPHQL_URL = "https://api.fireflies.ai/graphql"


async def _fireflies_request(query: str, variables: dict = None) -> dict:
    """Make a request to the Fireflies GraphQL API."""
    settings = get_settings()
    
    if not settings.fireflies_api_key:
        return {"error": True, "code": "CONFIGURATION_ERROR", 
                "message": "Fireflies API key not configured"}
    
    headers = {
        "Authorization": f"Bearer {settings.fireflies_api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                FIREFLIES_GRAPHQL_URL,
                json=payload,
                headers=headers,
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {"error": True, "code": "EXTERNAL_API_ERROR", 
                    "message": f"Fireflies API error: {e.response.status_code}"}
        except httpx.RequestError as e:
            return {"error": True, "code": "EXTERNAL_API_ERROR", 
                    "message": f"Failed to connect to Fireflies: {str(e)}"}


async def search_fireflies_transcripts(query: str) -> dict:
    """
    Search for transcripts in Fireflies.ai.
    
    Args:
        query: Search keyword
    
    Returns:
        Array of Fireflies transcripts with: id, title, date, duration, participants
    """
    if not query or len(query.strip()) == 0:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "Query is required"}
    
    graphql_query = """
    query Transcripts($query: String) {
        transcripts(title: $query) {
            id
            title
            date
            duration
            participants
        }
    }
    """
    
    result = await _fireflies_request(graphql_query, {"query": query})
    
    if "error" in result:
        return result
    
    if "errors" in result:
        return {"error": True, "code": "EXTERNAL_API_ERROR", 
                "message": result["errors"][0].get("message", "Unknown Fireflies error")}
    
    transcripts = result.get("data", {}).get("transcripts", [])
    
    formatted = []
    for t in transcripts:
        formatted.append({
            "id": t.get("id"),
            "title": t.get("title"),
            "date": t.get("date"),
            "duration": t.get("duration", 0),
            "participants": t.get("participants", [])
        })
    
    return {"transcripts": formatted, "count": len(formatted)}


async def import_fireflies_transcript(transcript_id: str, user_email: str) -> dict:
    """
    Import a transcript from Fireflies into the database.
    
    Args:
        transcript_id: Fireflies transcript ID
        user_email: Email of user importing the transcript
    
    Returns:
        Created meeting record with full transcript
    """
    if not transcript_id or len(transcript_id.strip()) == 0:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "transcript_id is required"}
    
    # Check for duplicate
    try:
        with get_db() as cursor:
            cursor.execute("""
                SELECT MeetingId, Title, MeetingDate
                FROM Meeting
                WHERE Source = 'Fireflies' AND SourceMeetingId = ?
            """, (transcript_id,))
            
            existing = cursor.fetchone()
            if existing:
                return {
                    "id": existing[0],
                    "title": existing[1],
                    "date": existing[2].isoformat() if existing[2] else None,
                    "already_imported": True,
                    "message": "Transcript was already imported"
                }
    except Exception as e:
        return {"error": True, "code": "DATABASE_ERROR", "message": str(e)}
    
    # Fetch full transcript from Fireflies
    graphql_query = """
    query Transcript($id: String!) {
        transcript(id: $id) {
            id
            title
            date
            duration
            participants
            sentences {
                speaker_name
                text
            }
            summary {
                overview
            }
        }
    }
    """
    
    result = await _fireflies_request(graphql_query, {"id": transcript_id})
    
    if "error" in result:
        return result
    
    if "errors" in result:
        return {"error": True, "code": "EXTERNAL_API_ERROR", 
                "message": result["errors"][0].get("message", "Unknown Fireflies error")}
    
    transcript_data = result.get("data", {}).get("transcript")
    
    if not transcript_data:
        return {"error": True, "code": "NOT_FOUND", 
                "message": f"Fireflies transcript {transcript_id} not found"}
    
    # Build raw transcript from sentences
    sentences = transcript_data.get("sentences", [])
    raw_transcript = "\n".join([
        f"{s.get('speaker_name', 'Unknown')}: {s.get('text', '')}"
        for s in sentences
    ])
    
    # Get summary
    summary = None
    summary_data = transcript_data.get("summary")
    if summary_data:
        summary = summary_data.get("overview")
    
    # Parse date
    meeting_date = datetime.utcnow()
    if transcript_data.get("date"):
        try:
            meeting_date = datetime.fromisoformat(transcript_data["date"].replace('Z', '+00:00'))
        except ValueError:
            pass
    
    # Create meeting record
    now = datetime.utcnow()
    participants = transcript_data.get("participants", [])
    attendees = ", ".join(participants) if participants else None
    
    try:
        with get_db() as cursor:
            cursor.execute("""
                INSERT INTO Meeting (Title, MeetingDate, RawTranscript, Summary,
                                     Attendees, Source, SourceMeetingId,
                                     CreatedAt, CreatedBy, UpdatedAt, UpdatedBy)
                OUTPUT INSERTED.MeetingId
                VALUES (?, ?, ?, ?, ?, 'Fireflies', ?, ?, ?, ?, ?)
            """, (
                transcript_data.get("title", "Untitled Meeting"),
                meeting_date,
                raw_transcript,
                summary,
                attendees,
                transcript_id,
                now,
                user_email,
                now,
                user_email
            ))
            
            row = cursor.fetchone()
            meeting_id = row[0]
            
            return {
                "id": meeting_id,
                "title": transcript_data.get("title", "Untitled Meeting"),
                "date": meeting_date.isoformat(),
                "attendees": attendees,
                "source": "Fireflies",
                "transcript_length": len(raw_transcript),
                "message": "Transcript imported successfully"
            }
    except Exception as e:
        return {"error": True, "code": "DATABASE_ERROR", "message": str(e)}
