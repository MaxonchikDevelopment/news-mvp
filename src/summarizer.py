"""Summarizer module for processing news with prompts."""

from mistralai import Mistral

from src.config import MISTRAL_API_KEY
from src.prompts import PROMPT
from src.utils import clean_text


def summarize_news(news: str) -> str:
    """
    Summarize a given news article using the Mistral API.

    Args:
        news (str): Raw news text.

    Returns:
        str: Summarized and formatted news text.
    """
    # Initialize client
    client = Mistral(api_key=MISTRAL_API_KEY)

    # Clean input text
    cleaned_news = clean_text(news)

    # Call Mistral API
    response = client.chat.complete(
        model="mistral-small-latest",
        messages=[
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": cleaned_news},
        ],
    )

    # Extract model response safely
    message = response.choices[0].message
    content = message.content if message and message.content else ""

    # Ensure bullet points always start on a new line
    formatted_result = content.replace("- ", "\n- ")

    return formatted_result
