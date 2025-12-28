"""Tests for HubSpot client."""

from unittest.mock import AsyncMock, patch

import pytest

from services.orchestrator.hubspot_client import HubSpotClient
from shared.config import Settings


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
        enable_hubspot=True,
    )


@pytest.fixture
def hubspot_client(mock_settings: Settings) -> HubSpotClient:
    """Create HubSpot client."""
    return HubSpotClient(mock_settings)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upsert_contact_existing(hubspot_client: HubSpotClient) -> None:
    """Test upserting an existing contact."""
    with patch.object(hubspot_client, "_make_request", new_callable=AsyncMock) as mock_request:
        # Search returns existing contact
        mock_request.return_value = {"total": 1, "results": [{"id": "12345"}]}

        contact_id = await hubspot_client.upsert_contact("+61400000000")

        assert contact_id == "12345"
        # Should only search, not create
        assert mock_request.call_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upsert_contact_new(hubspot_client: HubSpotClient) -> None:
    """Test creating a new contact."""
    with patch.object(hubspot_client, "_make_request", new_callable=AsyncMock) as mock_request:
        # Search returns no results
        mock_request.side_effect = [
            {"total": 0, "results": []},  # Search result
            {"id": "67890"},  # Create result
        ]

        contact_id = await hubspot_client.upsert_contact("+61400000000")

        assert contact_id == "67890"
        assert mock_request.call_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_ticket(hubspot_client: HubSpotClient) -> None:
    """Test creating a ticket."""
    with patch.object(hubspot_client, "_make_request", new_callable=AsyncMock) as mock_request:
        mock_request.side_effect = [
            {"id": "ticket-123"},  # Create ticket
            {},  # Associate ticket
        ]

        ticket_id = await hubspot_client.create_ticket(
            "contact-123",
            "Test Subject",
            "Test Description",
            "HIGH",
        )

        assert ticket_id == "ticket-123"
        assert mock_request.call_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_add_note_to_ticket(hubspot_client: HubSpotClient) -> None:
    """Test adding a note to a ticket."""
    with patch.object(hubspot_client, "_make_request", new_callable=AsyncMock) as mock_request:
        mock_request.side_effect = [
            {"id": "note-123"},  # Create note
            {},  # Associate note
        ]

        await hubspot_client.add_note_to_ticket("ticket-123", "Test note content")

        assert mock_request.call_count == 2
