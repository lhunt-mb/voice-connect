"""Tests for escalation logic.

Note: Keyword-based escalation has been removed. Escalation is now handled
by the AI via the escalate_to_human tool. These tests cover the remaining
escalation utilities.
"""

import pytest

from services.orchestrator.escalation import generate_escalation_summary
from shared.types import CallStatus, SessionState


@pytest.fixture
def sample_session() -> SessionState:
    """Create a sample session state."""
    return SessionState(
        conversation_id="test-conv-123",
        call_sid="CA123456",
        stream_sid="ST123456",
        caller_phone="+61400000000",
        status=CallStatus.ACTIVE,
    )


@pytest.mark.unit
def test_generate_escalation_summary(sample_session: SessionState) -> None:
    """Test escalation summary generation."""
    sample_session.transcript_buffer = [
        "Hello",
        "I have a question",
        "Can you help me?",
        "I need to speak with an agent",
    ]

    summary = generate_escalation_summary(sample_session)

    assert "Call Duration:" in summary
    assert sample_session.caller_phone and sample_session.caller_phone in summary
    assert "Recent Conversation:" in summary
    assert "I need to speak with an agent" in summary


@pytest.mark.unit
def test_generate_escalation_summary_no_transcript(sample_session: SessionState) -> None:
    """Test escalation summary with no transcript."""
    sample_session.transcript_buffer = []

    summary = generate_escalation_summary(sample_session)

    assert "Call Duration:" in summary
    assert "No transcript available" in summary
