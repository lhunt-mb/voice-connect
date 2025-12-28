"""AI assistant prompts for OpenAI Realtime API.

This module contains all prompt configurations used by the orchestrator.
Prompts are organized as structured data to enable testing with DeepEval.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AssistantPrompt:
    """Configuration for an AI assistant prompt.

    Attributes:
        instructions: System instructions that define the assistant's behavior
        voice: Voice model identifier (e.g., "alloy", "echo", "shimmer")
        context: Optional context about the prompt's purpose (for testing/documentation)
    """

    instructions: str
    voice: str = "alloy"
    context: str = ""

    def to_session_config(self) -> dict[str, Any]:
        """Convert prompt to OpenAI Realtime API session configuration.

        Returns:
            Dictionary with session configuration including instructions and voice
        """
        return {"instructions": self.instructions, "voice": self.voice}


# Default assistant prompt for general customer service
DEFAULT_ASSISTANT_PROMPT = AssistantPrompt(
    instructions=(
        "You are a helpful AI assistant speaking with an Australian accent. "
        "Use Australian expressions and pronunciation naturally. "
        "If the user requests to speak with a human agent or representative, "
        "acknowledge their request politely."
    ),
    voice="alloy",
    context="General purpose assistant for customer service interactions with Australian accent",
)


# Example: Technical support assistant prompt
TECHNICAL_SUPPORT_PROMPT = AssistantPrompt(
    instructions=(
        "You are a technical support AI assistant speaking with an Australian accent. "
        "Use Australian expressions naturally while providing clear, step-by-step troubleshooting guidance. "
        "If the issue requires human expertise or the user requests it, "
        "politely acknowledge and offer to transfer to a human specialist."
    ),
    voice="alloy",
    context="Technical support with Australian accent and escalation handling",
)


# Example: Sales assistant prompt
SALES_ASSISTANT_PROMPT = AssistantPrompt(
    instructions=(
        "You are a friendly sales assistant speaking with an Australian accent. "
        "Use Australian expressions naturally while helping customers understand product features and pricing. "
        "If the customer needs detailed pricing or wants to make a purchase, "
        "politely offer to connect them with a sales representative."
    ),
    voice="shimmer",
    context="Sales assistance with Australian accent and product information",
)


def get_prompt(prompt_type: str = "default") -> AssistantPrompt:
    """Get a prompt by type.

    Args:
        prompt_type: Type of prompt to retrieve (default, technical, sales)

    Returns:
        AssistantPrompt configuration

    Raises:
        ValueError: If prompt_type is not recognized
    """
    prompts = {
        "default": DEFAULT_ASSISTANT_PROMPT,
        "technical": TECHNICAL_SUPPORT_PROMPT,
        "sales": SALES_ASSISTANT_PROMPT,
    }

    if prompt_type not in prompts:
        raise ValueError(f"Unknown prompt type: {prompt_type}. Available: {list(prompts.keys())}")

    return prompts[prompt_type]
