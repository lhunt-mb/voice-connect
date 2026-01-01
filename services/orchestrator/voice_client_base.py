"""Abstract base class for voice AI clients."""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any


class VoiceClientBase(ABC):
    """Abstract base class for voice AI clients (OpenAI Realtime, Nova Sonic, etc.)."""

    @abstractmethod
    async def connect(self, conversation_id: str) -> None:
        """Connect to the voice AI service.

        Args:
            conversation_id: Unique conversation identifier
        """
        pass

    @abstractmethod
    async def send_audio_base64(self, audio_b64: str) -> None:
        """Send base64-encoded audio to the voice AI service.

        Args:
            audio_b64: Base64-encoded audio data (G.711 μ-law format)
        """
        pass

    @abstractmethod
    async def cancel_response(self) -> None:
        """Cancel the current response generation."""
        pass

    @abstractmethod
    async def send_user_message(self, text: str) -> None:
        """Send a text message to the AI and trigger a response.

        Args:
            text: Text message to send
        """
        pass

    @abstractmethod
    async def events(self) -> AsyncGenerator[dict[str, Any], None]:
        """Async iterator for receiving events from the voice AI service.

        Yields:
            Event dictionaries containing audio deltas, transcripts, etc.
        """
        # This is an abstract async generator - implementations should use `async def` and `yield`
        yield  # type: ignore[misc]
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """Close the connection to the voice AI service."""
        pass

    def supports_tools(self) -> bool:
        """Check if this provider supports tool calling.

        Default implementation returns False.
        Subclasses with tool support should override to return True.

        Returns:
            bool: True if provider supports tools, False otherwise
        """
        return False

    async def send_tool_result(
        self,
        tool_call_id: str,
        result: str,
    ) -> None:
        """Send tool execution result back to the voice AI provider.

        This is an optional method for providers that support tool calling.
        Default implementation raises NotImplementedError.

        Args:
            tool_call_id: Provider-specific identifier for the tool call
            result: Tool execution result as string

        Raises:
            NotImplementedError: If provider doesn't support tool calling
        """
        raise NotImplementedError(f"{self.__class__.__name__} does not support tool calling")
