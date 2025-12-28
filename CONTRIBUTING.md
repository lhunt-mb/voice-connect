# Contributing to Voice OpenAI Connect

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

## Development Setup

1. **Fork and clone the repository**
   ```bash
   git clone https://github.com/your-username/voice-openai-connect.git
   cd voice-openai-connect
   ```

2. **Install dependencies**
   ```bash
   pip install -e ".[dev]"
   ```

3. **Install pre-commit hooks**
   ```bash
   pre-commit install
   ```

4. **Copy environment template**
   ```bash
   cp .env.example .env
   # Edit .env with your development credentials
   ```

## Code Standards

### Python Style

- **Python 3.12** required
- **Type hints** on all functions and methods
- **Ruff** for formatting and linting
- **Pyright** for type checking (strict mode)

### Running Checks

```bash
# Format code
make format

# Lint
make lint

# Type check
make typecheck

# Run all checks
make format lint typecheck
```

### Pre-commit

Pre-commit hooks run automatically on `git commit`:
- Ruff formatting and linting
- Pyright type checking
- Unit test smoke tests

To run manually:
```bash
pre-commit run --all-files
```

## Testing

### Writing Tests

- Place unit tests in `tests/unit/`
- Mark tests with `@pytest.mark.unit`
- Use descriptive test names: `test_<function>_<scenario>`
- Mock external dependencies (boto3, httpx, etc.)

Example:
```python
@pytest.mark.unit
def test_generate_token_default_length() -> None:
    """Test token generation with default length."""
    token = generate_token()
    assert len(token) == 10
    assert token.isdigit()
```

### Running Tests

```bash
# All tests
make test

# Unit tests only
make test-unit

# With coverage
make test-cov
```

### Test Coverage

- Aim for >80% coverage on new code
- Focus on business logic and integration points
- Mock external services (Twilio, OpenAI, HubSpot, AWS)

## Commit Messages

Use conventional commit format:

```
<type>(<scope>): <subject>

<body>

<footer>
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting)
- `refactor`: Code refactoring
- `test`: Test changes
- `chore`: Build/tooling changes

Examples:
```
feat(orchestrator): add sentiment-based escalation

Implement sentiment analysis on user transcripts to
proactively trigger escalation when negative sentiment
is detected.

Closes #123
```

```
fix(gateway): handle OpenAI connection timeout

Add proper timeout handling when OpenAI WebSocket
fails to connect within 10 seconds.
```

## Pull Request Process

1. **Create a feature branch**
   ```bash
   git checkout -b feat/my-new-feature
   ```

2. **Make your changes**
   - Write code
   - Add tests
   - Update documentation

3. **Run checks locally**
   ```bash
   make format lint typecheck test
   ```

4. **Commit your changes**
   ```bash
   git add .
   git commit -m "feat(scope): description"
   ```

5. **Push to your fork**
   ```bash
   git push origin feat/my-new-feature
   ```

6. **Create Pull Request**
   - Provide clear description
   - Reference related issues
   - Ensure CI passes

### PR Requirements

- ✅ All tests pass
- ✅ Code coverage maintained or improved
- ✅ Type checking passes (pyright)
- ✅ Code formatted (ruff)
- ✅ Documentation updated
- ✅ Commit messages follow convention

## Code Review

- Be respectful and constructive
- Focus on code quality and maintainability
- Suggest improvements, don't demand
- Explain reasoning for requested changes

## Project Structure

```
voice-openai-connect/
├── shared/           # Shared utilities (config, logging, types)
├── services/
│   ├── orchestrator/ # Business logic and integrations
│   └── gateway/      # FastAPI gateway service
├── aws/
│   └── connect_lambda/  # Amazon Connect Lambda
├── tests/
│   └── unit/         # Unit tests
└── scripts/          # Deployment and utility scripts
```

## Adding New Features

### New Integration

1. Create client in `services/orchestrator/`
2. Add configuration to `shared/config.py`
3. Add types to `shared/types.py`
4. Write unit tests
5. Update documentation

### New Escalation Policy

1. Add logic to `services/orchestrator/escalation.py`
2. Update `check_escalation_needed()` function
3. Add tests for new policy
4. Document in README

### New API Endpoint

1. Add route to `services/gateway/app.py`
2. Update OpenAPI docs
3. Add integration test
4. Update README

## Documentation

Update documentation for:
- New features
- API changes
- Configuration changes
- Architecture changes

Documentation locations:
- README.md - User guide and quickstart
- ARCHITECTURE.md - System design and implementation
- Code docstrings - Inline documentation

## Questions?

- Open a GitHub issue for questions
- Tag with `question` label
- We'll respond within 48 hours

## License

By contributing, you agree that your contributions will be licensed under the same license as the project.
