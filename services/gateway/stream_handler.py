"""WebSocket stream handler for managing Twilio-Voice AI audio bridge."""

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import WebSocket

from services.orchestrator.orchestrator import Orchestrator
from services.orchestrator.voice_client_base import VoiceClientBase
from shared.logging import call_sid_ctx, conversation_id_ctx, stream_sid_ctx
from shared.types import SessionState

logger = logging.getLogger(__name__)


class StreamHandler:
    """Handles bidirectional audio streaming between Twilio and Voice AI (OpenAI/Nova)."""

    def __init__(
        self,
        websocket: WebSocket,
        session: SessionState,
        voice_client: VoiceClientBase,
        orchestrator: Orchestrator,
    ) -> None:
        """Initialize the stream handler."""
        self.websocket = websocket
        self.session = session
        self.voice_client = voice_client
        self.orchestrator = orchestrator
        self._running = False
        self._openai_task: asyncio.Task[None] | None = None

        # Set correlation IDs for logging
        call_sid_ctx.set(session.call_sid)
        stream_sid_ctx.set(session.stream_sid)
        conversation_id_ctx.set(session.conversation_id)

    async def handle_stream(self) -> None:
        """Handle the complete stream lifecycle with dual concurrent tasks."""
        try:
            self._running = True

            # Connect to Voice AI (OpenAI or Nova)
            await self.voice_client.connect(self.session.conversation_id)

            # Create two concurrent tasks following blog article pattern:
            # 1. Receive from Twilio → Send to OpenAI
            # 2. Receive from OpenAI → Send to Twilio
            twilio_to_openai_task = asyncio.create_task(self._handle_twilio_to_openai())
            openai_to_twilio_task = asyncio.create_task(self._handle_openai_to_twilio())

            # Wait for either task to complete (usually means stream ended)
            _, pending = await asyncio.wait(
                [twilio_to_openai_task, openai_to_twilio_task], return_when=asyncio.FIRST_COMPLETED
            )

            # Cancel remaining tasks
            for task in pending:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

        except Exception as e:
            logger.error("Stream handler error", extra={"error": str(e)}, exc_info=True)
        finally:
            await self._cleanup()

    async def _handle_twilio_to_openai(self) -> None:
        """Receive audio from Twilio and forward to OpenAI.

        Following the blog article pattern: iterate over Twilio messages and
        send audio payloads directly to OpenAI.
        """
        try:
            async for message_text in self._iter_twilio_messages():
                try:
                    message = json.loads(message_text)
                    event_type = message.get("event")

                    if event_type == "start":
                        start_data = message.get("start", {})
                        logger.info(
                            "Twilio stream started",
                            extra={
                                "stream_sid": message.get("streamSid"),
                                "call_sid": start_data.get("callSid"),
                            },
                        )

                    elif event_type == "media":
                        # Forward audio to OpenAI (payload is already base64-encoded)
                        media = message.get("media", {})
                        payload = media.get("payload")

                        if payload:
                            # Send base64 audio directly to Voice AI (no decode/re-encode needed)
                            await self.voice_client.send_audio_base64(payload)

                    elif event_type == "stop":
                        logger.info("Twilio stream stopped", extra={"stream_sid": message.get("streamSid")})
                        self._running = False
                        break

                except json.JSONDecodeError as e:
                    logger.warning("Failed to decode Twilio message", extra={"error": str(e)})

        except Exception as e:
            logger.error("Error in Twilio→OpenAI handler", extra={"error": str(e)}, exc_info=True)
            self._running = False

    async def _iter_twilio_messages(self) -> AsyncIterator[str]:
        """Async iterator for Twilio WebSocket messages."""
        while self._running:
            try:
                data = await asyncio.wait_for(self.websocket.receive_text(), timeout=1.0)
                yield data
            except TimeoutError:
                continue
            except Exception as e:
                logger.error("Error receiving from Twilio", extra={"error": str(e)})
                break

    async def _handle_openai_to_twilio(self) -> None:
        """Receive events from OpenAI and forward audio to Twilio.

        Following the blog article pattern: iterate over OpenAI events and
        forward audio deltas to Twilio.
        """
        try:
            async for event in self.voice_client.events():
                if not self._running:
                    break

                event_type = event.get("type")
                logger.info("Processing OpenAI event", extra={"event_type": event_type})

                if event_type == "response.audio.delta":
                    # Get audio delta and send to Twilio
                    audio_b64 = event.get("delta")
                    if audio_b64:
                        # Send to Twilio (no decode/re-encode needed - already base64)
                        twilio_message = {
                            "event": "media",
                            "streamSid": self.session.stream_sid,
                            "media": {"payload": audio_b64},
                        }
                        await self.websocket.send_json(twilio_message)
                        logger.info("Sent audio chunk to Twilio", extra={"audio_length": len(audio_b64)})

                elif event_type == "conversation.item.input_audio_transcription.completed":
                    # Handle user transcript for escalation checking
                    await self._handle_input_transcript(event)

                elif event_type == "response.done":
                    logger.info("OpenAI response completed")

                elif event_type == "error":
                    logger.error("OpenAI error event", extra={"event": event})

        except Exception as e:
            logger.error("Error in OpenAI→Twilio handler", extra={"error": str(e)}, exc_info=True)
            self._running = False

    async def _handle_input_transcript(self, event: dict[str, Any]) -> None:
        """Handle completed user transcript from OpenAI.

        Check for escalation triggers.
        """
        transcript = event.get("transcript", "")
        if not transcript:
            return

        logger.info("User transcript", extra={"transcript": transcript})

        # Check for escalation
        try:
            escalated = await self.orchestrator.check_and_handle_escalation(self.session, transcript)

            if escalated:
                # Inform user via OpenAI audio
                await self._send_escalation_message()

                # End the stream - this will trigger the action URL
                # which will check for the escalation token and route appropriately
                self._running = False

        except Exception as e:
            logger.error("Error checking escalation", extra={"error": str(e)}, exc_info=True)

    async def _send_escalation_message(self) -> None:
        """Send a message to user about escalation via OpenAI.

        This sends a text message to OpenAI which will generate audio
        to inform the user they're being transferred to an agent.
        """
        logger.info("Sending escalation message to user")

        try:
            # Cancel any current response in progress
            await self.voice_client.cancel_response()

            # Give Voice AI a moment to process the cancellation
            await asyncio.sleep(0.1)

            # Send a text message to Voice AI to generate audio response
            escalation_text = (
                "I understand you'd like to speak with a human agent. "
                "Let me transfer you now. Please hold for just a moment."
            )

            await self.voice_client.send_user_message(escalation_text)

            # Wait for Voice AI to finish generating and sending the audio response
            # We'll wait for the response.done event
            async for event in self.voice_client.events():
                event_type = event.get("type")

                if event_type == "response.audio.delta":
                    # Forward audio to Twilio
                    audio_b64 = event.get("delta")
                    if audio_b64:
                        twilio_message = {
                            "event": "media",
                            "streamSid": self.session.stream_sid,
                            "media": {"payload": audio_b64},
                        }
                        await self.websocket.send_json(twilio_message)

                elif event_type == "response.done":
                    logger.info("Escalation message sent to user")
                    break

                elif event_type == "error":
                    logger.error("Error sending escalation message", extra={"event": event})
                    break

            # Give a brief pause for the audio to finish playing
            await asyncio.sleep(0.5)

        except Exception as e:
            logger.error("Failed to send escalation message", extra={"error": str(e)}, exc_info=True)

    async def _cleanup(self) -> None:
        """Clean up resources."""
        logger.info("Cleaning up stream handler")

        if self._openai_task and not self._openai_task.done():
            self._openai_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._openai_task

        await self.voice_client.close()
