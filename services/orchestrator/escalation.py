"""Escalation logic and policies.

Escalation is now handled by the AI via the escalate_to_human tool,
which allows context-aware decisions about when to transfer to a human agent.
"""

import logging
from datetime import UTC, datetime

from shared.types import SessionState

logger = logging.getLogger(__name__)


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
