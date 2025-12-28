# AI Assistant Prompts

This directory contains AI assistant prompt configurations for the OpenAI Realtime API integration.

## Overview

The `prompts.py` module provides structured, testable prompt configurations that define the behavior of AI assistants in the system. Prompts are abstracted from the orchestrator code to enable:

- **Testability**: Evaluate prompts with DeepEval metrics
- **Maintainability**: Centralized prompt management
- **Flexibility**: Easy switching between different assistant personalities
- **Version Control**: Track prompt changes over time

## Structure

### AssistantPrompt Class

The `AssistantPrompt` dataclass represents a prompt configuration:

```python
@dataclass(frozen=True)
class AssistantPrompt:
    instructions: str  # System instructions for the AI
    voice: str = "alloy"  # Voice model (alloy, echo, shimmer, etc.)
    context: str = ""  # Description for documentation/testing
```

### Predefined Prompts

Three predefined prompts are available (all configured with Australian accent):

1. **DEFAULT_ASSISTANT_PROMPT**: General purpose customer service assistant with Australian accent
2. **TECHNICAL_SUPPORT_PROMPT**: Technical troubleshooting with Australian accent and escalation
3. **SALES_ASSISTANT_PROMPT**: Sales and product information assistance with Australian accent

## Usage

### In Production Code

```python
from services.orchestrator.prompts import DEFAULT_ASSISTANT_PROMPT, get_prompt
from services.orchestrator.openai_realtime import OpenAIRealtimeClient

# Use default prompt
client = OpenAIRealtimeClient(settings)

# Or specify a custom prompt
client = OpenAIRealtimeClient(settings, prompt=get_prompt("technical"))

# Or create a custom prompt
from services.orchestrator.prompts import AssistantPrompt

custom_prompt = AssistantPrompt(
    instructions="You are a billing support assistant speaking with an Australian accent...",
    voice="shimmer",
    context="Billing and payment support with Australian accent"
)
client = OpenAIRealtimeClient(settings, prompt=custom_prompt)
```

### Creating New Prompts

To add a new prompt:

1. Define the prompt in `prompts.py`:

```python
BILLING_SUPPORT_PROMPT = AssistantPrompt(
    instructions=(
        "You are a billing support assistant speaking with an Australian accent. "
        "Use Australian expressions naturally while helping customers with payment issues, invoices, and refunds. "
        "For complex billing disputes, offer to escalate to a billing specialist."
    ),
    voice="alloy",
    context="Billing and payment support with Australian accent and escalation",
)
```

2. Add it to the `get_prompt()` function:

```python
def get_prompt(prompt_type: str = "default") -> AssistantPrompt:
    prompts = {
        "default": DEFAULT_ASSISTANT_PROMPT,
        "technical": TECHNICAL_SUPPORT_PROMPT,
        "sales": SALES_ASSISTANT_PROMPT,
        "billing": BILLING_SUPPORT_PROMPT,  # Add here
    }
    # ...
```

3. Add tests in `tests/unit/test_prompts.py`

## Testing with DeepEval

### Running Unit Tests

Basic unit tests validate prompt structure and configuration:

```bash
# Run all prompt tests
pytest tests/unit/test_prompts.py

# Run only unit tests (skip DeepEval)
pytest tests/unit/test_prompts.py -m "not deepeval"
```

### Running DeepEval Tests

DeepEval tests use LLM-based metrics to evaluate prompt quality:

```bash
# Set your OpenAI API key
export OPENAI_API_KEY=your_key_here

# Install deepeval if not already installed
pip install -e ".[dev]"

# Run DeepEval tests
pytest tests/unit/test_prompts.py -m deepeval

# Run with verbose output
pytest tests/unit/test_prompts.py -m deepeval -v
```

### DeepEval Metrics Used

The test suite evaluates prompts using:

- **AnswerRelevancyMetric**: Validates responses are relevant to user queries
- **PromptAlignmentMetric**: Ensures outputs follow prompt instructions
- Threshold: 0.7 (70% minimum score to pass)

### Example DeepEval Test

```python
@pytest.mark.deepeval
def test_default_prompt_answer_relevancy(self) -> None:
    """Test that default prompt produces relevant answers."""
    from deepeval import evaluate
    from deepeval.metrics import AnswerRelevancyMetric
    from deepeval.test_case import LLMTestCase

    test_input = "What if these shoes don't fit?"
    actual_output = "We offer a 30-day full refund at no extra cost."

    metric = AnswerRelevancyMetric(
        threshold=0.7,
        model="gpt-4o",  # Use gpt-4o for structured output support
        include_reason=True
    )
    test_case = LLMTestCase(input=test_input, actual_output=actual_output)

    evaluate(test_cases=[test_case], metrics=[metric])
    assert metric.is_successful()
```

## Best Practices

### Writing Effective Prompts

1. **Be Specific**: Clearly define the assistant's role and capabilities
2. **Include Accent**: Specify Australian accent and natural expression usage
3. **Include Escalation**: Always mention how to handle human escalation requests
4. **Set Boundaries**: Define what the assistant should and shouldn't do
5. **Use Context**: Provide meaningful context for documentation and testing

### Prompt Guidelines

- Keep instructions concise but comprehensive
- Use active voice and clear language
- Include expected behaviors (e.g., "acknowledge politely")
- Test prompts with realistic scenarios before deployment

### Voice Selection

Available voices in OpenAI Realtime API:
- `alloy`: Neutral, professional
- `echo`: Clear, direct
- `shimmer`: Warm, friendly
- `fable`: Expressive, storytelling
- `onyx`: Authoritative, deep
- `nova`: Energetic, upbeat

## Monitoring and Iteration

### Tracking Prompt Performance

1. Monitor conversation logs for escalation rates
2. Track customer satisfaction scores
3. Review conversation transcripts for prompt adherence
4. Run DeepEval tests regularly to catch prompt degradation

### Updating Prompts

When updating prompts:
1. Create a new prompt version
2. Run full test suite (unit + DeepEval)
3. Deploy to staging environment
4. Monitor performance metrics
5. Gradually roll out to production

## References

- [OpenAI Realtime API Documentation](https://platform.openai.com/docs/guides/realtime)
- [DeepEval Documentation](https://docs.confident-ai.com/)
- [Prompt Engineering Guide](https://platform.openai.com/docs/guides/prompt-engineering)

## Support

For questions or issues with prompts:
- Review test failures in `tests/unit/test_prompts.py`
- Check DeepEval metrics for quality issues
- Consult team documentation for prompt guidelines
