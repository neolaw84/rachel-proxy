"""Model and provider detection utilities."""

import re


def is_gemini_model(
    model: str | None,
    base_url: str | None = None,
    provider: str | None = None,
) -> bool:
    """Return True if model name, base_url, or provider corresponds to Google Gemini."""
    if provider and provider == "gemini_byok":
        return True
    if not model and not base_url:
        return False
    if model and re.search(r"gemini", str(model), re.IGNORECASE):
        return True
    if base_url and re.search(r"generativelanguage\.googleapis\.com", str(base_url), re.IGNORECASE):
        return True
    return False
