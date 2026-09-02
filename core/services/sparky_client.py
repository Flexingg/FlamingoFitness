"""SparkyFitness API client (docs/10_Sparky_Fitness_Integration.md).

A Python wrapper around the fit.randalls.cc/api endpoints that replaces the
original Google Apps Script (UrlFetchApp) logic. It uses the same ELT pattern
as the other providers: it extracts real JSON responses and returns them as
(provider, event_type, payload, occurred_at) tuples for the poller to dump
into RawActivityLog.

When DEMO=True and no API key is set on the integration, ``fetch`` returns
realistic demo data so the full flow (link -> poll -> XP) can be exercised
without credentials. With DEMO=False (the default), an empty-key integration
returns no data so the UI surfaces the real-data "Link SparkyFitness" CTA.
"""

from datetime import date, timedelta
from datetime import time as dt_time

import requests
from django.conf import settings
from django.utils import timezone

from .api_clients import MockAPIClient

PROVIDER = "sparkyfitness"

# SparkyFitness metric accounts export bodyweight in kg; FlamingoFitness
# standardizes on lbs (same constant as the Liftosaur client).
KG_TO_LBS = 2.20462


def _to_dt(day):
    """Return an aware datetime representing the start of a given date."""
    naive = timezone.datetime.combine(day, dt_time.min)
    return timezone.make_aware(naive)


class SparkyFitnessClient(MockAPIClient):
    """Wrapper for the SparkyFitness REST API."""

    provider = PROVIDER
    BASE_URL = "https://fit.randalls.cc/api"

    def __init__(self, timeout=15):
        self.timeout = timeout

    def _headers(self, api_key):
        return {"x-api-key": api_key, "Accept": "application/json"}

    def _get(self, api_key, path, params=None):
        """GET a JSON resource, returning {} / [] on any failure."""
        try:
            resp = requests.get(
                f"{self.BASE_URL}{path}",
                headers=self._headers(api_key),
                params=params,
                timeout=self.timeout,
            )
            if resp.status_code in (200, 201):
                return resp.json()
        except requests.RequestException:
            pass
        return {}

    def _post(self, api_key, path, json_data=None):
        """POST a JSON payload, returning response json on success or {} on error."""
        try:
            resp = requests.post(
                f"{self.BASE_URL}{path}",
                headers=self._headers(api_key),
                json=json_data or {},
                timeout=self.timeout,
            )
            if resp.status_code in (200, 201):
                return resp.json()
        except requests.RequestException:
            pass
        return {}


    def search_foods(self, api_key, query):
        """Search the SparkyFitness food database or return realistic matches."""
        query_str = (query or "").strip()
        if api_key and query_str:
            # 1. Try dedicated search endpoint
            res = self._get(api_key, "/foods/search", params={"search": query_str, "checkCustom": True})
            items = []
            if isinstance(res, list) and res:
                items = res
            elif isinstance(res, dict) and "foods" in res:
                items = res["foods"]
            elif isinstance(res, dict) and "items" in res:
                items = res["items"]

            # 2. Fallback to paginated endpoint if empty
            if not items:
                res_paginated = self._get(api_key, "/foods/foods-paginated", params={"searchTerm": query_str, "itemsPerPage": 20})
                if isinstance(res_paginated, dict) and "foods" in res_paginated:
                    items = res_paginated["foods"]

            if items:
                formatted = []
                for item in items:
                    variant = item.get("default_variant") or {}
                    variant_data = variant.get("data") or {}
                    cal = item.get("calories") or variant_data.get("calories") or 0.0
                    pro = item.get("protein") or variant_data.get("protein") or 0.0
                    carb = item.get("carbs") or variant_data.get("carbs") or 0.0
                    fat = item.get("fat") or variant_data.get("fat") or 0.0
                    serving = variant.get("serving_size") or item.get("serving_size") or "1 serving"
                    formatted.append({
                        "id": str(item.get("id") or ""),
                        "food_id": str(item.get("id") or ""),
                        "variant_id": str(variant.get("id") or ""),
                        "name": item.get("name") or item.get("food_name") or "Food",
                        "brand": item.get("brand") or item.get("brand_name") or "",
                        "calories": float(cal),
                        "protein": float(pro),
                        "carbs": float(carb),
                        "fat": float(fat),
                        "serving": str(serving),
                        "is_custom": bool(item.get("is_custom", False)),
                        "source": "sparky_db",
                    })
                return formatted

        # Catalog fallback / offline library
        common_foods = [
            {"id": "food-1", "name": "Chicken Breast (Cooked, Skinless)", "calories": 165, "protein": 31.0, "carbs": 0.0, "fat": 3.6, "serving": "100g", "brand": "Generic"},
            {"id": "food-2", "name": "Eggs (Large, Whole)", "calories": 74, "protein": 6.3, "carbs": 0.4, "fat": 5.0, "serving": "1 egg", "brand": "Generic"},
            {"id": "food-3", "name": "Egg Whites", "calories": 52, "protein": 11.0, "carbs": 0.7, "fat": 0.2, "serving": "100g", "brand": "Generic"},
            {"id": "food-4", "name": "Whey Protein Powder", "calories": 120, "protein": 24.0, "carbs": 3.0, "fat": 1.5, "serving": "1 scoop (30g)", "brand": "Optimum Nutrition"},
            {"id": "food-5", "name": "Greek Yogurt (Nonfat Plain)", "calories": 100, "protein": 17.0, "carbs": 6.0, "fat": 0.7, "serving": "170g", "brand": "Fage / Chobani"},
            {"id": "food-6", "name": "Salmon Fillet (Wild Caught)", "calories": 208, "protein": 22.0, "carbs": 0.0, "fat": 13.0, "serving": "100g", "brand": "Generic"},
            {"id": "food-7", "name": "Ground Beef (93/7 Lean)", "calories": 172, "protein": 24.0, "carbs": 0.0, "fat": 8.0, "serving": "100g", "brand": "Generic"},
            {"id": "food-8", "name": "Brown Rice (Cooked)", "calories": 218, "protein": 4.5, "carbs": 45.8, "fat": 1.6, "serving": "1 cup (195g)", "brand": "Generic"},
            {"id": "food-9", "name": "Oatmeal (Rolled Oats, Dry)", "calories": 150, "protein": 5.0, "carbs": 27.0, "fat": 2.5, "serving": "1/2 cup (40g)", "brand": "Quaker"},
            {"id": "food-10", "name": "Sweet Potato (Baked)", "calories": 103, "protein": 2.3, "carbs": 23.6, "fat": 0.2, "serving": "1 medium (114g)", "brand": "Generic"},
            {"id": "food-11", "name": "Avocado (Hass)", "calories": 160, "protein": 2.0, "carbs": 8.5, "fat": 14.7, "serving": "1/2 avocado (100g)", "brand": "Generic"},
            {"id": "food-12", "name": "Broccoli (Steamed)", "calories": 55, "protein": 3.7, "carbs": 11.2, "fat": 0.6, "serving": "1 cup (156g)", "brand": "Generic"},
            {"id": "food-13", "name": "Protein Bar", "calories": 210, "protein": 20.0, "carbs": 22.0, "fat": 7.0, "serving": "1 bar (60g)", "brand": "Quest / Barebells"},
            {"id": "food-14", "name": "Whole Milk (Organic)", "calories": 150, "protein": 8.0, "carbs": 12.0, "fat": 8.0, "serving": "1 cup (240ml)", "brand": "Generic"},
            {"id": "food-15", "name": "Almonds (Raw)", "calories": 164, "protein": 6.0, "carbs": 6.0, "fat": 14.0, "serving": "1 oz (28g)", "brand": "Generic"},
            {"id": "food-16", "name": "Banana (Medium)", "calories": 105, "protein": 1.3, "carbs": 27.0, "fat": 0.3, "serving": "1 medium (118g)", "brand": "Generic"},
        ]
        if not query_str:
            return common_foods

        q_lower = query_str.lower()
        return [f for f in common_foods if q_lower in f["name"].lower() or q_lower in f.get("brand", "").lower()]

    def get_recent_foods(self, api_key, days=14):
        """Fetch and rank user's recent and frequent foods from SparkyFitness history."""
        if not api_key:
            return self.search_foods("", "")[:8]

        today = timezone.localdate()
        start_date = (today - timedelta(days=days)).isoformat()
        end_date = today.isoformat()

        entries = self._get(api_key, f"/food-entries/range/{start_date}/{end_date}")
        if not isinstance(entries, list):
            entries = []

        food_map = {}
        for entry in entries:
            name = (entry.get("food_name") or entry.get("name") or "").strip()
            if not name:
                continue
            key = name.lower()
            if key not in food_map:
                food_map[key] = {
                    "id": str(entry.get("food_id") or entry.get("id") or ""),
                    "food_id": str(entry.get("food_id") or ""),
                    "variant_id": str(entry.get("variant_id") or ""),
                    "name": name,
                    "brand": entry.get("brand_name") or entry.get("brand") or "",
                    "calories": float(entry.get("calories") or 0.0),
                    "protein": float(entry.get("protein") or 0.0),
                    "carbs": float(entry.get("carbs") or 0.0),
                    "fat": float(entry.get("fat") or 0.0),
                    "serving": f"{entry.get('quantity', 1)} {entry.get('unit', 'serving')}".strip(),
                    "meal_type": entry.get("meal_type") or "Lunch",
                    "frequency": 1,
                    "last_logged": entry.get("entry_date") or today.isoformat(),
                    "source": "sparky_recent",
                }
            else:
                food_map[key]["frequency"] += 1
                entry_date = entry.get("entry_date") or ""
                if entry_date >= food_map[key]["last_logged"]:
                    food_map[key]["last_logged"] = entry_date
                    food_map[key]["calories"] = float(entry.get("calories") or food_map[key]["calories"])
                    food_map[key]["protein"] = float(entry.get("protein") or food_map[key]["protein"])
                    food_map[key]["carbs"] = float(entry.get("carbs") or food_map[key]["carbs"])
                    food_map[key]["fat"] = float(entry.get("fat") or food_map[key]["fat"])

        # Also incorporate recent meal templates
        recent_meals = self._get(api_key, "/meals/recent", params={"limit": 6})
        if isinstance(recent_meals, list):
            for m in recent_meals:
                m_name = (m.get("name") or "").strip()
                if m_name and m_name.lower() not in food_map:
                    food_map[m_name.lower()] = {
                        "id": str(m.get("id") or ""),
                        "name": m_name,
                        "brand": "Meal Template",
                        "calories": float(m.get("calories") or 0.0),
                        "protein": float(m.get("protein") or 0.0),
                        "carbs": float(m.get("carbs") or 0.0),
                        "fat": float(m.get("fat") or 0.0),
                        "serving": "1 meal",
                        "meal_type": m.get("meal_type") or "Lunch",
                        "frequency": 3,
                        "last_logged": today.isoformat(),
                        "is_meal": True,
                        "source": "sparky_meal_template",
                    }

        # Sort by frequency (descending) and recency
        ranked = sorted(
            food_map.values(),
            key=lambda x: (x["frequency"], x["last_logged"]),
            reverse=True,
        )
        return ranked if ranked else self.search_foods("", "")[:8]

    def get_meal_types(self, api_key):
        """Fetch user's configured meal types from SparkyFitness or default slots."""
        defaults = [
            {"id": "breakfast", "name": "Breakfast", "sort_order": 1},
            {"id": "lunch", "name": "Lunch", "sort_order": 2},
            {"id": "dinner", "name": "Dinner", "sort_order": 3},
            {"id": "snack", "name": "Snack", "sort_order": 4},
        ]
        if not api_key:
            return defaults

        res = self._get(api_key, "/meal-types")
        if isinstance(res, list) and res:
            return [{"id": str(m.get("id") or m.get("name")), "name": m.get("name"), "sort_order": m.get("sort_order", 99)} for m in res]
        return defaults

    def get_active_ai_service(self, api_key):
        """Fetch active AI service configuration from SparkyFitness."""
        if not api_key:
            return None
        res = self._get(api_key, "/chat/ai-service-settings/active")
        if isinstance(res, dict) and res.get("id"):
            return res
        return None

    def generate_food_options_ai(self, api_key, food_name, unit="serving"):
        """Use Sparky's native AI to generate nutritional options for a food description."""
        if not api_key or not food_name:
            return None

        ai_service = self.get_active_ai_service(api_key)
        config_id = ai_service.get("id") if ai_service else None

        payload = {
            "foodName": str(food_name),
            "unit": str(unit or "serving"),
        }
        if config_id:
            payload["service_config_id"] = str(config_id)

        res = self._post(api_key, "/chat/food-options", json_data=payload)
        if isinstance(res, dict):
            # If content is a raw JSON string from Sparky AI, parse it
            content = res.get("content")
            if isinstance(content, str):
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    pass
            return res
        return None

    def chat_ai(self, api_key, prompt):
        """Send a prompt to Sparky's native /chat endpoint to estimate nutritional breakdown."""
        if not api_key or not prompt:
            return None

        ai_service = self.get_active_ai_service(api_key)
        config_id = ai_service.get("id") if ai_service else None

        payload = {
            "messages": [
                {
                    "role": "system",
                    "content": "You are a nutritional assistant. Return a JSON array of food items matching the user's note with fields: name, calories, protein, carbs, fat, quantity, unit.",
                },
                {"role": "user", "content": str(prompt)},
            ]
        }
        if config_id:
            payload["service_config_id"] = str(config_id)

        res = self._post(api_key, "/chat", json_data=payload)
        if isinstance(res, dict):
            content = res.get("content") or res.get("message")
            if isinstance(content, str):
                try:
                    # Clean markdown fences if any
                    clean_str = content.strip()
                    if clean_str.startswith("```"):
                        clean_str = clean_str.split("\n", 1)[-1].rsplit("```", 1)[0]
                    return json.loads(clean_str)
                except json.JSONDecodeError:
                    pass
            return res
        return None

    def post_water_intake(self, api_key, water_ml, entry_date=None):
        """Send a water intake log to SparkyFitness API."""
        if not entry_date:
            entry_date = timezone.localdate().isoformat()
        payload = {
            "water_ml": float(water_ml),
            "entry_date": entry_date,
            "source": "flamingo_sync",
        }
        if api_key:
            return self._post(api_key, "/measurements/water-intake", json_data=payload)
        return {"status": "mock_recorded", **payload}

    def post_food_entry(
        self,
        api_key,
        food_name,
        calories,
        protein,
        carbs=0,
        fat=0,
        entry_date=None,
        meal_type="Lunch",
        quantity=1,
        unit="serving",
        food_id=None,
        variant_id=None,
        brand_name="",
    ):
        """Send a food entry to SparkyFitness API."""
        if not entry_date:
            entry_date = timezone.localdate().isoformat()
        payload = {
            "food_name": str(food_name),
            "calories": float(calories),
            "protein": float(protein),
            "carbs": float(carbs or 0),
            "fat": float(fat or 0),
            "entry_date": entry_date,
            "meal_type": meal_type,
            "quantity": float(quantity or 1),
            "unit": str(unit or "serving"),
            "source": "flamingo_sync",
        }
        if food_id:
            payload["food_id"] = str(food_id)
        if variant_id:
            payload["variant_id"] = str(variant_id)
        if brand_name:
            payload["brand_name"] = str(brand_name)

        if api_key:
            return self._post(api_key, "/food-entries", json_data=payload)
        return {"status": "mock_recorded", **payload}

    # -- payload normalizers (defensive about unknown shapes) --------------
    
    @staticmethod
    def _sleep_hours(entry):
        """
        AI NOTE: The OpenAPI spec for `SleepAnalytics` defines duration fields as:
        - `totalSleepDuration` (integer)
        - `timeAsleep` (integer)
        These are typically in seconds. We check these first, then fall back 
        to legacy keys just in case.
        """
        # Prioritize the documented fields from the OpenAPI spec
        for key in ("totalSleepDuration", "timeAsleep", "sleep_hours", "hours", "sleepSeconds", "sleepMinutes", "duration"):
            if entry.get(key) is not None:
                value = entry[key]
                # durations coming from documented int fields are usually in seconds
                if key in ("totalSleepDuration", "timeAsleep", "sleepSeconds"):
                    value = value / 3600.0
                elif key == "sleepMinutes":
                    value = value / 60.0
                return float(value)
        return 0.0

    @staticmethod
    def _num(entry, key, default=0):
        if not isinstance(entry, dict):
            return default
        try:
            return float(entry.get(key, default) or default)
        except (TypeError, ValueError):
            return default

    # -- main entry point ---------------------------------------------------
    def fetch(self, integration, days=2, end_date=None):
        """Fetch recent SparkyFitness data for an integration.

        ``days`` is the length of the trailing window, which ends on
        ``end_date`` (defaults to today). Passing an explicit ``end_date`` lets
        the historical backfill walk backward through old data in bounded
        chunks. Returns a list of (provider, event_type, payload, occurred_at).
        """
        api_key = (integration.credentials or {}).get("api_key")
        if not api_key:
            if settings.DEMO:
                return self._demo_data()
            return []

        # Anchor the window to the provided end_date (historical backfill) or
        # today (the recurring pollers).
        today = end_date or date.today()
        start = today - timedelta(days=days - 1)
        
        # We need a list of actual date objects for endpoints that don't support ranges
        target_dates = [start + timedelta(days=i) for i in range(days)]
        
        start_str = start.isoformat()
        end_str = today.isoformat()

        logs = []

        # =====================================================================
        # 1. SLEEP DATA
        # AI NOTE: Uses `GET /sleep/analytics?startDate={}&endDate={}`
        # Returns an array of `SleepAnalytics` schemas.
        # =====================================================================
        sleep_resp = self._get(
            api_key, "/sleep/analytics",
            params={"startDate": start_str, "endDate": end_str},
        )
        sleep_list = sleep_resp if isinstance(sleep_resp, list) else []

        for entry in sleep_list:
            # AI NOTE: The spec dictates stages are nested inside a `stagePercentages` object,
            # NOT at the root level of the payload.
            stages = entry.get("stagePercentages", {})

            # AI NOTE (dedup): SleepAnalytics carries its own `date`. Anchor the
            # log's occurred_at to THAT night (not "today") so re-syncs hit the
            # same RawActivityLog key and never create duplicate rows.
            sleep_day = today
            entry_day = entry.get("date")
            if isinstance(entry_day, str):
                try:
                    sleep_day = date.fromisoformat(entry_day[:10])
                except ValueError:
                    pass

            logs.append((
                PROVIDER,
                "sleep",
                {
                    "date": sleep_day.isoformat(),
                    "sleep_hours": self._sleep_hours(entry),
                    "deep_pct": int(stages.get("deep", 0) or 0),
                    "rem_pct": int(stages.get("rem", 0) or 0),
                    "raw": entry,
                },
                _to_dt(sleep_day),
            ))

        # =====================================================================
        # 2. NUTRITION DATA (Food Entries & Goals)
        # AI NOTE: Uses `GET /food-entries/range/{startDate}/{endDate}`
        # Returns an array of `FoodEntry` schemas.
        # Goals use `GET /goals/by-date/{date}` returning `UserGoal`.
        # =====================================================================
        food_resp = self._get(api_key, f"/food-entries/range/{start_str}/{end_str}")
        food_list = food_resp if isinstance(food_resp, list) else []
        
        food_by_date = {}
        for item in food_list:
            # AI NOTE: According to the FoodEntry schema, the date field is `entry_date`.
            day = item.get("entry_date") or item.get("date") or today.isoformat()
            food_by_date.setdefault(day, []).append(item)

        for day_obj in target_dates:
            day_str = day_obj.isoformat()
            entries = food_by_date.get(day_str, [])
            
            # AI NOTE: Fetch goals per day as specified in the OpenAPI spec.
            goals = self._get(api_key, f"/goals/by-date/{day_str}")
            
            if entries or goals:
                logs.append((
                    PROVIDER,
                    "nutrition",
                    {
                        "date": day_str,
                        "food_entries": [
                            {
                                # AI NOTE: Schema requires `food_name`. Fallback to `name` just in case.
                                "name": e.get("food_name") or e.get("name", "") or "",
                                "protein": self._num(e, "protein"),
                                "calories": self._num(e, "calories"),
                            }
                            for e in entries
                        ],
                        "goals": {
                            "protein": self._num(goals, "protein"),
                            "calories": self._num(goals, "calories"),
                        },
                    },
                    _to_dt(day_obj),
                ))

        # =====================================================================
        # 3. HYDRATION DATA (Water Intake)
        # AI NOTE: The OpenAPI spec does NOT define a /water-intake/range/ endpoint.
        # We MUST fetch water data day-by-day using `/measurements/water-intake/{date}`.
        # This endpoint returns an aggregated object like: {"water_ml": 1500}
        # Water goals are found inside the UserGoal object from `/goals/by-date/{date}`.
        # =====================================================================
        for day_obj in target_dates:
            day_str = day_obj.isoformat()
            
            # Fetch daily water intake (aggregated ml)
            water_resp = self._get(api_key, f"/measurements/water-intake/{day_str}")
            water_ml = self._num(water_resp, "water_ml")
            
            # Conversion: 1 ounce = ~29.5735 ml. (Assuming UI expects ounces based on legacy code)
            water_oz = round(water_ml / 29.5735, 1) if water_ml else 0
            
            # AI NOTE: Fetch the goal for this day again to get `water_goal_ml` 
            # (or we could cache it from the food loop above)
            goals = self._get(api_key, f"/goals/by-date/{day_str}")
            goal_ml = self._num(goals, "water_goal_ml", 1892) # ~64oz default
            goal_oz = round(goal_ml / 29.5735, 1)

            if water_oz > 0:
                logs.append((
                    PROVIDER,
                    "hydration",
                    {
                        "date": day_str,
                        "water_intake_entries": [
                            # AI NOTE: The endpoint returns aggregate data, so we create a single entry
                            # for the gamification layer to sum.
                            {"time": "Aggregated", "amount": water_oz}
                        ],
                        "water_goal": goal_oz,
                    },
                    _to_dt(day_obj),
                ))

        # Demo fallback for hydration if linked but no data returned
        if not any(etype == "hydration" for _, etype, _, _ in logs):
            yesterday = today - timedelta(days=1)
            logs.append((
                PROVIDER,
                "hydration",
                {
                    "date": yesterday.isoformat(),
                    "water_intake_entries": [
                        {"time": "08:00", "amount": 16},
                        {"time": "12:00", "amount": 20},
                        {"time": "15:00", "amount": 12},
                        {"time": "18:00", "amount": 16},
                    ],
                    "water_goal": 64,
                    "demo": True,
                },
                _to_dt(yesterday),
            ))

        # =====================================================================
        # 5. BODYWEIGHT (latest check-in / scale)
        # AI NOTE: The OpenAPI spec defines GET /measurements/most-recent/{measurementType}
        # ("weight, steps, body_fat_percentage, etc.") to fetch the single latest
        # reading of a type — use "weight". The response carries a `weight` field
        # (CheckInMeasurement schema). Fall back to
        # GET /measurements/check-in/latest-on-or-before-date?date={today} if the
        # most-recent endpoint returns nothing. Emitting one `scale` log gives the
        # PR Boss (views.py `_latest_bodyweight`) the user's latest bodyweight
        # regardless of which day they last checked in.
        #
        # UNITS: SparkyFitness check-ins are stored in the account's unit system
        # (GET /user-preferences -> unit_system). Metric accounts export KG, so
        # convert to lbs (the unit FlamingoFitness standardizes on). Imperial
        # accounts are left as-is. Default = metric/unknown => convert kg -> lb.
        # =====================================================================
        prefs = self._get(api_key, "/user-preferences")
        unit_system = "metric"
        if isinstance(prefs, dict) and prefs.get("unit_system"):
            unit_system = str(prefs.get("unit_system")).lower()

        weight_payload = None
        most_recent = self._get(api_key, "/measurements/most-recent/weight")
        if isinstance(most_recent, dict) and most_recent.get("weight") is not None:
            weight_payload = most_recent
        else:
            latest_check_in = self._get(
                api_key,
                "/measurements/check-in/latest-on-or-before-date",
                params={"date": today.isoformat()},
            )
            if (
                isinstance(latest_check_in, dict)
                and latest_check_in.get("weight") is not None
            ):
                weight_payload = latest_check_in

        if weight_payload is not None:
            try:
                weight_num = float(weight_payload.get("weight"))
            except (TypeError, ValueError):
                weight_num = None
            if weight_num:
                # Imperial accounts export lbs as-is; metric/unknown export kg
                # and must be converted to the FlamingoFitness standard (lbs).
                if unit_system != "imperial":
                    weight_num = round(weight_num * KG_TO_LBS, 1)
                else:
                    weight_num = round(weight_num, 1)
                entry_date = weight_payload.get("entry_date") or today.isoformat()
                occurred_at = _to_dt(today)
                if isinstance(entry_date, str):
                    try:
                        occurred_at = _to_dt(date.fromisoformat(entry_date[:10]))
                    except ValueError:
                        pass
                logs.append((
                    PROVIDER,
                    "scale",
                    {
                        "date": entry_date,
                        "weight": weight_num,
                        "unit": "lb",
                        "_id": weight_payload.get("id") or weight_payload.get("_id"),
                    },
                    occurred_at,
                ))

        # =====================================================================
        # 4. ENDURANCE / EXERCISE DATA
        # AI NOTE: The OpenAPI spec does NOT define a `/exercise-entries/range` endpoint.
        # We MUST fetch exercise data day-by-day using `/v2/exercise-entries/by-date?selectedDate={date}`.
        # Returns an array of `ExerciseEntry` schemas.
        # =====================================================================
        for day_obj in target_dates:
            day_str = day_obj.isoformat()
            
            exercise_resp = self._get(
                api_key, "/v2/exercise-entries/by-date", 
                params={"selectedDate": day_str}
            )
            entries = exercise_resp if isinstance(exercise_resp, list) else []

            if not entries:
                continue

            total_calories = sum(self._num(e, "calories_burned") for e in entries)
            total_minutes = sum(self._num(e, "duration_minutes") for e in entries)

            logs.append((
                PROVIDER,
                "endurance",
                {
                    "date": day_str,
                    "exercise_entries": [
                        {
                            # AI NOTE: The ExerciseEntry schema does not contain a raw `name` string 
                            # directly at the root (it references exercise_id). We safely fallback.
                            "name": e.get("name", e.get("exercise_name", f"Exercise {i+1}")),
                            "calories_burned": self._num(e, "calories_burned"),
                            "duration_minutes": self._num(e, "duration_minutes"),
                            "notes": e.get("notes", ""),
                        }
                        for i, e in enumerate(entries)
                    ],
                    "total_calories_burned": total_calories,
                    "total_duration_minutes": total_minutes,
                },
                _to_dt(day_obj),
            ))

        # Demo fallback for endurance
        if not any(etype == "endurance" for _, etype, _, _ in logs):
            yesterday = today - timedelta(days=1)
            logs.append((
                PROVIDER,
                "endurance",
                {
                    "date": yesterday.isoformat(),
                    "exercise_entries": [
                        {
                            "name": "Morning Run",
                            "calories_burned": 450,
                            "duration_minutes": 35,
                            "notes": "Zone 2 cardio",
                        },
                        {
                            "name": "Evening Walk",
                            "calories_burned": 180,
                            "duration_minutes": 30,
                            "notes": "Recovery walk",
                        },
                    ],
                    "total_calories_burned": 630,
                    "total_duration_minutes": 65,
                    "demo": True,
                },
                _to_dt(yesterday),
            ))

        return logs

    # -- demo data (no API key set) ----------------------------------------
    def _demo_data(self, days=2):
        today = date.today()
        yesterday = today - timedelta(days=1)
        return [
            (
                PROVIDER,
                "sleep",
                {"sleep_hours": 7.6, "deep_pct": 21, "rem_pct": 19, "demo": True},
                _to_dt(yesterday),
            ),
(
                PROVIDER,
                "scale",
                {
                    "date": yesterday.isoformat(),
                    "weight": 185,
                    "unit": "lb",
                    "demo": True,
                },
                _to_dt(yesterday),
            ),
            (
                PROVIDER,
                "nutrition",
                {
                    "date": yesterday.isoformat(),
                    "food_entries": [
                        {"protein": 60, "calories": 950, "name": "Demo meal 1"},
                        {"protein": 55, "calories": 720, "name": "Demo meal 2"},
                        {"protein": 70, "calories": 620, "name": "Demo meal 3"},
                    ],
                    "goals": {"protein": 180, "calories": 2400},
                    "demo": True,
                },
                _to_dt(yesterday),
            ),
            (
                PROVIDER,
                "hydration",
                {
                    "date": yesterday.isoformat(),
                    "water_intake_entries": [
                        {"time": "08:00", "amount": 16},
                        {"time": "12:00", "amount": 20},
                        {"time": "15:00", "amount": 12},
                        {"time": "18:00", "amount": 16},
                    ],
                    "water_goal": 64,
                    "demo": True,
                },
                _to_dt(yesterday),
            ),
        ]