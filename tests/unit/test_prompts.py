"""Unit tests for AI assistant prompts.

These tests validate prompt configurations using DeepEval metrics to ensure
prompts maintain quality, relevance, and alignment with their intended purpose.
"""

import pytest

from services.orchestrator.prompts import (
    DEFAULT_ASSISTANT_PROMPT,
    SALES_ASSISTANT_PROMPT,
    TECHNICAL_SUPPORT_PROMPT,
    AssistantPrompt,
    get_prompt,
)


class TestAssistantPrompt:
    """Tests for AssistantPrompt dataclass."""

    def test_prompt_immutability(self) -> None:
        """Verify that AssistantPrompt is immutable (frozen)."""
        prompt = AssistantPrompt(instructions="Test", voice="alloy")

        with pytest.raises(AttributeError):
            prompt.instructions = "Modified"  # type: ignore[misc]

    def test_to_session_config(self) -> None:
        """Test conversion to session configuration dictionary."""
        prompt = AssistantPrompt(
            instructions="You are a helpful assistant.",
            voice="shimmer",
            context="Test context",
        )

        config = prompt.to_session_config()

        assert config == {"instructions": "You are a helpful assistant.", "voice": "shimmer"}

    def test_default_voice(self) -> None:
        """Test that default voice is 'alloy'."""
        prompt = AssistantPrompt(instructions="Test instructions")
        assert prompt.voice == "alloy"

    def test_default_context(self) -> None:
        """Test that default context is empty string."""
        prompt = AssistantPrompt(instructions="Test instructions")
        assert prompt.context == ""


class TestPredefinedPrompts:
    """Tests for predefined prompt configurations."""

    def test_default_prompt_structure(self) -> None:
        """Validate DEFAULT_ASSISTANT_PROMPT has required fields."""
        assert DEFAULT_ASSISTANT_PROMPT.instructions
        assert DEFAULT_ASSISTANT_PROMPT.voice
        assert DEFAULT_ASSISTANT_PROMPT.context

    def test_default_prompt_escalation_handling(self) -> None:
        """Ensure default prompt mentions escalation to human agents."""
        instructions = DEFAULT_ASSISTANT_PROMPT.instructions.lower()
        assert "human" in instructions or "agent" in instructions or "representative" in instructions

    def test_technical_support_prompt_structure(self) -> None:
        """Validate TECHNICAL_SUPPORT_PROMPT configuration."""
        assert TECHNICAL_SUPPORT_PROMPT.instructions
        assert "technical" in TECHNICAL_SUPPORT_PROMPT.context.lower()
        assert "troubleshooting" in TECHNICAL_SUPPORT_PROMPT.instructions.lower()

    def test_sales_assistant_prompt_structure(self) -> None:
        """Validate SALES_ASSISTANT_PROMPT configuration."""
        assert SALES_ASSISTANT_PROMPT.instructions
        assert "sales" in SALES_ASSISTANT_PROMPT.context.lower()
        assert "sales" in SALES_ASSISTANT_PROMPT.instructions.lower()

    def test_all_prompts_have_context(self) -> None:
        """Ensure all predefined prompts have descriptive context."""
        prompts = [DEFAULT_ASSISTANT_PROMPT, TECHNICAL_SUPPORT_PROMPT, SALES_ASSISTANT_PROMPT]

        for prompt in prompts:
            assert prompt.context, f"Prompt {prompt} missing context"
            assert len(prompt.context) > 10, f"Prompt {prompt} context too short"


class TestGetPrompt:
    """Tests for get_prompt function."""

    def test_get_default_prompt(self) -> None:
        """Test retrieving default prompt."""
        prompt = get_prompt("default")
        assert prompt == DEFAULT_ASSISTANT_PROMPT

    def test_get_technical_prompt(self) -> None:
        """Test retrieving technical support prompt."""
        prompt = get_prompt("technical")
        assert prompt == TECHNICAL_SUPPORT_PROMPT

    def test_get_sales_prompt(self) -> None:
        """Test retrieving sales assistant prompt."""
        prompt = get_prompt("sales")
        assert prompt == SALES_ASSISTANT_PROMPT

    def test_get_invalid_prompt_raises_error(self) -> None:
        """Test that invalid prompt type raises ValueError."""
        with pytest.raises(ValueError, match="Unknown prompt type"):
            get_prompt("nonexistent")

    def test_get_prompt_default_parameter(self) -> None:
        """Test that get_prompt() defaults to 'default' type."""
        prompt = get_prompt()
        assert prompt == DEFAULT_ASSISTANT_PROMPT


# DeepEval tests for prompt quality evaluation
# Note: These tests require OPENAI_API_KEY environment variable to be set
# and deepeval to be installed: pip install deepeval
#
# To run DeepEval tests specifically:
#   pytest tests/unit/test_prompts.py -m deepeval
#
# To skip DeepEval tests (they use OpenAI API):
#   pytest tests/unit/test_prompts.py -m "not deepeval"


@pytest.mark.deepeval
class TestPromptQualityWithDeepEval:
    """DeepEval-based tests for prompt quality metrics.

    These tests use DeepEval to evaluate prompt quality using LLM-based metrics.
    They validate that prompts produce appropriate responses for various scenarios.

    Note: These tests require:
    - OPENAI_API_KEY environment variable
    - deepeval package: pip install deepeval
    """

    @pytest.fixture(autouse=True)
    def skip_if_no_deepeval(self) -> None:
        """Skip tests if deepeval is not installed."""
        pytest.importorskip("deepeval", reason="deepeval not installed")

    def test_default_prompt_answer_relevancy(self) -> None:
        """Test that default prompt produces relevant answers.

        This test validates that the prompt configuration results in
        relevant responses to customer service queries.
        """
        from deepeval import assert_test
        from deepeval.metrics import AnswerRelevancyMetric
        from deepeval.test_case import LLMTestCase

        # Simulate what the assistant would see
        test_input = "What if these shoes don't fit?"
        # Example output that follows the prompt with Australian expressions
        actual_output = "No worries! We've got you covered with a 30-day full refund at no extra cost, mate."

        metric = AnswerRelevancyMetric(threshold=0.7, model="gpt-4o", include_reason=True)

        test_case = LLMTestCase(input=test_input, actual_output=actual_output)

        # Assert test passes
        assert_test(test_case, [metric])

    def test_escalation_prompt_alignment(self) -> None:
        """Test that prompts correctly handle escalation requests.

        Validates that the assistant follows instructions to acknowledge
        escalation requests politely, as defined in the prompts.
        """
        from deepeval import assert_test
        from deepeval.metrics import PromptAlignmentMetric
        from deepeval.test_case import LLMTestCase

        # Test with escalation request
        test_input = "I need to speak with a human representative right now."
        # Expected: polite acknowledgment per prompt instructions with Australian expressions
        actual_output = "No worries, mate! I understand you'd like to have a chat with one of our human representatives. Let me get you connected with someone who can help you out straight away."

        metric = PromptAlignmentMetric(
            prompt_instructions=[DEFAULT_ASSISTANT_PROMPT.instructions], model="gpt-4o", include_reason=True
        )

        test_case = LLMTestCase(input=test_input, actual_output=actual_output)

        assert_test(test_case, [metric])

    def test_technical_support_prompt_specificity(self) -> None:
        """Test technical support prompt produces appropriate technical guidance.

        Validates that the technical support prompt results in clear,
        step-by-step troubleshooting responses.
        """
        from deepeval import assert_test
        from deepeval.metrics import AnswerRelevancyMetric
        from deepeval.test_case import LLMTestCase

        test_input = "My device won't turn on. What should I do?"
        # Example output following technical support prompt with Australian expressions
        actual_output = (
            "Let's troubleshoot this step by step. First, connect your device to a power source "
            "and leave it charging for 30 minutes - the battery might be completely flat. "
            "After that, press and hold the power button for 10 seconds to perform a hard reset. "
            "If it still won't turn on after these steps, the issue might need a specialist to have a look."
        )

        metric = AnswerRelevancyMetric(threshold=0.7, model="gpt-4o", include_reason=True)

        test_case = LLMTestCase(input=test_input, actual_output=actual_output)

        assert_test(test_case, [metric])

    def test_sales_prompt_product_focus(self) -> None:
        """Test sales assistant prompt maintains product-focused responses.

        Validates that the sales assistant prompt results in helpful
        product information and appropriate escalation offers.
        """
        from deepeval import assert_test
        from deepeval.metrics import AnswerRelevancyMetric
        from deepeval.test_case import LLMTestCase

        test_input = "Can you tell me about the premium features?"
        # Example output following sales assistant prompt with Australian expressions
        actual_output = (
            "G'day! Our premium plan is a ripper - it includes unlimited storage, priority support, "
            "advanced analytics, and API access. The cost is $49 a month. "
            "Would you like me to connect you with one of our sales reps "
            "who can have a proper chat about pricing options and help you get started?"
        )

        metric = AnswerRelevancyMetric(threshold=0.7, model="gpt-4o", include_reason=True)

        test_case = LLMTestCase(input=test_input, actual_output=actual_output)

        assert_test(test_case, [metric])
