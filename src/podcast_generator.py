# src/podcast_generator.py
"""Service to generate personalized podcast scripts from a user's TOP-7 news."""

import json
import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from mistralai import Mistral

# Load environment variables
load_dotenv()

# --- Configuration ---
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
PODCAST_MODEL = "mistral-small-latest"  # Можно использовать mistral-medium или другой, если нужно больше качества

# Import the prompt
try:
    from src.prompts import PODCAST_SCRIPT_PROMPT

    print("✅ Imported podcast prompts successfully")
except ImportError as e:
    print(f"❌ Failed to import podcast prompts: {e}")
    PODCAST_SCRIPT_PROMPT = "Error loading prompt."


class PodcastGenerator:
    """Generates personalized podcast scripts using Mistral AI."""

    def __init__(self):
        """Initialize the Podcast Generator with Mistral client."""
        if not MISTRAL_API_KEY:
            raise ValueError("MISTRAL_API_KEY not found in environment variables.")

        self.client = Mistral(api_key=MISTRAL_API_KEY)
        self.model = PODCAST_MODEL
        print(f"🎙️ PodcastGenerator initialized with model: {self.model}")

    def generate_podcast_script(
        self, user_profile: Dict[str, Any], top_7_news: List[Dict[str, Any]]
    ) -> str:
        """
        Generates a personalized podcast script for a user based on their TOP-7 news.

        Args:
            user_profile: Dictionary containing user profile data (id, email, locale, interests).
            top_7_news: List of dictionaries, each representing a news article with title, ynk_summary, etc.

        Returns:
            A string containing the full podcast script.
        """
        print(
            f"🎙️ Generating podcast script for user {user_profile.get('email', 'N/A')}..."
        )

        # Подготавливаем данные для промта
        user_profile_str = json.dumps(user_profile, indent=2, ensure_ascii=False)
        top_7_json_str = json.dumps(top_7_news, indent=2, ensure_ascii=False)

        # Формируем сообщение для Mistral
        # --- ИСПРАВЛЕНИЕ: system prompt должен быть просто текстом, а данные передаются в user message ---
        messages = [
            {"role": "system", "content": PODCAST_SCRIPT_PROMPT},  # <-- ИСПРАВЛЕНО
            {
                "role": "user",
                "content": f"Generate the podcast script for the user with profile {user_profile.get('email', 'N/A')}.\n\nUser Profile:\n{user_profile_str}\n\nTOP-7 News Items:\n{top_7_json_str}",  # <-- ИСПРАВЛЕНО
            },
        ]
        # --- КОНЕЦ ИСПРАВЛЕНИЯ ---

        try:
            # Вызываем Mistral API
            chat_response = self.client.chat.complete(
                model=self.model,
                messages=messages,
                temperature=0.7,  # Добавим немного креативности
                max_tokens=2000,  # Ограничиваем длину ответа
            )

            # Извлекаем текст скрипта
            script = chat_response.choices[0].message.content.strip()
            print("✅ Podcast script generated successfully.")
            return script

        except Exception as e:
            print(f"❌ Error generating podcast script: {e}")
            return (
                f"Oops! I couldn't generate your personalized podcast script this time. Here's your TOP-7 news instead:\n\n"
                + "\n\n".join([f"- {article['title']}" for article in top_7_news])
            )


# --- Singleton Instance ---
# Создаем один экземпляр для всего приложения
podcast_generator: Optional[PodcastGenerator] = None


def get_podcast_generator() -> Optional[PodcastGenerator]:
    """Get the singleton instance of PodcastGenerator."""
    global podcast_generator
    if podcast_generator is None:
        try:
            podcast_generator = PodcastGenerator()
        except Exception as e:
            print(f"⚠️ Failed to initialize PodcastGenerator: {e}")
            podcast_generator = None
    return podcast_generator
