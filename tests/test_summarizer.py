"""Unit tests for the summarizer module."""

from src.summarizer import summarize_news


def test_summarizer_includes_input():
    """Test that the summarizer output contains the input news text."""
    result = summarize_news("Test news")
    assert "Test news" in result
