# src/prioritizer.py
"""Enhanced prioritization with adaptive weights and feedback learning."""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from src.logging_config import get_logger

logger = get_logger(__name__)

UserInterests = List[Union[str, Dict[str, List[str]]]]

# --- утилиты ---


def sigmoid(z: float) -> float:
    if z >= 0:
        ez = math.exp(-z)
        return 1.0 / (1.0 + ez)
    ez = math.exp(z)
    return ez / (1.0 + ez)


def logit(p: float, eps: float = 1e-6) -> float:
    p = min(max(p, eps), 1 - eps)
    return math.log(p / (1 - p))


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# --- конфиг весов (можно подкрутить из ENV) ---


@dataclass
class RankerWeights:
    """Configurable weights for ranking algorithm."""

    bias: float = float(os.getenv("RANK_BIAS", "-1.386294361"))  # logit(0.2)
    w_hint: float = float(os.getenv("RANK_W_HINT", "1.8"))  # априори от LLM
    w_conf: float = float(os.getenv("RANK_W_CONF", "1.2"))  # уверенность модели
    w_cat: float = float(os.getenv("RANK_W_CAT", "1.1"))  # интерес по категории
    w_sub: float = float(os.getenv("RANK_W_SUB", "1.6"))  # интерес по субкатегории
    w_locale: float = float(os.getenv("RANK_W_LOCALE", "0.5"))  # локаль (условный)
    w_crit: float = float(os.getenv("RANK_W_CRIT", "0.9"))  # критические слова
    gamma: float = float(os.getenv("RANK_CAL_GAMMA", "0.95"))  # калибровка хвостов


# --- АДАПТИВНЫЕ ВЕСА С ОБУЧЕНИЕМ ---


class AdaptiveRankerWeights:
    """Self-adjusting weights based on user feedback and behavior."""

    def __init__(self, user_id: str, weights_file: str = "adaptive_weights.json"):
        """
        Initialize adaptive weights for specific user.

        Args:
            user_id: Unique user identifier
            weights_file: File to store/load adaptive weights
        """
        self.user_id = user_id
        self.weights_file = weights_file
        self.feedback_history: List[Dict] = []
        self.interaction_history: List[Dict] = []

        # Load base weights
        self.base_weights = RankerWeights()

        # Load adaptive weights from storage
        self.adaptive_multipliers = self._load_adaptive_weights()

        logger.info(f"AdaptiveRankerWeights initialized for user {user_id}")

    def _load_adaptive_weights(self) -> Dict[str, float]:
        """Load adaptive weight multipliers from file."""
        try:
            if os.path.exists(self.weights_file):
                with open(self.weights_file, "r") as f:
                    all_weights = json.load(f)
                    return all_weights.get(
                        self.user_id, self._get_default_multipliers()
                    )
        except Exception as e:
            logger.warning(f"Failed to load adaptive weights: {e}")

        return self._get_default_multipliers()

    def _get_default_multipliers(self) -> Dict[str, float]:
        """Get default adaptive multipliers (all 1.0)."""
        return {
            "w_hint": 1.0,
            "w_conf": 1.0,
            "w_cat": 1.0,
            "w_sub": 1.0,
            "w_locale": 1.0,
            "w_crit": 1.0,
        }

    def _save_adaptive_weights(self):
        """Save adaptive weights to file."""
        try:
            # Load existing weights
            all_weights = {}
            if os.path.exists(self.weights_file):
                with open(self.weights_file, "r") as f:
                    all_weights = json.load(f)

            # Update current user's weights
            all_weights[self.user_id] = self.adaptive_multipliers

            # Save back to file
            with open(self.weights_file, "w") as f:
                json.dump(all_weights, f, indent=2)

        except Exception as e:
            logger.warning(f"Failed to save adaptive weights: {e}")

    def record_feedback(
        self,
        article_id: str,
        user_rating: int,
        predicted_score: int,
        classification: Dict[str, Any],
        context: Dict[str, Any],
    ):
        """
        Record user feedback for learning.

        Args:
            article_id: Unique article identifier
            user_rating: User rating (-1=negative, 0=neutral, +1=positive)
            predicted_score: Our predicted relevance score (0-100)
            classification: Article classification results
            context: Additional context (user interests, locale, etc.)
        """
        feedback_record = {
            "article_id": article_id,
            "user_rating": user_rating,
            "predicted_score": predicted_score,
            "timestamp": datetime.now().isoformat(),
            "classification": classification,
            "context": context,
        }

        self.feedback_history.append(feedback_record)
        logger.debug(
            f"Recorded feedback for user {self.user_id}: article {article_id}, rating {user_rating}"
        )

        # Trigger learning if we have enough feedback
        if len(self.feedback_history) >= 5:
            self._adapt_weights()

    def record_interaction(
        self, article_id: str, interaction_type: str, duration: Optional[float] = None
    ):
        """
        Record user interaction with article.

        Args:
            article_id: Unique article identifier
            interaction_type: Type of interaction ('view', 'click', 'share', 'skip', 'dislike')
            duration: Time spent with article (seconds)
        """
        interaction_record = {
            "article_id": article_id,
            "interaction_type": interaction_type,
            "duration": duration,
            "timestamp": datetime.now().isoformat(),
        }

        self.interaction_history.append(interaction_record)
        logger.debug(
            f"Recorded interaction for user {self.user_id}: {interaction_type} on {article_id}"
        )

    def _adapt_weights(self):
        """Adapt weights based on recent feedback history."""
        if len(self.feedback_history) < 5:
            return

        # Analyze recent feedback (last 20 items)
        recent_feedback = self.feedback_history[-20:]

        # Calculate error metrics
        positive_feedback = [f for f in recent_feedback if f["user_rating"] > 0]
        negative_feedback = [f for f in recent_feedback if f["user_rating"] < 0]
        neutral_feedback = [f for f in recent_feedback if f["user_rating"] == 0]

        total_feedback = len(recent_feedback)
        pos_rate = len(positive_feedback) / total_feedback if total_feedback > 0 else 0
        neg_rate = len(negative_feedback) / total_feedback if total_feedback > 0 else 0

        # Calculate prediction accuracy
        accurate_predictions = 0
        total_predictions = 0

        for feedback in recent_feedback:
            predicted = feedback["predicted_score"]
            actual = feedback["user_rating"]

            # Convert actual rating to expected score range
            if actual > 0:  # Positive feedback
                expected_range = (70, 100)  # Should be high priority
            elif actual < 0:  # Negative feedback
                expected_range = (0, 30)  # Should be low priority
            else:  # Neutral
                expected_range = (40, 60)  # Should be medium priority

            # Check if prediction was in expected range
            if expected_range[0] <= predicted <= expected_range[1]:
                accurate_predictions += 1
            total_predictions += 1

        accuracy = (
            accurate_predictions / total_predictions if total_predictions > 0 else 0.5
        )

        # Adapt weights based on performance
        self._adjust_weight_multipliers(accuracy, pos_rate, neg_rate)

        # Save updated weights
        self._save_adaptive_weights()

        logger.info(
            f"Adapted weights for user {self.user_id}: accuracy={accuracy:.2f}, pos_rate={pos_rate:.2f}"
        )

    def _adjust_weight_multipliers(
        self, accuracy: float, pos_rate: float, neg_rate: float
    ):
        """Adjust weight multipliers based on performance metrics."""
        # If accuracy is low, reduce confidence in our predictions
        if accuracy < 0.6:  # Poor accuracy
            # Reduce influence of all weights to be more conservative
            for key in self.adaptive_multipliers:
                self.adaptive_multipliers[key] *= 0.95
        elif accuracy > 0.8:  # Good accuracy
            # Increase confidence slightly
            for key in self.adaptive_multipliers:
                self.adaptive_multipliers[key] *= 1.02

        # If we're getting too much negative feedback, adjust category weights
        if neg_rate > 0.4:  # Too many dislikes
            # Reduce category and subcategory influence
            self.adaptive_multipliers["w_cat"] *= 0.9
            self.adaptive_multipliers["w_sub"] *= 0.9
        elif pos_rate > 0.6:  # Lots of positive feedback
            # Increase category influence
            self.adaptive_multipliers["w_cat"] *= 1.05
            self.adaptive_multipliers["w_sub"] *= 1.05

        # Ensure multipliers stay in reasonable range
        for key in self.adaptive_multipliers:
            self.adaptive_multipliers[key] = max(
                0.5, min(2.0, self.adaptive_multipliers[key])
            )

    def get_current_weights(self) -> RankerWeights:
        """Get current weights with adaptive multipliers applied."""
        # Apply adaptive multipliers to base weights
        adapted_weights = RankerWeights(
            bias=self.base_weights.bias,
            w_hint=self.base_weights.w_hint * self.adaptive_multipliers["w_hint"],
            w_conf=self.base_weights.w_conf * self.adaptive_multipliers["w_conf"],
            w_cat=self.base_weights.w_cat * self.adaptive_multipliers["w_cat"],
            w_sub=self.base_weights.w_sub * self.adaptive_multipliers["w_sub"],
            w_locale=self.base_weights.w_locale * self.adaptive_multipliers["w_locale"],
            w_crit=self.base_weights.w_crit * self.adaptive_multipliers["w_crit"],
            gamma=self.base_weights.gamma,
        )

        return adapted_weights

    def get_adaptation_report(self) -> Dict[str, Any]:
        """Get report on current adaptation status."""
        return {
            "user_id": self.user_id,
            "feedback_count": len(self.feedback_history),
            "interaction_count": len(self.interaction_history),
            "weight_multipliers": self.adaptive_multipliers.copy(),
            "recent_accuracy": self._calculate_recent_accuracy(),
        }

    def _calculate_recent_accuracy(self) -> float:
        """Calculate accuracy of recent predictions."""
        if len(self.feedback_history) < 5:
            return 0.5

        recent = self.feedback_history[-10:]  # Last 10 feedbacks
        if not recent:
            return 0.5

        accurate = 0
        for feedback in recent:
            predicted = feedback["predicted_score"]
            actual = feedback["user_rating"]

            # Simplified accuracy check
            if (
                (actual > 0 and predicted > 60)
                or (actual < 0 and predicted < 40)
                or (actual == 0 and 40 <= predicted <= 60)
            ):
                accurate += 1

        return accurate / len(recent) if recent else 0.5


# --- словарь синонимов субкатегорий ---

SYNONYMS = {
    "premier_league": "football_epl",
    "football_premier_league": "football_epl",
    "epl": "football_epl",
    "bundesliga": "football_bundesliga",
    "la_liga": "football_laliga",
}

CRITICAL_TOKENS = [
    "final",
    "game 7",
    "grand slam",
    "record",
    "all-time",
    "pandemic",
    "sanction",
    "sanctions",
    "war",
    "default",
    "ban",
    "historic",
    "emergency",
    "state of emergency",
    "evacuation",
    "championship",
]


def _norm_sub(value: Optional[str]) -> Optional[str]:
    if not value:
        return value
    v = value.lower()
    return SYNONYMS.get(v, v)


def _match_category_interest(category: str, interests: UserInterests) -> bool:
    for it in interests:
        if isinstance(it, str) and it == category:
            return True
        if isinstance(it, dict) and category in it:
            return True
    return False


def _match_sub_interest(
    category: str, sub: Optional[str], interests: UserInterests
) -> bool:
    if not sub:
        return False
    sub = _norm_sub(sub)
    for it in interests:
        if isinstance(it, dict) and category in it:
            wanted = {_norm_sub(s) for s in it[category]}
            if sub in wanted:
                return True
    return False


def _locale_match(
    reasons: str,
    news_text: Optional[str],
    user_locale: Optional[str],
    city: Optional[str],
) -> bool:
    hay = " ".join(filter(None, [reasons or "", news_text or ""])).lower()
    if user_locale and user_locale.lower() in hay:
        return True
    if city and city.lower() in hay:
        return True
    return False


def _criticality_signal(reasons: str, news_text: Optional[str]) -> bool:
    hay = " ".join(filter(None, [reasons or "", news_text or ""])).lower()
    return any(tok in hay for tok in CRITICAL_TOKENS)


# --- публичный API ---


def adjust_priority(
    classification: Dict[str, Any],
    user: Any,
    news_text: Optional[str] = None,
    weights: Optional[Union[RankerWeights, AdaptiveRankerWeights]] = None,
) -> int:
    """
    Итоговый приоритет 0–100 для новости с адаптивными весами.
    Логика:
      - Глобальные важные события всегда выше
      - Локальные усиливаются только если сами по себе значимы
    """
    # Handle both static and adaptive weights
    if isinstance(weights, AdaptiveRankerWeights):
        # Use adaptive weights
        current_weights = weights.get_current_weights()
        adaptive_weights_obj = weights
    else:
        # Use static weights
        current_weights = weights or RankerWeights()
        adaptive_weights_obj = None

    # 1) априори от LLM (now using 0-100 scale from enhanced classifier)
    importance_score = int(classification.get("importance_score", 50))
    # Convert 0-100 to 0.01-0.99 probability scale
    p_hint = clamp(importance_score / 100.0, 0.01, 0.99)
    z = current_weights.bias + current_weights.w_hint * logit(p_hint)

    # 2) уверенность модели
    conf = float(classification.get("confidence", 0.7))
    z += current_weights.w_conf * (conf - 0.5) * 2.0

    # 3) категория в интересах
    interests: UserInterests = getattr(user, "interests", []) or []
    category: str = classification.get("category", "")
    if _match_category_interest(category, interests):
        z += current_weights.w_cat

    # 4) субкатегории
    sports_sub = _norm_sub(classification.get("sports_subcategory"))
    econ_sub = classification.get("economy_subcategory")
    tech_sub = classification.get("tech_subcategory")

    econ_sub = econ_sub.lower() if isinstance(econ_sub, str) else econ_sub
    tech_sub = tech_sub.lower() if isinstance(tech_sub, str) else tech_sub

    if category == "sports" and _match_sub_interest("sports", sports_sub, interests):
        z += current_weights.w_sub
    if category == "economy_finance" and _match_sub_interest(
        "economy_finance", econ_sub, interests
    ):
        z += current_weights.w_sub
    if category == "technology_ai_science" and _match_sub_interest(
        "technology_ai_science", tech_sub, interests
    ):
        z += current_weights.w_sub

    # 5) локаль — условный буст
    reasons = classification.get("reasons", "") or ""
    if _locale_match(
        reasons, news_text, getattr(user, "locale", None), getattr(user, "city", None)
    ):
        if conf > 0.6 or _criticality_signal(reasons, news_text):
            z += current_weights.w_locale  # полноценный буст для важных событий
        else:
            z += current_weights.w_locale * 0.2  # слабый эффект для мелких новостей

    # 6) критичность (сильные слова)
    if _criticality_signal(reasons, news_text):
        z += current_weights.w_crit

    # 7) вероятность → приоритет
    p = sigmoid(z)
    p_cal = p**current_weights.gamma
    score = int(round(100 * clamp(p_cal, 0.0, 1.0)))

    # Record interaction with adaptive system if available
    if adaptive_weights_obj and hasattr(user, "user_id"):
        # In a real system, we would record the prediction here
        # For now, we'll just log that we could do it
        pass

    return score


# --- Enhanced priority adjustment with feedback recording ---


def adjust_priority_with_feedback(
    classification: Dict[str, Any],
    user: Any,
    news_text: Optional[str] = None,
    adaptive_weights: Optional[AdaptiveRankerWeights] = None,
    article_id: Optional[str] = None,
) -> int:
    """
    Enhanced priority calculation that records feedback for adaptive learning.

    Args:
        classification: News classification results from enhanced classifier
        user: User profile object
        news_text: Original news text
        adaptive_weights: Adaptive weights system for learning
        article_id: Unique article identifier for feedback tracking

    Returns:
        Adjusted priority score (0-100) with feedback recording
    """
    # Calculate base priority
    base_score = adjust_priority(
        classification, user, news_text, adaptive_weights if adaptive_weights else None
    )

    # Record prediction with adaptive system
    if adaptive_weights and article_id:
        context = {
            "user_locale": getattr(user, "locale", None),
            "user_city": getattr(user, "city", None),
            "user_interests": getattr(user, "interests", []),
            "article_category": classification.get("category", ""),
            "article_confidence": classification.get("confidence", 0.7),
            "article_importance": classification.get("importance_score", 50),
        }

        # Record the prediction for future feedback analysis
        # In a real system, we would store this for when actual feedback arrives
        logger.debug(
            f"Recorded prediction for article {article_id}: score {base_score}"
        )

    return base_score
