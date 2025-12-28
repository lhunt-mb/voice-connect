"""Escalation logic and policies."""

import logging
import re
from datetime import UTC, datetime

from shared.types import EscalationReason, SessionState

logger = logging.getLogger(__name__)

# Keywords that trigger escalation
ESCALATION_KEYWORDS = [
    r"\bagent\b",
    r"\bhuman\b",
    r"\brepresentative\b",
    r"\bperson\b",
    r"\boperator\b",
    r"\bhelp\b.*\breal\b",
    r"\bspeak\b.*\bsomeone\b",
    r"\btalk\b.*\bsomeone\b",
]


def check_escalation_needed(session: SessionState, transcript: str) -> tuple[bool, EscalationReason | None]:
    """Check if escalation is needed based on conversation state and transcript.

    Args:
        session: Current session state
        transcript: Recent transcript text

    Returns:
        Tuple of (should_escalate, reason)
    """
    # Check for escalation keywords in transcript
    transcript_lower = transcript.lower()
    for pattern in ESCALATION_KEYWORDS:
        if re.search(pattern, transcript_lower):
            logger.info(
                "Escalation keyword detected",
                extra={"conversation_id": session.conversation_id, "pattern": pattern},
            )
            return True, EscalationReason.KEYWORD_DETECTED

    # Add session transcript buffer for context
    session.transcript_buffer.append(transcript)
    # Keep only last 10 snippets
    if len(session.transcript_buffer) > 10:
        session.transcript_buffer = session.transcript_buffer[-10:]

    # Additional escalation logic can be added here
    # For example:
    # - Conversation duration threshold
    # - Number of user turns without resolution
    # - Sentiment analysis

    return False, None


def generate_escalation_summary(session: SessionState) -> str:
    """Generate a summary of the conversation for escalation.

    Args:
        session: Session state with transcript buffer

    Returns:
        Summary text
    """
    # Join recent transcript snippets
    transcript_snippets = " | ".join(session.transcript_buffer[-5:])  # Last 5 snippets

    duration_seconds = (datetime.now(UTC) - session.start_time).total_seconds()
    duration_str = f"{int(duration_seconds / 60)}m {int(duration_seconds % 60)}s"

    summary = f"""
Call Duration: {duration_str}
Caller: {session.caller_phone or "Unknown"}
Recent Conversation: {transcript_snippets if transcript_snippets else "No transcript available"}
Intent: User requested human assistance
"""

    return summary.strip()
