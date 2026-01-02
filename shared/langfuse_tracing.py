"""Langfuse tracing integration for LLM observability.

Provides a centralized tracing client that integrates with the voice AI gateway
for conversation tracing, tool execution monitoring, and performance analytics.

Uses the Langfuse Python SDK v2+ API with context managers and manual span management.
"""

import logging
from contextvars import ContextVar
from typing import Any

from shared.config import Settings

logger = logging.getLogger(__name__)

# Context variable to hold the current span for nested operations
_current_span_ctx: ContextVar[Any] = ContextVar("langfuse_span", default=None)

# Singleton Langfuse client
_langfuse_client: Any = None


def init_langfuse(settings: Settings) -> Any:
    """Initialize the Langfuse client singleton.

    Args:
        settings: Application settings containing Langfuse configuration

    Returns:
        Langfuse client instance or None if disabled/unconfigured
    """
    global _langfuse_client

    if _langfuse_client is not None:
        return _langfuse_client

    if not settings.langfuse_enabled:
        logger.info("Langfuse tracing is disabled")
        return None

    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        logger.warning("Langfuse enabled but credentials not configured")
        return None

    try:
        from langfuse import Langfuse

        _langfuse_client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
            environment=settings.langfuse_environment,
            sample_rate=settings.langfuse_sample_rate,
            flush_at=50,  # Flush after 50 events
            flush_interval=5.0,  # Or every 5 seconds
            debug=settings.log_level.upper() == "DEBUG",
        )

        logger.info(
            "Langfuse client initialized",
            extra={
                "host": settings.langfuse_host,
                "environment": settings.langfuse_environment,
                "sample_rate": settings.langfuse_sample_rate,
            },
        )

        return _langfuse_client

    except ImportError:
        logger.warning("Langfuse package not installed, tracing disabled")
        return None
    except Exception as e:
        logger.error("Failed to initialize Langfuse client", extra={"error": str(e)})
        return None


def get_langfuse() -> Any:
    """Get the Langfuse client singleton.

    Returns:
        Langfuse client instance or None if not initialized
    """
    return _langfuse_client


def flush_langfuse() -> None:
    """Flush any pending Langfuse events.

    Should be called before application shutdown to ensure all traces are sent.
    """
    if _langfuse_client is not None:
        try:
            _langfuse_client.flush()
            logger.debug("Langfuse events flushed")
        except Exception as e:
            logger.error("Failed to flush Langfuse events", extra={"error": str(e)})


class ConversationTrace:
    """Context manager for tracing a complete voice conversation.

    Creates a top-level trace that encompasses all events within a single call,
    including voice turns, tool executions, and escalation handling.

    Uses the Langfuse v2+ API with start_as_current_span().
    """

    def __init__(
        self,
        conversation_id: str,
        call_sid: str,
        voice_provider: str,
        caller_phone: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Initialize a conversation trace.

        Args:
            conversation_id: Unique conversation identifier
            call_sid: Twilio call SID
            voice_provider: Voice provider name (openai/nova)
            caller_phone: Caller's phone number (optional)
            metadata: Additional metadata for the trace
        """
        self.conversation_id = conversation_id
        self.call_sid = call_sid
        self.voice_provider = voice_provider
        self.caller_phone = caller_phone
        self.metadata = metadata or {}
        self._span: Any = None
        self._span_context: Any = None
        self._current_generation: Any = None  # Track in-progress assistant generation

    def __enter__(self) -> "ConversationTrace":
        """Start the conversation trace."""
        client = get_langfuse()
        if client is None:
            return self

        try:
            # Create trace metadata
            trace_metadata = {
                "call_sid": self.call_sid,
                "voice_provider": self.voice_provider,
                "conversation_id": self.conversation_id,
                **self.metadata,
            }

            # Use start_as_current_span as context manager for automatic trace creation
            self._span_context = client.start_as_current_span(
                name="voice_conversation",
                input={"conversation_id": self.conversation_id},
                metadata=trace_metadata,
                level="INFO",
            )
            self._span = self._span_context.__enter__()

            # Update the underlying trace with additional info
            self._span.update_trace(
                name="voice_conversation",
                user_id=self.caller_phone,
                session_id=self.call_sid,
                tags=[f"provider:{self.voice_provider}", "voice"],
            )

            # Store span in context var for nested spans
            _current_span_ctx.set(self._span)

            logger.debug(
                "Started conversation trace",
                extra={"conversation_id": self.conversation_id, "call_sid": self.call_sid},
            )

        except Exception as e:
            logger.error("Failed to start conversation trace", extra={"error": str(e)})

        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """End the conversation trace."""
        if self._span is not None and self._span_context is not None:
            try:
                # Update span with final status if there was an error
                if exc_type is not None:
                    self._span.update(
                        level="ERROR",
                        status_message=str(exc_val),
                        metadata={
                            **self.metadata,
                            "error": str(exc_val),
                            "error_type": exc_type.__name__ if exc_type else None,
                        },
                    )

                # Exit the context manager
                self._span_context.__exit__(exc_type, exc_val, exc_tb)

                logger.debug(
                    "Ended conversation trace",
                    extra={"conversation_id": self.conversation_id},
                )

            except Exception as e:
                logger.error("Failed to end conversation trace", extra={"error": str(e)})

        # Clear context
        _current_span_ctx.set(None)

    def add_user_turn(self, transcript: str, audio_duration_ms: int | None = None) -> None:
        """Record a user speech turn.

        Args:
            transcript: User's spoken words (transcribed)
            audio_duration_ms: Duration of the audio in milliseconds
        """
        if self._span is None:
            return

        try:
            # Create a nested span for the user turn
            span = self._span.start_span(
                name="user_turn",
                input={"transcript": transcript},
                metadata={"audio_duration_ms": audio_duration_ms} if audio_duration_ms else {},
            )
            span.end()
        except Exception as e:
            logger.error("Failed to record user turn", extra={"error": str(e)})

    def start_assistant_turn(self, model: str | None = None) -> None:
        """Start tracking an assistant response generation.

        Call this when response generation begins to track latency.
        Use set_assistant_input() to add the user input if it arrives later.

        Args:
            model: Model used for generation
        """
        if self._span is None:
            return

        try:
            # End any previous in-progress generation
            if self._current_generation is not None:
                self._current_generation.end()
                self._current_generation = None

            # Start a new generation span (input will be set later if needed)
            self._current_generation = self._span.start_generation(
                name="assistant_turn",
                model=model or self.voice_provider,
            )
            logger.debug("Started assistant turn generation")
        except Exception as e:
            logger.error("Failed to start assistant turn", extra={"error": str(e)})

    def set_assistant_input(self, input_text: str) -> None:
        """Set the input for the current assistant generation.

        Call this when user transcript is available to associate it with
        the in-progress assistant response.

        Args:
            input_text: The user input that triggered this response
        """
        if self._current_generation is None:
            return

        try:
            self._current_generation.update(
                input={"user_message": input_text},
            )
            logger.debug("Set assistant turn input")
        except Exception as e:
            logger.error("Failed to set assistant input", extra={"error": str(e)})

    def end_assistant_turn(
        self,
        response_text: str | None = None,
        audio_duration_ms: int | None = None,
    ) -> None:
        """End tracking an assistant response generation.

        Call this when the response transcript is complete.

        Args:
            response_text: Assistant's response text
            audio_duration_ms: Duration of the audio in milliseconds
        """
        if self._current_generation is None:
            # No generation in progress, create a point-in-time record
            if self._span is not None and response_text:
                try:
                    generation = self._span.start_generation(
                        name="assistant_turn",
                        model=self.voice_provider,
                        output=response_text,
                        metadata={"audio_duration_ms": audio_duration_ms} if audio_duration_ms else {},
                    )
                    generation.end()
                except Exception as e:
                    logger.error("Failed to record assistant turn", extra={"error": str(e)})
            return

        try:
            # Update and end the generation with output
            self._current_generation.update(
                output=response_text,
                metadata={"audio_duration_ms": audio_duration_ms} if audio_duration_ms else {},
            )
            self._current_generation.end()
            self._current_generation = None
            logger.debug("Ended assistant turn generation")
        except Exception as e:
            logger.error("Failed to end assistant turn", extra={"error": str(e)})

    def add_assistant_turn(
        self,
        response_text: str | None = None,
        audio_duration_ms: int | None = None,
        model: str | None = None,
    ) -> None:
        """Record an assistant speech turn (legacy method for backwards compatibility).

        For proper latency tracking, use start_assistant_turn() and end_assistant_turn().

        Args:
            response_text: Assistant's response text (if available)
            audio_duration_ms: Duration of the audio in milliseconds
            model: Model used for generation
        """
        # If there's a generation in progress, end it with this output
        if self._current_generation is not None:
            self.end_assistant_turn(response_text, audio_duration_ms)
            return

        if self._span is None:
            return

        try:
            # Create a nested generation for the assistant turn (point-in-time record)
            generation = self._span.start_generation(
                name="assistant_turn",
                model=model or self.voice_provider,
                output=response_text,
                metadata={"audio_duration_ms": audio_duration_ms} if audio_duration_ms else {},
            )
            generation.end()
        except Exception as e:
            logger.error("Failed to record assistant turn", extra={"error": str(e)})

    def add_escalation(self, reason: str, token: str | None = None) -> None:
        """Record an escalation event.

        Args:
            reason: Reason for escalation
            token: Handover token (if generated)
        """
        if self._span is None:
            return

        try:
            # Create a nested span for the escalation event
            span = self._span.start_span(
                name="escalation",
                input={"reason": reason},
                metadata={"reason": reason, "token": token},
            )
            span.end()

            # Update trace tags to include escalated
            self._span.update_trace(tags=[f"provider:{self.voice_provider}", "voice", "escalated"])
        except Exception as e:
            logger.error("Failed to record escalation", extra={"error": str(e)})


class ToolSpan:
    """Context manager for tracing tool execution.

    Creates a span for each tool call, tracking inputs, outputs, latency, and success status.

    Uses the Langfuse v2+ API with start_span().
    """

    def __init__(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        conversation_id: str | None = None,
    ) -> None:
        """Initialize a tool span.

        Args:
            tool_name: Name of the tool being executed
            arguments: Tool call arguments
            conversation_id: Associated conversation ID (optional)
        """
        self.tool_name = tool_name
        self.arguments = arguments
        self.conversation_id = conversation_id
        self._span: Any = None

    def __enter__(self) -> "ToolSpan":
        """Start the tool span."""
        client = get_langfuse()
        if client is None:
            return self

        try:
            # Get current span from context if available
            parent_span = _current_span_ctx.get()

            if parent_span is not None:
                # Create span under existing trace/span
                self._span = parent_span.start_span(
                    name=f"tool:{self.tool_name}",
                    input=self.arguments,
                    metadata={"tool_name": self.tool_name},
                )
            else:
                # Create standalone span if no parent context
                self._span = client.start_span(
                    name=f"tool:{self.tool_name}",
                    input=self.arguments,
                    metadata={
                        "tool_name": self.tool_name,
                        "conversation_id": self.conversation_id,
                    },
                )

            logger.debug(
                "Started tool span",
                extra={"tool_name": self.tool_name, "conversation_id": self.conversation_id},
            )

        except Exception as e:
            logger.error("Failed to start tool span", extra={"error": str(e)})

        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """End the tool span."""
        if self._span is not None:
            try:
                if exc_type is not None:
                    self._span.update(
                        level="ERROR",
                        status_message=str(exc_val),
                        metadata={
                            "tool_name": self.tool_name,
                            "error": str(exc_val),
                            "error_type": exc_type.__name__ if exc_type else None,
                        },
                    )
                self._span.end()

                logger.debug(
                    "Ended tool span",
                    extra={"tool_name": self.tool_name, "error": exc_type is not None},
                )

            except Exception as e:
                logger.error("Failed to end tool span", extra={"error": str(e)})

    def set_output(self, output: str, success: bool = True) -> None:
        """Set the tool execution output.

        Args:
            output: Tool execution result
            success: Whether the tool executed successfully
        """
        if self._span is None:
            return

        try:
            self._span.update(
                output=output,
                level="DEFAULT" if success else "WARNING",
                metadata={
                    "tool_name": self.tool_name,
                    "success": success,
                    "output_length": len(output),
                },
            )
        except Exception as e:
            logger.error("Failed to set tool output", extra={"error": str(e)})


class GenerationSpan:
    """Context manager for tracing LLM generations.

    Used for tracking voice AI model generations, including model parameters,
    token usage (where available), and response content.

    Uses the Langfuse v2+ API with start_generation().
    """

    def __init__(
        self,
        name: str,
        model: str,
        input_data: dict[str, Any] | None = None,
        model_parameters: dict[str, Any] | None = None,
    ) -> None:
        """Initialize a generation span.

        Args:
            name: Name of the generation (e.g., "voice_response")
            model: Model identifier
            input_data: Input data for the generation
            model_parameters: Model configuration parameters
        """
        self.name = name
        self.model = model
        self.input_data = input_data
        self.model_parameters = model_parameters
        self._generation: Any = None

    def __enter__(self) -> "GenerationSpan":
        """Start the generation span."""
        client = get_langfuse()
        if client is None:
            return self

        try:
            parent_span = _current_span_ctx.get()

            if parent_span is not None:
                self._generation = parent_span.start_generation(
                    name=self.name,
                    model=self.model,
                    input=self.input_data,
                    model_parameters=self.model_parameters,
                )
            else:
                self._generation = client.start_generation(
                    name=self.name,
                    model=self.model,
                    input=self.input_data,
                    model_parameters=self.model_parameters,
                )

            logger.debug("Started generation span", extra={"name": self.name, "model": self.model})

        except Exception as e:
            logger.error("Failed to start generation span", extra={"error": str(e)})

        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """End the generation span."""
        if self._generation is not None:
            try:
                if exc_type is not None:
                    self._generation.update(
                        level="ERROR",
                        status_message=str(exc_val),
                    )
                self._generation.end()

                logger.debug("Ended generation span", extra={"name": self.name})

            except Exception as e:
                logger.error("Failed to end generation span", extra={"error": str(e)})

    def set_output(
        self,
        output: str | dict[str, Any],
        usage: dict[str, int] | None = None,
    ) -> None:
        """Set the generation output and usage.

        Args:
            output: Generation output
            usage: Token usage dict with keys like input_tokens, output_tokens, total_tokens
        """
        if self._generation is None:
            return

        try:
            update_kwargs: dict[str, Any] = {"output": output}

            if usage:
                update_kwargs["usage_details"] = usage

            self._generation.update(**update_kwargs)

        except Exception as e:
            logger.error("Failed to set generation output", extra={"error": str(e)})
