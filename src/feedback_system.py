"""User feedback collection and processing system for continuous improvement."""

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class Feedback:
    """Represents user feedback for a news item."""

    user_id: str
    news_id: str
    rating: int  # -1 (dislike), 0 (neutral), +1 (like)
    category: str
    timestamp: datetime
    comment: Optional[str] = None


class FeedbackSystem:
    """Manages user feedback collection and analysis."""

    def __init__(self, feedback_file: str = "user_feedback.json"):
        """
        Initialize feedback system.

        Args:
            feedback_file: File to store feedback persistently
        """
        self.feedback_file = feedback_file
        self.feedback_storage: List[Feedback] = []
        self.user_preferences: Dict[str, Dict[str, float]] = {}

        # Load existing feedback
        self._load_feedback()
        self._recalculate_preferences()

        print(
            f"📊 FeedbackSystem initialized with {len(self.feedback_storage)} feedback items"
        )

    def _load_feedback(self):
        """Load feedback from persistent storage."""
        try:
            if os.path.exists(self.feedback_file):
                with open(self.feedback_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data:
                        # Convert timestamp string to datetime
                        item["timestamp"] = datetime.fromisoformat(item["timestamp"])
                        feedback = Feedback(**item)
                        self.feedback_storage.append(feedback)
                print(
                    f"📥 Loaded {len(self.feedback_storage)} feedback items from {self.feedback_file}"
                )
        except Exception as e:
            print(f"⚠️  Failed to load feedback: {e}")
            self.feedback_storage = []

    def _save_feedback(self):
        """Save feedback to persistent storage."""
        try:
            # Convert datetime to string for JSON serialization
            data = []
            for feedback in self.feedback_storage:
                feedback_dict = asdict(feedback)
                feedback_dict["timestamp"] = feedback.timestamp.isoformat()
                data.append(feedback_dict)

            with open(self.feedback_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"💾 Feedback saved to {self.feedback_file}")
        except Exception as e:
            print(f"⚠️  Failed to save feedback: {e}")

    def add_feedback(
        self,
        user_id: str,
        news_id: str,
        rating: int,
        category: str,
        comment: Optional[str] = None,
    ):
        """
        Add user feedback for a news item.

        Args:
            user_id: User identifier
            news_id: News item identifier
            rating: User rating (-1, 0, +1)
            category: News category
            comment: Optional user comment
        """
        feedback = Feedback(
            user_id=user_id,
            news_id=news_id,
            rating=rating,
            category=category,
            timestamp=datetime.now(),
            comment=comment,
        )

        self.feedback_storage.append(feedback)
        self._save_feedback()
        self._update_user_preferences(feedback)

        print(f"👍 Feedback added: User {user_id} rated news {news_id} as {rating}")

    def _update_user_preferences(self, feedback: Feedback):
        """Update user preferences based on feedback."""
        user_id = feedback.user_id
        category = feedback.category
        rating = feedback.rating

        if user_id not in self.user_preferences:
            self.user_preferences[user_id] = {}

        current_score = self.user_preferences[user_id].get(category, 0.5)

        # Simple preference update algorithm
        if rating > 0:  # Like
            new_score = min(1.0, current_score + 0.1)
        elif rating < 0:  # Dislike
            new_score = max(0.0, current_score - 0.1)
        else:  # Neutral
            # Small adjustment towards 0.5 (neutral)
            if current_score > 0.5:
                new_score = current_score - 0.05
            else:
                new_score = current_score + 0.05

        self.user_preferences[user_id][category] = round(new_score, 3)
        print(f"📈 Updated preference for {user_id}/{category}: {new_score}")

    def _recalculate_preferences(self):
        """Recalculate all user preferences from stored feedback."""
        self.user_preferences = {}
        for feedback in self.feedback_storage:
            self._update_user_preferences(feedback)
        print(f"🔄 Recalculated preferences for {len(self.user_preferences)} users")

    def get_user_preference(self, user_id: str, category: str) -> float:
        """
        Get user preference score for a category.

        Args:
            user_id: User identifier
            category: News category

        Returns:
            Preference score (0.0 to 1.0, 0.5 = neutral)
        """
        return self.user_preferences.get(user_id, {}).get(category, 0.5)

    def get_feedback_stats(self) -> Dict[str, Any]:
        """Get feedback statistics."""
        if not self.feedback_storage:
            return {"total_feedback": 0}

        positive = sum(1 for f in self.feedback_storage if f.rating > 0)
        negative = sum(1 for f in self.feedback_storage if f.rating < 0)
        neutral = sum(1 for f in self.feedback_storage if f.rating == 0)
        total = len(self.feedback_storage)

        # Category distribution
        category_stats = {}
        for feedback in self.feedback_storage:
            category = feedback.category
            if category not in category_stats:
                category_stats[category] = {"positive": 0, "negative": 0, "neutral": 0}
            if feedback.rating > 0:
                category_stats[category]["positive"] += 1
            elif feedback.rating < 0:
                category_stats[category]["negative"] += 1
            else:
                category_stats[category]["neutral"] += 1

        return {
            "total_feedback": total,
            "positive": positive,
            "negative": negative,
            "neutral": neutral,
            "positive_ratio": round(positive / total, 3) if total > 0 else 0,
            "negative_ratio": round(negative / total, 3) if total > 0 else 0,
            "category_stats": category_stats,
        }

    def get_user_feedback_history(self, user_id: str) -> List[Feedback]:
        """Get feedback history for a specific user."""
        return [f for f in self.feedback_storage if f.user_id == user_id]


# Global feedback system instance
feedback_system = FeedbackSystem()
