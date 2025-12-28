"""HubSpot API client."""

import logging
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from shared.config import Settings

logger = logging.getLogger(__name__)


class HubSpotClient:
    """Async HTTP client for HubSpot API."""

    def __init__(self, settings: Settings) -> None:
        """Initialize the HubSpot client."""
        self.settings = settings
        self.enabled = settings.enable_hubspot and settings.hubspot_access_token is not None
        self.base_url = settings.hubspot_api_base_url
        self.headers = {
            "Authorization": f"Bearer {settings.hubspot_access_token or ''}",
            "Content-Type": "application/json",
        }

    def _check_enabled(self) -> None:
        """Check if HubSpot integration is enabled."""
        if not self.enabled:
            logger.warning("HubSpot integration is disabled or not configured")
            raise RuntimeError("HubSpot integration is not enabled")

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.RequestError)),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def _make_request(
        self, method: str, endpoint: str, json_data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Make an HTTP request to HubSpot API with retry logic."""
        url = f"{self.base_url}{endpoint}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(method, url, headers=self.headers, json=json_data)

            if response.status_code == 429:
                logger.warning("HubSpot rate limit hit, retrying", extra={"endpoint": endpoint})
                response.raise_for_status()

            response.raise_for_status()
            return response.json() if response.content else {}

    async def upsert_contact(self, phone: str) -> str:
        """Create or update a HubSpot contact by phone number.

        Args:
            phone: Phone number in E.164 format

        Returns:
            HubSpot contact ID
        """
        self._check_enabled()

        # Search for existing contact by phone
        search_payload = {
            "filterGroups": [
                {
                    "filters": [
                        {
                            "propertyName": "phone",
                            "operator": "EQ",
                            "value": phone,
                        }
                    ]
                }
            ],
        }

        try:
            search_result = await self._make_request("POST", "/crm/v3/objects/contacts/search", search_payload)

            if search_result.get("total", 0) > 0:
                contact_id = search_result["results"][0]["id"]
                logger.info("Found existing HubSpot contact", extra={"contact_id": contact_id, "phone": phone})
                return contact_id

        except httpx.HTTPStatusError as e:
            if e.response.status_code != 404:
                raise

        # Create new contact
        contact_data = {
            "properties": {
                "phone": phone,
                "lifecyclestage": "lead",
            }
        }

        result = await self._make_request("POST", "/crm/v3/objects/contacts", contact_data)
        contact_id = result["id"]

        logger.info("Created new HubSpot contact", extra={"contact_id": contact_id, "phone": phone})
        return contact_id

    async def create_ticket(self, contact_id: str, subject: str, description: str, priority: str = "MEDIUM") -> str:
        """Create a HubSpot ticket and associate it with a contact.

        Args:
            contact_id: HubSpot contact ID
            subject: Ticket subject
            description: Ticket description
            priority: Ticket priority (LOW, MEDIUM, HIGH)

        Returns:
            HubSpot ticket ID
        """
        self._check_enabled()

        ticket_data = {
            "properties": {
                "subject": subject,
                "content": description,
                "hs_pipeline": "0",  # Default pipeline
                "hs_pipeline_stage": "1",  # New ticket stage
                "hs_ticket_priority": priority,
            }
        }

        result = await self._make_request("POST", "/crm/v3/objects/tickets", ticket_data)
        ticket_id = result["id"]

        # Associate ticket with contact
        association_data = [
            {
                "from": {"id": ticket_id},
                "to": {"id": contact_id},
                "type": "ticket_to_contact",
            }
        ]

        try:
            await self._make_request(
                "PUT", "/crm/v4/associations/tickets/contacts/batch/create", {"inputs": association_data}
            )
            logger.info(
                "Created HubSpot ticket and associated with contact",
                extra={"ticket_id": ticket_id, "contact_id": contact_id},
            )
        except Exception as e:
            logger.warning("Failed to associate ticket with contact", extra={"error": str(e)})

        return ticket_id

    async def add_note_to_ticket(self, ticket_id: str, note_body: str) -> None:
        """Add a note to a HubSpot ticket.

        Args:
            ticket_id: HubSpot ticket ID
            note_body: Note content
        """
        self._check_enabled()

        note_data = {
            "properties": {
                "hs_note_body": note_body,
            }
        }

        result = await self._make_request("POST", "/crm/v3/objects/notes", note_data)
        note_id = result["id"]

        # Associate note with ticket
        association_data = [
            {
                "from": {"id": note_id},
                "to": {"id": ticket_id},
                "type": "note_to_ticket",
            }
        ]

        try:
            await self._make_request(
                "PUT", "/crm/v4/associations/notes/tickets/batch/create", {"inputs": association_data}
            )
            logger.info("Added note to HubSpot ticket", extra={"ticket_id": ticket_id, "note_id": note_id})
        except Exception as e:
            logger.warning("Failed to associate note with ticket", extra={"error": str(e)})
