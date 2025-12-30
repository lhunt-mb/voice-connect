"""Unit tests for Pipecat pipeline factory and components."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.orchestrator.prompts import AssistantPrompt, get_prompt
from services.pipecat.escalation_processor import EscalationProcessor
from services.pipecat.pipeline_factory import PipelineConfig
from shared.types import CallStatus, SessionState


@pytest.fixture
def sample_session() -> SessionState:
    """Create a sample session state for testing."""
    return SessionState(
        conversation_id="test-conv-123",
        call_sid="CA123456789",
        stream_sid="MZ123456789",
        caller_phone="+61412345678",
        status=CallStatus.ACTIVE,
        start_time=datetime.now(UTC),
        last_activity=datetime.now(UTC),
        transcript_buffer=[],
        metadata={},
    )


@pytest.fixture
def sample_prompt() -> AssistantPrompt:
    """Create a sample assistant prompt."""
    return AssistantPrompt(
        instructions="You are a helpful assistant.",
        voice="alloy",
        context="Test prompt",
    )


class TestAssistantPrompt:
    """Tests for AssistantPrompt class."""

    def test_to_session_config(self, sample_prompt: AssistantPrompt) -> None:
        """Test conversion to OpenAI session config."""
        config = sample_prompt.to_session_config()

        assert config["instructions"] == "You are a helpful assistant."
        assert config["voice"] == "alloy"

    def test_to_pipecat_messages(self, sample_prompt: AssistantPrompt) -> None:
        """Test conversion to Pipecat message format."""
        messages = sample_prompt.to_pipecat_messages()

        assert len(messages) == 1
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are a helpful assistant."

    def test_to_nova_sonic_config(self, sample_prompt: AssistantPrompt) -> None:
        """Test conversion to Nova Sonic config."""
        config = sample_prompt.to_nova_sonic_config()

        assert config["system_instruction"] == "You are a helpful assistant."
        assert config["voice_id"] == "olivia"  # alloy maps to olivia

    def test_nova_sonic_voice_mapping(self) -> None:
        """Test voice mapping for different OpenAI voices."""
        voice_mappings = [
            ("alloy", "olivia"),
            ("echo", "matteo"),
            ("shimmer", "tiffany"),
            ("verse", "olivia"),
            ("unknown", "olivia"),  # Default fallback
        ]

        for openai_voice, expected_nova_voice in voice_mappings:
            prompt = AssistantPrompt(
                instructions="Test",
                voice=openai_voice,
            )
            config = prompt.to_nova_sonic_config()
            assert (
                config["voice_id"] == expected_nova_voice
            ), f"Voice {openai_voice} should map to {expected_nova_voice}"


class TestPipelineConfig:
    """Tests for PipelineConfig dataclass."""

    def test_default_config(self, sample_prompt: AssistantPrompt, sample_session: SessionState) -> None:
        """Test default pipeline configuration."""
        config = PipelineConfig(
            provider="openai",
            prompt=sample_prompt,
            session=sample_session,
        )

        assert config.provider == "openai"
        assert config.vad_stop_secs == 0.5
        assert config.on_escalation is None

    def test_config_with_escalation(self, sample_prompt: AssistantPrompt, sample_session: SessionState) -> None:
        """Test pipeline configuration with escalation callback."""

        async def mock_escalation(session: SessionState, transcript: str) -> bool:
            return True

        config = PipelineConfig(
            provider="nova",
            prompt=sample_prompt,
            session=sample_session,
            on_escalation=mock_escalation,
            vad_stop_secs=0.3,
        )

        assert config.provider == "nova"
        assert config.vad_stop_secs == 0.3
        assert config.on_escalation is not None


class TestEscalationProcessor:
    """Tests for EscalationProcessor."""

    @pytest.fixture
    def mock_escalation_callback(self) -> AsyncMock:
        """Create a mock escalation callback."""
        return AsyncMock(return_value=True)

    @pytest.fixture
    def escalation_processor(
        self, sample_session: SessionState, mock_escalation_callback: AsyncMock
    ) -> EscalationProcessor:
        """Create an escalation processor for testing."""
        return EscalationProcessor(
            session=sample_session,
            on_escalation=mock_escalation_callback,
        )

    def test_initialization(self, escalation_processor: EscalationProcessor, sample_session: SessionState) -> None:
        """Test escalation processor initialization."""
        assert escalation_processor.session == sample_session
        assert escalation_processor.escalation_triggered is False
        assert escalation_processor._pending_escalation is False  # pyright: ignore[reportPrivateUsage]

    def test_reset(self, escalation_processor: EscalationProcessor) -> None:
        """Test reset functionality."""
        escalation_processor.escalation_triggered = True
        escalation_processor._pending_escalation = True  # pyright: ignore[reportPrivateUsage]

        escalation_processor.reset()

        assert escalation_processor.escalation_triggered is False
        assert escalation_processor._pending_escalation is False  # pyright: ignore[reportPrivateUsage]

    @pytest.mark.asyncio
    async def test_process_non_transcription_frame(
        self, escalation_processor: EscalationProcessor, mock_escalation_callback: AsyncMock
    ) -> None:
        """Test that non-transcription frames pass through unchanged."""
        from pipecat.frames.frames import Frame

        # Mock push_frame
        escalation_processor.push_frame = AsyncMock()

        # Create a non-transcription frame
        frame = MagicMock(spec=Frame)

        from pipecat.processors.frame_processor import FrameDirection

        await escalation_processor.process_frame(frame, FrameDirection.DOWNSTREAM)

        # Should pass frame through
        escalation_processor.push_frame.assert_called()
        # Escalation callback should not be called
        mock_escalation_callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_escalation_keyword(
        self, escalation_processor: EscalationProcessor, mock_escalation_callback: AsyncMock
    ) -> None:
        """Test escalation triggered by keyword."""
        from pipecat.frames.frames import TranscriptionFrame
        from pipecat.processors.frame_processor import FrameDirection

        escalation_processor.push_frame = AsyncMock()

        # Create a transcription frame with escalation keyword
        frame = TranscriptionFrame(text="I want to speak with a human agent please", user_id="user1", timestamp="now")

        await escalation_processor.process_frame(frame, FrameDirection.DOWNSTREAM)

        # Escalation callback should be called
        mock_escalation_callback.assert_called_once()
        assert escalation_processor.escalation_triggered is True

    @pytest.mark.asyncio
    async def test_no_escalation_for_normal_transcript(
        self, escalation_processor: EscalationProcessor, mock_escalation_callback: AsyncMock
    ) -> None:
        """Test that normal transcripts don't trigger escalation."""
        from pipecat.frames.frames import TranscriptionFrame
        from pipecat.processors.frame_processor import FrameDirection

        escalation_processor.push_frame = AsyncMock()

        # Create a transcription frame without escalation keyword
        frame = TranscriptionFrame(text="Hello, how are you today?", user_id="user1", timestamp="now")

        await escalation_processor.process_frame(frame, FrameDirection.DOWNSTREAM)

        # Escalation callback should not be called
        mock_escalation_callback.assert_not_called()
        assert escalation_processor.escalation_triggered is False


class TestGetPrompt:
    """Tests for get_prompt function."""

    def test_get_default_prompt(self) -> None:
        """Test getting default prompt."""
        prompt = get_prompt("default")
        assert prompt is not None
        assert "Australian" in prompt.instructions

    def test_get_technical_prompt(self) -> None:
        """Test getting technical support prompt."""
        prompt = get_prompt("technical")
        assert prompt is not None
        assert "technical support" in prompt.instructions.lower()

    def test_get_sales_prompt(self) -> None:
        """Test getting sales assistant prompt."""
        prompt = get_prompt("sales")
        assert prompt is not None
        assert "sales" in prompt.instructions.lower()

    def test_invalid_prompt_type(self) -> None:
        """Test error handling for invalid prompt type."""
        with pytest.raises(ValueError) as exc_info:
            get_prompt("invalid")
        assert "Unknown prompt type" in str(exc_info.value)
