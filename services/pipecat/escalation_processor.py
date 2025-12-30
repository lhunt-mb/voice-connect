"""Escalation frame processor for Pipecat pipelines.

This processor intercepts transcription frames and checks for escalation
keywords, triggering the escalation workflow when detected.
"""

import logging
from collections.abc import Callable, Coroutine
from typing import Any

from pipecat.frames.frames import (
    EndFrame,
    Frame,
    InterimTranscriptionFrame,
    TranscriptionFrame,
    TTSSpeakFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from services.orchestrator.escalation import check_escalation_needed
from shared.types import SessionState

logger = logging.getLogger(__name__)


class EscalationProcessor(FrameProcessor):
    """Processor that monitors transcriptions for escalation triggers.

    This processor sits in the pipeline and intercepts transcription frames,
    checking them against escalation keywords. When an escalation is triggered,
    it invokes the escalation callback and ends the pipeline so the action URL
    can handle the transfer.

    Attributes:
        session: The current session state
        on_escalation: Async callback invoked when escalation is triggered
        escalation_triggered: Whether escalation has been triggered
    """

    def __init__(
        self,
        session: SessionState,
        on_escalation: Callable[[SessionState, str], Coroutine[Any, Any, bool]],
        escalation_message: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the escalation processor.

        Args:
            session: Current session state
            on_escalation: Async callback when escalation triggers.
                          Should return True if escalation was successful.
            escalation_message: Optional custom message to speak during escalation
            **kwargs: Additional arguments for FrameProcessor
        """
        super().__init__(**kwargs)
        self.session = session
        self.on_escalation = on_escalation
        self.escalation_message = escalation_message or (
            "I understand you'd like to speak with a human agent. "
            "Let me transfer you now. Please hold for just a moment."
        )
        self.escalation_triggered = False
        self._pending_escalation = False

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        """Process frames and check for escalation triggers.

        Args:
            frame: The frame to process
            direction: Frame direction (downstream or upstream)
        """
        await super().process_frame(frame, direction)

        # Skip if escalation already triggered
        if self.escalation_triggered:
            await self.push_frame(frame, direction)
            return

        # Check transcription frames for escalation keywords
        if isinstance(frame, TranscriptionFrame) and not isinstance(frame, InterimTranscriptionFrame):
            transcript = frame.text
            if transcript:
                logger.info(
                    "Processing transcript for escalation",
                    extra={
                        "transcript": transcript,
                        "conversation_id": self.session.conversation_id,
                    },
                )

                # Check if escalation is needed
                should_escalate, reason = check_escalation_needed(self.session, transcript)

                if should_escalate and not self._pending_escalation:
                    self._pending_escalation = True
                    logger.info(
                        "Escalation triggered",
                        extra={
                            "reason": reason.value if reason else "unknown",
                            "conversation_id": self.session.conversation_id,
                        },
                    )

                    # Execute escalation workflow
                    try:
                        escalated = await self.on_escalation(self.session, transcript)

                        if escalated:
                            self.escalation_triggered = True
                            logger.info(
                                "Escalation successful, handover token stored in session",
                                extra={
                                    "token": self.session.metadata.get("handover_token", ""),
                                },
                            )
                            # The handover_token is now stored in session metadata.
                            # When the WebSocket closes (naturally or by us), the action URL
                            # will check for this token and dial Amazon Connect.
                            #
                            # Note: We tried using Twilio REST API to redirect the call,
                            # but it returns 404 for calls that are in a Media Stream.
                            # Instead, we rely on the action URL callback mechanism.

                            # Push TTS message to inform user about the transfer.
                            logger.info(
                                "Pushing escalation message",
                                extra={"conversation_id": self.session.conversation_id},
                            )
                            await self.push_frame(
                                TTSSpeakFrame(text=self.escalation_message),
                                FrameDirection.DOWNSTREAM,
                            )

                            # Push EndFrame to close our side of the pipeline
                            await self.push_frame(EndFrame(), FrameDirection.DOWNSTREAM)
                            return  # Don't push the original frame, pipeline is ending
                        else:
                            logger.warning("Escalation callback returned False")
                            self._pending_escalation = False

                    except Exception as e:
                        logger.error(
                            "Escalation failed",
                            extra={"error": str(e)},
                            exc_info=True,
                        )
                        self._pending_escalation = False

        # Pass frame downstream
        await self.push_frame(frame, direction)

    def reset(self) -> None:
        """Reset the escalation state.

        Call this when starting a new conversation or after handling escalation.
        """
        self.escalation_triggered = False
        self._pending_escalation = False


class TranscriptAggregatorProcessor(FrameProcessor):
    """Processor that aggregates transcription frames for context.

    This processor collects all transcription frames and maintains
    a running transcript buffer, useful for generating conversation
    summaries during escalation.
    """

    def __init__(
        self,
        session: SessionState,
        max_buffer_size: int = 10,
        **kwargs: Any,
    ) -> None:
        """Initialize the transcript aggregator.

        Args:
            session: Session state to update with transcripts
            max_buffer_size: Maximum number of transcript snippets to keep
            **kwargs: Additional arguments for FrameProcessor
        """
        super().__init__(**kwargs)
        self.session = session
        self.max_buffer_size = max_buffer_size

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        """Process frames and aggregate transcripts.

        Args:
            frame: The frame to process
            direction: Frame direction
        """
        await super().process_frame(frame, direction)

        # Capture final transcription frames (not interim)
        if isinstance(frame, TranscriptionFrame) and not isinstance(frame, InterimTranscriptionFrame):
            transcript = frame.text
            if transcript:
                self.session.transcript_buffer.append(transcript)

                # Keep buffer size limited
                if len(self.session.transcript_buffer) > self.max_buffer_size:
                    self.session.transcript_buffer = self.session.transcript_buffer[-self.max_buffer_size :]

        # Always pass frame downstream
        await self.push_frame(frame, direction)
