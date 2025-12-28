"""Tests for DynamoDB repository."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from services.orchestrator.dynamo_repository import DynamoRepository
from shared.config import Settings
from shared.types import EscalationReason, HandoverPayload


@pytest.fixture
def mock_settings() -> Settings:
    """Create mock settings."""
    return Settings(
        public_host="test.ngrok.io",
        twilio_account_sid="ACtest",
        twilio_auth_token="test_token",
        twilio_phone_number="+61000000000",
        openai_api_key="sk-test",
        connect_phone_number="+61000000001",
        connect_instance_id="test-instance",
        hubspot_access_token="pat-test",
        use_local_dynamodb=True,
        dynamodb_endpoint_url="http://localhost:8001",
    )


@pytest.fixture
def mock_dynamodb_resource() -> MagicMock:
    """Create mock DynamoDB resource."""
    mock_resource = MagicMock()
    mock_table = MagicMock()
    mock_resource.Table.return_value = mock_table
    return mock_resource


@pytest.fixture
def dynamo_repo(mock_settings: Settings, mock_dynamodb_resource: MagicMock) -> DynamoRepository:
    """Create DynamoDB repository with mocked resource."""
    with patch("services.orchestrator.dynamo_repository.create_dynamodb_resource", return_value=mock_dynamodb_resource):
        repo = DynamoRepository(mock_settings)
        return repo


@pytest.mark.unit
def test_put_handover(dynamo_repo: DynamoRepository, mock_dynamodb_resource: MagicMock) -> None:
    """Test storing handover payload."""
    payload = HandoverPayload(
        token="1234567890",
        conversation_id="test-conv-123",
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
        summary="Test conversation summary",
        escalation_reason=EscalationReason.USER_REQUEST,
    )

    dynamo_repo.put_handover(payload)

    # Verify put_item was called
    mock_table = mock_dynamodb_resource.Table.return_value
    mock_table.put_item.assert_called_once()

    # Verify item structure
    call_args = mock_table.put_item.call_args
    item = call_args.kwargs["Item"]
    assert item["token"] == "1234567890"
    assert item["conversation_id"] == "test-conv-123"
    assert item["escalation_reason"] == "user_request"


@pytest.mark.unit
def test_get_handover_success(dynamo_repo: DynamoRepository, mock_dynamodb_resource: MagicMock) -> None:
    """Test retrieving handover payload."""
    expires_at = datetime.now(UTC) + timedelta(minutes=10)

    mock_table = mock_dynamodb_resource.Table.return_value
    mock_table.get_item.return_value = {
        "Item": {
            "token": "1234567890",
            "conversation_id": "test-conv-123",
            "created_at": datetime.now(UTC).isoformat(),
            "expires_at": int(expires_at.timestamp()),
            "summary": "Test summary",
            "priority": "medium",
            "escalation_reason": "user_request",
        }
    }

    payload = dynamo_repo.get_handover("1234567890")

    assert payload is not None
    assert payload.token == "1234567890"
    assert payload.conversation_id == "test-conv-123"
    assert payload.escalation_reason == EscalationReason.USER_REQUEST


@pytest.mark.unit
def test_get_handover_not_found(dynamo_repo: DynamoRepository, mock_dynamodb_resource: MagicMock) -> None:
    """Test retrieving non-existent handover payload."""
    mock_table = mock_dynamodb_resource.Table.return_value
    mock_table.get_item.return_value = {}

    payload = dynamo_repo.get_handover("9999999999")

    assert payload is None


@pytest.mark.unit
def test_get_handover_expired(dynamo_repo: DynamoRepository, mock_dynamodb_resource: MagicMock) -> None:
    """Test retrieving expired handover payload."""
    expires_at = datetime.now(UTC) - timedelta(minutes=1)  # Already expired

    mock_table = mock_dynamodb_resource.Table.return_value
    mock_table.get_item.return_value = {
        "Item": {
            "token": "1234567890",
            "conversation_id": "test-conv-123",
            "created_at": datetime.now(UTC).isoformat(),
            "expires_at": int(expires_at.timestamp()),
            "summary": "Test summary",
            "priority": "medium",
            "escalation_reason": "user_request",
        }
    }

    payload = dynamo_repo.get_handover("1234567890")

    assert payload is None


@pytest.mark.unit
def test_delete_handover(dynamo_repo: DynamoRepository, mock_dynamodb_resource: MagicMock) -> None:
    """Test deleting handover payload."""
    dynamo_repo.delete_handover("1234567890")

    mock_table = mock_dynamodb_resource.Table.return_value
    mock_table.delete_item.assert_called_once_with(Key={"token": "1234567890"})
