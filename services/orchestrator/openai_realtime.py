"""OpenAI Realtime API WebSocket client."""

import asyncio
import base64
import contextlib
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

import websockets
from websockets.client import WebSocketClientProtocol  # type: ignore[attr-defined]

from services.orchestrator.prompts import DEFAULT_ASSISTANT_PROMPT, AssistantPrompt
from services.orchestrator.tools import OPENAI_TOOLS
from services.orchestrator.voice_client_base import VoiceClientBase
from shared.config import Settings

logger = logging.getLogger(__name__)


class OpenAIRealtimeClient(VoiceClientBase):
    """WebSocket client for OpenAI Realtime API."""

    def __init__(
        self,
        settings: Settings,
        prompt: AssistantPrompt | None = None,
        tool_executor: Any = None,
    ) -> None:
        """Initialize the OpenAI Realtime client.

        Args:
            settings: Application settings
            prompt: AI assistant prompt configuration. Defaults to DEFAULT_ASSISTANT_PROMPT
            tool_executor: Optional ToolExecutor for handling tool calls
        """
        self.settings = settings
        self.prompt = prompt or DEFAULT_ASSISTANT_PROMPT
        self.tool_executor = tool_executor
        self.ws: WebSocketClientProtocol | None = None
        self.conversation_id: str | None = None
        self._receive_task: asyncio.Task[None] | None = None
        self._event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def connect(self, conversation_id: str) -> None:
        """Connect to OpenAI Realtime API and configure session."""
        self.conversation_id = conversation_id

        url = "wss://api.openai.com/v1/realtime?model=" + self.settings.openai_realtime_model
        headers = {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "OpenAI-Beta": "realtime=v1",
        }

        logger.info(
            "Connecting to OpenAI Realtime API",
            extra={"conversation_id": conversation_id, "model": self.settings.openai_realtime_model},
        )

        try:
            self.ws = await websockets.connect(url, additional_headers=headers, ping_interval=20, ping_timeout=10)
            logger.info("Connected to OpenAI Realtime API", extra={"conversation_id": conversation_id})

            # Send session configuration
            await self._send_session_update()

            # Start receiving events
            self._receive_task = asyncio.create_task(self._receive_loop())

            # Trigger initial greeting from OpenAI
            await self._trigger_initial_greeting()

        except Exception as e:
            logger.error("Failed to connect to OpenAI Realtime API", extra={"error": str(e)}, exc_info=True)
            raise

    async def _send_session_update(self) -> None:
        """Send initial session configuration for GA Realtime API."""
        # Get prompt configuration
        prompt_config = self.prompt.to_session_config()

        session_config = {
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],  # GA API uses modalities, not output_modalities
                "instructions": prompt_config["instructions"],
                "voice": prompt_config["voice"],
                "input_audio_format": "g711_ulaw",  # Twilio's mulaw format
                "output_audio_format": "g711_ulaw",  # Send mulaw audio back to Twilio
                "input_audio_transcription": {"model": "whisper-1"},
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 500,
                },
                "tools": OPENAI_TOOLS if self.tool_executor else [],  # Add tools if executor available
            },
        }

        await self._send_event(session_config)
        logger.info(
            "Sent session configuration",
            extra={
                "conversation_id": self.conversation_id,
                "prompt_context": self.prompt.context,
                "tools_enabled": bool(self.tool_executor),
            },
        )

    async def _send_event(self, event: dict[str, Any]) -> None:
        """Send an event to OpenAI Realtime API."""
        if not self.ws:
            raise RuntimeError("WebSocket not connected")

        await self.ws.send(json.dumps(event))

    async def _receive_loop(self) -> None:
        """Continuously receive events from OpenAI and queue them."""
        if not self.ws:
            return

        try:
            async for message in self.ws:
                try:
                    if isinstance(message, str):
                        event = json.loads(message)

                        # Handle function call events if tool executor is available
                        if self.tool_executor and event.get("type") == "response.function_call_arguments.done":
                            asyncio.create_task(self._handle_function_call(event))
                        else:
                            # Queue all other events for processing
                            await self._event_queue.put(event)

                        logger.info(
                            "Received OpenAI event",
                            extra={"conversation_id": self.conversation_id, "event_type": event.get("type")},
                        )
                except json.JSONDecodeError as e:
                    logger.warning("Failed to decode OpenAI event", extra={"error": str(e)})
        except websockets.exceptions.ConnectionClosed:
            logger.warning("OpenAI WebSocket connection closed", extra={"conversation_id": self.conversation_id})
        except Exception as e:
            logger.error("Error in OpenAI receive loop", extra={"error": str(e)}, exc_info=True)

    async def send_audio(self, audio_data: bytes) -> None:
        """Send audio data to OpenAI Realtime API.

        Args:
            audio_data: G.711 μ-law (mulaw) audio bytes (8kHz mono from Twilio)
        """
        if not self.ws:
            raise RuntimeError("WebSocket not connected")

        # Encode to base64
        audio_b64 = base64.b64encode(audio_data).decode("utf-8")

        event = {
            "type": "input_audio_buffer.append",
            "audio": audio_b64,
        }

        await self._send_event(event)

    async def send_audio_base64(self, audio_b64: str) -> None:
        """Send base64-encoded audio data to OpenAI Realtime API.

        Args:
            audio_b64: Base64-encoded G.711 μ-law audio string
        """
        if not self.ws:
            raise RuntimeError("WebSocket not connected")

        event = {
            "type": "input_audio_buffer.append",
            "audio": audio_b64,
        }

        await self._send_event(event)

    async def cancel_response(self) -> None:
        """Cancel the current response generation.

        This should be called before sending a new message if a response
        is already in progress.
        """
        if not self.ws:
            raise RuntimeError("WebSocket not connected")

        cancel_event = {"type": "response.cancel"}
        await self._send_event(cancel_event)
        logger.info("Cancelled current response", extra={"conversation_id": self.conversation_id})

    async def send_user_message(self, text: str) -> None:
        """Send a text message to OpenAI and trigger a response.

        Args:
            text: Text message to send
        """
        if not self.ws:
            raise RuntimeError("WebSocket not connected")

        # Create a conversation item with user message
        event = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": text}],
            },
        }

        await self._send_event(event)

        # Trigger response generation
        response_event = {"type": "response.create"}
        await self._send_event(response_event)

        logger.info("Sent user message and triggered response", extra={"conversation_id": self.conversation_id})

    async def _trigger_initial_greeting(self) -> None:
        """Trigger OpenAI to generate an initial greeting.

        This creates an empty response request which causes OpenAI to
        generate a greeting based on the system instructions.
        """
        if not self.ws:
            raise RuntimeError("WebSocket not connected")

        # Wait a brief moment for session update to be processed
        await asyncio.sleep(0.1)

        # Trigger a response without any user input
        # This will cause OpenAI to generate an initial greeting
        response_event = {"type": "response.create"}
        await self._send_event(response_event)

        logger.info("Triggered initial greeting from OpenAI", extra={"conversation_id": self.conversation_id})

    async def _handle_function_call(self, event: dict[str, Any]) -> None:
        """Handle function call from OpenAI.

        Args:
            event: Function call event from OpenAI with call_id, name, and arguments
        """
        if not self.tool_executor:
            logger.warning("Received function call but no tool executor configured")
            return

        call_id = event.get("call_id")
        name = event.get("name")
        arguments_str = event.get("arguments", "{}")

        if not call_id:
            logger.error(
                "Function call missing call_id",
                extra={"conversation_id": self.conversation_id, "event": event},
            )
            return

        logger.info(
            "Received function call",
            extra={
                "conversation_id": self.conversation_id,
                "call_id": call_id,
                "function_name": name,
                "arguments": arguments_str[:100],  # Log first 100 chars
            },
        )

        try:
            # Parse arguments
            arguments = json.loads(arguments_str)

            # Execute tool
            result = await self.tool_executor.execute_tool(name, arguments)

            # Send result back to OpenAI
            await self.send_tool_result(call_id, result.result)

            logger.info(
                "Function call executed successfully",
                extra={
                    "conversation_id": self.conversation_id,
                    "call_id": call_id,
                    "function_name": name,
                    "success": result.success,
                },
            )

        except json.JSONDecodeError as e:
            logger.error(
                "Failed to parse function call arguments",
                extra={"conversation_id": self.conversation_id, "call_id": call_id, "error": str(e)},
            )
            # Send error result
            await self.send_tool_result(call_id, "Error: Failed to parse arguments")

        except Exception as e:
            logger.error(
                "Function call execution failed",
                extra={
                    "conversation_id": self.conversation_id,
                    "call_id": call_id,
                    "function_name": name,
                    "error": str(e),
                },
                exc_info=True,
            )
            # Send error result
            await self.send_tool_result(call_id, f"Error: {str(e)}")

    async def events(self) -> AsyncGenerator[dict[str, Any], None]:
        """Async iterator for receiving events from OpenAI."""
        while True:
            try:
                event = await asyncio.wait_for(self._event_queue.get(), timeout=0.1)
                yield event
            except TimeoutError:
                # Check if connection is still alive by checking if receive task is done
                if not self.ws or (self._receive_task and self._receive_task.done()):
                    logger.warning("OpenAI WebSocket closed during event iteration")
                    break
                continue
            except Exception as e:
                logger.error("Error receiving OpenAI event", extra={"error": str(e)}, exc_info=True)
                break

    async def close(self) -> None:
        """Close the OpenAI WebSocket connection."""
        logger.info("Closing OpenAI Realtime connection", extra={"conversation_id": self.conversation_id})

        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._receive_task

        if self.ws:
            await self.ws.close()
            self.ws = None

        logger.info("OpenAI Realtime connection closed", extra={"conversation_id": self.conversation_id})

    def supports_tools(self) -> bool:
        """Check if this provider supports tool calling.

        Returns:
            bool: True if tool_executor is configured, False otherwise
        """
        return self.tool_executor is not None

    async def send_tool_result(self, tool_call_id: str, result: str) -> None:
        """Send tool execution result back to OpenAI.

        Args:
            tool_call_id: OpenAI call_id for the function call
            result: Tool execution result as string
        """
        if not self.ws:
            raise RuntimeError("WebSocket not connected")

        # Create conversation item with function call output
        event = {
            "type": "conversation.item.create",
            "item": {
                "type": "function_call_output",
                "call_id": tool_call_id,
                "output": result,
            },
        }

        await self._send_event(event)

        # Trigger response generation with the tool result
        response_event = {"type": "response.create"}
        await self._send_event(response_event)

        logger.info(
            "Sent tool result to OpenAI",
            extra={
                "conversation_id": self.conversation_id,
                "call_id": tool_call_id,
                "result_length": len(result),
            },
        )
