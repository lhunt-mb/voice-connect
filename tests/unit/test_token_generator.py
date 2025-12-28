"""Tests for token generation."""

import pytest

from services.orchestrator.token_generator import generate_token


@pytest.mark.unit
def test_generate_token_default_length() -> None:
    """Test token generation with default length."""
    token = generate_token()
    assert len(token) == 10
    assert token.isdigit()


@pytest.mark.unit
def test_generate_token_custom_length() -> None:
    """Test token generation with custom length."""
    token = generate_token(length=8)
    assert len(token) == 8
    assert token.isdigit()


@pytest.mark.unit
def test_generate_token_uniqueness() -> None:
    """Test that generated tokens are different."""
    tokens = [generate_token() for _ in range(100)]
    # Should have high uniqueness (allow some collisions in 100 samples)
    assert len(set(tokens)) > 90


@pytest.mark.unit
def test_generate_token_numeric_only() -> None:
    """Test that tokens contain only digits."""
    for _ in range(10):
        token = generate_token()
        assert all(c in "0123456789" for c in token)
