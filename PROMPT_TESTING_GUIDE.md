# AI Prompt Testing Guide

This guide explains how to test and evaluate AI prompts using the new prompt abstraction and DeepEval framework.

## What Was Changed

The GenAI prompts have been extracted from the orchestrator into a separate, testable module:

### New Files

1. **[services/orchestrator/prompts.py](services/orchestrator/prompts.py)** - Prompt configurations
2. **[tests/unit/test_prompts.py](tests/unit/test_prompts.py)** - Unit and DeepEval tests
3. **[services/orchestrator/README_PROMPTS.md](services/orchestrator/README_PROMPTS.md)** - Detailed documentation

### Modified Files

1. **[services/orchestrator/openai_realtime.py](services/orchestrator/openai_realtime.py)** - Now accepts `AssistantPrompt` parameter
2. **[pyproject.toml](pyproject.toml)** - Added deepeval dependency and test marker

## Quick Start

### 1. Running Basic Unit Tests

Test prompt structure and configuration without LLM calls:

```bash
# Run all unit tests (excluding DeepEval)
pytest tests/unit/test_prompts.py -m "not deepeval" -v

# Should see 14 tests pass for:
# - AssistantPrompt immutability
# - Session config conversion
# - Predefined prompt structure
# - get_prompt() function
```

### 2. Running DeepEval Tests (Optional)

Evaluate prompt quality using LLM-based metrics:

```bash
# Set OpenAI API key
export OPENAI_API_KEY=sk-your-key-here

# Install DeepEval
pip install -e ".[dev]"

# Run DeepEval tests
pytest tests/unit/test_prompts.py -m deepeval -v

# These tests will:
# - Call OpenAI API to evaluate prompt responses
# - Measure answer relevancy (threshold: 0.7)
# - Check prompt alignment
# - Validate escalation handling
```

## Using Prompts in Code

### Default Prompt

```python
from services.orchestrator.openai_realtime import OpenAIRealtimeClient
from shared.config import Settings

# Uses DEFAULT_ASSISTANT_PROMPT automatically
client = OpenAIRealtimeClient(settings)
```

### Predefined Prompts

```python
from services.orchestrator.prompts import get_prompt

# Technical support prompt
client = OpenAIRealtimeClient(settings, prompt=get_prompt("technical"))

# Sales assistant prompt
client = OpenAIRealtimeClient(settings, prompt=get_prompt("sales"))
```

### Custom Prompts

```python
from services.orchestrator.prompts import AssistantPrompt

custom_prompt = AssistantPrompt(
    instructions="You are a billing support specialist...",
    voice="shimmer",
    context="Billing and payment support"
)

client = OpenAIRealtimeClient(settings, prompt=custom_prompt)
```

## Writing DeepEval Tests

### Example Test Structure

```python
@pytest.mark.deepeval
def test_my_prompt_quality(self) -> None:
    """Test prompt produces relevant answers."""
    from deepeval import evaluate
    from deepeval.metrics import AnswerRelevancyMetric
    from deepeval.test_case import LLMTestCase

    # Simulate user input
    test_input = "How do I reset my password?"

    # Example response that follows your prompt
    actual_output = "You can reset your password by clicking the 'Forgot Password' link on the login page."

    # Define metric
    metric = AnswerRelevancyMetric(
        threshold=0.7,  # 70% minimum score
        model="gpt-4o",  # Use gpt-4o for structured output support
        include_reason=True
    )

    # Create test case
    test_case = LLMTestCase(
        input=test_input,
        actual_output=actual_output
    )

    # Evaluate
    evaluate(test_cases=[test_case], metrics=[metric])

    # Assert success
    assert metric.is_successful(), f"Failed: {metric.reason}"
```

### Available DeepEval Metrics

From the Context7 documentation, key metrics include:

- **AnswerRelevancyMetric**: Is the answer relevant to the question?
- **PromptAlignmentMetric**: Does the output follow prompt instructions?
- **FaithfulnessMetric**: Is the answer factually accurate?
- **ContextualRelevancyMetric**: Is retrieved context relevant? (for RAG)

## Test Organization

### Current Test Structure

```
tests/unit/test_prompts.py
├── TestAssistantPrompt (4 tests)
│   ├── Immutability
│   ├── Session config conversion
│   ├── Default values
│   └── Configuration
├── TestPredefinedPrompts (5 tests)
│   ├── Structure validation
│   ├── Escalation handling
│   └── Context documentation
├── TestGetPrompt (5 tests)
│   └── Prompt retrieval logic
└── TestPromptQualityWithDeepEval (4 tests) [@deepeval marker]
    ├── Answer relevancy
    ├── Prompt alignment
    ├── Technical support
    └── Sales assistant
```

## CI/CD Integration

### Running in CI

```yaml
# GitHub Actions example
- name: Run unit tests
  run: pytest tests/unit/test_prompts.py -m "not deepeval"

# Optional: Run DeepEval tests with API key
- name: Run DeepEval tests
  if: env.OPENAI_API_KEY != ''
  run: pytest tests/unit/test_prompts.py -m deepeval
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

## Best Practices

### 1. Test Coverage

- **Unit tests**: Fast, always run (structure validation)
- **DeepEval tests**: Slower, optional (quality evaluation)

### 2. Writing Prompts

✅ **Good:**
- Clear role definition
- Specific behaviors
- Escalation handling
- Concise instructions

❌ **Avoid:**
- Vague instructions
- Overly long prompts
- No escalation path
- Missing context field

### 3. Iterating on Prompts

1. Modify prompt in [prompts.py](services/orchestrator/prompts.py)
2. Run unit tests: `pytest tests/unit/test_prompts.py -m "not deepeval"`
3. Run DeepEval: `pytest tests/unit/test_prompts.py -m deepeval`
4. Review metrics and iterate
5. Update documentation

## Example: Adding a New Prompt

### Step 1: Define the Prompt

```python
# In services/orchestrator/prompts.py

BILLING_SUPPORT_PROMPT = AssistantPrompt(
    instructions=(
        "You are a billing support specialist. "
        "Help customers with invoices, payments, and refunds. "
        "For complex disputes, offer to escalate to a billing manager."
    ),
    voice="alloy",
    context="Billing and payment assistance with escalation",
)
```

### Step 2: Register in get_prompt()

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

### Step 3: Add Tests

```python
# In tests/unit/test_prompts.py

def test_billing_prompt_structure(self) -> None:
    """Validate BILLING_SUPPORT_PROMPT configuration."""
    assert BILLING_SUPPORT_PROMPT.instructions
    assert "billing" in BILLING_SUPPORT_PROMPT.context.lower()

@pytest.mark.deepeval
def test_billing_prompt_quality(self) -> None:
    """Test billing prompt produces relevant answers."""
    # ... DeepEval test implementation
```

## Troubleshooting

### DeepEval Import Errors

If you see warnings about missing deepeval imports:

```bash
# Install deepeval
pip install -e ".[dev]"

# Or install directly
pip install deepeval
```

### Type Checking Warnings

The pyright warnings for deepeval imports are expected and non-blocking. DeepEval is an optional dependency for testing.

### API Key Issues

```bash
# Verify API key is set
echo $OPENAI_API_KEY

# Test API access
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

## Resources

- **DeepEval Documentation**: https://docs.confident-ai.com/
- **OpenAI Realtime API**: https://platform.openai.com/docs/guides/realtime
- **Prompt Engineering Guide**: https://platform.openai.com/docs/guides/prompt-engineering
- **Internal Documentation**: [README_PROMPTS.md](services/orchestrator/README_PROMPTS.md)

## Summary

The prompt abstraction provides:

✅ **Testability** - Unit and LLM-based quality tests
✅ **Maintainability** - Centralized prompt management
✅ **Flexibility** - Easy prompt switching
✅ **Quality Assurance** - DeepEval metrics validation

Start testing your prompts today to ensure consistent, high-quality AI interactions!
