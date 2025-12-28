"""Tests for Amazon Connect Lambda handler."""

from unittest.mock import MagicMock, patch

import pytest

from aws.connect_lambda.handler import fetch_handover_payload, lambda_handler, validate_token


@pytest.mark.unit
def test_validate_token_valid() -> None:
    """Test token validation with valid token."""
    assert validate_token("1234567890") is True
    assert validate_token("0000000000") is True
    assert validate_token("9999999999") is True


@pytest.mark.unit
def test_validate_token_invalid() -> None:
    """Test token validation with invalid tokens."""
    assert validate_token("123456789") is False  # Too short
    assert validate_token("12345678901") is False  # Too long
    assert validate_token("12345abcde") is False  # Contains letters
    assert validate_token("") is False  # Empty
    assert validate_token("123-456-7890") is False  # Contains hyphens


@pytest.mark.unit
@patch("aws.connect_lambda.handler.table")
def test_fetch_handover_payload_success(mock_table: MagicMock) -> None:
    """Test fetching handover payload successfully."""
    mock_table.get_item.return_value = {
        "Item": {
            "token": "1234567890",
            "conversation_id": "test-conv-123",
            "summary": "Test summary",
            "priority": "medium",
        }
    }

    payload = fetch_handover_payload("1234567890")

    assert payload is not None
    assert payload["token"] == "1234567890"
    assert payload["conversation_id"] == "test-conv-123"


@pytest.mark.unit
@patch("aws.connect_lambda.handler.table")
def test_fetch_handover_payload_not_found(mock_table: MagicMock) -> None:
    """Test fetching non-existent handover payload."""
    mock_table.get_item.return_value = {}

    payload = fetch_handover_payload("9999999999")

    assert payload is None


@pytest.mark.unit
@patch("aws.connect_lambda.handler.fetch_handover_payload")
def test_lambda_handler_success(mock_fetch: MagicMock) -> None:
    """Test Lambda handler with valid token."""
    mock_fetch.return_value = {
        "token": "1234567890",
        "conversation_id": "test-conv-123",
        "caller_phone": "+61400000000",
        "hubspot_contact_id": "12345",
        "hubspot_ticket_id": "67890",
        "summary": "Test summary",
        "intent": "support",
        "priority": "high",
        "escalation_reason": "user_request",
    }

    event = {
        "Details": {
            "ContactData": {"ContactId": "contact-123"},
            "Parameters": {"token": "1234567890"},
        }
    }

    result = lambda_handler(event, None)

    assert result["success"] is True
    assert result["conversation_id"] == "test-conv-123"
    assert result["priority"] == "high"
    assert result["route_to_queue"] == "escalation"


@pytest.mark.unit
@patch("aws.connect_lambda.handler.fetch_handover_payload")
def test_lambda_handler_invalid_token(mock_fetch: MagicMock) -> None:
    """Test Lambda handler with invalid token format."""
    event = {
        "Details": {
            "ContactData": {"ContactId": "contact-123"},
            "Parameters": {"token": "invalid"},
        }
    }

    result = lambda_handler(event, None)

    assert result["success"] is False
    assert result["error_message"] == "Invalid token format"
    assert result["route_to_queue"] == "fallback"
    mock_fetch.assert_not_called()


@pytest.mark.unit
@patch("aws.connect_lambda.handler.fetch_handover_payload")
def test_lambda_handler_token_not_found(mock_fetch: MagicMock) -> None:
    """Test Lambda handler with token not found."""
    mock_fetch.return_value = None

    event = {
        "Details": {
            "ContactData": {"ContactId": "contact-123"},
            "Parameters": {"token": "1234567890"},
        }
    }

    result = lambda_handler(event, None)

    assert result["success"] is False
    assert result["error_message"] == "Token not found or expired"
    assert result["route_to_queue"] == "fallback"


@pytest.mark.unit
def test_lambda_handler_no_token() -> None:
    """Test Lambda handler with no token provided."""
    event = {
        "Details": {
            "ContactData": {"ContactId": "contact-123"},
            "Parameters": {},
        }
    }

    result = lambda_handler(event, None)

    assert result["success"] is False
    assert result["error_message"] == "No token provided"
    assert result["route_to_queue"] == "fallback"


@pytest.mark.unit
def test_lambda_handler_invalid_event() -> None:
    """Test Lambda handler with invalid event structure."""
    event = {"invalid": "structure"}

    result = lambda_handler(event, None)

    assert result["success"] is False
    assert "error_message" in result
