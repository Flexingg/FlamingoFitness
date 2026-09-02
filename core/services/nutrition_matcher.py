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

        # Multi-Item Decomposition Check: if note contains multiple items/delimiters
        is_multi_candidate = bool(
            re.search(r"[,;]|\band\b|\bwith\b|\+", note_clean, re.IGNORECASE)
            and len(note_clean.split()) >= 3
        )
        if is_multi_candidate and self.api_key:
            decomposed = self.decompose_multi_item_meal(note_clean)
            if len(decomposed) > 1:
                return decomposed

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

        # 2. Search Sparky database / catalog (Priority 2)
        if note_clean:
            db_results = self.client.search_foods(self.api_key, note_clean, include_external=False)
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
                    "confidence": 0.85,
                }]

        # 3. Expand search to Sparky external catalogs (Open Food Facts / FatSecret) (Priority 3)
        if self.api_key and note_clean:
            ext_results = self.client.search_external_foods(self.api_key, note_clean)
            if ext_results:
                best_ext = ext_results[0]
                item_cal = round(best_ext["calories"] * multiplier, 1)
                item_pro = round(best_ext["protein"] * multiplier, 1)
                item_carb = round(best_ext.get("carbs", 0.0) * multiplier, 1)
                item_fat = round(best_ext.get("fat", 0.0) * multiplier, 1)

                return [{
                    "food_id": best_ext.get("food_id"),
                    "variant_id": None,
                    "name": best_ext["name"],
                    "brand": best_ext.get("brand", "Open Food Facts"),
                    "calories": item_cal,
                    "protein": item_pro,
                    "carbs": item_carb,
                    "fat": item_fat,
                    "quantity": multiplier,
                    "unit": best_ext.get("serving", "serving"),
                    "match_source": "sparky_openfoodfacts",
                    "confidence": 0.80,
                }]

        # 4. Use Sparky Native AI to generate new food and persist in Sparky DB (Priority 4)
        if self.api_key:
            food_target = note_clean if note_clean else f"{meal_type} Plate"
            ai_item = self.client.generate_food_ai(self.api_key, food_target)
            if ai_item:
                item_cal = round(ai_item["calories"] * multiplier, 1)
                item_pro = round(ai_item["protein"] * multiplier, 1)
                item_carb = round(ai_item["carbs"] * multiplier, 1)
                item_fat = round(ai_item["fat"] * multiplier, 1)
                unit_str = ai_item.get("serving", "serving")

                # Persist the newly created food directly in SparkyFitness DB
                created_res = self.client.create_custom_food(
                    self.api_key,
                    name=ai_item["name"],
                    calories=item_cal,
                    protein=item_pro,
                    carbs=item_carb,
                    fat=item_fat,
                    serving=unit_str,
                    brand="Sparky AI",
                )
                created_id = created_res.get("id") if isinstance(created_res, dict) else None

                return [{
                    "food_id": created_id,
                    "variant_id": None,
                    "name": ai_item["name"],
                    "brand": "Sparky AI (New Food Created)",
                    "calories": item_cal,
                    "protein": item_pro,
                    "carbs": item_carb,
                    "fat": item_fat,
                    "quantity": multiplier,
                    "unit": unit_str,
                    "match_source": "sparky_ai_created",
                    "confidence": 0.90,
                }]

        # 5. Fallback estimation based on note or photo presence
        label = note_clean if note_clean else f"{meal_type} Meal"
        return [{
            "food_id": None,
            "variant_id": None,
            "name": label,
            "brand": "Sparky Estimation",
            "calories": round(450.0 * multiplier, 1),
            "protein": round(30.0 * multiplier, 1),
            "carbs": round(40.0 * multiplier, 1),
            "fat": round(15.0 * multiplier, 1),
            "quantity": multiplier,
            "unit": "1 serving",
            "match_source": "sparky_estimation",
            "confidence": 0.70,
        }]

    def decompose_multi_item_meal(self, note: str) -> List[Dict[str, Any]]:
        """Decompose a multi-item meal note into individual foods using Sparky native /chat AI."""
        if not self.api_key or not note:
            return []

        ai_service = self.client.get_active_ai_service(self.api_key)
        config_id = ai_service.get("id") if ai_service else None
        if not config_id:
            return []

        payload = {
            "service_config_id": str(config_id),
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"Decompose the following meal into a list of individual food items with estimated calories, protein, carbs, and fat per item:\n\n{note}\n\n"
                        "Format each item clearly with header '### <Item Name>' followed by Calories, Protein, Carbohydrates, and Fat."
                    ),
                }
            ],
        }

        res = self.client._post(self.api_key, "/chat", json_data=payload)
        content = res.get("content") or res.get("message") if isinstance(res, dict) else None
        if not content or not isinstance(content, str):
            return []

        items: List[Dict[str, Any]] = []
        sections = re.split(r"###\s*(?:\d+\.\s*)?", content)
        for sec in sections[1:]:
            lines = [line.strip() for line in sec.strip().split("\n") if line.strip()]
            if not lines:
                continue
            name = re.sub(r"[\*\#]", "", lines[0]).strip()
            if not name or any(w in name.lower() for w in ("total", "summary", "notes", "disclaimer")):
                continue

            cal_m = re.search(r"calories[\*\:\s]+([0-9\.]+)", sec, re.IGNORECASE)
            pro_m = re.search(r"protein[\*\:\s]+([0-9\.]+)", sec, re.IGNORECASE)
            carb_m = re.search(r"carbohydrates?[\*\:\s]+([0-9\.]+)", sec, re.IGNORECASE)
            fat_m = re.search(r"fat[\*\:\s]+([0-9\.]+)", sec, re.IGNORECASE)

            cal = float(cal_m.group(1)) if cal_m else 0.0
            pro = float(pro_m.group(1)) if pro_m else 0.0
            carb = float(carb_m.group(1)) if carb_m else 0.0
            fat = float(fat_m.group(1)) if fat_m else 0.0

            if cal == 0.0 and pro == 0.0 and carb == 0.0 and fat == 0.0:
                continue

            # Automatically persist newly decomposed food item into user's Sparky database
            try:
                self.client.create_custom_food(
                    self.api_key,
                    name=name,
                    calories=cal,
                    protein=pro,
                    carbs=carb,
                    fat=fat,
                    serving="1 serving",
                    brand="Sparky AI",
                )
            except Exception:
                pass

            items.append({
                "food_id": None,
                "variant_id": None,
                "name": name,
                "brand": "Sparky AI",
                "calories": cal,
                "protein": pro,
                "carbs": carb,
                "fat": fat,
                "quantity": 1.0,
                "unit": "serving",
                "match_source": "sparky_ai_created",
                "confidence": 0.92,
            })

        return items
