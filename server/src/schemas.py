"""Input validation schemas for Meeting Intelligence API and MCP tools."""

from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import date, datetime
import re


# === Shared Validators ===

EMAIL_PATTERN = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
HTML_TAG_PATTERN = re.compile(r'</?[a-zA-Z][^>]*>')


def strip_html_tags(text: str) -> str:
    """Strip HTML tags from text to prevent stored XSS.

    Matches actual HTML tags (e.g. <script>, <img onerror=...>) but preserves
    legitimate angle bracket usage (e.g. "meeting < 30 mins", "a < b > c").
    """
    if not text:
        return text
    return HTML_TAG_PATTERN.sub('', text)


def validate_email_format(email: str) -> str:
    """Validate and normalise email address."""
    email = email.strip().lower()
    if not EMAIL_PATTERN.match(email):
        raise ValueError(f'Invalid email format: {email}')
    return email


def validate_iso_date(date_str: str) -> str:
    """Validate ISO 8601 date or datetime string."""
    try:
        datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        raise ValueError('Invalid date format. Use ISO 8601 (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)')
    return date_str


def validate_comma_emails(value: str) -> str:
    """Validate comma-separated email list."""
    if not value:
        return value
    emails = [e.strip() for e in value.split(',') if e.strip()]
    for email in emails:
        if not EMAIL_PATTERN.match(email):
            raise ValueError(f'Invalid email in list: {email}')
    return ','.join(emails)


# === Meeting Schemas ===

class MeetingCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255,
                       description="Meeting title")
    meeting_date: str = Field(...,
                              description="Meeting date (ISO 8601: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)")
    summary: Optional[str] = Field(None, max_length=50000,
                                   description="Meeting summary (markdown)")
    transcript: Optional[str] = Field(None, max_length=500000,
                                      description="Raw transcript (max 500KB)")
    attendees: Optional[str] = Field(None, max_length=5000,
                                     description="Comma-separated email addresses")
    source: Optional[str] = Field("Manual", max_length=50,
                                  description="Source system")
    source_meeting_id: Optional[str] = Field(None, max_length=255,
                                             description="External system ID")
    tags: Optional[str] = Field(None, max_length=1000,
                                description="Comma-separated lowercase tags")

    @field_validator('title', 'summary', 'transcript')
    @classmethod
    def sanitise_text(cls, v):
        return strip_html_tags(v) if v else v

    @field_validator('meeting_date')
    @classmethod
    def check_meeting_date(cls, v):
        return validate_iso_date(v)

    @field_validator('tags')
    @classmethod
    def normalise_tags(cls, v):
        if v:
            return v.lower().strip()
        return v

    @field_validator('attendees')
    @classmethod
    def check_attendees(cls, v):
        if v:
            return validate_comma_emails(v)
        return v


class MeetingUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    summary: Optional[str] = Field(None, max_length=50000)
    transcript: Optional[str] = Field(None, max_length=500000)
    attendees: Optional[str] = Field(None, max_length=5000)
    tags: Optional[str] = Field(None, max_length=1000)

    @field_validator('title', 'summary', 'transcript')
    @classmethod
    def sanitise_text(cls, v):
        return strip_html_tags(v) if v else v

    @field_validator('tags')
    @classmethod
    def normalise_tags(cls, v):
        if v:
            return v.lower().strip()
        return v

    @field_validator('attendees')
    @classmethod
    def check_attendees(cls, v):
        if v:
            return validate_comma_emails(v)
        return v


class MeetingId(BaseModel):
    meeting_id: int = Field(..., gt=0, description="Meeting ID (positive integer)")


class MeetingSearch(BaseModel):
    query: str = Field(..., min_length=1, max_length=500, description="Search keyword")
    limit: Optional[int] = Field(50, gt=0, le=200, description="Max results")

    @field_validator('query')
    @classmethod
    def sanitise_query(cls, v):
        return strip_html_tags(v) if v else v


class MeetingListFilter(BaseModel):
    attendee: Optional[str] = Field(None, max_length=128)
    tag: Optional[str] = Field(None, max_length=100)
    days_back: Optional[int] = Field(None, gt=0, le=3650)
    limit: Optional[int] = Field(50, gt=0, le=200)


# === Action Schemas ===

class ActionCreate(BaseModel):
    action_text: str = Field(..., min_length=1, max_length=10000,
                             description="Action description")
    owner: str = Field(..., min_length=1, max_length=128,
                       description="Owner email address")
    meeting_id: Optional[int] = Field(None, gt=0,
                                       description="Associated meeting ID")
    due_date: Optional[str] = Field(None,
                                    description="Due date (YYYY-MM-DD)")
    notes: Optional[str] = Field(None, max_length=10000,
                                 description="Additional notes")

    @field_validator('action_text', 'notes')
    @classmethod
    def sanitise_text(cls, v):
        return strip_html_tags(v) if v else v

    @field_validator('owner')
    @classmethod
    def check_owner(cls, v):
        return validate_email_format(v)

    @field_validator('due_date')
    @classmethod
    def check_due_date(cls, v):
        if v:
            try:
                date.fromisoformat(v)
            except ValueError:
                raise ValueError('Invalid date format. Use YYYY-MM-DD')
        return v


class ActionUpdate(BaseModel):
    action_text: Optional[str] = Field(None, min_length=1, max_length=10000)
    owner: Optional[str] = Field(None, min_length=1, max_length=128)
    due_date: Optional[str] = Field(None)
    notes: Optional[str] = Field(None, max_length=10000)

    @field_validator('action_text', 'notes')
    @classmethod
    def sanitise_text(cls, v):
        return strip_html_tags(v) if v else v

    @field_validator('owner')
    @classmethod
    def check_owner(cls, v):
        if v:
            return validate_email_format(v)
        return v

    @field_validator('due_date')
    @classmethod
    def check_due_date(cls, v):
        if v:
            try:
                date.fromisoformat(v)
            except ValueError:
                raise ValueError('Invalid date format. Use YYYY-MM-DD')
        return v


class ActionId(BaseModel):
    action_id: int = Field(..., gt=0, description="Action ID (positive integer)")


class ActionListFilter(BaseModel):
    status: Optional[str] = Field("Open")
    owner: Optional[str] = Field(None, max_length=128)
    meeting_id: Optional[int] = Field(None, gt=0)
    limit: Optional[int] = Field(50, gt=0, le=200)

    @field_validator('status')
    @classmethod
    def check_status(cls, v):
        valid = {'Open', 'Complete', 'Parked', 'all'}
        if v and v not in valid:
            raise ValueError(f"Status must be one of: {', '.join(sorted(valid))}")
        return v


# === Decision Schemas ===

class DecisionCreate(BaseModel):
    decision_text: str = Field(..., min_length=1, max_length=10000,
                               description="Decision statement")
    meeting_id: int = Field(..., gt=0,
                            description="Associated meeting ID")
    context: Optional[str] = Field(None, max_length=10000,
                                   description="Decision context")

    @field_validator('decision_text', 'context')
    @classmethod
    def sanitise_text(cls, v):
        return strip_html_tags(v) if v else v


class DecisionId(BaseModel):
    decision_id: int = Field(..., gt=0, description="Decision ID (positive integer)")


class DecisionListFilter(BaseModel):
    meeting_id: Optional[int] = Field(None, gt=0)
    limit: Optional[int] = Field(50, gt=0, le=200)


# === Status Schema (for REST API) ===

class StatusUpdate(BaseModel):
    status: str = Field(..., description="New status value")

    @field_validator('status')
    @classmethod
    def check_status(cls, v):
        valid = {'Open', 'Complete', 'Parked'}
        if v not in valid:
            raise ValueError(f"Status must be one of: {', '.join(sorted(valid))}")
        return v
