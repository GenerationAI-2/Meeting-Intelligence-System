# SQL Query Audit — Meeting Intelligence

Date: 2026-02-09
Auditor: Agent (Stream D — Input Validation Hardening)

## Summary

Total queries audited: 41
Parameterised (SAFE): 41
String-formatted (UNSAFE): 0

All queries use `?` parameter placeholders with pyodbc. Three functions use f-strings for dynamic SQL construction (`list_meetings`, `update_meeting`, `list_actions`, `update_action`), but only for assembling hardcoded column names and conditions — user-supplied values are always passed as parameterised arguments.

## Query Inventory

### database.py

| Function | Line | Query | Status |
|----------|------|-------|--------|
| test_connection | 185 | `SELECT 1` | SAFE — no user input |

### tools/meetings.py

| Function | Line | Query | Status |
|----------|------|-------|--------|
| list_meetings | 58–64 | `SELECT MeetingId, Title, MeetingDate, Attendees, Source, Tags FROM Meeting WHERE ... ORDER BY MeetingDate DESC OFFSET 0 ROWS FETCH NEXT ? ROWS ONLY` | SAFE — f-string assembles hardcoded conditions, all values use `?` params |
| get_meeting | 114–120 | `SELECT ... FROM Meeting WHERE MeetingId = ?` | SAFE — uses `?` param |
| search_meetings | 175–189 | `SELECT ... FROM Meeting WHERE Title LIKE ? OR RawTranscript LIKE ? ...` | SAFE — uses `?` params |
| create_meeting | 253–259 | `INSERT INTO Meeting (...) OUTPUT INSERTED.MeetingId VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)` | SAFE — uses `?` params |
| update_meeting | 347 | `SELECT MeetingId FROM Meeting WHERE MeetingId = ?` | SAFE — uses `?` param |
| update_meeting | 352–356 | `UPDATE Meeting SET ... WHERE MeetingId = ?` | SAFE — f-string assembles hardcoded SET clauses, values use `?` params |
| delete_meeting | 385 | `SELECT MeetingId, Title FROM Meeting WHERE MeetingId = ?` | SAFE — uses `?` param |
| delete_meeting | 393 | `DELETE FROM Decision WHERE MeetingId = ?` | SAFE — uses `?` param |
| delete_meeting | 394 | `DELETE FROM Action WHERE MeetingId = ?` | SAFE — uses `?` param |
| delete_meeting | 395 | `DELETE FROM Meeting WHERE MeetingId = ?` | SAFE — uses `?` param |

### tools/actions.py

| Function | Line | Query | Status |
|----------|------|-------|--------|
| list_actions | 73–82 | `SELECT ActionId, ActionText, Owner, DueDate, Status, MeetingId FROM Action WHERE ... ORDER BY ...` | SAFE — f-string assembles hardcoded conditions, all values use `?` params |
| get_action | 130–135 | `SELECT ... FROM Action WHERE ActionId = ?` | SAFE — uses `?` param |
| create_action | 203 | `SELECT MeetingId FROM Meeting WHERE MeetingId = ?` | SAFE — uses `?` param |
| create_action | 207–213 | `INSERT INTO Action (...) OUTPUT INSERTED.ActionId VALUES (?, ?, ?, 'Open', ?, ?, ?, ?, ?, ?)` | SAFE — uses `?` params |
| update_action | 301 | `SELECT ActionId FROM Action WHERE ActionId = ?` | SAFE — uses `?` param |
| update_action | 306–310 | `UPDATE Action SET ... WHERE ActionId = ?` | SAFE — f-string assembles hardcoded SET clauses, values use `?` params |
| complete_action | 338 | `SELECT ActionId FROM Action WHERE ActionId = ?` | SAFE — uses `?` param |
| complete_action | 342–346 | `UPDATE Action SET Status = 'Complete', UpdatedAt = ?, UpdatedBy = ? WHERE ActionId = ?` | SAFE — uses `?` params |
| park_action | 373 | `SELECT ActionId FROM Action WHERE ActionId = ?` | SAFE — uses `?` param |
| park_action | 377–381 | `UPDATE Action SET Status = 'Parked', UpdatedAt = ?, UpdatedBy = ? WHERE ActionId = ?` | SAFE — uses `?` params |
| delete_action | 407 | `SELECT ActionId FROM Action WHERE ActionId = ?` | SAFE — uses `?` param |
| delete_action | 411 | `DELETE FROM Action WHERE ActionId = ?` | SAFE — uses `?` param |

### tools/decisions.py

| Function | Line | Query | Status |
|----------|------|-------|--------|
| list_decisions | 39–47 | `SELECT ... FROM Decision d JOIN Meeting m ... WHERE d.MeetingId = ? ORDER BY ... FETCH NEXT ? ROWS ONLY` | SAFE — uses `?` params |
| list_decisions | 49–56 | `SELECT ... FROM Decision d JOIN Meeting m ... ORDER BY ... FETCH NEXT ? ROWS ONLY` | SAFE — uses `?` param |
| get_decision | 100–106 | `SELECT ... FROM Decision d JOIN Meeting m ... WHERE d.DecisionId = ?` | SAFE — uses `?` param |
| create_decision | 159 | `SELECT MeetingId, Title FROM Meeting WHERE MeetingId = ?` | SAFE — uses `?` param |
| create_decision | 164–168 | `INSERT INTO Decision (...) OUTPUT INSERTED.DecisionId VALUES (?, ?, ?, ?, ?)` | SAFE — uses `?` params |
| delete_decision | 206 | `SELECT DecisionId FROM Decision WHERE DecisionId = ?` | SAFE — uses `?` param |
| delete_decision | 210 | `DELETE FROM Decision WHERE DecisionId = ?` | SAFE — uses `?` param |

### api.py

| Function | Line | Query | Status |
|----------|------|-------|--------|
| get_meeting_endpoint | 166–169 | `SELECT DecisionId, DecisionText, Context FROM Decision WHERE MeetingId = ?` | SAFE — uses `?` param |
| get_meeting_endpoint | 175–178 | `SELECT ActionId, ActionText, Owner, DueDate, Status FROM Action WHERE MeetingId = ?` | SAFE — uses `?` param |
| update_action_status_endpoint | 252–255 | `UPDATE Action SET Status = 'Open', UpdatedAt = ?, UpdatedBy = ? WHERE ActionId = ?` | SAFE — uses `?` params |
| delete_meeting_endpoint | 300 | `SELECT MeetingId FROM Meeting WHERE MeetingId = ?` | SAFE — uses `?` param |
| delete_meeting_endpoint | 305 | `DELETE FROM Decision WHERE MeetingId = ?` | SAFE — uses `?` param |
| delete_meeting_endpoint | 306 | `DELETE FROM Action WHERE MeetingId = ?` | SAFE — uses `?` param |
| delete_meeting_endpoint | 307 | `DELETE FROM Meeting WHERE MeetingId = ?` | SAFE — uses `?` param |
| delete_action_endpoint | 321 | `SELECT ActionId FROM Action WHERE ActionId = ?` | SAFE — uses `?` param |
| delete_action_endpoint | 325 | `DELETE FROM Action WHERE ActionId = ?` | SAFE — uses `?` param |
| delete_decision_endpoint | 339 | `SELECT DecisionId FROM Decision WHERE DecisionId = ?` | SAFE — uses `?` param |
| delete_decision_endpoint | 343 | `DELETE FROM Decision WHERE DecisionId = ?` | SAFE — uses `?` param |

## Dynamic SQL Pattern Analysis

Four functions build SQL dynamically using f-strings:

1. **`meetings.list_meetings`** — Builds WHERE clause from hardcoded conditions (`"MeetingDate >= DATEADD(day, -?, GETUTCDATE())"`, `"Attendees LIKE ?"`, `"Tags LIKE ?"`). User values passed as `?` params. **SAFE.**

2. **`meetings.update_meeting`** — Builds SET clause from hardcoded column assignments (`"Title = ?"`, `"Summary = ?"`, etc.). User values passed as `?` params. **SAFE.**

3. **`actions.list_actions`** — Same pattern as `list_meetings`. Hardcoded conditions, parameterised values. **SAFE.**

4. **`actions.update_action`** — Same pattern as `update_meeting`. Hardcoded SET clauses, parameterised values. **SAFE.**

## Conclusion

**SQL Injection Risk: NONE.** All 41 queries use parameterised statements. No remediation required.
