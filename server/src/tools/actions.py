"""Meeting Intelligence MCP Server - Action Tools"""

from datetime import datetime, date
from typing import Optional
from ..database import get_db


def list_actions(
    status: Optional[str] = None,
    owner: Optional[str] = None,
    meeting_id: Optional[int] = None,
    limit: int = 50
) -> dict:
    """
    List action items.
    
    Args:
        status: Filter by "Open", "Complete", "Parked" (default: Open only)
        owner: Filter by owner name
        meeting_id: Filter by source meeting
        limit: Maximum results (default 50, max 200)
    
    Returns:
        Array of actions with: id, text, owner, due_date, status, meeting_id
    """
    # Validate inputs
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
    
    # Build query
    conditions = []
    params = []
    
    # Default to Open if no status specified
    if status:
        conditions.append("Status = ?")
        params.append(status)
    else:
        conditions.append("Status = ?")
        params.append("Open")
    
    if owner:
        conditions.append("Owner LIKE ?")
        params.append(f"%{owner}%")
    
    if meeting_id:
        conditions.append("MeetingId = ?")
        params.append(meeting_id)
    
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    params.append(limit)
    
    try:
        with get_db() as cursor:
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
    except Exception as e:
        return {"error": True, "code": "DATABASE_ERROR", "message": str(e)}


def get_action(action_id: int) -> dict:
    """
    Get full details of a specific action.
    
    Args:
        action_id: The action ID
    
    Returns:
        Full action record including notes and timestamps
    """
    if not isinstance(action_id, int) or action_id < 1:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "action_id must be a positive integer"}
    
    try:
        with get_db() as cursor:
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
    except Exception as e:
        return {"error": True, "code": "DATABASE_ERROR", "message": str(e)}


def create_action(
    action_text: str,
    owner: str,
    user_email: str,
    due_date: Optional[str] = None,
    meeting_id: Optional[int] = None,
    notes: Optional[str] = None
) -> dict:
    """
    Create a new action item.
    
    Args:
        action_text: What needs to be done
        owner: Person responsible
        user_email: Email of user creating the record
        due_date: ISO date format (optional)
        meeting_id: Link to source meeting (optional)
        notes: Additional context (optional)
    
    Returns:
        Created action with ID
    """
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
    
    try:
        with get_db() as cursor:
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
                  notes, now, user_email, now, user_email))
            
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
    except Exception as e:
        return {"error": True, "code": "DATABASE_ERROR", "message": str(e)}


def update_action(
    action_id: int,
    user_email: str,
    action_text: Optional[str] = None,
    owner: Optional[str] = None,
    due_date: Optional[str] = None,
    notes: Optional[str] = None
) -> dict:
    """
    Update an existing action.
    
    Args:
        action_id: The action ID
        user_email: Email of user updating the record
        action_text: Updated description (optional)
        owner: New owner (optional)
        due_date: New due date (optional)
        notes: Updated notes (optional)
    
    Returns:
        Updated action record
    """
    if not isinstance(action_id, int) or action_id < 1:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "action_id must be a positive integer"}
    
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
    params.append(user_email)
    
    params.append(action_id)
    
    try:
        with get_db() as cursor:
            # Check exists
            cursor.execute("SELECT ActionId FROM Action WHERE ActionId = ?", (action_id,))
            if not cursor.fetchone():
                return {"error": True, "code": "NOT_FOUND", "message": f"Action with ID {action_id} not found"}
            
            # Update
            cursor.execute(f"""
                UPDATE Action
                SET {', '.join(updates)}
                WHERE ActionId = ?
            """, tuple(params))
            
        # Return updated action (new transaction)
        return get_action(action_id)
    except Exception as e:
        return {"error": True, "code": "DATABASE_ERROR", "message": str(e)}


def complete_action(action_id: int, user_email: str) -> dict:
    """
    Mark an action as complete.
    
    Args:
        action_id: The action ID
        user_email: Email of user completing the action
    
    Returns:
        Updated action with Status = "Complete"
    """
    if not isinstance(action_id, int) or action_id < 1:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "action_id must be a positive integer"}
    
    try:
        with get_db() as cursor:
            # Check exists
            cursor.execute("SELECT ActionId FROM Action WHERE ActionId = ?", (action_id,))
            if not cursor.fetchone():
                return {"error": True, "code": "NOT_FOUND", "message": f"Action with ID {action_id} not found"}
            
            cursor.execute("""
                UPDATE Action
                SET Status = 'Complete', UpdatedAt = ?, UpdatedBy = ?
                WHERE ActionId = ?
            """, (datetime.utcnow(), user_email, action_id))
            
        return get_action(action_id)
    except Exception as e:
        return {"error": True, "code": "DATABASE_ERROR", "message": str(e)}


def park_action(action_id: int, user_email: str) -> dict:
    """
    Park an action (put on hold).
    
    Args:
        action_id: The action ID
        user_email: Email of user parking the action
    
    Returns:
        Updated action with Status = "Parked"
    """
    if not isinstance(action_id, int) or action_id < 1:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "action_id must be a positive integer"}
    
    try:
        with get_db() as cursor:
            # Check exists
            cursor.execute("SELECT ActionId FROM Action WHERE ActionId = ?", (action_id,))
            if not cursor.fetchone():
                return {"error": True, "code": "NOT_FOUND", "message": f"Action with ID {action_id} not found"}
            
            cursor.execute("""
                UPDATE Action
                SET Status = 'Parked', UpdatedAt = ?, UpdatedBy = ?
                WHERE ActionId = ?
            """, (datetime.utcnow(), user_email, action_id))
            
        return get_action(action_id)
    except Exception as e:
        return {"error": True, "code": "DATABASE_ERROR", "message": str(e)}


def delete_action(action_id: int) -> dict:
    """
    Permanently delete an action.
    
    Args:
        action_id: The action ID
    
    Returns:
        Confirmation message
    """
    if not isinstance(action_id, int) or action_id < 1:
        return {"error": True, "code": "VALIDATION_ERROR", "message": "action_id must be a positive integer"}
    
    try:
        with get_db() as cursor:
            # Check exists
            cursor.execute("SELECT ActionId FROM Action WHERE ActionId = ?", (action_id,))
            if not cursor.fetchone():
                return {"error": True, "code": "NOT_FOUND", "message": f"Action with ID {action_id} not found"}
            
            cursor.execute("DELETE FROM Action WHERE ActionId = ?", (action_id,))
            
            return {"message": f"Action {action_id} deleted successfully", "deleted": True}
    except Exception as e:
        return {"error": True, "code": "DATABASE_ERROR", "message": str(e)}
