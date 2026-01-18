"""Meeting Intelligence MCP Server - Pydantic Schemas"""

from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, Field


# Error Response
class ErrorResponse(BaseModel):
    error: bool = True
    code: str
    message: str


# Meeting Schemas
class MeetingBase(BaseModel):
    title: str
    meeting_date: datetime
    attendees: Optional[str] = None
    summary: Optional[str] = None
    transcript: Optional[str] = None
    source: str = "Manual"
    source_meeting_id: Optional[str] = None


class MeetingCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    meeting_date: str = Field(..., description="ISO date format")
    attendees: Optional[str] = None
    summary: Optional[str] = None
    transcript: Optional[str] = None
    source: str = "Manual"
    source_meeting_id: Optional[str] = None


class MeetingUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    summary: Optional[str] = None
    attendees: Optional[str] = None


class MeetingListItem(BaseModel):
    id: int
    title: str
    date: datetime
    attendees: Optional[str]
    source: str


class MeetingDetail(BaseModel):
    id: int
    title: str
    date: datetime
    attendees: Optional[str]
    summary: Optional[str]
    transcript: Optional[str]
    source: str
    source_meeting_id: Optional[str]
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str


class MeetingSearchResult(BaseModel):
    id: int
    title: str
    date: datetime
    snippet: str


# Action Schemas
class ActionCreate(BaseModel):
    action_text: str = Field(..., min_length=1)
    owner: str = Field(..., min_length=1, max_length=128)
    due_date: Optional[str] = None
    meeting_id: Optional[int] = None
    notes: Optional[str] = None


class ActionUpdate(BaseModel):
    action_text: Optional[str] = Field(None, min_length=1)
    owner: Optional[str] = Field(None, min_length=1, max_length=128)
    due_date: Optional[str] = None
    notes: Optional[str] = None


class ActionListItem(BaseModel):
    id: int
    text: str
    owner: str
    due_date: Optional[date]
    status: str
    meeting_id: Optional[int]


class ActionDetail(BaseModel):
    id: int
    text: str
    owner: str
    due_date: Optional[date]
    status: str
    meeting_id: Optional[int]
    notes: Optional[str]
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str


# Decision Schemas
class DecisionCreate(BaseModel):
    meeting_id: int
    decision_text: str = Field(..., min_length=1)
    context: Optional[str] = None


class DecisionListItem(BaseModel):
    id: int
    text: str
    context: Optional[str]
    meeting_id: int
    meeting_title: str
    created_at: datetime


# Fireflies Schemas
class FirefliesTranscript(BaseModel):
    id: str
    title: str
    date: datetime
    duration: int
    participants: list[str]
