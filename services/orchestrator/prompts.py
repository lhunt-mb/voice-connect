"""AI assistant prompts for OpenAI Realtime API.

This module contains all prompt configurations used by the orchestrator.
Prompts are loaded from markdown files for easier reading and editing.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Directory containing prompt markdown files
PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_prompt(filename: str) -> str:
    """Load a prompt from a markdown file.

    Args:
        filename: Name of the markdown file (without .md extension)

    Returns:
        Contents of the markdown file as a string

    Raises:
        FileNotFoundError: If the prompt file doesn't exist
    """
    filepath = PROMPTS_DIR / f"{filename}.md"
    return filepath.read_text(encoding="utf-8")


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


# Prompt configurations with metadata
# Instructions are loaded from markdown files in the prompts/ directory
PROMPT_CONFIGS: dict[str, dict[str, str]] = {
    "default": {
        "file": "default",
        "voice": "alloy",
        "context": "General purpose assistant for customer service interactions with Australian accent",
    },
    "technical": {
        "file": "technical",
        "voice": "alloy",
        "context": "Technical support with Australian accent and escalation handling",
    },
    "sales": {
        "file": "sales",
        "voice": "shimmer",
        "context": "Sales assistance with Australian accent and product information",
    },
    "qld_intake": {
        "file": "qld_intake",
        "voice": "alloy",
        "context": "QLD road injury legal intake voice AI - Maurice Blackburn",
    },
}


def get_prompt(prompt_type: str = "default") -> AssistantPrompt:
    """Get a prompt by type.

    Args:
        prompt_type: Type of prompt to retrieve (default, technical, sales, qld_intake)

    Returns:
        AssistantPrompt configuration

    Raises:
        ValueError: If prompt_type is not recognized
        FileNotFoundError: If the prompt file doesn't exist
    """
    if prompt_type not in PROMPT_CONFIGS:
        raise ValueError(f"Unknown prompt type: {prompt_type}. Available: {list(PROMPT_CONFIGS.keys())}")

    config = PROMPT_CONFIGS[prompt_type]
    instructions = _load_prompt(config["file"])

    return AssistantPrompt(
        instructions=instructions,
        voice=config["voice"],
        context=config["context"],
    )


# Pre-loaded prompts for backward compatibility and direct import
# These are loaded at module import time
DEFAULT_ASSISTANT_PROMPT = get_prompt("default")
TECHNICAL_SUPPORT_PROMPT = get_prompt("technical")
SALES_ASSISTANT_PROMPT = get_prompt("sales")
QLD_INTAKE_PROMPT = get_prompt("qld_intake")
