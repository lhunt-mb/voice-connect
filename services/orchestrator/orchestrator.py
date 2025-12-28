"""Main orchestrator for managing conversation flow and escalations."""

import logging
from datetime import UTC, datetime, timedelta

from services.orchestrator.dynamo_repository import DynamoRepository
from services.orchestrator.escalation import check_escalation_needed, generate_escalation_summary
from services.orchestrator.hubspot_client import HubSpotClient
from services.orchestrator.token_generator import generate_token
from shared.config import Settings
from shared.logging import handover_id_ctx
from shared.types import CallStatus, EscalationReason, HandoverPayload, SessionState

logger = logging.getLogger(__name__)


class Orchestrator:
    """Orchestrator for managing conversation state and integrations."""

    def __init__(self, settings: Settings) -> None:
        """Initialize the orchestrator."""
        self.settings = settings
        self.dynamo_repo = DynamoRepository(settings)
        self.hubspot_client = HubSpotClient(settings)

    async def check_and_handle_escalation(self, session: SessionState, transcript: str) -> bool:
        """Check if escalation is needed and handle it.

        Args:
            session: Current session state
            transcript: Recent transcript text

        Returns:
            True if escalation was triggered, False otherwise
        """
        should_escalate, reason = check_escalation_needed(session, transcript)

        if not should_escalate:
            return False

        logger.info(
            "Escalation triggered",
            extra={"conversation_id": session.conversation_id, "reason": reason},
        )

        await self.execute_escalation(session, reason or EscalationReason.AGENT_DECISION)
        return True

    async def execute_escalation(self, session: SessionState, reason: EscalationReason) -> str:
        """Execute the escalation process.

        1. Generate handover token
        2. Create/update HubSpot contact
        3. Create HubSpot ticket
        4. Store handover in DynamoDB
        5. Initiate call to Amazon Connect with DTMF

        Args:
            session: Current session state
            reason: Escalation reason

        Returns:
            Handover token
        """
        session.status = CallStatus.ESCALATING

        # Generate handover token
        token = generate_token(self.settings.token_length)
        handover_id_ctx.set(token)

        logger.info(
            "Starting escalation process",
            extra={
                "conversation_id": session.conversation_id,
                "handover_id": token,
                "reason": reason.value,
            },
        )

        # Generate conversation summary
        summary = generate_escalation_summary(session)

        # Create/update HubSpot contact (if enabled)
        hubspot_contact_id = None
        hubspot_ticket_id = None

        if self.hubspot_client.enabled:
            try:
                if session.caller_phone:
                    hubspot_contact_id = await self.hubspot_client.upsert_contact(session.caller_phone)
                else:
                    # Create contact with placeholder if no phone available
                    hubspot_contact_id = await self.hubspot_client.upsert_contact("+10000000000")

                # Create HubSpot ticket
                ticket_subject = f"Voice Escalation - {session.conversation_id}"
                priority_map = {"low": "LOW", "medium": "MEDIUM", "high": "HIGH"}
                priority = priority_map.get(session.metadata.get("priority", "medium"), "MEDIUM")

                hubspot_ticket_id = await self.hubspot_client.create_ticket(
                    hubspot_contact_id,
                    ticket_subject,
                    summary,
                    priority,
                )

                # Add metadata note
                metadata_note = f"""
Conversation ID: {session.conversation_id}
Call SID: {session.call_sid}
Stream SID: {session.stream_sid}
Escalation Reason: {reason.value}
Handover Token: {token}
                """
                await self.hubspot_client.add_note_to_ticket(hubspot_ticket_id, metadata_note.strip())

                logger.info(
                    "Created HubSpot ticket for escalation",
                    extra={
                        "conversation_id": session.conversation_id,
                        "hubspot_contact_id": hubspot_contact_id,
                        "hubspot_ticket_id": hubspot_ticket_id,
                    },
                )

            except Exception as e:
                logger.error("Failed to create HubSpot records", extra={"error": str(e)}, exc_info=True)
                # Continue with escalation even if HubSpot fails
        else:
            logger.info("HubSpot integration disabled, skipping CRM updates")

        # Store handover in DynamoDB
        expires_at = datetime.now(UTC) + timedelta(seconds=self.settings.token_ttl_seconds)

        handover_payload = HandoverPayload(
            token=token,
            conversation_id=session.conversation_id,
            created_at=datetime.now(UTC),
            expires_at=expires_at,
            caller_phone=session.caller_phone,
            hubspot_contact_id=hubspot_contact_id,
            hubspot_ticket_id=hubspot_ticket_id,
            summary=summary,
            intent=session.metadata.get("intent"),
            priority=session.metadata.get("priority", "medium"),
            escalation_reason=reason,
        )

        self.dynamo_repo.put_handover(handover_payload)

        # Store token in session metadata for later use during call redirect
        session.metadata["handover_token"] = token

        # Note: We no longer initiate the Connect call here.
        # Instead, the stream handler will redirect the active Twilio call
        # to a TwiML endpoint that handles the dial to Connect.
        # This keeps the caller on the line instead of disconnecting them.

        session.status = CallStatus.ESCALATING
        logger.info("Escalation prepared", extra={"conversation_id": session.conversation_id, "handover_id": token})

        return token
