"""Tests for escalation logic."""

import pytest

from services.orchestrator.escalation import check_escalation_needed, generate_escalation_summary
from shared.types import CallStatus, EscalationReason, SessionState


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
def test_escalation_keyword_agent(sample_session: SessionState) -> None:
    """Test escalation with 'agent' keyword."""
    should_escalate, reason = check_escalation_needed(sample_session, "I need to speak with an agent")

    assert should_escalate is True
    assert reason == EscalationReason.KEYWORD_DETECTED


@pytest.mark.unit
def test_escalation_keyword_human(sample_session: SessionState) -> None:
    """Test escalation with 'human' keyword."""
    should_escalate, reason = check_escalation_needed(sample_session, "Can I talk to a human?")

    assert should_escalate is True
    assert reason == EscalationReason.KEYWORD_DETECTED


@pytest.mark.unit
def test_escalation_keyword_representative(sample_session: SessionState) -> None:
    """Test escalation with 'representative' keyword."""
    should_escalate, reason = check_escalation_needed(sample_session, "I want a representative please")

    assert should_escalate is True
    assert reason == EscalationReason.KEYWORD_DETECTED


@pytest.mark.unit
def test_no_escalation(sample_session: SessionState) -> None:
    """Test no escalation with normal conversation."""
    should_escalate, reason = check_escalation_needed(sample_session, "Hello, I have a question about my account")

    assert should_escalate is False
    assert reason is None


@pytest.mark.unit
def test_escalation_case_insensitive(sample_session: SessionState) -> None:
    """Test escalation keyword detection is case-insensitive."""
    should_escalate, reason = check_escalation_needed(sample_session, "I NEED TO SPEAK WITH AN AGENT")

    assert should_escalate is True
    assert reason == EscalationReason.KEYWORD_DETECTED


@pytest.mark.unit
def test_transcript_buffer(sample_session: SessionState) -> None:
    """Test that transcript buffer is updated."""
    initial_buffer_len = len(sample_session.transcript_buffer)

    check_escalation_needed(sample_session, "First message")
    check_escalation_needed(sample_session, "Second message")

    assert len(sample_session.transcript_buffer) == initial_buffer_len + 2


@pytest.mark.unit
def test_transcript_buffer_limit(sample_session: SessionState) -> None:
    """Test that transcript buffer is limited to 10 entries."""
    for i in range(15):
        check_escalation_needed(sample_session, f"Message {i}")

    assert len(sample_session.transcript_buffer) <= 10


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
