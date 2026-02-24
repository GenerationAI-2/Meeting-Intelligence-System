"""Tests for input validation across MCP tools and REST endpoints."""
import sys
import os
import pytest
from pydantic import ValidationError

# Add server/src to path so schemas can be imported
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from schemas import (
    MeetingCreate, MeetingUpdate, MeetingId, MeetingSearch, MeetingListFilter,
    ActionCreate, ActionUpdate, ActionId, ActionListFilter,
    DecisionCreate, DecisionId, DecisionListFilter,
    StatusUpdate,
)


class TestMeetingValidation:

    def test_valid_meeting_create(self):
        m = MeetingCreate(title="Test", meeting_date="2026-02-09")
        assert m.title == "Test"

    def test_empty_title_rejected(self):
        with pytest.raises(ValidationError):
            MeetingCreate(title="", meeting_date="2026-02-09")

    def test_title_exceeds_max_length(self):
        with pytest.raises(ValidationError):
            MeetingCreate(title="x" * 256, meeting_date="2026-02-09")

    def test_title_at_max_length(self):
        m = MeetingCreate(title="x" * 255, meeting_date="2026-02-09")
        assert len(m.title) == 255

    def test_invalid_date_rejected(self):
        with pytest.raises(ValidationError):
            MeetingCreate(title="Test", meeting_date="not-a-date")

    def test_valid_date_formats(self):
        m1 = MeetingCreate(title="Test", meeting_date="2026-02-09")
        assert m1.meeting_date == "2026-02-09"
        m2 = MeetingCreate(title="Test", meeting_date="2026-02-09T14:30:00")
        assert m2.meeting_date == "2026-02-09T14:30:00"
        m3 = MeetingCreate(title="Test", meeting_date="2026-02-09T14:30:00Z")
        assert m3.meeting_date == "2026-02-09T14:30:00Z"

    def test_negative_meeting_id_rejected(self):
        with pytest.raises(ValidationError):
            MeetingId(meeting_id=-1)

    def test_zero_meeting_id_rejected(self):
        with pytest.raises(ValidationError):
            MeetingId(meeting_id=0)

    def test_valid_meeting_id(self):
        m = MeetingId(meeting_id=42)
        assert m.meeting_id == 42

    def test_tags_normalised_to_lowercase(self):
        m = MeetingCreate(title="Test", meeting_date="2026-02-09", tags="Sales, IMPORTANT")
        assert m.tags == "sales, important"

    def test_valid_attendees(self):
        m = MeetingCreate(title="Test", meeting_date="2026-02-09",
                          attendees="John Marshall, Jane Smith")
        assert m.attendees == "John Marshall,Jane Smith"

    def test_attendees_html_stripped(self):
        m = MeetingCreate(title="Test", meeting_date="2026-02-09",
                          attendees="<script>alert('xss')</script>John, Jane")
        assert "<script>" not in m.attendees

    def test_transcript_max_length(self):
        with pytest.raises(ValidationError):
            MeetingCreate(title="Test", meeting_date="2026-02-09", transcript="x" * 500001)

    def test_transcript_at_max_length(self):
        m = MeetingCreate(title="Test", meeting_date="2026-02-09", transcript="x" * 500000)
        assert len(m.transcript) == 500000

    def test_summary_max_length(self):
        with pytest.raises(ValidationError):
            MeetingCreate(title="Test", meeting_date="2026-02-09", summary="x" * 50001)

    def test_source_max_length(self):
        with pytest.raises(ValidationError):
            MeetingCreate(title="Test", meeting_date="2026-02-09", source="x" * 51)

    def test_search_empty_query_rejected(self):
        with pytest.raises(ValidationError):
            MeetingSearch(query="")

    def test_search_limit_capped(self):
        with pytest.raises(ValidationError):
            MeetingSearch(query="test", limit=500)

    def test_search_valid(self):
        s = MeetingSearch(query="test", limit=20)
        assert s.query == "test"
        assert s.limit == 20

    def test_search_default_limit(self):
        s = MeetingSearch(query="test")
        assert s.limit == 50

    def test_list_filter_defaults(self):
        f = MeetingListFilter()
        assert f.limit == 50
        assert f.attendee is None
        assert f.tag is None
        assert f.days_back is None

    def test_list_filter_days_back_max(self):
        with pytest.raises(ValidationError):
            MeetingListFilter(days_back=3651)

    def test_update_optional_fields(self):
        u = MeetingUpdate(title="New Title")
        assert u.title == "New Title"
        assert u.summary is None

    def test_update_empty_title_rejected(self):
        with pytest.raises(ValidationError):
            MeetingUpdate(title="")


class TestActionValidation:

    def test_valid_action_create(self):
        a = ActionCreate(action_text="Do something", owner="John Marshall")
        assert a.owner == "John Marshall"

    def test_owner_accepts_plain_name(self):
        a = ActionCreate(action_text="Do something", owner="Craig Corfield")
        assert a.owner == "Craig Corfield"

    def test_owner_html_stripped(self):
        a = ActionCreate(action_text="Do something", owner="<b>John</b>")
        assert a.owner == "John"

    def test_empty_action_text_rejected(self):
        with pytest.raises(ValidationError):
            ActionCreate(action_text="", owner="John Marshall")

    def test_action_text_max_length(self):
        with pytest.raises(ValidationError):
            ActionCreate(action_text="x" * 10001, owner="John")

    def test_invalid_due_date(self):
        with pytest.raises(ValidationError):
            ActionCreate(action_text="Do something", owner="John", due_date="31/02/2026")

    def test_valid_due_date(self):
        a = ActionCreate(action_text="Do something", owner="John", due_date="2026-03-15")
        assert a.due_date == "2026-03-15"

    def test_notes_max_length(self):
        with pytest.raises(ValidationError):
            ActionCreate(action_text="Do something", owner="John", notes="x" * 10001)

    def test_invalid_status_rejected(self):
        with pytest.raises(ValidationError):
            ActionListFilter(status="InvalidStatus")

    def test_valid_statuses(self):
        for status in ['Open', 'Complete', 'Parked', 'all']:
            f = ActionListFilter(status=status)
            assert f.status == status

    def test_default_status(self):
        f = ActionListFilter()
        assert f.status is None

    def test_negative_action_id(self):
        with pytest.raises(ValidationError):
            ActionId(action_id=-5)

    def test_zero_action_id(self):
        with pytest.raises(ValidationError):
            ActionId(action_id=0)

    def test_valid_action_id(self):
        a = ActionId(action_id=1)
        assert a.action_id == 1

    def test_negative_meeting_id_in_action(self):
        with pytest.raises(ValidationError):
            ActionCreate(action_text="Do something", owner="John", meeting_id=-1)

    def test_update_valid_owner(self):
        u = ActionUpdate(owner="Craig Corfield")
        assert u.owner == "Craig Corfield"

    def test_list_filter_limit_max(self):
        with pytest.raises(ValidationError):
            ActionListFilter(limit=201)


class TestDecisionValidation:

    def test_valid_decision_create(self):
        d = DecisionCreate(decision_text="We decided X", meeting_id=1)
        assert d.meeting_id == 1

    def test_missing_meeting_id(self):
        with pytest.raises(ValidationError):
            DecisionCreate(decision_text="We decided X")

    def test_zero_meeting_id(self):
        with pytest.raises(ValidationError):
            DecisionCreate(decision_text="We decided X", meeting_id=0)

    def test_negative_meeting_id(self):
        with pytest.raises(ValidationError):
            DecisionCreate(decision_text="We decided X", meeting_id=-1)

    def test_empty_decision_text(self):
        with pytest.raises(ValidationError):
            DecisionCreate(decision_text="", meeting_id=1)

    def test_decision_text_max_length(self):
        with pytest.raises(ValidationError):
            DecisionCreate(decision_text="x" * 10001, meeting_id=1)

    def test_decision_text_at_max_length(self):
        d = DecisionCreate(decision_text="x" * 10000, meeting_id=1)
        assert len(d.decision_text) == 10000

    def test_context_max_length(self):
        with pytest.raises(ValidationError):
            DecisionCreate(decision_text="Test", meeting_id=1, context="x" * 10001)

    def test_valid_context(self):
        d = DecisionCreate(decision_text="Test", meeting_id=1, context="Some context")
        assert d.context == "Some context"

    def test_negative_decision_id(self):
        with pytest.raises(ValidationError):
            DecisionId(decision_id=-1)

    def test_zero_decision_id(self):
        with pytest.raises(ValidationError):
            DecisionId(decision_id=0)

    def test_valid_decision_id(self):
        d = DecisionId(decision_id=5)
        assert d.decision_id == 5

    def test_decision_id_string_rejected(self):
        with pytest.raises(ValidationError):
            DecisionId(decision_id="abc")

    def test_decision_id_float_coerced(self):
        d = DecisionId(decision_id=3.0)
        assert d.decision_id == 3

    def test_list_filter_defaults(self):
        f = DecisionListFilter()
        assert f.limit == 50
        assert f.meeting_id is None

    def test_list_filter_limit_max(self):
        with pytest.raises(ValidationError):
            DecisionListFilter(limit=201)

    def test_list_filter_negative_meeting_id(self):
        with pytest.raises(ValidationError):
            DecisionListFilter(meeting_id=-1)


class TestStatusUpdate:

    def test_valid_statuses(self):
        for status in ['Open', 'Complete', 'Parked']:
            s = StatusUpdate(status=status)
            assert s.status == status

    def test_invalid_status(self):
        with pytest.raises(ValidationError):
            StatusUpdate(status="InvalidStatus")

    def test_all_not_valid_for_status_update(self):
        with pytest.raises(ValidationError):
            StatusUpdate(status="all")


class TestDueDateValidation:
    """B7: due_date format enforcement."""

    def test_valid_iso_date(self):
        a = ActionCreate(action_text="Do task", owner="Alice", due_date="2026-03-15")
        assert a.due_date == "2026-03-15"

    def test_relative_date_rejected(self):
        with pytest.raises(ValidationError, match="ISO 8601"):
            ActionCreate(action_text="Do task", owner="Alice", due_date="next Friday")

    def test_slash_format_rejected(self):
        with pytest.raises(ValidationError, match="ISO 8601"):
            ActionCreate(action_text="Do task", owner="Alice", due_date="2026/03/15")

    def test_text_date_rejected(self):
        with pytest.raises(ValidationError, match="ISO 8601"):
            ActionCreate(action_text="Do task", owner="Alice", due_date="March 15")

    def test_end_of_sprint_rejected(self):
        with pytest.raises(ValidationError, match="ISO 8601"):
            ActionCreate(action_text="Do task", owner="Alice", due_date="end of sprint")

    def test_none_accepted(self):
        a = ActionCreate(action_text="Do task", owner="Alice", due_date=None)
        assert a.due_date is None

    def test_empty_string_treated_as_none(self):
        a = ActionCreate(action_text="Do task", owner="Alice", due_date="")
        assert a.due_date is None

    def test_whitespace_string_treated_as_none(self):
        a = ActionCreate(action_text="Do task", owner="Alice", due_date="  ")
        assert a.due_date is None

    def test_update_also_validates(self):
        with pytest.raises(ValidationError, match="ISO 8601"):
            ActionUpdate(due_date="next week")

    def test_update_empty_string_treated_as_none(self):
        a = ActionUpdate(due_date="")
        assert a.due_date is None


class TestSummaryMarkdownValidation:
    """B8: summary markdown enforcement for long summaries."""

    def test_short_plain_text_accepted(self):
        """Summaries under 500 chars don't need markdown."""
        m = MeetingCreate(title="Test", meeting_date="2026-02-24",
                          summary="Quick standup. Discussed sprint progress, no blockers.")
        assert m.summary is not None

    def test_long_plain_text_rejected(self):
        """Summaries over 500 chars without markdown are rejected."""
        plain_text = "This is a long meeting summary. " * 20  # ~640 chars
        with pytest.raises(ValidationError, match="markdown formatted"):
            MeetingCreate(title="Test", meeting_date="2026-02-24", summary=plain_text)

    def test_long_text_with_heading_accepted(self):
        """A single ## heading is enough to pass."""
        summary = "## Overview\n\n" + "Discussion point about the project. " * 20
        m = MeetingCreate(title="Test", meeting_date="2026-02-24", summary=summary)
        assert m.summary is not None

    def test_long_text_with_bullets_accepted(self):
        """Bullet points are enough to pass."""
        summary = "- First item discussed\n" + "More details about the meeting. " * 20
        m = MeetingCreate(title="Test", meeting_date="2026-02-24", summary=summary)
        assert m.summary is not None

    def test_long_text_with_bold_accepted(self):
        """Bold text is enough to pass."""
        summary = "The **key decision** was made. " + "More context about the meeting. " * 20
        m = MeetingCreate(title="Test", meeting_date="2026-02-24", summary=summary)
        assert m.summary is not None

    def test_long_text_with_star_bullets_accepted(self):
        """Star bullets are enough to pass."""
        summary = "* First item\n" + "Additional discussion notes. " * 20
        m = MeetingCreate(title="Test", meeting_date="2026-02-24", summary=summary)
        assert m.summary is not None

    def test_none_summary_accepted(self):
        m = MeetingCreate(title="Test", meeting_date="2026-02-24", summary=None)
        assert m.summary is None

    def test_exactly_500_chars_plain_text_accepted(self):
        """Boundary: 500 chars exactly should pass without markdown."""
        summary = "x" * 500
        m = MeetingCreate(title="Test", meeting_date="2026-02-24", summary=summary)
        assert len(m.summary) == 500

    def test_501_chars_plain_text_rejected(self):
        """Boundary: 501 chars without markdown should be rejected."""
        summary = "x" * 501
        with pytest.raises(ValidationError, match="markdown formatted"):
            MeetingCreate(title="Test", meeting_date="2026-02-24", summary=summary)

    def test_update_also_validates(self):
        """MeetingUpdate should enforce the same rule."""
        plain_text = "This is a long update summary. " * 20
        with pytest.raises(ValidationError, match="markdown formatted"):
            MeetingUpdate(summary=plain_text)
