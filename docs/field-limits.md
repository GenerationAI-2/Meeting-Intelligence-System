# Database Field Limits

Reference document for all field constraints in the Meeting Intelligence System.

## Meetings Table

| Field | Type | Max Length | Required | Format |
|-------|------|------------|----------|--------|
| MeetingId | INT | - | Auto | Primary key |
| Title | NVARCHAR | 255 | Yes | Plain text |
| MeetingDate | DATETIME2 | - | Yes | ISO 8601 (YYYY-MM-DD or full datetime) |
| Attendees | NVARCHAR(MAX) | No limit | No | Comma-separated emails |
| Summary | NVARCHAR(MAX) | No limit | No | Markdown supported |
| RawTranscript | NVARCHAR(MAX) | No limit | No | Plain text |
| Source | NVARCHAR | 50 | No | e.g., "Manual", "fireflies" |
| SourceMeetingId | NVARCHAR | 255 | No | External system ID |
| CreatedAt | DATETIME2 | - | Auto | ISO 8601 |
| CreatedBy | NVARCHAR | 128 | Yes | Email address |
| UpdatedAt | DATETIME2 | - | Auto | ISO 8601 |
| UpdatedBy | NVARCHAR | 128 | Yes | Email address |

## Actions Table

| Field | Type | Max Length | Required | Format |
|-------|------|------------|----------|--------|
| ActionId | INT | - | Auto | Primary key |
| MeetingId | INT | - | No | Foreign key to Meeting |
| ActionText | NVARCHAR(MAX) | No limit | Yes | Plain text |
| Owner | NVARCHAR | 128 | Yes | Email format preferred |
| DueDate | DATE | - | No | YYYY-MM-DD |
| Status | NVARCHAR | 20 | Yes | "Open", "Complete", "Parked" |
| Notes | NVARCHAR(MAX) | No limit | No | Plain text |
| CreatedAt | DATETIME2 | - | Auto | ISO 8601 |
| CreatedBy | NVARCHAR | 128 | Yes | Email address |
| UpdatedAt | DATETIME2 | - | Auto | ISO 8601 |
| UpdatedBy | NVARCHAR | 128 | Yes | Email address |

## Decisions Table

| Field | Type | Max Length | Required | Format |
|-------|------|------------|----------|--------|
| DecisionId | INT | - | Auto | Primary key |
| MeetingId | INT | - | Yes | Foreign key to Meeting |
| DecisionText | NVARCHAR(MAX) | No limit | Yes | Plain text |
| Context | NVARCHAR(MAX) | No limit | No | Plain text |
| CreatedAt | DATETIME2 | - | Auto | ISO 8601 |
| CreatedBy | NVARCHAR | 128 | Yes | Email address |

## Notes for AI Assistants

1. **Dates**: Always use ISO 8601 format (YYYY-MM-DD for dates, full ISO for datetimes)
2. **Emails**: Use standard email format for Owner and CreatedBy/UpdatedBy fields
3. **Status values**: Only "Open", "Complete", or "Parked" are valid for actions
4. **Markdown**: Only the meeting Summary field supports markdown formatting
5. **No limit fields**: NVARCHAR(MAX) fields have no practical limit (up to 2GB), but keep content reasonable
6. **Required fields**: Fields marked "Yes" must be provided; "Auto" fields are set by the system

## Field Limits Summary

| Field | Hard Limit |
|-------|------------|
| Title | 255 chars |
| Owner | 128 chars |
| Source | 50 chars |
| SourceMeetingId | 255 chars |
| Status | 20 chars |
| CreatedBy/UpdatedBy | 128 chars |
| ActionText, DecisionText, Notes, Context, Summary, Transcript, Attendees | No limit |
