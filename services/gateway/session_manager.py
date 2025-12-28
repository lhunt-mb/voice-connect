"""Session manager for tracking active call sessions."""

import logging
import uuid
from datetime import UTC, datetime

from shared.types import SessionState

logger = logging.getLogger(__name__)


class SessionManager:
    """Manager for active call sessions."""

    def __init__(self) -> None:
        """Initialize the session manager."""
        self.sessions: dict[str, SessionState] = {}

    def create_session(self, call_sid: str, stream_sid: str, caller_phone: str | None = None) -> SessionState:
        """Create a new session.

        Args:
            call_sid: Twilio call SID
            stream_sid: Twilio stream SID
            caller_phone: Caller phone number

        Returns:
            New session state
        """
        conversation_id = str(uuid.uuid4())

        session = SessionState(
            conversation_id=conversation_id,
            call_sid=call_sid,
            stream_sid=stream_sid,
            caller_phone=caller_phone,
        )

        self.sessions[stream_sid] = session

        logger.info(
            "Created new session",
            extra={
                "conversation_id": conversation_id,
                "call_sid": call_sid,
                "stream_sid": stream_sid,
            },
        )

        return session

    def get_session(self, stream_sid: str) -> SessionState | None:
        """Get session by stream SID."""
        return self.sessions.get(stream_sid)

    def get_session_by_call_sid(self, call_sid: str) -> SessionState | None:
        """Get session by call SID.

        Args:
            call_sid: Twilio call SID

        Returns:
            Session state if found, None otherwise
        """
        for session in self.sessions.values():
            if session.call_sid == call_sid:
                return session
        return None

    def update_activity(self, stream_sid: str) -> None:
        """Update last activity timestamp for a session."""
        session = self.sessions.get(stream_sid)
        if session:
            session.last_activity = datetime.now(UTC)

    def remove_session(self, stream_sid: str) -> SessionState | None:
        """Remove and return a session."""
        session = self.sessions.pop(stream_sid, None)
        if session:
            logger.info(
                "Removed session",
                extra={
                    "conversation_id": session.conversation_id,
                    "stream_sid": stream_sid,
                },
            )
        return session

    def get_all_sessions(self) -> list[SessionState]:
        """Get all active sessions."""
        return list(self.sessions.values())
