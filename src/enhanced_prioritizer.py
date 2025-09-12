"""Enhanced prioritization with feedback integration.
This module extends the original prioritizer by incorporating user feedback
while preserving all the excellent mathematical logic.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

# Import your excellent original prioritization function
from prioritizer import DEFAULT_WEIGHTS, RankerWeights, adjust_priority


def adjust_priority_with_feedback(
    classification: Dict[str, Any],
    user: Any,
    news_text: Optional[str] = None,
    weights: RankerWeights = DEFAULT_WEIGHTS,
    feedback_system=None,
) -> int:
    """
    Enhanced priority calculation that builds upon your excellent mathematical foundation.

    This function:
    1. Uses your proven adjust_priority as the base (90% of the magic)
    2. Adds user feedback to fine-tune personalization (10% personalization boost)

    Args:
        classification: Your excellent classification results
        user: User profile with interests
        news_text: Original news text
        weights: Your carefully tuned weights
        feedback_system: Feedback system for preference adjustment

    Returns:
        Final priority score (0-100) with feedback enhancement
    """
    # Step 1: Get your excellent base priority score
    base_score = adjust_priority(classification, user, news_text, weights)

    # Step 2: Apply gentle feedback adjustment (if available)
    if feedback_system is not None:
        try:
            category = classification.get("category", "")
            user_id = getattr(user, "user_id", "unknown")

            # Get user's preference for this category (learned from feedback)
            preference = feedback_system.get_user_preference(user_id, category)

            # Gentle adjustment: -10 to +10 points based on user preference
            # This preserves your mathematical foundation while adding personalization
            feedback_boost = (preference - 0.5) * 20  # -10 to +10

            # Apply the boost to your excellent base score
            enhanced_score = base_score + feedback_boost

            # Keep within valid range
            final_score = max(0, min(100, int(enhanced_score)))

            # Log significant adjustments
            if abs(feedback_boost) > 2:  # Only log meaningful adjustments
                print(
                    f"🎯 Feedback enhancement: {user_id}/{category} "
                    f"(preference: {preference:.2f}) → {feedback_boost:+.0f} points"
                )

            return final_score

        except Exception as e:
            print(f"⚠️  Feedback enhancement failed: {e}")
            # Gracefully fall back to your excellent base score
            return base_score

    # No feedback system? Return your excellent base score
    return base_score
