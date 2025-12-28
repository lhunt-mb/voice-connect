"""Token generation utilities."""

import random
import string


def generate_token(length: int = 10) -> str:
    """Generate a random numeric token.

    Args:
        length: Length of the token (default 10 digits)

    Returns:
        Numeric token string
    """
    return "".join(random.choices(string.digits, k=length))
