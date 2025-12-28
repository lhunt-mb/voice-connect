# DeepEval Testing Notes

## Model Compatibility

### Issue
The initial implementation used `gpt-4` as the evaluation model, which caused errors with DeepEval:

```
openai.BadRequestError: Error code: 400 - {'error': {'message': "Invalid parameter: 'response_format' of type 'json_schema' is not supported with this model.
```

### Solution
Updated all DeepEval tests to use **`gpt-4o`** instead of `gpt-4`.

`gpt-4o` supports structured outputs with JSON schema, which is required by DeepEval's evaluation metrics.

### Files Changed
- [tests/unit/test_prompts.py](tests/unit/test_prompts.py) - Updated all 4 DeepEval tests
- [PROMPT_TESTING_GUIDE.md](PROMPT_TESTING_GUIDE.md) - Updated documentation
- [services/orchestrator/README_PROMPTS.md](services/orchestrator/README_PROMPTS.md) - Updated examples

## Running DeepEval Tests

### Prerequisites
```bash
# Set OpenAI API key
export OPENAI_API_KEY=sk-your-key-here

# Verify deepeval is installed (should already be in dev dependencies)
pip install -e ".[dev]"
```

### Run Tests
```bash
# Run only DeepEval tests
pytest tests/unit/test_prompts.py -m deepeval -v

# Run with detailed output
pytest tests/unit/test_prompts.py -m deepeval -v -s
```

### Expected Behavior

When run with a valid API key, the tests will:
1. Call OpenAI API using `gpt-4o`
2. Evaluate test cases using DeepEval metrics
3. Return scores and reasons for each evaluation
4. Assert that scores meet the 0.7 threshold

**Note**: These tests will incur OpenAI API costs (typically $0.01-0.05 per test run).

## Test Coverage

### Unit Tests (Always Run)
- ✅ 14 tests
- ✅ No API calls required
- ✅ Fast execution (~0.02s)

### DeepEval Tests (Optional)
- ✅ 4 tests
- ⚠️ Requires OpenAI API key
- ⚠️ Slower execution (~10-30s)
- ⚠️ Incurs API costs

## Metrics Used

All DeepEval tests use these metrics with `gpt-4o`:

1. **AnswerRelevancyMetric** (3 tests)
   - Threshold: 0.7
   - Evaluates if responses are relevant to queries
   - Tests: default prompt, technical support, sales

2. **PromptAlignmentMetric** (1 test)
   - Threshold: 0.7
   - Validates outputs follow prompt instructions
   - Tests: escalation handling

## CI/CD Integration

### Recommended Approach

```yaml
# .github/workflows/test.yml

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Run unit tests (fast)
        run: pytest tests/unit/test_prompts.py -m "not deepeval"

      # Optional: Run DeepEval on main branch only
      - name: Run DeepEval tests (with API key)
        if: github.ref == 'refs/heads/main' && env.OPENAI_API_KEY != ''
        run: pytest tests/unit/test_prompts.py -m deepeval
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

## Troubleshooting

### Test Failures

If DeepEval tests fail:

1. **Check API Key**: Ensure `OPENAI_API_KEY` is set correctly
2. **Verify Model Access**: Confirm your account has access to `gpt-4o`
3. **Review Thresholds**: Consider adjusting threshold from 0.7 if needed
4. **Check Reasons**: DeepEval includes `reason` field explaining why tests failed

### Model Not Available

If you don't have access to `gpt-4o`:

```python
# Update tests to use gpt-4o-mini (cheaper, still supports structured output)
metric = AnswerRelevancyMetric(
    threshold=0.7,
    model="gpt-4o-mini",  # Alternative model
    include_reason=True
)
```

## Cost Estimation

Approximate costs per test run (4 tests with `gpt-4o`):
- Input tokens: ~500 per test = 2,000 total
- Output tokens: ~200 per test = 800 total
- Cost: ~$0.015-$0.030 per full test run

**Recommendation**: Run DeepEval tests on:
- Main branch merges
- Before production deployments
- When prompts are modified
- NOT on every PR (use unit tests instead)

## Future Improvements

Potential enhancements:
1. Add more evaluation metrics (Faithfulness, Bias, Toxicity)
2. Create golden dataset for regression testing
3. Implement A/B testing framework for prompt variations
4. Add performance benchmarks (latency, token usage)
5. Integrate with monitoring (track production prompt quality)

## Resources

- **DeepEval Documentation**: https://docs.confident-ai.com/
- **OpenAI Models**: https://platform.openai.com/docs/models
- **Structured Outputs**: https://platform.openai.com/docs/guides/structured-outputs
- **Internal Docs**: [PROMPT_TESTING_GUIDE.md](PROMPT_TESTING_GUIDE.md)
