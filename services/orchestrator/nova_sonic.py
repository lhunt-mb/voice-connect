"""Amazon Nova 2 Sonic speech-to-speech client using Bedrock streaming API."""

import asyncio
import audioop
import base64
import contextlib
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from aws_sdk_bedrock_runtime.client import BedrockRuntimeClient
from aws_sdk_bedrock_runtime.config import Config
from aws_sdk_bedrock_runtime.models import (
    BidirectionalInputPayloadPart,
    InvokeModelWithBidirectionalStreamInputChunk,
    InvokeModelWithBidirectionalStreamOperationInput,
)
from smithy_aws_core.identity.environment import EnvironmentCredentialsResolver

from services.orchestrator.prompts import DEFAULT_ASSISTANT_PROMPT, AssistantPrompt
from services.orchestrator.tools import NOVA_TOOLS
from services.orchestrator.voice_client_base import VoiceClientBase
from shared.config import Settings

logger = logging.getLogger(__name__)


class NovaClient(VoiceClientBase):
    """Client for Amazon Nova 2 Sonic speech-to-speech model via Bedrock."""

    def __init__(
        self,
        settings: Settings,
        prompt: AssistantPrompt | None = None,
        tool_executor: Any = None,
    ) -> None:
        """Initialize the Nova 2 Sonic client.

        Args:
            settings: Application settings
            prompt: AI assistant prompt configuration. Defaults to DEFAULT_ASSISTANT_PROMPT
            tool_executor: Optional ToolExecutor for handling tool calls
        """
        self.settings = settings
        self.prompt = prompt or DEFAULT_ASSISTANT_PROMPT
        self.tool_executor = tool_executor
        self.conversation_id: str | None = None
        self._event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._audio_input_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._response_task: asyncio.Task[None] | None = None
        self._audio_sender_task: asyncio.Task[None] | None = None
        self._connected = False
        self._stream_response: Any = None
        self._audio_stream_started = False
        self._response_started = False  # Track if we've emitted response.created
        self._escalation_triggered = False
        self._escalation_reason: str | None = None

        # Get Nova region (fallback to aws_region for backward compatibility)
        nova_region = settings.nova_region or settings.aws_region

        # Initialize Bedrock client with experimental SDK
        config = Config(
            endpoint_uri=f"https://bedrock-runtime.{nova_region}.amazonaws.com",
            region=nova_region,
            aws_credentials_identity_resolver=EnvironmentCredentialsResolver(),
        )
        self.bedrock_client = BedrockRuntimeClient(config=config)
        self.model_id = "amazon.nova-2-sonic-v1:0"

        logger.info(
            "Initialized Nova 2 Sonic client",
            extra={"nova_region": nova_region, "model_id": self.model_id},
        )

        # Session identifiers for Nova 2 Sonic events
        self.prompt_name = str(uuid.uuid4())
        self.content_name = str(uuid.uuid4())
        self.audio_content_name = str(uuid.uuid4())

    async def connect(self, conversation_id: str) -> None:
        """Connect to Nova 2 Sonic (initialize bidirectional stream).

        Args:
            conversation_id: Unique conversation identifier
        """
        self.conversation_id = conversation_id

        try:
            # Initialize bidirectional stream
            self._stream_response = await self.bedrock_client.invoke_model_with_bidirectional_stream(
                InvokeModelWithBidirectionalStreamOperationInput(model_id=self.model_id)
            )
            self._connected = True

            logger.info(
                "Nova 2 Sonic bidirectional stream initialized",
                extra={"conversation_id": conversation_id, "model": self.model_id},
            )

            # Send initialization events (session start + prompt start + system prompt)
            await self._initialize_session()

            # Start response processing task AFTER initialization
            self._response_task = asyncio.create_task(self._process_responses())

            # Start audio sender task (will start audio stream when first audio arrives)
            self._audio_sender_task = asyncio.create_task(self._process_audio_queue())

        except Exception as e:
            logger.error(
                "Failed to initialize Nova 2 Sonic stream",
                extra={"error": str(e), "conversation_id": conversation_id},
                exc_info=True,
            )
            raise

    async def _initialize_session(self) -> None:
        """Send Nova 2 Sonic session initialization events."""
        # Session start event - match AWS sample exactly
        session_start_config: dict[str, Any] = {
            "event": {
                "sessionStart": {
                    "inferenceConfiguration": {
                        "maxTokens": 1024,
                        "topP": 0.9,
                        "temperature": 0.7,
                    }
                }
            }
        }

        # Add tools if tool executor is configured
        if self.tool_executor:
            session_start_config["event"]["sessionStart"]["tools"] = NOVA_TOOLS

        await self._send_event(session_start_config)

        # Prompt start event - configures output formats
        prompt_start = {
            "event": {
                "promptStart": {
                    "promptName": self.prompt_name,
                    "textOutputConfiguration": {"mediaType": "text/plain"},
                    "audioOutputConfiguration": {
                        "mediaType": "audio/lpcm",
                        "sampleRateHertz": 24000,  # Nova 2 Sonic requires 24kHz output
                        "sampleSizeBits": 16,
                        "channelCount": 1,
                        "voiceId": "olivia",
                        "encoding": "base64",
                        "audioType": "SPEECH",
                    },
                }
            }
        }
        await self._send_event(prompt_start)

        # System message with assistant instructions
        prompt_config = self.prompt.to_session_config()
        system_prompt = prompt_config["instructions"]

        await self._send_text_content(system_prompt, role="SYSTEM")

        logger.info("Nova 2 Sonic session initialized", extra={"conversation_id": self.conversation_id})

    async def _trigger_initial_greeting(self) -> None:
        """Trigger Nova 2 Sonic to generate an initial greeting."""
        # CRITICAL: Nova Sonic requires audio streaming to be started before it will respond
        # Send SYSTEM_SPEECH to trigger greeting, then immediately start audio stream
        greeting_message = "Hello! How can I help you today?"
        await self._send_text_content(greeting_message, role="SYSTEM_SPEECH")

        # Now start the audio content stream - this tells Nova we're ready to receive responses
        # The audio sender task will handle the actual audio streaming
        await self._start_audio_content()
        self._audio_stream_started = True

        logger.info("Triggered initial greeting from Nova 2 Sonic", extra={"conversation_id": self.conversation_id})

    async def _send_event(self, event_dict: dict[str, Any]) -> None:
        """Send an event to the Nova 2 Sonic stream.

        Args:
            event_dict: Event dictionary to send
        """
        if not self._stream_response or not self._connected:
            logger.warning("Stream not connected, cannot send event")
            return

        event_json = json.dumps(event_dict)
        logger.debug(
            "Sending event to Nova",
            extra={
                "conversation_id": self.conversation_id,
                "event_type": list(event_dict.get("event", {}).keys()),
                "event_json": event_json,
            },
        )
        event = InvokeModelWithBidirectionalStreamInputChunk(
            value=BidirectionalInputPayloadPart(bytes_=event_json.encode("utf-8"))
        )

        try:
            await self._stream_response.input_stream.send(event)
            logger.debug("Event sent successfully", extra={"conversation_id": self.conversation_id})
        except Exception as e:
            logger.error(
                "Failed to send event to Nova stream",
                extra={"error": str(e), "conversation_id": self.conversation_id},
                exc_info=True,
            )

    async def _send_text_content(self, text: str, role: str = "USER") -> None:
        """Send text content to Nova 2 Sonic.

        Args:
            text: Text to send
            role: Role (USER, SYSTEM, ASSISTANT)
        """
        content_id = str(uuid.uuid4())

        # Content start
        content_start = {
            "event": {
                "contentStart": {
                    "promptName": self.prompt_name,
                    "contentName": content_id,
                    "type": "TEXT",
                    "role": role,
                    "interactive": False,
                    "textInputConfiguration": {"mediaType": "text/plain"},
                }
            }
        }
        await self._send_event(content_start)

        # Text input
        text_input = {
            "event": {
                "textInput": {
                    "promptName": self.prompt_name,
                    "contentName": content_id,
                    "content": text,
                }
            }
        }
        await self._send_event(text_input)

        # Content end
        await self._end_content(content_id)

    async def _start_audio_content(self) -> None:
        """Start an audio content block."""
        content_start = {
            "event": {
                "contentStart": {
                    "promptName": self.prompt_name,
                    "contentName": self.audio_content_name,
                    "type": "AUDIO",
                    "interactive": True,
                    "role": "USER",
                    "audioInputConfiguration": {
                        "mediaType": "audio/lpcm",
                        "sampleRateHertz": 16000,  # Nova 2 Sonic requires 16kHz input
                        "sampleSizeBits": 16,
                        "channelCount": 1,
                        "audioType": "SPEECH",
                        "encoding": "base64",
                    },
                }
            }
        }
        await self._send_event(content_start)

    async def _end_content(self, content_id: str) -> None:
        """End a content block.

        Args:
            content_id: Content identifier to end
        """
        content_end = {
            "event": {
                "contentEnd": {
                    "promptName": self.prompt_name,
                    "contentName": content_id,
                }
            }
        }
        await self._send_event(content_end)

    async def send_audio_base64(self, audio_b64: str) -> None:
        """Send base64-encoded audio to Nova 2 Sonic.

        Args:
            audio_b64: Base64-encoded G.711 μ-law audio string (Twilio format)
        """
        if not self._connected:
            raise RuntimeError("Client not connected")

        # Decode base64 to bytes (G.711 μ-law from Twilio at 8kHz)
        audio_bytes = base64.b64decode(audio_b64)
        logger.debug(
            f"Audio conversion - Input: {len(audio_bytes)} bytes, first 20 bytes: {audio_bytes[:20].hex() if len(audio_bytes) >= 20 else audio_bytes.hex()}",
            extra={"conversation_id": self.conversation_id},
        )

        # Convert G.711 μ-law to 16-bit LPCM
        # audioop.ulaw2lin converts μ-law to linear PCM
        # width=2 means output will be 16-bit (2 bytes per sample)
        pcm_8khz = audioop.ulaw2lin(audio_bytes, 2)
        logger.debug(
            f"Audio conversion - After ulaw2lin: {len(pcm_8khz)} bytes, first 40 bytes: {pcm_8khz[:40].hex() if len(pcm_8khz) >= 40 else pcm_8khz.hex()}",
            extra={"conversation_id": self.conversation_id},
        )

        # Upsample from 8kHz to 16kHz (Nova 2 Sonic requirement)
        # audioop.ratecv(fragment, width, nchannels, inrate, outrate, state)
        # Returns (fragment, state) tuple
        pcm_16khz, _ = audioop.ratecv(pcm_8khz, 2, 1, 8000, 16000, None)
        logger.debug(
            f"Audio conversion - After ratecv: {len(pcm_16khz)} bytes, first 40 bytes: {pcm_16khz[:40].hex() if len(pcm_16khz) >= 40 else pcm_16khz.hex()}",
            extra={"conversation_id": self.conversation_id},
        )

        # Queue converted audio for sending
        await self._audio_input_queue.put(pcm_16khz)

    async def _process_audio_queue(self) -> None:
        """Process queued audio and send to Nova."""
        try:
            while self._connected:
                try:
                    # Get audio from queue with timeout
                    audio_bytes = await asyncio.wait_for(self._audio_input_queue.get(), timeout=0.1)

                    # Start audio stream on first audio chunk (AWS sample pattern)
                    if not self._audio_stream_started:
                        await self._start_audio_content()
                        self._audio_stream_started = True
                        logger.info("Started audio content stream", extra={"conversation_id": self.conversation_id})

                    # Convert to base64 for Nova (required format)
                    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

                    # Send audio input event
                    audio_input = {
                        "event": {
                            "audioInput": {
                                "promptName": self.prompt_name,
                                "contentName": self.audio_content_name,
                                "content": audio_b64,
                            }
                        }
                    }
                    await self._send_event(audio_input)

                except TimeoutError:
                    continue
                except Exception as e:
                    logger.error(
                        "Error processing audio queue",
                        extra={"error": str(e), "conversation_id": self.conversation_id},
                        exc_info=True,
                    )
        finally:
            # End audio content when done
            if self._connected:
                await self._end_content(self.audio_content_name)

    async def _process_responses(self) -> None:
        """Process streaming responses from Nova 2 Sonic."""
        logger.info("Starting Nova response processor", extra={"conversation_id": self.conversation_id})
        try:
            # Process output stream - the stream response has events we can async iterate
            while self._connected:
                try:
                    # Await next output event from the stream
                    logger.debug("Awaiting next output from Nova", extra={"conversation_id": self.conversation_id})
                    output_result = await self._stream_response.await_output()
                    logger.debug(
                        f"Got output_result: {type(output_result)}", extra={"conversation_id": self.conversation_id}
                    )

                    # output_result is a tuple: (output_index, output_member)
                    if output_result and len(output_result) >= 2:
                        output_member = output_result[1]

                        # Receive the actual data from the output member
                        result = await output_member.receive()

                        if (
                            result
                            and hasattr(result, "value")
                            and result.value
                            and hasattr(result.value, "bytes_")
                            and result.value.bytes_
                        ):
                            response_data = result.value.bytes_.decode("utf-8")
                            json_data = json.loads(response_data)

                            logger.debug(
                                "Received Nova event",
                                extra={
                                    "conversation_id": self.conversation_id,
                                    "event_keys": list(json_data.get("event", {}).keys())
                                    if "event" in json_data
                                    else [],
                                },
                            )

                            # Log all events for debugging
                            logger.info(
                                "Nova 2 Sonic event received",
                                extra={"conversation_id": self.conversation_id, "event": json_data},
                            )

                            # Handle different event types
                            if "event" in json_data:
                                event = json_data["event"]

                                # Tool use event - handle tool calling
                                if "toolUse" in event and self.tool_executor:
                                    asyncio.create_task(self._handle_tool_use(event))

                                # Audio output
                                elif "audioOutput" in event:
                                    # Emit response.created on first audio output for latency tracking
                                    if not self._response_started:
                                        self._response_started = True
                                        await self._event_queue.put({"type": "response.created"})

                                    audio_content = event["audioOutput"]["content"]
                                    # Audio is base64-encoded 24kHz LPCM from Nova
                                    pcm_24khz = base64.b64decode(audio_content)

                                    # Downsample from 24kHz to 8kHz (Twilio requirement)
                                    # audioop.ratecv(fragment, width, nchannels, inrate, outrate, state)
                                    pcm_8khz, _ = audioop.ratecv(pcm_24khz, 2, 1, 24000, 8000, None)

                                    # Convert 16-bit LPCM to G.711 μ-law (width=2 for 16-bit input)
                                    ulaw_bytes = audioop.lin2ulaw(pcm_8khz, 2)

                                    # Re-encode to base64 for Twilio
                                    ulaw_b64 = base64.b64encode(ulaw_bytes).decode("utf-8")

                                    normalized_event = {
                                        "type": "response.audio.delta",
                                        "delta": ulaw_b64,
                                    }
                                    await self._event_queue.put(normalized_event)

                                    logger.debug(
                                        "Received audio from Nova 2 Sonic",
                                        extra={"conversation_id": self.conversation_id, "size": len(audio_content)},
                                    )

                                # Text output (transcription)
                                elif "textOutput" in event:
                                    text_content = event["textOutput"]["content"]
                                    role = event["textOutput"].get("role", "")

                                    if role == "USER":
                                        # User transcription
                                        normalized_event = {
                                            "type": "conversation.item.input_audio_transcription.completed",
                                            "transcript": text_content,
                                        }
                                        await self._event_queue.put(normalized_event)

                                        logger.info(
                                            "User transcript from Nova 2 Sonic",
                                            extra={"conversation_id": self.conversation_id, "transcript": text_content},
                                        )

                                    elif role == "ASSISTANT":
                                        # Assistant response transcription
                                        normalized_event = {
                                            "type": "response.audio_transcript.done",
                                            "transcript": text_content,
                                        }
                                        await self._event_queue.put(normalized_event)

                                        logger.info(
                                            "Assistant transcript from Nova 2 Sonic",
                                            extra={"conversation_id": self.conversation_id, "transcript": text_content},
                                        )

                                # Content/response completion
                                elif "contentEnd" in event:
                                    # Reset response started flag for next response
                                    self._response_started = False

                                    normalized_event = {"type": "response.done"}
                                    await self._event_queue.put(normalized_event)

                                    logger.info(
                                        "Nova 2 Sonic response completed",
                                        extra={"conversation_id": self.conversation_id},
                                    )

                except StopAsyncIteration:
                    logger.info("Nova 2 Sonic stream ended", extra={"conversation_id": self.conversation_id})
                    break
                except Exception as e:
                    logger.error(
                        "Error processing Nova response",
                        extra={"error": str(e), "conversation_id": self.conversation_id},
                        exc_info=True,
                    )
                    break

        except Exception as e:
            logger.error(
                "Fatal error in response processor",
                extra={"error": str(e), "conversation_id": self.conversation_id},
                exc_info=True,
            )
            error_event = {"type": "error", "error": {"message": str(e)}}
            await self._event_queue.put(error_event)

    async def cancel_response(self) -> None:
        """Cancel the current response generation.

        Note: Nova 2 Sonic handles this differently than OpenAI.
        We need to end the current prompt and start a new one.
        """
        if self._connected:
            # End current prompt
            prompt_end = {"event": {"promptEnd": {"promptName": self.prompt_name}}}
            await self._send_event(prompt_end)

            # Generate new prompt name for next interaction
            self.prompt_name = str(uuid.uuid4())

            logger.info("Cancelled current Nova response", extra={"conversation_id": self.conversation_id})

    async def send_user_message(self, text: str) -> None:
        """Send a text message to Nova and trigger a response.

        Args:
            text: Text message to send
        """
        if not self._connected:
            raise RuntimeError("Client not connected")

        await self._send_text_content(text, role="USER")

        logger.info("Sent text message to Nova", extra={"conversation_id": self.conversation_id, "text": text})

    async def events(self) -> AsyncGenerator[dict[str, Any], None]:
        """Async iterator for receiving events from Nova 2 Sonic.

        Yields:
            Event dictionaries compatible with OpenAI Realtime format
        """
        while self._connected:
            try:
                event = await asyncio.wait_for(self._event_queue.get(), timeout=0.1)
                yield event
            except TimeoutError:
                continue
            except Exception as e:
                logger.error(
                    "Error receiving Nova event",
                    extra={"error": str(e), "conversation_id": self.conversation_id},
                    exc_info=True,
                )
                break

    async def close(self) -> None:
        """Close the Nova 2 Sonic connection."""
        logger.info("Closing Nova 2 Sonic connection", extra={"conversation_id": self.conversation_id})

        self._connected = False

        # Cancel tasks
        if self._response_task and not self._response_task.done():
            self._response_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._response_task

        if self._audio_sender_task and not self._audio_sender_task.done():
            self._audio_sender_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._audio_sender_task

        # End session
        if self._stream_response:
            try:
                session_end = {"event": {"sessionEnd": {}}}
                await self._send_event(session_end)
            except Exception as e:
                logger.warning("Error sending session end event", extra={"error": str(e)})

        logger.info("Nova 2 Sonic connection closed", extra={"conversation_id": self.conversation_id})

    def supports_tools(self) -> bool:
        """Check if this provider supports tool calling.

        Returns:
            bool: True if tool_executor is configured, False otherwise
        """
        return self.tool_executor is not None

    async def _handle_tool_use(self, event: dict[str, Any]) -> None:
        """Handle tool use event from Nova 2 Sonic.

        Args:
            event: Tool use event from Nova with toolUseId, name, and input
        """
        if not self.tool_executor:
            logger.warning("Received tool use event but no tool executor configured")
            return

        tool_use = event.get("toolUse", {})
        tool_use_id = tool_use.get("toolUseId")
        name = tool_use.get("name")
        input_data = tool_use.get("input", {})

        logger.info(
            "Received tool use event",
            extra={
                "conversation_id": self.conversation_id,
                "tool_use_id": tool_use_id,
                "tool_name": name,
                "input": str(input_data)[:100],  # Log first 100 chars
            },
        )

        try:
            # Execute tool with conversation_id for Langfuse tracing
            result = await self.tool_executor.execute_tool(name, input_data, self.conversation_id)

            # Check if tool triggers escalation
            if result.triggers_escalation:
                self._escalation_triggered = True
                self._escalation_reason = input_data.get("reason", "AI requested escalation")
                logger.info(
                    "Tool triggered escalation",
                    extra={
                        "conversation_id": self.conversation_id,
                        "reason": self._escalation_reason,
                    },
                )
                # Queue a special escalation event for the stream handler
                await self._event_queue.put(
                    {
                        "type": "escalation.triggered",
                        "reason": self._escalation_reason,
                    }
                )

            # Send result back to Nova
            await self.send_tool_result(tool_use_id, result.result)

            logger.info(
                "Tool use executed successfully",
                extra={
                    "conversation_id": self.conversation_id,
                    "tool_use_id": tool_use_id,
                    "tool_name": name,
                    "success": result.success,
                },
            )

        except Exception as e:
            logger.error(
                "Tool use execution failed",
                extra={
                    "conversation_id": self.conversation_id,
                    "tool_use_id": tool_use_id,
                    "tool_name": name,
                    "error": str(e),
                },
                exc_info=True,
            )
            # Send error result
            await self.send_tool_result(tool_use_id, f"Error: {str(e)}")

    async def send_tool_result(self, tool_call_id: str, result: str) -> None:
        """Send tool execution result back to Nova 2 Sonic.

        Args:
            tool_call_id: Nova toolUseId for the tool call
            result: Tool execution result as string
        """
        if not self._connected:
            raise RuntimeError("Client not connected")

        content_id = str(uuid.uuid4())

        # Content start with toolResultConfiguration
        content_start = {
            "event": {
                "contentStart": {
                    "promptName": self.prompt_name,
                    "contentName": content_id,
                    "type": "TEXT",
                    "role": "USER",
                    "interactive": False,
                    "toolResultConfiguration": {
                        "toolUseId": tool_call_id,
                        "status": "success",
                    },
                    "textInputConfiguration": {"mediaType": "text/plain"},
                }
            }
        }
        await self._send_event(content_start)

        # Tool result with content
        tool_result = {
            "event": {
                "toolResult": {
                    "promptName": self.prompt_name,
                    "contentName": content_id,
                    "content": result,
                }
            }
        }
        await self._send_event(tool_result)

        # Content end
        await self._end_content(content_id)

        logger.info(
            "Sent tool result to Nova",
            extra={
                "conversation_id": self.conversation_id,
                "tool_use_id": tool_call_id,
                "result_length": len(result),
            },
        )
