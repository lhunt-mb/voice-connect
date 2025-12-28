"""Shared type definitions."""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CallStatus(str, Enum):
    """Call status enumeration."""

    ACTIVE = "active"
    ESCALATING = "escalating"
    COMPLETED = "completed"
    FAILED = "failed"


class EscalationReason(str, Enum):
    """Escalation reason enumeration."""

    USER_REQUEST = "user_request"
    KEYWORD_DETECTED = "keyword_detected"
    AGENT_DECISION = "agent_decision"
    ERROR = "error"


class SessionState(BaseModel):
    """Session state for an active call."""

    conversation_id: str = Field(..., description="Unique conversation identifier")
    call_sid: str = Field(..., description="Twilio call SID")
    stream_sid: str = Field(..., description="Twilio stream SID")
    caller_phone: str | None = Field(default=None, description="Caller phone number")
    status: CallStatus = Field(default=CallStatus.ACTIVE, description="Current call status")
    start_time: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Session start time")
    last_activity: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Last activity timestamp")
    transcript_buffer: list[str] = Field(default_factory=list, description="Recent transcript snippets")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class HandoverPayload(BaseModel):
    """Handover payload stored in DynamoDB."""

    token: str = Field(..., description="10-digit handover token")
    conversation_id: str = Field(..., description="Conversation identifier")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Creation timestamp")
    expires_at: datetime = Field(..., description="Expiration timestamp")
    caller_phone: str | None = Field(default=None, description="Caller phone number")
    hubspot_contact_id: str | None = Field(default=None, description="HubSpot contact ID")
    hubspot_ticket_id: str | None = Field(default=None, description="HubSpot ticket ID")
    summary: str = Field(..., description="Conversation summary")
    intent: str | None = Field(default=None, description="Detected intent")
    priority: str = Field(default="medium", description="Escalation priority")
    escalation_reason: EscalationReason = Field(..., description="Reason for escalation")


class HubSpotContact(BaseModel):
    """HubSpot contact representation."""

    contact_id: str = Field(..., description="HubSpot contact ID")
    phone: str | None = Field(default=None, description="Phone number")
    email: str | None = Field(default=None, description="Email address")
    firstname: str | None = Field(default=None, description="First name")
    lastname: str | None = Field(default=None, description="Last name")


class HubSpotTicket(BaseModel):
    """HubSpot ticket representation."""

    ticket_id: str = Field(..., description="HubSpot ticket ID")
    subject: str = Field(..., description="Ticket subject")
    content: str = Field(..., description="Ticket content")
    priority: str = Field(default="MEDIUM", description="Ticket priority")


class TwilioMediaEvent(BaseModel):
    """Twilio Media Stream event."""

    event: str = Field(..., description="Event type: start, media, stop")
    streamSid: str | None = Field(default=None, description="Stream SID")
    media: dict[str, Any] | None = Field(default=None, description="Media payload")
    start: dict[str, Any] | None = Field(default=None, description="Start event data")
    stop: dict[str, Any] | None = Field(default=None, description="Stop event data")


class OpenAIRealtimeEvent(BaseModel):
    """OpenAI Realtime API event."""

    type: str = Field(..., description="Event type")
    event_id: str | None = Field(default=None, description="Event ID")
    data: dict[str, Any] = Field(default_factory=dict, description="Event data")
