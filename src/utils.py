"""Utility functions for text preprocessing and cleaning."""

import re


def clean_text(text: str) -> str:
    """Clean and normalize text by removing extra whitespace and line breaks.

    Args:
        text (str): Raw input text.

    Returns:
        str: Cleaned text with normalized spaces.
    """
    # Replace multiple spaces/newlines with a single space
    text = re.sub(r"\s+", " ", text)
    return text.strip()
