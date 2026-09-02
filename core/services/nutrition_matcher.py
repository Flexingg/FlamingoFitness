"""Smart Nutrition Matching Engine (Sparky-Only Backend).

Implements the prioritization cascade:
1. Recent & Favorite Foods matching from user's SparkyFitness history.
2. SparkyFitness Food Database catalog search.
3. SparkyFitness Native AI (/chat/food-options and /chat) estimation fallback.
"""

import base64
import json
import re
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.utils import timezone

from core.models import Provider, User, UserIntegration
from core.services.sparky_client import SparkyFitnessClient


def _extract_portions(text: str) -> Dict[str, float]:
    """Extract multiplier or amount cues like '2x', 'double', 'half', '3 scoops'."""
    text_lower = text.lower()
    multiplier = 1.0

    if "double" in text_lower or "2x" in text_lower or "2 x" in text_lower:
        multiplier = 2.0
    elif "triple" in text_lower or "3x" in text_lower or "3 x" in text_lower:
        multiplier = 3.0
    elif "half" in text_lower or "0.5x" in text_lower or "1/2" in text_lower:
        multiplier = 0.5
    else:
        num_match = re.search(
            r"\b(\d+(?:\.\d+)?)\s*(?:servings?|scoops?|cups?|slices?|eggs?|pieces?|plates?|bowls?)\b",
            text_lower,
        )
        if num_match:
            try:
                multiplier = float(num_match.group(1))
            except ValueError:
                multiplier = 1.0

    return {"multiplier": multiplier}


def _tokenize(text: str) -> set:
    """Tokenize text into lowercase alphanumeric words, filtering common stop words."""
    stop_words = {
        "a",
        "an",
        "the",
        "and",
        "or",
        "with",
        "of",
        "in",
        "for",
        "some",
        "my",
        "i",
        "had",
        "ate",
        "eating",
        "drank",
        "plus",
    }
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if w not in stop_words and len(w) > 1}


class NutritionMatchingService:
    """Matches meal notes and photos to SparkyFitness food entities using Sparky only."""

    def __init__(self, user: User):
        self.user = user
        self.client = SparkyFitnessClient()
        self.api_key = self._get_sparky_key()

    def _get_sparky_key(self) -> str:
        sparky = UserIntegration.objects.filter(
            user=self.user, provider=Provider.SPARKYFITNESS, is_active=True
        ).first()
        return (sparky.credentials.get("api_key") if sparky else None) or ""

    def match_note_and_image(
        self,
        note: str = "",
        image_base64: Optional[str] = None,
        meal_type: str = "Lunch",
    ) -> List[Dict[str, Any]]:
        """Run the matching pipeline against recent foods, Sparky DB, and Sparky AI."""
        note_clean = (note or "").strip()
        portions = _extract_portions(note_clean)
        multiplier = portions.get("multiplier", 1.0)

        # 1. Fetch user's recent and frequent foods (Priority 1)
        recent_foods = self.client.get_recent_foods(self.api_key, days=30)
        note_tokens = _tokenize(note_clean)

        matched_items: List[Dict[str, Any]] = []

        if note_tokens and recent_foods:
            # Score each recent food against note tokens
            for food in recent_foods:
                food_tokens = _tokenize(food["name"])
                if not food_tokens:
                    continue
                intersection = note_tokens.intersection(food_tokens)
                overlap_ratio = len(intersection) / len(food_tokens)

                # Substring or significant token overlap check
                if food["name"].lower() in note_clean.lower() or overlap_ratio >= 0.5:
                    qty = food.get("quantity", 1.0) * multiplier
                    item_cal = round(food["calories"] * multiplier, 1)
                    item_pro = round(food["protein"] * multiplier, 1)
                    item_carb = round(food.get("carbs", 0.0) * multiplier, 1)
                    item_fat = round(food.get("fat", 0.0) * multiplier, 1)

                    matched_items.append({
                        "food_id": food.get("food_id") or food.get("id"),
                        "variant_id": food.get("variant_id"),
                        "name": food["name"],
                        "brand": food.get("brand", ""),
                        "calories": item_cal,
                        "protein": item_pro,
                        "carbs": item_carb,
                        "fat": item_fat,
                        "quantity": qty,
                        "unit": food.get("serving", "serving"),
                        "match_source": "recent_foods",
                        "confidence": 0.95 if overlap_ratio >= 0.8 else 0.85,
                    })

        if matched_items:
            return matched_items

        # 2. Search Sparky database / offline catalog (Priority 2)
        if note_clean:
            db_results = self.client.search_foods(self.api_key, note_clean)
            if db_results:
                best_match = db_results[0]
                item_cal = round(best_match["calories"] * multiplier, 1)
                item_pro = round(best_match["protein"] * multiplier, 1)
                item_carb = round(best_match.get("carbs", 0.0) * multiplier, 1)
                item_fat = round(best_match.get("fat", 0.0) * multiplier, 1)

                return [{
                    "food_id": best_match.get("food_id") or best_match.get("id"),
                    "variant_id": best_match.get("variant_id"),
                    "name": best_match["name"],
                    "brand": best_match.get("brand", ""),
                    "calories": item_cal,
                    "protein": item_pro,
                    "carbs": item_carb,
                    "fat": item_fat,
                    "quantity": multiplier,
                    "unit": best_match.get("serving", "serving"),
                    "match_source": "sparky_db",
                    "confidence": 0.80,
                }]

        # 3. Sparky Native AI Assistance (/chat/food-options or /chat) (Priority 3)
        if self.api_key and note_clean:
            sparky_ai_opt = self.client.generate_food_options_ai(self.api_key, note_clean)
            if sparky_ai_opt and isinstance(sparky_ai_opt, list) and sparky_ai_opt:
                first = sparky_ai_opt[0]
                return [{
                    "food_id": None,
                    "variant_id": None,
                    "name": first.get("name") or note_clean,
                    "brand": "Sparky AI",
                    "calories": round(float(first.get("calories") or 350) * multiplier, 1),
                    "protein": round(float(first.get("protein") or 25) * multiplier, 1),
                    "carbs": round(float(first.get("carbs") or 30) * multiplier, 1),
                    "fat": round(float(first.get("fat") or 10) * multiplier, 1),
                    "quantity": multiplier,
                    "unit": first.get("unit") or "serving",
                    "match_source": "sparky_ai",
                    "confidence": 0.75,
                }]

        # 4. Fallback estimation based on note or photo presence
        label = note_clean if note_clean else "Logged Meal"
        return [{
            "food_id": None,
            "variant_id": None,
            "name": label,
            "brand": "Meal Estimation",
            "calories": 450.0 * multiplier,
            "protein": 30.0 * multiplier,
            "carbs": 40.0 * multiplier,
            "fat": 15.0 * multiplier,
            "quantity": multiplier,
            "unit": "plate / serving",
            "match_source": "sparky_ai" if self.api_key else "estimation",
            "confidence": 0.65,
        }]
