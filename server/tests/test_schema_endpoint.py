"""Tests for the schema endpoint (P8)."""
import sys
import os
from unittest.mock import MagicMock

# Add server/ to path so src package can be imported
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Mock external dependencies before importing api to avoid Azure AD setup failures
# in test environments without Azure credentials.
mock_azure_auth = MagicMock()
sys.modules["fastapi_azure_auth"] = mock_azure_auth
mock_azure_auth.SingleTenantAzureAuthorizationCodeBearer = MagicMock(return_value=MagicMock())

from src.api import get_entity_schema


EXPECTED_ENTITIES = ["meeting", "action", "decision"]

MEETING_FIELDS = ["title", "meeting_date", "summary", "transcript", "attendees", "source", "source_meeting_id", "tags"]
ACTION_FIELDS = ["action_text", "owner", "due_date", "meeting_id", "notes"]
DECISION_FIELDS = ["decision_text", "meeting_id", "context"]


class TestSchemaEndpoint:
    """Tests for GET /api/schema and get_entity_schema()."""

    def test_schema_returns_dict(self):
        schema = get_entity_schema()
        assert isinstance(schema, dict)

    def test_schema_has_version(self):
        schema = get_entity_schema()
        assert "version" in schema
        assert schema["version"] == "1.0"

    def test_schema_includes_all_three_entities(self):
        schema = get_entity_schema()
        assert "entities" in schema
        for entity in EXPECTED_ENTITIES:
            assert entity in schema["entities"], f"Missing entity: {entity}"

    def test_meeting_fields_complete(self):
        schema = get_entity_schema()
        meeting_fields = schema["entities"]["meeting"]["fields"]
        for field in MEETING_FIELDS:
            assert field in meeting_fields, f"Missing meeting field: {field}"

    def test_action_fields_complete(self):
        schema = get_entity_schema()
        action_fields = schema["entities"]["action"]["fields"]
        for field in ACTION_FIELDS:
            assert field in action_fields, f"Missing action field: {field}"

    def test_decision_fields_complete(self):
        schema = get_entity_schema()
        decision_fields = schema["entities"]["decision"]["fields"]
        for field in DECISION_FIELDS:
            assert field in decision_fields, f"Missing decision field: {field}"

    def test_field_definitions_have_required_properties(self):
        """Every field definition must include type, required, description, and example."""
        schema = get_entity_schema()
        required_props = {"type", "required", "description", "example"}
        for entity_name, entity in schema["entities"].items():
            for field_name, field_def in entity["fields"].items():
                for prop in required_props:
                    assert prop in field_def, (
                        f"{entity_name}.{field_name} missing '{prop}'"
                    )

    def test_required_fields_marked_correctly(self):
        schema = get_entity_schema()
        # Meeting required fields
        assert schema["entities"]["meeting"]["fields"]["title"]["required"] is True
        assert schema["entities"]["meeting"]["fields"]["meeting_date"]["required"] is True
        assert schema["entities"]["meeting"]["fields"]["summary"]["required"] is False
        # Action required fields
        assert schema["entities"]["action"]["fields"]["action_text"]["required"] is True
        assert schema["entities"]["action"]["fields"]["owner"]["required"] is True
        assert schema["entities"]["action"]["fields"]["due_date"]["required"] is False
        # Decision required fields
        assert schema["entities"]["decision"]["fields"]["decision_text"]["required"] is True
        assert schema["entities"]["decision"]["fields"]["meeting_id"]["required"] is True
        assert schema["entities"]["decision"]["fields"]["context"]["required"] is False

    def test_action_status_values_listed(self):
        schema = get_entity_schema()
        action = schema["entities"]["action"]
        assert "status_values" in action
        assert action["status_values"] == ["Open", "Complete", "Parked"]

    def test_relationships_documented(self):
        schema = get_entity_schema()
        assert "relationships" in schema
        rels = schema["relationships"]
        # Action -> Meeting
        action_rel = [r for r in rels if r["from"] == "action.meeting_id"]
        assert len(action_rel) == 1
        assert action_rel[0]["to"] == "meeting"
        assert action_rel[0]["required"] is False
        # Decision -> Meeting
        decision_rel = [r for r in rels if r["from"] == "decision.meeting_id"]
        assert len(decision_rel) == 1
        assert decision_rel[0]["to"] == "meeting"
        assert decision_rel[0]["required"] is True

    def test_entity_descriptions_present(self):
        schema = get_entity_schema()
        for entity_name, entity in schema["entities"].items():
            assert "description" in entity, f"{entity_name} missing description"
            assert len(entity["description"]) > 0

    def test_cascade_delete_documented(self):
        schema = get_entity_schema()
        assert "cascade_deletes" in schema
