"""Tests for the Flamingo Fitness gamification + API layers.

Run with:  python manage.py test core
"""

from datetime import timedelta
import json

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from core.models import (
    BadgeDef,
    BattleLog,
    BossConfig,
    Campaign,
    CampaignBoss,
    CampaignProgress,
    DailyReadiness,
    Friendship,
    GearItemDef,
    GearPackDef,
    Gym,
    Modality,
    PlayerProfile,
    Provider,
    PvPMatch,
    RawActivityLog,
    ScrapShopItem,
    SkillTree,
    UserBadge,
    UserGear,
    UserIntegration,
    XPLedger,
)
from core.services.gamification import (
    XP_PER_LEVEL,
    body_battery_xp,
    calorie_xp,
    endurance_xp,
    hydration_tokens,
    hydration_xp,
    nutrition_tokens,
    nutrition_xp,
    process_log,
    process_payload,
    protein_xp,
    session_time_xp,
    sleep_xp,
    strength_xp,
    summarize_strength,
)
from core.services.liftosaur_client import LiftosaurClient, parse_history_record_text
from core.services.readiness import compute_readiness

User = get_user_model()


# ---------------------------------------------------------------------------
# Pure math (no DB) - docs/03_gamification_math.md
# ---------------------------------------------------------------------------
class XPMathTests(SimpleTestCase):
    def test_endurance_zone2_3(self):
        self.assertEqual(endurance_xp(45, "zone2"), 45)  # x1.0
        self.assertEqual(endurance_xp(30, ""), 30)

    def test_endurance_hiit(self):
        self.assertEqual(endurance_xp(45, "zone4"), 68)  # 45 x 1.5
        self.assertEqual(endurance_xp(20, "HIIT"), 30)
        self.assertEqual(endurance_xp(10, "zone5"), 15)

    def test_strength_volume_and_bonus(self):
        self.assertEqual(strength_xp(15000, completed=True), 35)  # 15 + 20
        self.assertEqual(strength_xp(15000, completed=False), 15)
        self.assertEqual(strength_xp(0, completed=True), 20)

    def test_sleep_bands(self):
        self.assertEqual(sleep_xp(8.5), 50)
        self.assertEqual(sleep_xp(8.0), 50)
        self.assertEqual(sleep_xp(7.5), 35)
        self.assertEqual(sleep_xp(7.0), 35)
        self.assertEqual(sleep_xp(6.5), 25)
        self.assertEqual(sleep_xp(6.0), 25)
        self.assertEqual(sleep_xp(5.5), 15)
        self.assertEqual(sleep_xp(5.0), 15)
        self.assertEqual(sleep_xp(4.5), 0)

    def test_body_battery_and_nutrition(self):
        self.assertEqual(body_battery_xp(62), 62)
        # Legacy boolean support
        self.assertEqual(nutrition_xp(True), 50)
        self.assertEqual(nutrition_xp(False), 0)
        # Granular protein & calorie calculations
        self.assertEqual(protein_xp(180, 180), 25)  # 100%
        self.assertEqual(protein_xp(160, 180), 15)  # 88.8%
        self.assertEqual(protein_xp(120, 180), 10)  # 66.6%
        self.assertEqual(protein_xp(90, 180), 0)    # 50%
        
        self.assertEqual(calorie_xp(2000, 2400), 25)  # under
        self.assertEqual(calorie_xp(2400, 2400), 25)  # exact
        self.assertEqual(calorie_xp(2500, 2400), 15)  # 104% (<=110%)
        self.assertEqual(calorie_xp(2700, 2400), 10)  # 112.5% (<=120%)
        self.assertEqual(calorie_xp(3000, 2400), 0)   # 125% (>120%)

        # Combined nutrition XP
        # Perfect
        self.assertEqual(nutrition_xp(180, 2200, 180, 2400), 50)
        # Protein hit, calories over
        self.assertEqual(nutrition_xp(180, 3000, 180, 2400), 25)
        # Calories on target, protein missed
        self.assertEqual(nutrition_xp(90, 2000, 180, 2400), 25)
        # Both close
        self.assertEqual(nutrition_xp(160, 2500, 180, 2400), 30)

    def test_hydration_xp_and_tokens(self):
        self.assertEqual(hydration_xp(100, 100), 30)
        self.assertEqual(hydration_xp(85, 100), 20)
        self.assertEqual(hydration_xp(65, 100), 10)
        self.assertEqual(hydration_xp(50, 100), 0)

        self.assertEqual(hydration_tokens(100, 100), 10)
        self.assertEqual(hydration_tokens(85, 100), 5)
        self.assertEqual(hydration_tokens(65, 100), 0)


# ---------------------------------------------------------------------------
# DB-backed integration tests
# ---------------------------------------------------------------------------
class GamificationFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="tester", password="pw", streak=5
        )

    def _log(self, event_type, payload, source=Provider.GARMIN):
        return RawActivityLog.objects.create(
            user=self.user, source=source, event_type=event_type, payload=payload
        )

    def test_cardio_log_generates_endurance_xp_and_updates_tree(self):
        log = self._log("cardio", {"minutes": 45, "intensity": "zone4"}, Provider.PELOTON)
        entries = process_log(log)
        self.assertTrue(log.processed)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].amount, 68)
        tree = SkillTree.objects.get(user=self.user, modality="endurance")
        self.assertEqual(tree.total_xp, 68)
        self.assertEqual(tree.xp, 68)

    def test_strength_pr_awards_boss_xp_and_speedups(self):
        log = self._log(
            "strength",
            {"volume_lbs": 15000, "completed": True, "pr": True},
            Provider.LIFTOSAUR,
        )
        entries = process_log(log)
        # base (35) + boss fight bonus (35) = 70
        self.assertEqual(sum(e.amount for e in entries), 70)
        profile_obj = PlayerProfile.objects.get(user=self.user)
        self.assertEqual(profile_obj.tokens, 300 + 100)  # starter + PR boss reward

    def test_skill_tree_level_up(self):
        from core.services.gamification import apply_to_skill_tree

        apply_to_skill_tree(self.user, "strength", XP_PER_LEVEL)
        apply_to_skill_tree(self.user, "strength", XP_PER_LEVEL)
        apply_to_skill_tree(self.user, "strength", XP_PER_LEVEL // 2)
        tree = SkillTree.objects.get(user=self.user, modality="strength")
        self.assertEqual(tree.level, 3)
        self.assertEqual(tree.xp, 50)
        self.assertEqual(tree.progress_pct, 50)

    def test_macro_perfect_awards_nutrition_xp_and_materials(self):
        log = self._log(
            "macro",
            {"protein_hit": True, "under_calorie": True},
            Provider.HOME_ASSISTANT,
        )
        entries = process_log(log)
        self.assertEqual(entries[0].amount, 50)
        profile_obj = PlayerProfile.objects.get(user=self.user)
        self.assertEqual(profile_obj.tokens, 300 + 25)  # starter + perfect macro

    def test_macro_partial_protein_only(self):
        log = self._log(
            "macro",
            {"protein_hit": True, "under_calorie": False},
            Provider.HOME_ASSISTANT,
        )
        entries = process_log(log)
        self.assertEqual(entries[0].amount, 25)
        profile_obj = PlayerProfile.objects.get(user=self.user)
        self.assertEqual(profile_obj.tokens, 300 + 5)

    def test_macro_partial_calorie_only(self):
        log = self._log(
            "macro",
            {"protein_hit": False, "under_calorie": True},
            Provider.HOME_ASSISTANT,
        )
        entries = process_log(log)
        self.assertEqual(entries[0].amount, 25)
        profile_obj = PlayerProfile.objects.get(user=self.user)
        self.assertEqual(profile_obj.tokens, 300 + 5)

    def test_hydration_tiered_flow(self):
        log = self._log(
            "hydration",
            {
                "water_goal": 100,
                "water_intake_entries": [{"amount": 85}],
            },
            Provider.SPARKYFITNESS,
        )
        entries = process_log(log)
        self.assertEqual(entries[0].amount, 20)  # 85% = 20 XP
        profile_obj = PlayerProfile.objects.get(user=self.user)
        self.assertEqual(profile_obj.tokens, 300 + 5)  # 80%+ = +5 tokens

    def test_duplicate_log_is_idempotent(self):
        log = self._log("cardio", {"minutes": 30, "intensity": "zone3"})
        first = process_log(log)
        second = process_log(log)
        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])  # already processed

    def test_process_payload_without_raw_log(self):
        entries = process_payload(
            self.user, Provider.PELOTON, "cardio",
            {"minutes": 30, "intensity": "zone3"},
        )
        self.assertEqual(entries[0].amount, 30)

class ReadinessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="r", password="pw")

    def test_low_body_battery_mandates_rest_day(self):
        RawActivityLog.objects.create(
            user=self.user,
            source=Provider.GARMIN,
            event_type="body_battery",
            payload={"charge": 30},
        )
        RawActivityLog.objects.create(
            user=self.user,
            source=Provider.GARMIN,
            event_type="sleep",
            payload={"sleep_hours": 6},
        )
        r = compute_readiness(self.user)
        self.assertEqual(r.streak_requirement, DailyReadiness.StreakRequirement.REST_DAY)

    def test_high_readiness_greenlights_training(self):
        RawActivityLog.objects.create(
            user=self.user,
            source=Provider.GARMIN,
            event_type="body_battery",
            payload={"charge": 85},
        )
        RawActivityLog.objects.create(
            user=self.user,
            source=Provider.GARMIN,
            event_type="sleep",
            payload={"sleep_hours": 8},
        )
        r = compute_readiness(self.user)
        self.assertEqual(r.streak_requirement, DailyReadiness.StreakRequirement.TRAIN)


class APITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="api", password="pw", streak=7)
        for provider in (Provider.GARMIN, Provider.PELOTON, Provider.LIFTOSAUR):
            UserIntegration.objects.create(
                user=self.user, provider=provider, is_active=True
            )

    def test_dashboard_state_requires_auth(self):
        resp = self.client.get("/api/v1/dashboard/state")
        self.assertEqual(resp.status_code, 302)  # redirect to login

    def test_dashboard_state_shape(self):
        self.client.force_login(self.user)
        resp = self.client.get("/api/v1/dashboard/state")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("user", body)
        self.assertIn("resources", body)
        self.assertIn("readiness", body)
        self.assertIn("skill_trees", body)
        self.assertEqual(body["user"]["username"], "api")

    def test_leaderboard_weekly(self):
        self.client.force_login(self.user)
        resp = self.client.get("/api/v1/leaderboard/weekly")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["window_days"], 7)

    def test_home_assistant_webhook(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            "/api/v1/webhooks/home-assistant",
            data={
                "entity_id": "binary_sensor.nfc_gym",
                "state": "on",
                "attributes": {},
            },
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.json()["accepted"])


class LeaderboardKindFilterTests(TestCase):
    """docs/17 #17 - like-with-like ``?kind=`` filter on /api/v1/leaderboard/weekly.

    The leaderboard aggregates a single modality when ?kind is supplied, ignores
    other modalities, rejects unknown kinds with 400, and advertises its kinds.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="alpha", password="pw")
        self.other = User.objects.create_user(username="beta", password="pw")
        # alpha: strength 100 + endurance 50; beta: endurance 80 + nutrition 30.
        XPLedger.objects.create(user=self.user, modality="strength", amount=100, description="t")
        XPLedger.objects.create(user=self.user, modality="endurance", amount=50, description="t")
        XPLedger.objects.create(user=self.other, modality="endurance", amount=80, description="t")
        XPLedger.objects.create(user=self.other, modality="nutrition", amount=30, description="t")

    def _by_name(self, body):
        return {row["username"]: row["total_xp"] for row in body["leaderboard"]}

    def test_no_kind_returns_all_modalities(self):
        resp = self.client.get("/api/v1/leaderboard/weekly")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["kind"], "all")
        self.assertEqual(self._by_name(body), {"alpha": 150, "beta": 110})

    def test_kind_filters_to_one_modality(self):
        resp = self.client.get("/api/v1/leaderboard/weekly?kind=endurance")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["kind"], "endurance")
        # Only endurance XP counts: alpha(50) and beta(80); neither alpha's
        # strength(100) nor beta's nutrition(30) leaks onto the board.
        self.assertEqual(self._by_name(body), {"alpha": 50, "beta": 80})

    def test_nutrition_kind_only_counts_nutrition(self):
        resp = self.client.get("/api/v1/leaderboard/weekly?kind=nutrition")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._by_name(resp.json()), {"beta": 30})

    def test_invalid_kind_returns_400(self):
        resp = self.client.get("/api/v1/leaderboard/weekly?kind=bogus")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.json())

    def test_kinds_are_advertised(self):
        body = self.client.get("/api/v1/leaderboard/weekly").json()
        values = {k["value"] for k in body["kinds"]}
        self.assertEqual(values, {value for value, _ in Modality.choices})

    def test_rows_are_ranked(self):
        body = self.client.get("/api/v1/leaderboard/weekly").json()
        ranks = [row["rank"] for row in body["leaderboard"]]
        self.assertEqual(ranks, [1, 2])  # alpha (150) first, beta (110) second


class InsightsAPITests(TestCase):
    """?days= (bounded history) and ?raw=1 (raw payload) on the skill-tree views.

    Powers the interactive Graph / Raw-data ranges in the skill-tree panels
    (docs/18). ``days`` must bound the returned history by the RawActivityLog
    occurred_at window; a missing/invalid value keeps the existing behaviour
    (all history).
    """

    def setUp(self):
        self.user = User.objects.create_user(username="insight", password="pw")
        UserIntegration.objects.create(
            user=self.user, provider=Provider.SPARKYFITNESS,
            credentials={"api_key": "k"}, is_active=True,
        )
        # Three hydration logs: today, in-range this week, and old (25 days ago).
        self._hydration(0, 92)
        self._hydration(5, 74)
        self._hydration(25, 41)

    def _hydration(self, days_ago, oz):
        d = timezone.localdate() - timedelta(days=days_ago)
        return RawActivityLog.objects.create(
            user=self.user, source=Provider.SPARKYFITNESS, event_type="hydration",
            occurred_at=timezone.now() - timedelta(days=days_ago),
            payload={
                "date": d.isoformat(),
                "water_goal": 80,
                "water_intake_entries": [{"time": "12:00", "amount": oz}],
            },
        )

    def test_days_filter_bounds_history(self):
        self.client.force_login(self.user)
        resp = self.client.get("/api/v1/hydration/?days=7")
        self.assertEqual(resp.status_code, 200)
        dates = {h["date"] for h in resp.json()["history"]}
        self.assertNotIn((timezone.localdate() - timedelta(days=25)).isoformat(), dates)
        self.assertIn(timezone.localdate().isoformat(), dates)
        self.assertEqual(len(dates), 2)

    def test_no_days_returns_all(self):
        self.client.force_login(self.user)
        resp = self.client.get("/api/v1/hydration/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["history"]), 3)

    def test_invalid_days_ignored(self):
        self.client.force_login(self.user)
        resp = self.client.get("/api/v1/hydration/?days=abc")
        self.assertEqual(len(resp.json()["history"]), 3)

    def test_raw_flag_includes_payload(self):
        self.client.force_login(self.user)
        resp = self.client.get("/api/v1/hydration/?raw=1")
        self.assertEqual(resp.status_code, 200)
        for h in resp.json()["history"]:
            self.assertIn("raw_payload", h)

    def test_nutrition_and_recovery_also_bounded(self):
        self.client.force_login(self.user)
        RawActivityLog.objects.create(
            user=self.user, source=Provider.SPARKYFITNESS, event_type="nutrition",
            occurred_at=timezone.now() - timedelta(days=2),
            payload={
                "date": (timezone.localdate() - timedelta(days=2)).isoformat(),
                "food_entries": [{"protein": 90, "calories": 800}],
                "goals": {"protein": 180, "calories": 2400},
            },
        )
        RawActivityLog.objects.create(
            user=self.user, source=Provider.SPARKYFITNESS, event_type="sleep",
            occurred_at=timezone.now() - timedelta(days=15),
            payload={
                "sleep_hours": 9,
                "date": (timezone.localdate() - timedelta(days=15)).isoformat(),
            },
        )
        self.assertEqual(len(self.client.get("/api/v1/nutrition/?days=7").json()["history"]), 1)
        self.assertEqual(len(self.client.get("/api/v1/recovery/?days=7").json()["history"]), 0)
        self.assertEqual(len(self.client.get("/api/v1/recovery/").json()["history"]), 1)


class SparkyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="sparky", password="pw")

    def test_sparky_client_demo_data(self):
        from django.conf import settings
        from core.services.sparky_client import SparkyFitnessClient

        if not getattr(settings, "DEMO", False):
            self.skipTest("DEMO mode is off — SparkyFitness returns [] without a key.")

        integration = UserIntegration.objects.create(
            user=self.user, provider=Provider.SPARKYFITNESS,
            credentials={"api_key": ""}, is_active=True,
        )
        logs = SparkyFitnessClient().fetch(integration)
        event_types = {log[1] for log in logs}
        self.assertIn("nutrition", event_types)
        self.assertIn("sleep", event_types)

    def test_sparky_perfect_macros_awards_xp_and_materials(self):
        log = RawActivityLog.objects.create(
            user=self.user,
            source=Provider.SPARKYFITNESS,
            event_type="nutrition",
            payload={
                "date": "2026-08-07",
                "food_entries": [
                    {"protein": 60, "calories": 950},
                    {"protein": 55, "calories": 720},
                    {"protein": 70, "calories": 620},
                ],
                "goals": {"protein": 180, "calories": 2400},
            },
        )
        entries = process_log(log)
        self.assertEqual(sum(e.amount for e in entries), 50)
        profile_obj = PlayerProfile.objects.get(user=self.user)
        self.assertEqual(profile_obj.tokens, 300 + 25)  # starter + perfect macro

    def test_sparky_protein_only_awards_partial_xp_and_tokens(self):
        log = RawActivityLog.objects.create(
            user=self.user,
            source=Provider.SPARKYFITNESS,
            event_type="nutrition",
            payload={
                "food_entries": [
                    {"protein": 90, "calories": 1500},
                    {"protein": 95, "calories": 1500},
                ],
                "goals": {"protein": 180, "calories": 2400},
            },
        )
        entries = process_log(log)
        self.assertEqual(sum(e.amount for e in entries), 25)
        profile_obj = PlayerProfile.objects.get(user=self.user)
        self.assertEqual(profile_obj.tokens, 300 + 5)

    def test_sparky_calories_only_awards_partial_xp_and_tokens(self):
        log = RawActivityLog.objects.create(
            user=self.user,
            source=Provider.SPARKYFITNESS,
            event_type="nutrition",
            payload={
                "food_entries": [
                    {"protein": 40, "calories": 1000},
                    {"protein": 40, "calories": 1000},
                ],
                "goals": {"protein": 180, "calories": 2400},
            },
        )
        entries = process_log(log)
        self.assertEqual(sum(e.amount for e in entries), 25)
        profile_obj = PlayerProfile.objects.get(user=self.user)
        self.assertEqual(profile_obj.tokens, 300 + 5)

    def test_sparky_close_macros_awards_partial_xp_and_tokens(self):
        log = RawActivityLog.objects.create(
            user=self.user,
            source=Provider.SPARKYFITNESS,
            event_type="nutrition",
            payload={
                "food_entries": [
                    {"protein": 80, "calories": 1250},
                    {"protein": 80, "calories": 1250},
                ],
                "goals": {"protein": 180, "calories": 2400},
            },
        )
        entries = process_log(log)
        self.assertEqual(sum(e.amount for e in entries), 30)  # 160g=15 XP + 2500cal=15 XP
        profile_obj = PlayerProfile.objects.get(user=self.user)
        self.assertEqual(profile_obj.tokens, 300 + 5)

    def test_not_perfect_macros_no_award(self):
        log = RawActivityLog.objects.create(
            user=self.user,
            source=Provider.SPARKYFITNESS,
            event_type="nutrition",
            payload={
                "food_entries": [{"protein": 20, "calories": 3000}],
                "goals": {"protein": 180, "calories": 2400},
            },
        )
        entries = process_log(log)
        self.assertEqual(entries, [])

    def test_fetch_pulls_latest_bodyweight_via_most_recent(self):
        # Real path must emit a `scale` log from GET /measurements/most-recent/weight.
        # SparkyFitness metric accounts export kg -> converted to lbs (x2.20462).
        from core.services.sparky_client import SparkyFitnessClient

        integration = UserIntegration.objects.create(
            user=self.user, provider=Provider.SPARKYFITNESS,
            credentials={"api_key": "sk_test"}, is_active=True,
        )
        client = SparkyFitnessClient()

        def fake_get(api_key, path, params=None):
            if path == "/measurements/most-recent/weight":
                return {
                    "id": "ci-1",
                    "entry_date": "2026-08-06",
                    "weight": 83.0,  # kg
                }
            return {}

        client._get = fake_get
        logs = client.fetch(integration)
        scales = [p for _, et, p, _ in logs if et == "scale"]
        self.assertEqual(len(scales), 1)
        self.assertEqual(scales[0]["weight"], 183.0)  # 83 kg -> 183.0 lb
        self.assertEqual(scales[0]["date"], "2026-08-06")
        self.assertEqual(scales[0]["unit"], "lb")

    def test_fetch_bodyweight_falls_back_to_check_in(self):
        # If /measurements/most-recent/weight returns nothing, fall back to
        # /measurements/check-in/latest-on-or-before-date.
        from core.services.sparky_client import SparkyFitnessClient

        integration = UserIntegration.objects.create(
            user=self.user, provider=Provider.SPARKYFITNESS,
            credentials={"api_key": "sk_test"}, is_active=True,
        )
        client = SparkyFitnessClient()

        def fake_get(api_key, path, params=None):
            if path == "/measurements/check-in/latest-on-or-before-date":
                return {"entry_date": "2026-08-05", "weight": 84}  # kg
            return {}

        client._get = fake_get
        logs = client.fetch(integration)
        scales = [p for _, et, p, _ in logs if et == "scale"]
        self.assertEqual(len(scales), 1)
        self.assertEqual(scales[0]["weight"], 185.2)  # 84 kg -> 185.2 lb

    def test_fetch_bodyweight_imperial_preference_keeps_lbs(self):
        # Imperial accounts already export lbs - no conversion.
        from core.services.sparky_client import SparkyFitnessClient

        integration = UserIntegration.objects.create(
            user=self.user, provider=Provider.SPARKYFITNESS,
            credentials={"api_key": "sk_test"}, is_active=True,
        )
        client = SparkyFitnessClient()

        def fake_get(api_key, path, params=None):
            if path == "/user-preferences":
                return {"unit_system": "imperial"}
            if path == "/measurements/most-recent/weight":
                return {"entry_date": "2026-08-06", "weight": 185}
            return {}

        client._get = fake_get
        logs = client.fetch(integration)
        scales = [p for _, et, p, _ in logs if et == "scale"]
        self.assertEqual(len(scales), 1)
        self.assertEqual(scales[0]["weight"], 185.0)

    def test_fetch_no_weight_means_no_scale_log(self):
        from core.services.sparky_client import SparkyFitnessClient

        integration = UserIntegration.objects.create(
            user=self.user, provider=Provider.SPARKYFITNESS,
            credentials={"api_key": "sk_test"}, is_active=True,
        )
        client = SparkyFitnessClient()
        client._get = lambda api_key, path, params=None: {}
        logs = client.fetch(integration)
        self.assertFalse(any(et == "scale" for _, et, _, _ in logs))

    def test_fetch_sleep_anchored_to_entry_date(self):
        # Sleep logs must carry the night's own date (stable dedup key),
        # not "today" - otherwise re-syncs duplicate rows day over day.
        from core.services.sparky_client import SparkyFitnessClient

        integration = UserIntegration.objects.create(
            user=self.user, provider=Provider.SPARKYFITNESS,
            credentials={"api_key": "sk_test"}, is_active=True,
        )
        client = SparkyFitnessClient()

        def fake_get(api_key, path, params=None):
            if path == "/sleep/analytics":
                return [
                    {
                        "date": "2026-08-06",
                        "timeAsleep": 28800,  # 8h in seconds
                        "stagePercentages": {"deep": 20, "rem": 22},
                    }
                ]
            return {}

        client._get = fake_get
        logs = client.fetch(integration)
        sleeps = [(p, occ) for _, et, p, occ in logs if et == "sleep"]
        self.assertEqual(len(sleeps), 1)
        payload, occurred_at = sleeps[0]
        self.assertEqual(payload["date"], "2026-08-06")
        self.assertEqual(occurred_at.date().isoformat(), "2026-08-06")


class AccountTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="acc", password="pw")

    def test_signup_creates_user_and_logs_in(self):
        resp = self.client.post(
            "/signup/",
            {
                "username": "newbie",
                "email": "newbie@example.com",
                "password1": "s3cret-pass",
                "password2": "s3cret-pass",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(User.objects.filter(username="newbie").exists())
        self.assertTrue(resp.wsgi_request.user.is_authenticated)

    def test_profile_requires_auth(self):
        resp = self.client.get("/profile/")
        self.assertEqual(resp.status_code, 302)  # redirect to login

    def test_link_sparky_without_key_uses_demo(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            "/profile/", {"api_key": ""},
        )
        self.assertEqual(resp.status_code, 302)
        integration = UserIntegration.objects.get(
            user=self.user, provider=Provider.SPARKYFITNESS
        )
        self.assertTrue(integration.is_active)

        # With DEMO=False (default), an empty key integration yields no logs.
        from django.conf import settings
        from core.services.sparky_client import SparkyFitnessClient

        logs = SparkyFitnessClient().fetch(integration)
        if getattr(settings, "DEMO", False):
            self.assertTrue(logs)  # demo data present
        else:
            self.assertEqual(logs, [])  # real mode: no key => no data

    def test_theme_update_saves_per_account(self):
        self.client.force_login(self.user)
        # Default is device; update to light.
        self.assertEqual(self.user.theme, "device")
        resp = self.client.post("/profile/", {"action": "theme", "theme": "light"})
        self.assertEqual(resp.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.theme, "light")

        # Invalid choice is rejected and the stored value is unchanged.
        resp = self.client.post("/profile/", {"action": "theme", "theme": "neon"})
        self.assertEqual(resp.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.theme, "light")

        # The dashboard page serves the preference for the theme controller.
        resp = self.client.get("/")
        self.assertContains(resp, 'data-theme="light"')

    def test_theme_update_requires_auth(self):
        resp = self.client.post("/profile/", {"action": "theme", "theme": "dark"})
        self.assertEqual(resp.status_code, 302)  # redirect to login

    def test_login_page_renders(self):
        resp = self.client.get("/login/")
        self.assertEqual(resp.status_code, 200)

    def test_logout_via_post(self):
        self.client.force_login(self.user)
        resp = self.client.post("/logout/")
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(resp.wsgi_request.user.is_authenticated)


class NutritionViewTests(TestCase):
    """GET /api/v1/nutrition/ feeds the Nutrition panel on the plan."""

    def setUp(self):
        self.user = User.objects.create_user(username="noms", password="pw")

    def test_needs_login(self):
        resp = self.client.get("/api/v1/nutrition/")
        self.assertEqual(resp.status_code, 302)  # redirect to login

    def test_endpoint_returns_summary_and_history(self):
        from django.test import override_settings
        from core.services.sparky_client import SparkyFitnessClient

        integration = UserIntegration.objects.create(
            user=self.user,
            provider=Provider.SPARKYFITNESS,
            credentials={"api_key": ""},
            is_active=True,
        )
        # Run one demo poll so nutrition logs exist. override_settings ensures
        # demo data is returned even when the global DEMO flag is False.
        with override_settings(DEMO=True):
            polled = list(SparkyFitnessClient().fetch(integration))

        for source, event_type, payload, occurred_at in polled:
            log = RawActivityLog.objects.create(
                user=self.user,
                source=source,
                event_type=event_type,
                payload=payload,
                occurred_at=occurred_at,
            )
            process_log(log)

        self.client.force_login(self.user)
        resp = self.client.get("/api/v1/nutrition/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()

        self.assertTrue(body["linked"])
        self.assertTrue(body["demo"])
        self.assertTrue(body["history"])  # at least the demo nutrition entry

        first = body["history"][0]
        # Demo day hits protein (185>=180) and is under calories (2290<=2400).
        self.assertTrue(first["perfect"])
        self.assertEqual(first["xp"], 50)
        self.assertEqual(first["tokens"], 25)
        self.assertEqual(first["protein_goal"], 180)
        self.assertEqual(first["calorie_goal"], 2400)
        self.assertEqual(len(first["food_entries"]), 3)

        # The most recent entry is surfaced as `today`.
        self.assertTrue(body["today"]["perfect"])
        self.assertEqual(body["today"]["xp"], 50)

        # Skill tree was credited for the perfect-macro XP.
        self.assertEqual(body["skill_tree"]["total_xp"], 50)
        self.assertEqual(body["skill_tree"]["progress_pct"], 50)



class LiftosaurTests(TestCase):
    SAMPLE = (
        '2026-08-07 6:00 PM/program: "5/3/1"/dayName: "Squat Day"/'
        "week: 1/dayInWeek: 1/duration: 3300s/"
        "exercises: {\n  Squat / 3 x 5 225lb, 1 x 3 275lb\n  Bench Press / 3 x 5 185lb\n}"
    )

    def test_session_time_xp(self):
        self.assertEqual(session_time_xp(55), 1)   # 1 XP per 30 min
        self.assertEqual(session_time_xp(0), 0)
        self.assertEqual(session_time_xp(None), 0)

    def test_parse_history_record_text(self):
        parsed = parse_history_record_text(self.SAMPLE)
        self.assertEqual(parsed["program"], "5/3/1")
        self.assertEqual(parsed["day_name"], "Squat Day")
        self.assertEqual(parsed["duration_minutes"], 55)
        names = [e["name"] for e in parsed["exercises"]]
        self.assertIn("Squat", names)
        self.assertIn("Bench Press", names)
        squat = next(e for e in parsed["exercises"] if e["name"] == "Squat")
        self.assertEqual(squat["sets"], 4)        # 3 + 1
        self.assertEqual(squat["weight"], 275.0)  # heaviest set
        self.assertGreater(squat["est_1rm"], 275)

    def test_demo_client_returns_strength_log(self):
        from django.test import override_settings
        with override_settings(DEMO=True):
            logs = LiftosaurClient()._demo_data()
        self.assertEqual(len(logs), 1)
        _, event_type, payload, _ = logs[0]
        self.assertEqual(event_type, "strength")
        self.assertGreaterEqual(payload["total_volume_lbs"], 15000)

    def test_summarize_strength_volume_and_time_xp(self):
        from django.utils import timezone as tz
        raw = RawActivityLog.objects.create(
            user=User.objects.create_user(username="lifter"),
            source=Provider.LIFTOSAUR,
            event_type="strength",
            occurred_at=tz.now(),
            payload={
                "date": "2026-08-07",
                "program": "5/3/1",
                "duration_minutes": 55,
                "total_volume_lbs": 22000,
                "completed": True,
                "exercises": [
                    {"name": "Squat", "sets": 5, "reps": 5, "weight": 315,
                     "unit": "lb", "volume_lbs": 7875, "est_1rm": 367.5},
                ],
            },
        )
        summary = summarize_strength(raw)
        # 22000 // 1000 = 22, +20 completion, +1 time (55//30) = 43
        self.assertEqual(summary["xp"], 43)
        self.assertEqual(summary["total_volume_lbs"], 22000)
        self.assertEqual(summary["exercises"][0]["name"], "Squat")


    def test_parse_colon_layout(self):
        # Real-world Liftosaur layout: "Name:" header line followed by set lines.
        sample = (
            "2026-08-08 09:14:12 +00:00\n"
            'program: "5/3/1"\n'
            'dayName: "Push Day"\n'
            "exercises: {\n"
            "  Bench Press:\n"
            "    5 x 5 185lb\n"
            "    5 x 5 185lb\n"
            "  Squat:\n"
            "    - 3 x 3 315lb\n"
            "}"
        )
        parsed = parse_history_record_text(sample)
        names = [e["name"] for e in parsed["exercises"]]
        self.assertIn("Bench Press", names)
        self.assertIn("Squat", names)
        bench = next(e for e in parsed["exercises"] if e["name"] == "Bench Press")
        self.assertEqual(bench["sets"], 10)          # 5 + 5
        self.assertEqual(bench["weight"], 185.0)
        squat = next(e for e in parsed["exercises"] if e["name"] == "Squat")
        self.assertEqual(squat["sets"], 3)           # dashed line still parsed
        self.assertEqual(squat["weight"], 315.0)

    def test_real_api_spec_record_text(self):
        # Exact Liftoscript Workout layout from docs/liftosaur_api_spec.md:
        # single-line exercises with warmup/target labelled sections that must be
        # excluded from completed-set/volume totals.
        spec = (
            "2026-03-01T10:00:00Z / program: \"5/3/1\" / dayName: \"Push Day\" "
            "/ week: 1 / dayInWeek: 1 / duration: 3600s / exercises: {\n"
            "  Bench Press, Barbell / 3x5 185lb, 1x3 185lb / warmup: 1x5 95lb, 1x3 135lb / target: 3x5 185lb 120s\n"
            "  Overhead Press / 3x10 95lb / target: 3x10 95lb 60s\n"
            "}"
        )
        parsed = parse_history_record_text(spec)
        self.assertEqual(parsed["program"], "5/3/1")
        self.assertEqual(parsed["day_name"], "Push Day")
        self.assertEqual(parsed["duration_minutes"], 60)
        name_list = [e["name"] for e in parsed["exercises"]]
        self.assertIn("Bench Press, Barbell", name_list)
        self.assertIn("Overhead Press", name_list)
        bench = next(e for e in parsed["exercises"] if e["name"] == "Bench Press, Barbell")
        # Only the two completed sets (3x5 185lb, 1x3 185lb) count; warmup/target skipped.
        self.assertEqual(bench["sets"], 4)
        self.assertEqual(bench["weight"], 185.0)
        # Volume = 3*5*185 + 1*3*185 = 2775 + 555 = 3330 lb.
        self.assertAlmostEqual(bench["volume_lbs"], 3330.0, places=1)
        ohp = next(e for e in parsed["exercises"] if e["name"] == "Overhead Press")
        self.assertEqual(ohp["sets"], 3)
        self.assertAlmostEqual(ohp["volume_lbs"], 3 * 10 * 95.0, places=1)

    def test_fetch_unwraps_data_envelope(self):
        # The real API wraps responses in {"data": {...}}; the client must read
        # records/hasMore/nextCursor from inside that envelope or a live sync
        # silently produces 0 rows.
        client = LiftosaurClient()

        def fake_get(api_key, path, params=None):
            return {
                "data": {
                    "records": [
                        {
                            "id": 1,
                            "text": (
                                "2026-03-01T10:00:00Z / program: \"5/3/1\" / dayName: \"Push Day\" "
                                "/ duration: 3600s / exercises: {\n"
                                "  Bench Press, Barbell / 3x5 185lb |\n"
                                "  Squat / 5x5 225lb\n"
                                "}"
                            ),
                        }
                    ],
                    "hasMore": False,
                }
            }

        client._get = fake_get
        owner = User.objects.create_user(username="smallift")
        integration = UserIntegration(
            user=owner,
            credentials={"api_key": "lftsk_test"},
        )
        logs = client.fetch(integration, days=30)
        self.assertEqual(len(logs), 1)
        _, event_type, payload, _ = logs[0]
        self.assertEqual(event_type, "strength")
        names = [e["name"] for e in payload["exercises"]]
        self.assertIn("Bench Press, Barbell", names)
        self.assertIn("Squat", names)
        self.assertEqual(payload["total_sets"], 8)   # 3 + 5 elapsed working sets
class StrengthBossViewTests(TestCase):
    """GET /api/v1/strength/ and GET /api/v1/boss/."""

    def setUp(self):
        self.user = User.objects.create_user(username="squatter")
        UserIntegration.objects.create(
            user=self.user, provider=Provider.LIFTOSAUR,
            credentials={}, is_active=True,
        )
        UserIntegration.objects.create(
            user=self.user, provider=Provider.SPARKYFITNESS,
            credentials={}, is_active=True,
        )
        BossConfig.objects.create(
            name="Bench Press", exercise_match="Bench Press",
            bodyweight_multiplier=1.5,
        )
        self.client.force_login(self.user)

    def _seed(self):
        from datetime import date, timedelta
        from django.utils import timezone as tz

        yesterday = (date.today() - timedelta(days=1)).isoformat()
        RawActivityLog.objects.create(
            user=self.user, source=Provider.LIFTOSAUR, event_type="strength",
            occurred_at=tz.now(),
            payload={
                "date": yesterday, "program": "5/3/1", "day_name": "Squat Day",
                "duration_minutes": 55, "total_volume_lbs": 22000, "volume_lbs": 22000,
                "total_sets": 15, "completed": True, "pr": False,
                "exercises": [
                    {"name": "Bench Press", "sets": 5, "reps": 5, "weight": 265,
                     "unit": "lb", "volume_lbs": 6625, "est_1rm": 309.2},
                ],
            },
        )
        RawActivityLog.objects.create(
            user=self.user, source=Provider.SPARKYFITNESS, event_type="scale",
            occurred_at=tz.now(),
            payload={"date": yesterday, "weight": 180, "unit": "lb"},
        )

    def test_strength_endpoint(self):
        self._seed()
        resp = self.client.get("/api/v1/strength/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["linked"])
        self.assertGreaterEqual(body["today"]["total_volume_lbs"], 22000)
        # PRs moved out of the Strength panel - they live on /api/v1/boss/ now.
        self.assertNotIn("best_lifts", body)

    def test_boss_endpoint_conquered(self):
        self._seed()
        resp = self.client.get("/api/v1/boss/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["bodyweight"], 180.0)
        bench = next(b for b in body["bosses"] if b["name"] == "Bench Press")
        self.assertEqual(bench["goal"], 270.0)      # 180 * 1.5
        self.assertEqual(bench["best_lift"], 309.2)
        self.assertTrue(bench["conquered"])
        # Personal records now ship with the PR Boss payload.
        self.assertEqual(body["best_lifts"][0]["name"], "Bench Press")

    def test_boss_endpoint_requires_bodyweight(self):
        resp = self.client.get("/api/v1/boss/")
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()["bodyweight"])


class RecoveryViewTests(TestCase):
    """GET /api/v1/recovery/ feeds the green Recovery node's panel."""

    def setUp(self):
        self.user = User.objects.create_user(username="sleepy", password="pw")
        UserIntegration.objects.create(
            user=self.user, provider=Provider.SPARKYFITNESS,
            credentials={"api_key": "sk_test"}, is_active=True,
        )
        self.client.force_login(self.user)

    def test_needs_login(self):
        client = self.client_class()
        resp = client.get("/api/v1/recovery/")
        self.assertEqual(resp.status_code, 302)

    def test_endpoint_returns_readiness_and_sleep_history(self):
        from django.utils import timezone as tz

        RawActivityLog.objects.create(
            user=self.user, source=Provider.SPARKYFITNESS, event_type="sleep",
            occurred_at=tz.now(),
            payload={
                "date": tz.localdate().isoformat(),
                "sleep_hours": 8.2, "deep_pct": 21, "rem_pct": 19,
            },
        )
        resp = self.client.get("/api/v1/recovery/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["linked"])
        self.assertFalse(body["demo"])  # has a real api key
        self.assertIn("score", body["readiness"])
        self.assertIn("streak_requirement", body["readiness"])
        self.assertEqual(len(body["history"]), 1)
        self.assertEqual(body["history"][0]["sleep_hours"], 8.2)
        self.assertEqual(body["history"][0]["xp"], 50)  # 8h+ sleep
        self.assertIsNotNone(body["today"])
        self.assertIn("skill_tree", body)

    def test_endpoint_without_sparky_shows_unlinked(self):
        other = User.objects.create_user(username="nosleep", password="pw")
        client = self.client_class()
        client.force_login(other)
        resp = client.get("/api/v1/recovery/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body["linked"])
        self.assertEqual(body["history"], [])


class IngestDedupTests(TestCase):
    """Syncing twice must never duplicate rows or XP (any modality)."""

    def setUp(self):
        from django.utils import timezone as tz

        self.user = User.objects.create_user(username="dupcheck", password="pw")
        self.integration = UserIntegration.objects.create(
            user=self.user, provider=Provider.SPARKYFITNESS,
            credentials={"api_key": "sk_test"}, is_active=True,
        )
        self.day = tz.make_aware(tz.datetime(2026, 8, 7, 0, 0))
        # A full day of tuples covering every dedup-sensitive modality.
        self.results = [
            (
                "sparkyfitness", "nutrition",
                {
                    "date": "2026-08-07",
                    "food_entries": [{"protein": 185, "calories": 2200}],
                    "goals": {"protein": 180, "calories": 2400},
                },
                self.day,
            ),
            (
                "sparkyfitness", "hydration",
                {
                    "date": "2026-08-07",
                    "water_intake_entries": [{"time": "08:00", "amount": 70}],
                    "water_goal": 64,
                },
                self.day,
            ),
            (
                "sparkyfitness", "endurance",
                {
                    "date": "2026-08-07",
                    "exercise_entries": [{"name": "Run", "calories_burned": 450,
                                          "duration_minutes": 35}],
                    "total_calories_burned": 450,
                    "total_duration_minutes": 35,
                },
                self.day,
            ),
            (
                "sparkyfitness", "sleep",
                {"date": "2026-08-07", "sleep_hours": 8.1, "deep_pct": 20,
                 "rem_pct": 21},
                self.day,
            ),
            (
                "sparkyfitness", "scale",
                {"date": "2026-08-07", "weight": 183.0, "unit": "lb"},
                self.day,
            ),
            (
                "liftosaur", "strength",
                {
                    "date": "2026-08-07", "program": "5/3/1",
                    "duration_minutes": 55, "total_volume_lbs": 22000,
                    "volume_lbs": 22000, "total_sets": 15, "completed": True,
                    "pr": True,
                    "exercises": [
                        {"name": "Squat", "sets": 5, "reps": 5, "weight": 315,
                         "unit": "lb", "volume_lbs": 7875, "est_1rm": 367.5},
                    ],
                },
                self.day,
            ),
        ]

    def test_double_sync_creates_no_duplicates(self):
        from core.tasks import ingest_results

        first = ingest_results(self.integration, self.results)
        self.assertEqual(first, 6)
        xp_after_first = XPLedger.objects.filter(user=self.user).count()
        self.assertGreater(xp_after_first, 0)

        # Second sync of the exact same data (beat poll / manual re-link).
        second = ingest_results(self.integration, self.results)
        self.assertEqual(second, 0)

        # Row counts unchanged per modality (no duplicate imports).
        for event_type in ("nutrition", "hydration", "endurance", "sleep",
                           "scale"):
            count = RawActivityLog.objects.filter(
                user=self.user, source=Provider.SPARKYFITNESS,
                event_type=event_type,
            ).count()
            self.assertEqual(count, 1, msg=f"duplicate {event_type} rows")
        self.assertEqual(
            RawActivityLog.objects.filter(
                user=self.user, source=Provider.LIFTOSAUR,
                event_type="strength",
            ).count(),
            1,
            msg="duplicate strength/PR rows",
        )

        # XP must not be double-awarded on re-sync.
        self.assertEqual(XPLedger.objects.filter(user=self.user).count(),
                         xp_after_first)

    def test_refresh_updates_payload_in_place(self):
        from core.tasks import ingest_results

        ingest_results(self.integration, self.results)
        more_water = [
            (
                "sparkyfitness", "hydration",
                {
                    "date": "2026-08-07",
                    "water_intake_entries": [{"time": "08:00", "amount": 90}],
                    "water_goal": 64,
                },
                self.day,
            ),
        ]
        created = ingest_results(self.integration, more_water)
        self.assertEqual(created, 0)
        log = RawActivityLog.objects.get(
            user=self.user, source=Provider.SPARKYFITNESS,
            event_type="hydration",
        )
        self.assertEqual(log.payload["water_intake_entries"][0]["amount"], 90)

    def test_legacy_duplicates_are_collapsed_not_crash(self):
        # Before dedup landed, repeated polls created several rows for the
        # same key (e.g. admin had 18 sleep rows on one date). Ingest must
        # collapse them - keep the newest, drop the rest - instead of raising
        # MultipleObjectsReturned.
        from core.tasks import ingest_results

        sleep_tuple = next(t for t in self.results if t[1] == "sleep")
        _, event_type, payload, occurred_at = sleep_tuple

        # Simulate 18 legacy duplicate rows for that key.
        for i in range(18):
            RawActivityLog.objects.create(
                user=self.user, source="sparkyfitness", event_type=event_type,
                payload=dict(payload, stale_marker=i), occurred_at=occurred_at,
            )
        self.assertEqual(
            RawActivityLog.objects.filter(
                user=self.user, event_type="sleep"
            ).count(),
            18,
        )

        xp_before = XPLedger.objects.filter(user=self.user).count()
        created = ingest_results(self.integration, [sleep_tuple])
        self.assertEqual(created, 0)

        # Exactly one row survives, refreshed with the latest payload.
        rows = RawActivityLog.objects.filter(
            user=self.user, event_type="sleep"
        )
        self.assertEqual(rows.count(), 1)
        self.assertNotIn("stale_marker", rows.get().payload)
        # The collapsed rows were processed=False stubs, so no XP was ever
        # awarded for them and none is awarded now.
        self.assertEqual(
            XPLedger.objects.filter(user=self.user).count(), xp_before
        )

        # A second sync stays stable (no crash, no growth).
        created = ingest_results(self.integration, [sleep_tuple])
        self.assertEqual(created, 0)
        self.assertEqual(
            RawActivityLog.objects.filter(
                user=self.user, event_type="sleep"
            ).count(),
            1,
        )


class ProfileLinkTests(TestCase):
    """Profile page renders both link forms and persists Liftosaur keys."""

    def setUp(self):
        self.user = User.objects.create_user(username="linker")
        self.client.force_login(self.user)

    def test_profile_renders_liftosaur_linking(self):
        resp = self.client.get("/profile/")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn("Link Liftosaur", html)
        self.assertIn("lftsk_", html)

    def test_post_liftosaur_key_creates_integration(self):
        from django.test import override_settings

        with override_settings(DEMO=True, CELERY_TASK_ALWAYS_EAGER=True):
            resp = self.client.post(
                "/profile/",
                {"provider": "liftosaur", "api_key": ""},
            )
        self.assertEqual(resp.status_code, 302)
        integration = UserIntegration.objects.get(user=self.user, provider=Provider.LIFTOSAUR)
        self.assertTrue(integration.is_active)
        # The Link & Sync must have ingested strength logs immediately.
        self.assertTrue(
            RawActivityLog.objects.filter(
                user=self.user, source=Provider.LIFTOSAUR, event_type="strength"
            ).exists()
        )

    def test_post_sparky_still_works_without_provider(self):
        from django.test import override_settings

        with override_settings(DEMO=True, CELERY_TASK_ALWAYS_EAGER=True):
            resp = self.client.post(
                "/profile/",
                {"api_key": ""},
            )
        self.assertEqual(resp.status_code, 302)
        integration = UserIntegration.objects.get(user=self.user, provider=Provider.SPARKYFITNESS)
        self.assertTrue(integration.is_active)
        self.assertTrue(
            RawActivityLog.objects.filter(
                user=self.user, source=Provider.SPARKYFITNESS
            ).exists()
        )

    def test_profile_renders_sync_history_when_linked(self):
        UserIntegration.objects.create(
            user=self.user, provider=Provider.SPARKYFITNESS, is_active=True
        )
        resp = self.client.get("/profile/")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        # Segmented fetch-history control renders for a linked provider.
        self.assertIn("Fetch history", html)
        self.assertIn("30 days", html)
        self.assertIn("365 days", html)
        self.assertIn("data record(s) stored", html)

    def test_sync_history_sparky_365_renders_profile(self):
        """Selecting 365 days must land back on a rendered (non-blank) profile."""
        from django.test import override_settings

        UserIntegration.objects.create(
            user=self.user,
            provider=Provider.SPARKYFITNESS,
            credentials={"api_key": ""},
            is_active=True,
        )
        with override_settings(DEMO=True, CELERY_TASK_ALWAYS_EAGER=True):
            resp = self.client.post(
                "/profile/",
                {
                    "action": "sync_history",
                    "provider": "sparkyfitness",
                    "days": "365",
                },
                follow=True,
            )
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn("Fetch history", html)
        self.assertIn("Link SparkyFitness", html)

    def test_backfill_sparky_chunks_365_days(self):
        """A 365-day import must run in bounded chunks (not one huge loop)."""
        from unittest import mock

        from core.tasks import backfill_sparkyfitness_for_user

        UserIntegration.objects.create(
            user=self.user,
            provider=Provider.SPARKYFITNESS,
            credentials={"api_key": "k"},
            is_active=True,
        )
        fake = mock.Mock()
        fake.fetch.return_value = [
            (Provider.SPARKYFITNESS, "sleep", {"sleep_hours": 7}, timezone.now())
        ]
        with mock.patch("core.tasks.SparkyFitnessClient", return_value=fake):
            count = backfill_sparkyfitness_for_user(self.user.id, 365)

        days_log = [c.kwargs.get("days") for c in fake.fetch.call_args_list]
        # 365 days split into 12 x 30 + 1 x 5 across the chunking walk.
        self.assertEqual(len(days_log), 13)
        self.assertEqual(days_log[:12], [30] * 12)
        self.assertEqual(days_log[12], 5)
        # Windows walk strictly backward (newest first).
        end_dates = [c.kwargs.get("end_date") for c in fake.fetch.call_args_list]
        self.assertTrue(
            all(end_dates[i] > end_dates[i + 1] for i in range(len(end_dates) - 1))
        )
        # Task completes successfully, not -1.
        self.assertGreaterEqual(count, 0)

    def test_backfill_skips_when_already_running(self):
        """A second backfill for the same user+provider is a no-op."""
        from django.core.cache import cache
        from django.test import override_settings
        from unittest import mock

        from core.tasks import backfill_lock_key, backfill_sparkyfitness_for_user

        UserIntegration.objects.create(
            user=self.user, provider=Provider.SPARKYFITNESS, is_active=True
        )
        caches = {
            "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
        }
        with override_settings(CACHES=caches):
            cache.set(
                backfill_lock_key(self.user.id, Provider.SPARKYFITNESS),
                "1",
                timeout=60,
            )
            with mock.patch("core.tasks.SparkyFitnessClient") as factory:
                count = backfill_sparkyfitness_for_user(self.user.id, 365)
            factory.assert_not_called()
            self.assertEqual(count, 0)

    def test_sync_history_sparky_ingests_without_xp(self):
        from django.test import override_settings

        UserIntegration.objects.create(
            user=self.user,
            provider=Provider.SPARKYFITNESS,
            credentials={"api_key": ""},
            is_active=True,
        )
        with override_settings(DEMO=True, CELERY_TASK_ALWAYS_EAGER=True):
            resp = self.client.post(
                "/profile/",
                {
                    "action": "sync_history",
                    "provider": "sparkyfitness",
                    "days": "30",
                },
            )
        self.assertEqual(resp.status_code, 302)
        logs = RawActivityLog.objects.filter(
            user=self.user, source=Provider.SPARKYFITNESS
        )
        self.assertTrue(logs.exists())
        # Historical import must not award XP / badges...
        self.assertFalse(XPLedger.objects.filter(user=self.user).exists())
        # ...and the rows are stamped processed so they can never convert later.
        self.assertEqual(logs.filter(processed=True).count(), logs.count())

    def test_sync_history_sparky_is_idempotent(self):
        from django.test import override_settings

        UserIntegration.objects.create(
            user=self.user,
            provider=Provider.SPARKYFITNESS,
            credentials={"api_key": ""},
            is_active=True,
        )
        with override_settings(DEMO=True, CELERY_TASK_ALWAYS_EAGER=True):
            for _ in range(2):
                self.client.post(
                    "/profile/",
                    {
                        "action": "sync_history",
                        "provider": "sparkyfitness",
                        "days": "30",
                    },
                )
        logs = RawActivityLog.objects.filter(
            user=self.user, source=Provider.SPARKYFITNESS
        )
        # Keyed by (source, event_type, occurred_at), so re-syncing never
        # duplicates a day's row.
        self.assertEqual(
            logs.count(),
            logs.values("source", "event_type", "occurred_at").distinct().count(),
        )

    def test_sync_history_liftosaur_ingests_without_xp(self):
        from django.test import override_settings

        UserIntegration.objects.create(
            user=self.user,
            provider=Provider.LIFTOSAUR,
            credentials={"api_key": ""},
            is_active=True,
        )
        with override_settings(DEMO=True, CELERY_TASK_ALWAYS_EAGER=True):
            resp = self.client.post(
                "/profile/",
                {
                    "action": "sync_history",
                    "provider": "liftosaur",
                    "days": "30",
                },
            )
        self.assertEqual(resp.status_code, 302)
        logs = RawActivityLog.objects.filter(
            user=self.user, source=Provider.LIFTOSAUR, event_type="strength"
        )
        self.assertTrue(logs.exists())
        self.assertFalse(XPLedger.objects.filter(user=self.user).exists())
        self.assertTrue(all(log.processed for log in logs))

    def test_sync_history_requires_valid_range(self):
        from django.test import override_settings

        UserIntegration.objects.create(
            user=self.user, provider=Provider.SPARKYFITNESS, is_active=True
        )
        with override_settings(DEMO=True, CELERY_TASK_ALWAYS_EAGER=True):
            resp = self.client.post(
                "/profile/",
                {
                    "action": "sync_history",
                    "provider": "sparkyfitness",
                    "days": "9999",
                },
            )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(
            RawActivityLog.objects.filter(
                user=self.user, source=Provider.SPARKYFITNESS
            ).exists()
        )

    def test_sync_history_requires_linked_integration(self):
        from django.test import override_settings

        with override_settings(DEMO=True, CELERY_TASK_ALWAYS_EAGER=True):
            resp = self.client.post(
                "/profile/",
                {"action": "sync_history", "provider": "sparkyfitness", "days": "30"},
            )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(
            RawActivityLog.objects.filter(
                user=self.user, source=Provider.SPARKYFITNESS
            ).exists()
        )
# ---------------------------------------------------------------------------
# Achievement Badges (Roadmap idea #5)
# ---------------------------------------------------------------------------
class BadgeTests(TestCase):
    """GET /api/v1/badges/ + the check_badges derivation engine."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="badger", password="pw", streak=0
        )

    def _grant_one_log(self, event_type="cardio", days_ago=0, hour=12):
        now = timezone.now().replace(hour=hour, minute=0, second=0, microsecond=0)
        occurred = now - timedelta(days=days_ago) if days_ago else now
        return RawActivityLog.objects.create(
            user=self.user,
            source=Provider.PELOTON,
            event_type=event_type,
            payload={},
            occurred_at=occurred,
        )

    def test_catalog_seeded_once(self):
        from core.services.badges import BADGE_CATALOG, sync_badge_defs

        total = len(BADGE_CATALOG)
        self.assertEqual(sync_badge_defs(), total)  # full catalog created
        self.assertEqual(sync_badge_defs(), 0)  # second pass is a no-op
        self.assertEqual(BadgeDef.objects.count(), total)

    def test_endpoint_requires_auth(self):
        resp = self.client.get("/api/v1/badges/")
        self.assertEqual(resp.status_code, 302)  # redirect to login

    def test_endpoint_shape(self):
        from core.services.badges import BADGE_CATALOG

        self.client.force_login(self.user)
        resp = self.client.get("/api/v1/badges/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(
            set(body),
            {
                "total", "earned", "total_points", "earned_points",
                "newly_awarded", "badges",
            },
        )
        self.assertEqual(body["total"], len(BADGE_CATALOG))
        self.assertEqual(body["earned"], 0)
        self.assertEqual(body["earned_points"], 0)
        self.assertGreater(body["total_points"], 0)
        self.assertEqual(body["newly_awarded"], [])
        keys = {b["key"] for b in body["badges"]}
        for expected in (
            "first_steps", "ten_day_flame", "perfect_week",
            "all_modality_master", "early_bird", "night_owl",
        ):
            self.assertIn(expected, keys)
        first = next(b for b in body["badges"] if b["key"] == "first_steps")
        self.assertEqual(first["points"], 5)
        self.assertFalse(first["granted"])
        self.assertIsNone(first["awarded_at"])
        self.assertEqual(first["progress"]["value"], 0)
        self.assertEqual(first["progress"]["target"], 1)

    def test_first_steps_unlocked_on_first_log(self):
        from core.services.badges import check_badges

        self._grant_one_log()
        newly = check_badges(self.user)
        self.assertIn("first_steps", newly)
        # Idempotent: a re-run grants nothing.
        self.assertEqual(check_badges(self.user), [])

    def test_ten_day_flame_unlocked_by_streak(self):
        from core.services.badges import check_badges

        self.user.streak = 10
        self.user.save()
        newly = check_badges(self.user)
        self.assertIn("ten_day_flame", newly)

    def test_perfect_week_requires_all_seven_days(self):
        from core.services.badges import check_badges

        for d in range(7):
            self._grant_one_log(days_ago=d)
        newly = check_badges(self.user)
        self.assertIn("perfect_week", newly)
        self.assertIn("first_steps", newly)

    def test_perfect_week_missing_a_day_is_locked(self):
        from core.services.badges import check_badges

        for d in range(6):  # only 6 of 7 days
            self._grant_one_log(days_ago=d)
        newly = check_badges(self.user)
        self.assertNotIn("perfect_week", newly)

    def test_all_modality_master(self):
        from core.services.badges import check_badges

        for m in Modality:
            SkillTree.objects.create(user=self.user, modality=m.value, level=3)
        newly = check_badges(self.user)
        self.assertIn("all_modality_master", newly)

    def test_all_modality_master_missing_one(self):
        from core.services.badges import check_badges

        for m in Modality:
            if m == Modality.RECOVERY:
                continue
            SkillTree.objects.create(user=self.user, modality=m.value, level=3)
        newly = check_badges(self.user)
        self.assertNotIn("all_modality_master", newly)

    def test_habit_badges(self):
        from core.services.badges import check_badges

        now = timezone.now()
        for hour in (4, 22):
            RawActivityLog.objects.create(
                user=self.user, source=Provider.PELOTON, event_type="cardio",
                payload={}, occurred_at=now.replace(
                    hour=hour, minute=0, second=0, microsecond=0
                ),
            )
        newly = check_badges(self.user)
        self.assertIn("early_bird", newly)
        self.assertIn("night_owl", newly)

    def test_state_reflects_earned_grants(self):
        from core.services.badges import badges_state

        self._grant_one_log()  # noon log -> only first_steps
        state = badges_state(self.user)
        self.assertEqual(state["earned"], 1)
        self.assertEqual(state["earned_points"], 5)  # First Steps is worth 5 pts
        self.assertIn("first_steps", state["newly_awarded"])
        granted = [b for b in state["badges"] if b["granted"]]
        self.assertEqual([b["key"] for b in granted], ["first_steps"])
        self.assertTrue(granted[0]["awarded_at"])  # ISO award timestamp
        self.assertEqual(granted[0]["progress"]["pct"], 100)
        # A second call grants nothing new.
        self.assertEqual(badges_state(self.user)["newly_awarded"], [])



    def test_admin_created_rule_badge_is_granted(self):
        """Badges created purely in the admin (key + rule) work with no code."""
        from core.services.badges import badges_state, check_badges

        BadgeDef.objects.create(
            key="streak_3",
            name="3-Day Spark",
            description="Reach a 3-day streak.",
            icon="fa-fire",
            category="Streaks",
            points=15,
            rule={"type": "streak", "minimum": 3},
            sort_order=99,
        )
        self.user.streak = 5
        self.user.save()
        newly = check_badges(self.user)
        self.assertIn("streak_3", newly)
        state = badges_state(self.user)
        badge = next(b for b in state["badges"] if b["key"] == "streak_3")
        self.assertTrue(badge["granted"])
        self.assertEqual(badge["points"], 15)
        self.assertTrue(badge["awarded_at"])

    def test_progress_shown_when_locked(self):
        from core.services.badges import badges_state

        self.user.streak = 4
        self.user.save()
        state = badges_state(self.user)
        flame = next(b for b in state["badges"] if b["key"] == "ten_day_flame")
        self.assertFalse(flame["granted"])
        self.assertIsNone(flame["awarded_at"])
        self.assertEqual(flame["progress"]["value"], 4)
        self.assertEqual(flame["progress"]["target"], 10)
        self.assertEqual(flame["progress"]["pct"], 40)
        self.assertIn("4 of 10", flame["progress"]["text"])

    def test_points_totals(self):
        from core.services.badges import BADGE_CATALOG, badges_state

        state = badges_state(self.user)  # nothing earned yet
        self.assertEqual(state["earned_points"], 0)
        expected_total = sum(b["points"] for b in state["badges"])
        self.assertEqual(state["total_points"], expected_total)
        # Total always matches the seeded catalog (no hard-coded sum, so the
        # catalog can grow without breaking this test).
        self.assertEqual(
            expected_total, sum(b["points"] for b in BADGE_CATALOG)
        )


# ---------------------------------------------------------------------------
# Top-nav stat explainers (GET /api/v1/stats/<stat>/)
# ---------------------------------------------------------------------------
class StatInfoAPITests(TestCase):
    """Clicking the streak / materials / energy badges explains the stat and
    shows recent history of earning it (core/services/stat_explainers.py)."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="statinfo", password="pw", streak=4
        )
        self.client.login(username="statinfo", password="pw")

    def test_stat_info_requires_login(self):
        self.client.logout()
        resp = self.client.get("/stats/streak/")
        self.assertEqual(resp.status_code, 302)

    def test_unknown_stat_404(self):
        resp = self.client.get("/stats/gold/")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("error", resp.json())

    def test_streak_shape_and_history(self):
        today = timezone.localdate()
        DailyReadiness.objects.create(
            user=self.user, date=today, score=80,
            streak_requirement=DailyReadiness.StreakRequirement.TRAIN,
        )
        DailyReadiness.objects.create(
            user=self.user, date=today - timedelta(days=1), score=30,
            streak_requirement=DailyReadiness.StreakRequirement.REST_DAY,
        )
        resp = self.client.get("/stats/streak/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["stat"], "streak")
        self.assertEqual(body["value"], 4)
        self.assertEqual(len(body["history"]), 2)
        labels = {h["label"] for h in body["history"]}
        self.assertEqual(labels, {"Training day", "Rest day"})

    def test_tokens_reflect_perfect_macro(self):
        # Perfect macros award +25 tokens to the PlayerProfile wallet.
        log = RawActivityLog.objects.create(
            user=self.user,
            source=Provider.SPARKYFITNESS,
            event_type="nutrition",
            payload={
                "date": timezone.localdate().isoformat(),
                "food_entries": [{"protein": 200, "calories": 100}],
                "goals": {"protein": 150, "calories": 2000},
            },
        )
        process_log(log)
        resp = self.client.get("/stats/tokens/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["stat"], "tokens")
        self.assertEqual(body["value"], 300 + 25)  # starter + perfect macro

    def test_stamina_shape(self):
        resp = self.client.get("/stats/stamina/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["stat"], "stamina")
        self.assertEqual(body["value"], 3)
        fact_labels = [f["label"] for f in body["facts"]]
        self.assertIn("Attacks per day", fact_labels)
        self.assertIn("Rest-day bonus", fact_labels)



# ---------------------------------------------------------------------------
# Phase 8 (docs/13): Leagues, Challenges & Flocks
# ---------------------------------------------------------------------------
from datetime import date  # noqa: E402

from core.models import (  # noqa: E402
    Challenge,
    Flock,
    FlockInvite,
    FlockMembership,
    Friendship,
    LeagueResult,
    LeagueWeek,
)
from core.services.leagues import (  # noqa: E402
    WEEKLY_REWARDS,
    close_league_week,
    ensure_current_week,
    league_state,
    tier_for_xp,
    week_start_for,
)
from core.services.challenges import (  # noqa: E402
    calories_burned_in_window,
    challenge_state,
)
from core.services.social import (  # noqa: E402
    FLOCK_MAX_MEMBERS,
    create_flock,
    friends_of,
    invite_to_flock,
    leave_flock,
    respond_flock_invite,
    respond_friend_request,
    search_users,
    send_friend_request,
    social_state,
)


class LeagueMathTests(SimpleTestCase):
    def test_tier_thresholds(self):
        self.assertEqual(tier_for_xp(0), "bronze")
        self.assertEqual(tier_for_xp(99), "bronze")
        self.assertEqual(tier_for_xp(100), "silver")
        self.assertEqual(tier_for_xp(299), "silver")
        self.assertEqual(tier_for_xp(300), "gold")
        self.assertEqual(tier_for_xp(599), "gold")
        self.assertEqual(tier_for_xp(600), "diamond")
        self.assertEqual(tier_for_xp(999), "diamond")
        self.assertEqual(tier_for_xp(1000), "flamingo_legend")
        self.assertEqual(tier_for_xp(99999), "flamingo_legend")

    def test_week_start_is_monday(self):
        # 2026-08-10 is a Monday; every weekday of that week maps back to it.
        for offset in range(7):
            day = date(2026, 8, 10) + timedelta(days=offset)
            self.assertEqual(week_start_for(day), date(2026, 8, 10))


class LeagueFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="leaguer", password="pw")
        self.rival = User.objects.create_user(username="rival", password="pw")

    def _xp(self, user, amount, modality="endurance", days_ago=0):
        entry = XPLedger.objects.create(
            user=user, modality=modality, amount=amount, description="t"
        )
        if days_ago:
            created = timezone.now() - timedelta(days=days_ago)
            XPLedger.objects.filter(pk=entry.pk).update(created_at=created)
        return entry

    def test_ensure_current_week_creates_monday_row_and_is_idempotent(self):
        week = ensure_current_week()
        self.assertEqual(week.week_start, week_start_for(timezone.localdate()))
        self.assertEqual(week.status, "open")
        again = ensure_current_week()
        self.assertEqual(week.pk, again.pk)
        self.assertEqual(LeagueWeek.objects.count(), 1)

    def test_close_week_snapshots_ranks_tiers_and_pays_rewards(self):
        week = ensure_current_week()
        self._xp(self.user, 320)    # gold tier, rank 1
        self._xp(self.rival, 110)   # silver tier, rank 2
        results = close_league_week(week)
        week.refresh_from_db()
        self.assertEqual(week.status, "closed")
        self.assertIsNotNone(week.closed_at)
        self.assertEqual(len(results), 2)

        first = LeagueResult.objects.get(week=week, user=self.user)
        second = LeagueResult.objects.get(week=week, user=self.rival)
        self.assertEqual(first.rank, 1)
        self.assertEqual(first.xp, 320)
        self.assertEqual(first.tier, "gold")
        self.assertEqual(first.reward, WEEKLY_REWARDS[1])
        self.assertEqual(second.rank, 2)
        self.assertEqual(second.tier, "silver")
        self.assertEqual(second.reward, WEEKLY_REWARDS[2])

        resources = PlayerProfile.objects.get(user=self.user)
        self.assertEqual(resources.tokens, 300 + WEEKLY_REWARDS[1]["tokens"])

    def test_close_week_is_idempotent(self):
        week = ensure_current_week()
        self._xp(self.user, 50)
        close_league_week(week)
        self.assertEqual(close_league_week(week), [])
        self.assertEqual(LeagueResult.objects.filter(week=week).count(), 1)
        # Rank-1 reward paid exactly once - the re-run must not double-pay.
        self.assertEqual(
            PlayerProfile.objects.get(user=self.user).tokens,
            300 + WEEKLY_REWARDS[1]["tokens"],
        )

    def test_stale_open_weeks_close_lazily(self):
        last_monday = week_start_for(timezone.localdate()) - timedelta(days=7)
        stale = LeagueWeek.objects.create(week_start=last_monday, status="open")
        self._xp(self.user, 650, days_ago=8)  # falls inside last week
        current = ensure_current_week()
        stale.refresh_from_db()
        self.assertEqual(stale.status, "closed")
        self.assertEqual(current.week_start, week_start_for(timezone.localdate()))
        result = LeagueResult.objects.get(week=stale, user=self.user)
        self.assertEqual(result.xp, 650)
        self.assertEqual(result.tier, "diamond")

    def test_league_state_shape_and_you_row(self):
        self._xp(self.rival, 150)
        body = league_state(self.user)
        self.assertEqual(
            set(body),
            {"week", "tiers", "my_tier", "my_rank", "leaderboard", "history"},
        )
        self.assertEqual(body["week"]["status"], "open")
        self.assertGreaterEqual(body["week"]["days_left"], 0)
        self.assertIsNone(body["my_rank"])  # 0 XP this week
        usernames = [r["username"] for r in body["leaderboard"]]
        self.assertIn("leaguer", usernames)  # always shown, even at 0 XP
        me = next(r for r in body["leaderboard"] if r["is_you"])
        self.assertEqual(me["xp"], 0)
        self.assertEqual(me["tier"], "bronze")
        rival = next(r for r in body["leaderboard"] if r["username"] == "rival")
        self.assertEqual(rival["rank"], 1)
        self.assertEqual(rival["tier"], "silver")


class ChallengeFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="burner", password="pw")
        self.challenge = Challenge.objects.create(
            slug="calories_burned_30d",
            name="Calorie Torch",
            metric=Challenge.Metric.CALORIES_BURNED,
            window_days=30,
            is_active=True,
        )

    def _endurance_log(self, user, calories, days_ago=0):
        log = RawActivityLog.objects.create(
            user=user,
            source=Provider.SPARKYFITNESS,
            event_type="endurance",
            payload={"total_calories_burned": calories, "exercise_entries": []},
        )
        if days_ago:
            occurred = timezone.now() - timedelta(days=days_ago)
            RawActivityLog.objects.filter(pk=log.pk).update(occurred_at=occurred)
        return log

    def _cardio_log(self, user, calories, days_ago=0):
        log = RawActivityLog.objects.create(
            user=user,
            source=Provider.PELOTON,
            event_type="cardio",
            payload={"minutes": 45, "calories": calories},
        )
        if days_ago:
            occurred = timezone.now() - timedelta(days=days_ago)
            RawActivityLog.objects.filter(pk=log.pk).update(occurred_at=occurred)
        return log

    def test_calories_window_sums_both_sources_and_excludes_old(self):
        self._endurance_log(self.user, 600)          # in window
        self._cardio_log(self.user, 250)             # in window
        self._endurance_log(self.user, 999, days_ago=31)  # outside 30d window
        self.assertEqual(calories_burned_in_window(self.user, 30), 850)

    def test_only_one_active_challenge(self):
        second = Challenge.objects.create(
            slug="new_challenge", name="New", is_active=True
        )
        self.challenge.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(self.challenge.is_active)
        self.assertTrue(second.is_active)
        self.assertEqual(Challenge.objects.filter(is_active=True).count(), 1)

    def test_challenge_state_orders_and_marks_you(self):
        rival = User.objects.create_user(username="rival2", password="pw")
        self._endurance_log(self.user, 6320)
        self._endurance_log(rival, 1200)
        body = challenge_state(self.user)
        self.assertEqual(body["challenge"]["slug"], "calories_burned_30d")
        self.assertEqual(body["challenge"]["unit"], "kcal")
        self.assertEqual(body["my_progress"], 6320)
        board = body["leaderboard"]
        self.assertEqual(board[0]["username"], "burner")
        self.assertEqual(board[0]["rank"], 1)
        self.assertTrue(board[0]["is_you"])
        self.assertEqual(board[1]["username"], "rival2")
        self.assertEqual(board[1]["progress"], 1200)

    def test_challenge_state_without_active_challenge(self):
        Challenge.objects.filter(pk=self.challenge.pk).update(is_active=False)
        body = challenge_state(self.user)
        self.assertIsNone(body["challenge"])
        self.assertEqual(body["leaderboard"], [])


class SocialFlowTests(TestCase):
    def setUp(self):
        self.a = User.objects.create_user(username="alpha", password="pw")
        self.b = User.objects.create_user(username="beta", password="pw")
        self.c = User.objects.create_user(username="gamma", password="pw")

    def _make_friends(self, a, b):
        ok, _ = send_friend_request(a, b.username)
        self.assertTrue(ok)
        ok, _ = respond_friend_request(b, a.pk, accept=True)
        self.assertTrue(ok)

    # ---- Friends ----
    def test_request_accept_makes_friends_both_sides(self):
        ok, _ = send_friend_request(self.a, "beta")
        self.assertTrue(ok)
        self.assertEqual([u.username for u in friends_of(self.a)], [])
        ok, _ = respond_friend_request(self.b, self.a.pk, accept=True)
        self.assertTrue(ok)
        self.assertEqual([u.username for u in friends_of(self.a)], ["beta"])
        self.assertEqual([u.username for u in friends_of(self.b)], ["alpha"])

    def test_reverse_pending_auto_accepts(self):
        send_friend_request(self.a, "beta")
        ok, friendship = send_friend_request(self.b, "alpha")
        self.assertTrue(ok)
        self.assertEqual(friendship.status, Friendship.Status.ACCEPTED)
        self.assertEqual(len(friends_of(self.a)), 1)

    def test_decline_removes_request(self):
        send_friend_request(self.a, "beta")
        ok, _ = respond_friend_request(self.b, self.a.pk, accept=False)
        self.assertTrue(ok)
        self.assertEqual(Friendship.objects.count(), 0)

    def test_self_and_duplicate_requests_rejected(self):
        ok, err = send_friend_request(self.a, "alpha")
        self.assertFalse(ok)
        self.assertEqual(err["status"], 400)
        send_friend_request(self.a, "beta")
        ok, err = send_friend_request(self.a, "beta")
        self.assertFalse(ok)
        ok, err = send_friend_request(self.a, "ghost")
        self.assertFalse(ok)
        self.assertEqual(err["status"], 404)

    def test_remove_friend(self):
        from core.services.social import remove_friend

        self._make_friends(self.a, self.b)
        ok, _ = remove_friend(self.a, self.b.pk)
        self.assertTrue(ok)
        self.assertEqual(friends_of(self.a), [])
        ok, err = remove_friend(self.a, self.b.pk)
        self.assertFalse(ok)
        self.assertEqual(err["status"], 404)

    def test_search_excludes_self_and_tags_relationships(self):
        self._make_friends(self.a, self.b)
        send_friend_request(self.a, "gamma")
        results = {r["username"]: r["relationship"] for r in search_users("a", self.a)}
        self.assertNotIn("alpha", results)  # never yourself
        self.assertEqual(results["beta"], "friends")
        self.assertEqual(results["gamma"], "pending_out")

    # ---- Flocks ----
    def test_create_flock_and_owner_role(self):
        ok, flock = create_flock(self.a, "Beach Squad")
        self.assertTrue(ok)
        membership = FlockMembership.objects.get(user=self.a)
        self.assertEqual(membership.role, "owner")
        self.assertEqual(membership.flock, flock)
        ok, err = create_flock(self.a, "Another")
        self.assertFalse(ok)  # already in a flock
        ok, err = create_flock(self.b, "   ")
        self.assertFalse(ok)  # blank name

    def test_invite_requires_owner_and_friend(self):
        create_flock(self.a, "Beach Squad")
        ok, err = invite_to_flock(self.a, self.b.pk)
        self.assertFalse(ok)  # not friends yet
        self._make_friends(self.a, self.b)
        ok, invite = invite_to_flock(self.a, self.b.pk)
        self.assertTrue(ok)
        self.assertEqual(invite.status, FlockInvite.Status.PENDING)
        # A member (non-owner) cannot invite.
        respond_flock_invite(self.b, invite.flock_id, accept=True)
        ok, err = invite_to_flock(self.b, self.c.pk)
        self.assertFalse(ok)

    def test_accept_invite_capacity_enforced(self):
        create_flock(self.a, "Big Flock")
        flock = Flock.objects.first()
        # Fill the flock to capacity (owner + 7 members).
        for i in range(FLOCK_MAX_MEMBERS - 1):
            user = User.objects.create_user(username="m%d" % i, password="pw")
            self._make_friends(self.a, user)
            invite_to_flock(self.a, user.pk)
            ok, _ = respond_flock_invite(user, flock.pk, accept=True)
            self.assertTrue(ok)
        self.assertEqual(flock.memberships.count(), FLOCK_MAX_MEMBERS)
        # The 9th person cannot join.
        self._make_friends(self.a, self.b)
        invite_to_flock(self.a, self.b.pk)
        ok, err = respond_flock_invite(self.b, flock.pk, accept=True)
        self.assertFalse(ok)
        self.assertIn("full", err["message"].lower())

    def test_last_member_leaving_deletes_flock(self):
        create_flock(self.a, "Solo Flock")
        flock_pk = Flock.objects.first().pk
        ok, _ = leave_flock(self.a)
        self.assertTrue(ok)
        self.assertFalse(Flock.objects.filter(pk=flock_pk).exists())
        ok, err = leave_flock(self.a)
        self.assertFalse(ok)

    def test_flock_weekly_standings_order(self):
        from core.services.social import flock_weekly_standings

        create_flock(self.a, "XP Racers")
        self._make_friends(self.a, self.b)
        invite_to_flock(self.a, self.b.pk)
        respond_flock_invite(self.b, Flock.objects.first().pk, accept=True)
        XPLedger.objects.create(user=self.b, modality="endurance", amount=90)
        XPLedger.objects.create(user=self.a, modality="endurance", amount=40)
        standings = flock_weekly_standings(Flock.objects.first())
        self.assertEqual([m["username"] for m in standings], ["beta", "alpha"])
        self.assertEqual(standings[0]["weekly_xp"], 90)

    def test_social_state_shape(self):
        self._make_friends(self.a, self.b)
        create_flock(self.a, "Fam")
        invite_to_flock(self.a, self.b.pk)
        body = social_state(self.b, q="alp")
        self.assertEqual(
            set(body),
            {
                "friends", "incoming_requests", "outgoing_requests",
                "flock", "flock_invites", "search_results",
            },
        )
        self.assertEqual(body["friends"][0]["username"], "alpha")
        self.assertEqual(len(body["flock_invites"]), 1)
        self.assertEqual(body["flock_invites"][0]["name"], "Fam")
        self.assertEqual(body["search_results"][0]["relationship"], "friends")


class Phase8APITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="social8", password="pw")
        self.other = User.objects.create_user(username="other8", password="pw")
        self.client.login(username="social8", password="pw")

    # ---- GET endpoints ----
    def test_get_endpoints_require_login(self):
        self.client.logout()
        for url in ("/leagues/", "/challenges/", "/social/"):
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 302, url)

    def test_leagues_shape(self):
        resp = self.client.get("/leagues/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(
            set(body),
            {"week", "tiers", "my_tier", "my_rank", "leaderboard", "history"},
        )
        self.assertEqual(body["week"]["status"], "open")
        self.assertTrue(any(row["is_you"] for row in body["leaderboard"]))

    def test_challenges_shape_with_seeded_default(self):
        Challenge.objects.create(
            slug="calories_burned_30d", name="Calorie Torch",
            metric=Challenge.Metric.CALORIES_BURNED, window_days=30,
            is_active=True,
        )
        resp = self.client.get("/challenges/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["challenge"]["slug"], "calories_burned_30d")
        self.assertEqual(body["challenge"]["window_days"], 30)
        self.assertEqual(body["my_progress"], 0)
        self.assertTrue(any(row["is_you"] for row in body["leaderboard"]))

    def test_social_shape(self):
        resp = self.client.get("/social/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(
            set(body),
            {
                "friends", "incoming_requests", "outgoing_requests",
                "flock", "flock_invites", "search_results",
            },
        )
        self.assertIsNone(body["flock"])
        self.assertEqual(body["search_results"], [])

    # ---- Friend POSTs ----
    def test_friends_request_and_accept_flow(self):
        resp = self.client.post(
            "/friends/request", data={"username": "other8"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["outgoing_requests"][0]["username"], "other8")

        # Log in as the recipient and accept.
        self.client.login(username="other8", password="pw")
        resp = self.client.post(
            "/friends/respond",
            data={"user_id": self.user.pk, "action": "accept"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["friends"][0]["username"], "social8")

    def test_friends_request_unknown_username_404(self):
        resp = self.client.post(
            "/friends/request", data={"username": "ghost"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 404)
        self.assertIn("error", resp.json())

    def test_friends_respond_bad_action_400(self):
        resp = self.client.post(
            "/friends/respond", data={"user_id": 1, "action": "maybe"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    # ---- Flock POSTs ----
    def test_flocks_create_invite_respond_leave_flow(self):
        resp = self.client.post(
            "/flocks/create", data={"name": "Beach Squad"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["flock"]["name"], "Beach Squad")
        self.assertEqual(body["flock"]["my_role"], "owner")

        # Become friends, then invite.
        send_friend_request(self.user, "other8")
        respond_friend_request(self.other, self.user.pk, accept=True)
        resp = self.client.post(
            "/flocks/invite", data={"user_id": self.other.pk},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)

        # Recipient accepts.
        flock_id = Flock.objects.get(name="Beach Squad").pk
        self.client.login(username="other8", password="pw")
        resp = self.client.post(
            "/flocks/respond",
            data={"flock_id": flock_id, "action": "accept"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["flock"]["member_count"], 2)

        # Leaving drops back to no flock.
        resp = self.client.post("/flocks/leave", data={}, content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()["flock"])

    def test_flocks_create_400_when_already_in_flock(self):
        create_flock(self.user, "First")
        resp = self.client.post(
            "/flocks/create", data={"name": "Second"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_invite_non_friend_400(self):
        create_flock(self.user, "First")
        resp = self.client.post(
            "/flocks/invite", data={"user_id": self.other.pk},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def _make_friends_with_other(self):
        send_friend_request(self.user, "other8")
        respond_friend_request(self.other, self.user.pk, accept=True)

    # ---- CSRF ----
    def test_csrf_403_without_token(self):
        from django.test import Client

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.login(username="social8", password="pw")
        resp = csrf_client.post(
            "/friends/request", data={"username": "other8"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)


class AvatarUploadTests(TestCase):
    """Profile-picture uploads (docs/13 UI tune-up)."""

    UPLOAD_URL = "/api/v1/profile/avatar"

    def setUp(self):
        self.user = User.objects.create_user(username="avater", password="pw")
        self.client.login(username="avater", password="pw")

    def _png(self, size=64):
        from django.core.files.uploadedfile import SimpleUploadedFile

        # PNG magic bytes (what the service sniffs) + padding payload.
        return SimpleUploadedFile(
            "me.png", b"\x89PNG\r\n\x1a\n" + (b"\x00" * size),
            content_type="image/png",
        )

    def test_upload_success(self):
        resp = self.client.post(self.UPLOAD_URL, {"avatar": self._png()})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ok"])
        self.user.refresh_from_db()
        self.assertTrue(self.user.avatar.startswith("/media/avatars/"))
        self.assertEqual(body["avatar"], self.user.avatar)

    def test_upload_rejects_non_image(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        fake = SimpleUploadedFile(
            "note.txt", b"hello world - definitely not an image",
            content_type="text/plain",
        )
        resp = self.client.post(self.UPLOAD_URL, {"avatar": fake})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.json())
        self.user.refresh_from_db()
        self.assertNotIn("/media/", self.user.avatar)

    def test_upload_requires_a_file(self):
        resp = self.client.post(self.UPLOAD_URL, {})
        self.assertEqual(resp.status_code, 400)

    def test_reset_restores_default(self):
        self.user.avatar = "/media/avatars/1_stale.png"
        self.user.save()
        resp = self.client.post(self.UPLOAD_URL, {"action": "reset"})
        self.assertEqual(resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertIn("dicebear", self.user.avatar)

    def test_upload_requires_login(self):
        self.client.logout()
        resp = self.client.post(self.UPLOAD_URL, {"avatar": self._png()})
        self.assertEqual(resp.status_code, 302)

    def test_csrf_403_without_token_on_upload(self):
        from django.test import Client

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        resp = csrf_client.post(self.UPLOAD_URL, {"avatar": self._png()})
        self.assertEqual(resp.status_code, 403)

    def test_dashboard_state_exposes_avatar(self):
        resp = self.client.get("/api/v1/dashboard/state")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("avatar", resp.json()["user"])
        self.assertIn("dicebear", resp.json()["user"]["avatar"])


class MediaServingWhiteNoiseTests(SimpleTestCase):
    """Media-serving WhiteNoise middleware unit tests."""

    def test_post_startup_avatar_is_served_by_media_middleware(self):
        """Freshly uploaded avatars must not fall through WhiteNoise's index.

        MediaServingWhiteNoise resolves /media/* from the filesystem per request
        instead of WhiteNoise's startup-time snapshot, so a picture saved after
        the server booted returns 200 instead of 404 (which would otherwise let
        the frontend's onerror handler silently swap it back to the default).
        """
        import tempfile
        from pathlib import Path

        from django.http import HttpResponse
        from django.test import RequestFactory, override_settings

        from flamingo_fitness.whitenoise import MediaServingWhiteNoise

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            avatars = Path(tmp) / "avatars"
            avatars.mkdir()
            with override_settings(MEDIA_ROOT=tmp):
                # Upload happens long after the server started: build the
                # middleware first, then write the file to disk.
                middleware = MediaServingWhiteNoise(
                    lambda request: HttpResponse("passthrough")
                )
                name = "42_after_boot.png"
                payload = b"\x89PNG\r\n\x1a\n" + (b"\x00" * 16)
                (avatars / name).write_bytes(payload)

                url = "/media/avatars/" + name
                # find_file() is the disk-backed resolver used for /media/*.
                self.assertIsNotNone(middleware.find_file(url))

                resp = middleware(RequestFactory().get(url))
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(b"".join(resp.streaming_content), payload)
                # Release the streaming file handle before the temp dir is
                # removed (Windows holds an open handle and would block cleanup).
                resp.close()


class AuthCookieSchemeTests(TestCase):
    """Secure cookie flags must follow the request scheme.

    DEBUG=False sets CSRF_COOKIE_SECURE / SESSION_COOKIE_SECURE to True, which
    breaks the plain-HTTP LAN install: browsers refuse to send Secure cookies
    over http:// so the login POST returns 403 (CSRF) and the dashboard never
    loads. SchemeAwareSecureCookiesMiddleware rewrites the flags per request.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="securecookie", password="securecookie-pass"
        )

    def test_login_over_plain_http_loads_dashboard(self):
        import re

        from django.conf import settings as django_settings
        from django.test import Client

        # enforce_csrf_checks=True mimics a real browser: without a usable CSRF
        # cookie + token the POST would be rejected with 403.
        client = Client(enforce_csrf_checks=True)
        login_page = client.get("/login/")
        self.assertEqual(login_page.status_code, 200)

        csrf_cookie = login_page.cookies[django_settings.CSRF_COOKIE_NAME]
        self.assertFalse(
            csrf_cookie["secure"],
            "CSRF cookie must NOT be Secure over plain HTTP or browsers drop it",
        )

        token = re.search(
            r'name="csrfmiddlewaretoken" value="([^"]+)"',
            login_page.content.decode("utf-8"),
        ).group(1)
        resp = client.post(
            "/login/",
            {
                "csrfmiddlewaretoken": token,
                "username": "securecookie",
                "password": "securecookie-pass",
                "next": "/",
            },
            HTTP_REFERER="http://testserver/login/",
        )
        self.assertEqual(resp.status_code, 302, "login must redirect to the dashboard")
        self.assertEqual(resp.url, "/")
        self.assertTrue(client.session.get("_auth_user_id"))

        session_cookie = resp.cookies[django_settings.SESSION_COOKIE_NAME]
        self.assertFalse(session_cookie["secure"])

        # Follow-up requests over http must stay authenticated.
        dashboard = client.get("/")
        self.assertEqual(dashboard.status_code, 200)

    def test_auth_cookies_stay_secure_over_https(self):
        from django.conf import settings as django_settings
        from django.test import Client

        client = Client(secure=True)
        resp = client.get("/login/", HTTP_X_FORWARDED_PROTO="https")
        self.assertEqual(resp.status_code, 200)
        csrf_cookie = resp.cookies[django_settings.CSRF_COOKIE_NAME]
        self.assertTrue(
            csrf_cookie["secure"],
            "CSRF cookie must stay Secure over HTTPS (Cloudflare tunnel)",
        )
# ---------------------------------------------------------------------------
# Phase 9 (docs/15): Token, Gacha & Battle (replaces the base meta-game)
# ---------------------------------------------------------------------------
class CombatEconomyMathTests(SimpleTestCase):
    def test_rarity_weights_shift_with_streak(self):
        from core.services.combat import rarity_weights

        base = rarity_weights(0)
        long = rarity_weights(30)
        self.assertGreater(long['legendary'], base['legendary'])
        self.assertGreater(long['epic'], base['epic'])
        self.assertLess(long['common'], base['common'])

    def test_rarity_weights_total_preserved(self):
        from core.services.combat import rarity_weights

        for streak in (0, 7, 15, 40):
            w = rarity_weights(streak)
            total = sum(w[r] for r in w)
            self.assertAlmostEqual(total, 100.0, delta=0.001)

    def test_open_pack_dynamic_rarity_pick_obeys_rng(self):
        from core.services.combat import _pick_rarity

        # rng always rolls near 0 -> picks the lowest (common) bucket.
        picked = _pick_rarity({'common': 60, 'rare': 28, 'epic': 10, 'legendary': 2}, lambda: 0.01)
        self.assertEqual(picked, 'common')


class TokenEconomyFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tokenuser", password="pw", streak=5)

    def test_daily_token_harvest_is_idempotent(self):
        from core.services.combat import daily_token_harvest, profile

        XPLedger.objects.create(user=self.user, modality=Modality.ENDURANCE, amount=120)
        p = profile(self.user)
        before = p.tokens
        minted = daily_token_harvest(self.user, on_date=timezone.localdate())
        # streak 5 -> multiplier 1.25; 120 XP / 10 = 12 * 1.25 = 15.
        self.assertEqual(minted, 15)
        self.assertEqual(profile(self.user).tokens, before + 15)
        # Same date re-run mints nothing.
        self.assertEqual(daily_token_harvest(self.user, on_date=timezone.localdate()), 0)

    def test_perfect_macro_awards_tokens(self):
        from core.services.combat import profile

        user2 = User.objects.create_user(username="tokenuser2", password="pw")
        log = RawActivityLog.objects.create(
            user=user2, source=Provider.SPARKYFITNESS, event_type="nutrition",
            payload={"date": timezone.localdate().isoformat(),
                     "food_entries": [{"protein": 200, "calories": 100}],
                     "goals": {"protein": 150, "calories": 2000}},
        )
        process_log(log)
        self.assertEqual(profile(user2).tokens, 300 + 25)


class GachaFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="gachauser", password="pw")
        self.pack = GearPackDef.objects.create(
            slug="test_pack", name="Test Pack", price_tokens=100, draws=2,
            domains=[], guaranteed_min_rarity="common",
        )
        self.gear = GearItemDef.objects.create(
            slug="test_sword", name="Test Sword", rarity="common",
            effect_type="domain_multiplier", effect_domain="strength",
            effect_value=1.5, pack=self.pack, weight=100,
        )

    def test_open_pack_spends_tokens_and_grants_draws(self):
        from core.services.combat import open_pack, profile

        p = profile(self.user)
        self.assertEqual(p.tokens, 300)
        ok, err, manifest = open_pack(self.user, self.pack, rng=lambda: 0.01)
        self.assertTrue(ok, err)
        self.assertEqual(len(manifest), 2)  # pack.draws
        p.refresh_from_db()
        self.assertEqual(p.tokens, 200)  # 300 - 100
        self.assertEqual(UserGear.objects.filter(user=self.user).count(), 2)

    def test_open_pack_insufficient_tokens(self):
        from core.services.combat import open_pack, profile

        p = profile(self.user)
        p.tokens = 50
        p.save()
        ok, err, _ = open_pack(self.user, self.pack)
        self.assertFalse(ok)
        self.assertIn("tokens", err)

class BattleFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="battler", password="pw")
        self.boss = CampaignBoss.objects.create(
            campaign="strength", slug="test_boss", name="Test Boss",
            hp_total=100000, element="strength", weaknesses=[], resistances=[],
        )

    def test_engage_and_attack_decrement_stamina_and_log(self):
        from core.services.combat import attack_boss, engage_boss

        engage_boss(self.user, "strength", on_date=timezone.localdate())
        result, err = attack_boss(self.user, "strength", on_date=timezone.localdate())
        self.assertIsNone(err)
        self.assertEqual(result["stamina_left"], 2)  # 3 - 1
        self.assertTrue(BattleLog.objects.filter(user=self.user, campaign="strength").exists())
        prog = CampaignProgress.objects.get(user=self.user, campaign="strength")
        self.assertFalse(prog.conquered)
        self.assertLessEqual(prog.damage_dealt, prog.total_hp)

    def test_attack_without_stamina_errors(self):
        from core.services.combat import attack_boss, engage_boss, profile

        engage_boss(self.user, "strength", on_date=timezone.localdate())
        p = profile(self.user)
        # Mark stamina as already-refreshed today so the daily refill is skipped
        # and the spend guard actually trips for the rest of the day.
        p.stamina = 0
        p.stamina_updated_at = timezone.now()
        p.save()
        result, err = attack_boss(self.user, "strength", on_date=timezone.localdate())
        self.assertIsNone(result)
        self.assertIn("stamina", err)


class SiegeRankingTests(TestCase):
    """docs/17 #33 (per-campaign siege leaderboard) + #34 (siege kill timeline).

    The leaderboard aggregates BattleLog.total_damage against a specific boss
    among the requester's friends/flock; the diary derives per-boss halved +
    conquered milestones. Both only surface attacks attributed to a boss.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="sieger", password="pw")
        self.friend = User.objects.create_user(username="sieger_friend", password="pw")
        self.stranger = User.objects.create_user(username="sieger_stranger", password="pw")
        Friendship.objects.create(
            from_user=self.user, to_user=self.friend, status="accepted"
        )
        self.boss = CampaignBoss.objects.create(
            campaign="strength", slug="rank_boss", name="Rank Boss",
            hp_total=1000, element="strength", weaknesses=[], resistances=[],
        )

    def _log(self, user, damage, tokens=0, boss=None):
        return BattleLog.objects.create(
            user=user, campaign="strength", boss=boss or self.boss,
            date=timezone.localdate(), total_damage=damage, tokens_won=tokens,
        )

    def test_leaderboard_ranks_friends_and_self_excludes_strangers(self):
        self._log(self.user, 500)
        self._log(self.friend, 700)
        self._log(self.stranger, 900)  # not a friend / not in scope

        resp = self.client.force_login(self.user)
        resp = self.client.get("/api/v1/battle/leaderboard/strength/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        names = [r["username"] for r in body["leaderboard"]]
        self.assertEqual(names, ["sieger_friend", "sieger"])
        self.assertNotIn("sieger_stranger", names)
        self.assertEqual(body["leaderboard"][0]["damage"], 700)
        self.assertEqual(body["my_rank"], 2)
        self.assertEqual(body["my_damage"], 500)

    def test_history_reports_halved_and_conquered(self):
        self._log(self.user, 400)
        self._log(self.user, 400)
        self._log(self.user, 300, tokens=150)  # killing blow on the last attack

        resp = self.client.force_login(self.user)
        resp = self.client.get("/api/v1/battle/history/strength/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(len(body["bosses"]), 1)
        boss = body["bosses"][0]
        self.assertEqual(boss["name"], "Rank Boss")
        self.assertTrue(boss["halved"])
        self.assertTrue(boss["conquered"])
        self.assertEqual(boss["total_damage"], 1100)
        self.assertEqual(len(boss["attacks"]), 3)

    def test_history_skips_unattributed_rows(self):
        # A legacy attack with no boss FK must not contaminate the diary.
        BattleLog.objects.create(
            user=self.user, campaign="strength", boss=None,
            date=timezone.localdate(), total_damage=999,
        )
        resp = self.client.force_login(self.user)
        resp = self.client.get("/api/v1/battle/history/strength/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["bosses"], [])

    def test_leaderboard_auth_and_invalid_campaign(self):
        self.assertEqual(self.client.get("/api/v1/battle/leaderboard/strength/").status_code, 302)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get("/api/v1/battle/leaderboard/bogus/").status_code, 400)
        self.assertEqual(self.client.get("/api/v1/battle/history/bogus/").status_code, 400)


class PvPFlowTests(TestCase):
    def setUp(self):
        self.attacker = User.objects.create_user(username="pvpatk", password="pw")
        self.defender = User.objects.create_user(username="pvpdef", password="pw")

    def test_set_defense_and_attack_resolution(self):
        from core.services.combat import attack_gym, set_defense

        set_defense(self.defender, terrain="strength", name="Defender Gym")
        gym = Gym.objects.get(owner=self.defender)
        self.assertTrue(gym.defense_snapshot)

        result, err = attack_gym(self.attacker, gym)
        self.assertIsNone(err)
        self.assertIn("did_win", result)
        self.assertIn("winner", result)
        self.assertTrue(PvPMatch.objects.filter(attacker=self.attacker, gym=gym).exists())

class CombatAPITests(TestCase):
    """Walk the Phase 9 endpoints (docs/15 §6) happy paths + CSRF-403."""

    def setUp(self):
        self.user = User.objects.create_user(username="combatapi", password="pw")
        self.client.login(username="combatapi", password="pw")
        self.pack = GearPackDef.objects.create(
            slug="api_pack", name="API Pack", price_tokens=100, draws=1,
            domains=[], guaranteed_min_rarity="common",
        )
        GearItemDef.objects.create(
            slug="api_blade", name="API Blade", rarity="common",
            effect_type="domain_multiplier", effect_domain="strength",
            effect_value=1.5, pack=self.pack, weight=100,
        )
        CampaignBoss.objects.create(
            campaign="strength", slug="api_boss", name="API Boss",
            hp_total=50000, element="strength", weaknesses=[], resistances=[],
        )

    def test_state_endpoints_require_login(self):
        self.client.logout()
        for url in ("/battle/state", "/shop/state", "/loadout/state", "/pvp/state"):
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 302, url)

    def test_state_endpoint_shapes(self):
        resp = self.client.get("/battle/state")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("campaigns", resp.json())
        self.assertIn("wallet", resp.json())

        resp = self.client.get("/shop/state")
        body = resp.json()
        self.assertIn("packs", body)
        self.assertIn("owned", body)
        self.assertTrue(body["packs"])

        resp = self.client.get("/loadout/state")
        self.assertIn("equipped", resp.json())

        resp = self.client.get("/pvp/state")
        self.assertIn("attackable", resp.json())

    def test_shop_open_flow(self):
        resp = self.client.post(
            "/shop/open", data={"pack_slug": "api_pack"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertEqual(len(body["manifest"]), 1)

    def test_battle_engage_and_attack_flow(self):
        resp = self.client.post(
            "/battle/engage", data={"campaign": "strength"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])

        resp = self.client.post(
            "/battle/attack", data={"campaign": "strength"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertIn("total_damage", body)
        self.assertIn("stamina_left", body)

    def test_mutations_require_csrf(self):
        from django.test import Client

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.login(username="combatapi", password="pw")
        resp = csrf_client.post(
            "/shop/open", data={"pack_slug": "api_pack"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)

class ScrapAndEffectTests(TestCase):
    """Phase 10 (docs/16): new item effect types + the scrap economy."""

    def setUp(self):
        from core.services.combat import profile

        self.user = User.objects.create_user(username="gearuser", password="pw")
        self.profile = profile(self.user)
        self.client.login(username="gearuser", password="pw")

    def _give_gear(self, equipped_slot=None, quantity=1, **kw):
        gd = GearItemDef.objects.create(**kw)
        return UserGear.objects.create(
            user=self.user, gear_def=gd, rarity=kw.get("rarity", "common"),
            equipped_slot=equipped_slot, quantity=quantity,
        )

    # --- New item types ---
    def test_flat_bonus_adds_flat_damage_to_one_domain(self):
        from core.services.combat import additive_bonus

        ug = self._give_gear(
            slug="flat_cardio", name="Flat Cardio", slot="head", rarity="rare",
            effect_type="flat_bonus", effect_domain="cardio", effect_value=50,
        )
        self.assertEqual(additive_bonus(self.profile, self.user, "cardio"), 0.0)
        ug.equipped_slot = "head"
        ug.save(update_fields=["equipped_slot"])
        self.assertEqual(additive_bonus(self.profile, self.user, "cardio"), 50.0)
        self.assertEqual(additive_bonus(self.profile, self.user, "strength"), 0.0)

    def test_scales_with_another_domain(self):
        from core.services.combat import additive_bonus, base_damage_for

        RawActivityLog.objects.create(
            user=self.user, source=Provider.LIFTOSAUR, event_type="strength",
            payload={"total_volume_lbs": 60000}, occurred_at=timezone.now(),
        )
        self._give_gear(
            slug="crossband", name="Cross Band", slot="right_hand", rarity="rare",
            effect_type="scales_with", effect_domain="cardio", effect_value=0.25,
            effect_params={"scales_from": "strength"}, equipped_slot="right_hand",
        )
        base_strength = base_damage_for("strength", self.user)
        self.assertGreater(base_strength, 0)
        # Cardio gains 25% of the strength base damage as flat bonus.
        self.assertAlmostEqual(
            additive_bonus(self.profile, self.user, "cardio"), 0.25 * base_strength
        )

    def test_scales_with_streak(self):
        from core.services.combat import additive_bonus

        self.user.streak = 10
        self.user.save(update_fields=["streak"])
        self._give_gear(
            slug="streakshoes", name="Streak Shoes", slot="feet", rarity="epic",
            effect_type="scales_with", effect_domain="cardio", effect_value=2,
            effect_params={"scales_from": "streak"}, equipped_slot="feet",
        )
        self.assertEqual(additive_bonus(self.profile, self.user, "cardio"), 20.0)

    def test_stamina_cap_raises_cap_and_refill(self):
        from core.services.combat import refresh_stamina, stamina_cap

        self._give_gear(
            slug="anklets", name="Anklets", slot="feet", rarity="rare",
            effect_type="stamina_cap", effect_value=1, equipped_slot="feet",
        )
        self.assertEqual(stamina_cap(self.profile, self.user), 4)  # 3 + 1
        self.profile.stamina = 0
        self.profile.stamina_updated_at = None
        self.profile.save(update_fields=["stamina", "stamina_updated_at"])
        refresh_stamina(self.profile, self.user)
        self.assertEqual(self.profile.stamina, 4)


    def test_token_multiplier_boosts_dividend(self):
        from core.services.combat import daily_token_harvest, token_dividend_multiplier

        self._give_gear(
            slug="ledger", name="Ledger", slot="accessory", rarity="epic",
            effect_type="token_multiplier", effect_value=1.5, equipped_slot="accessory",
        )
        self.assertEqual(token_dividend_multiplier(self.profile, self.user), 1.5)
        XPLedger.objects.create(user=self.user, modality=Modality.ENDURANCE, amount=120)
        # streak 0 -> x1; (120/10)=12 * 1.5 = 18
        minted = daily_token_harvest(self.user, on_date=timezone.localdate())
        self.assertEqual(minted, 18)

    def test_stamina_refund_consumable(self):
        from core.services.combat import consume_consumable

        self.profile.stamina = 0
        self.profile.save(update_fields=["stamina"])
        ug = self._give_gear(
            slug="adrenaline", name="Adrenaline", slot="", rarity="rare",
            effect_type="stamina_refund", effect_value=2, is_consumable=True,
            max_stack=9, quantity=1,
        )
        ok, err = consume_consumable(self.profile, self.user, ug.pk)
        self.assertTrue(ok, err)
        self.assertEqual(self.profile.stamina, 2)
        self.assertFalse(UserGear.objects.filter(pk=ug.pk).exists())

    def test_grant_tokens_consumable(self):
        from core.services.combat import consume_consumable

        before = self.profile.tokens
        ug = self._give_gear(
            slug="coinopener", name="Coin Opener", slot="", rarity="epic",
            effect_type="grant_tokens", effect_value=50, is_consumable=True,
            max_stack=9,
        )
        ok, err = consume_consumable(self.profile, self.user, ug.pk)
        self.assertTrue(ok, err)
        self.assertEqual(self.profile.tokens, before + 50)

    # --- Scrap economy ---
    def test_recycle_gear_credits_scraps_by_rarity(self):
        from core.services.combat import recycle_gear, scrap_value

        self.assertEqual(scrap_value("rare"), 15)
        ug = self._give_gear(
            slug="junk", name="Junk", slot="head", rarity="rare",
            effect_type="domain_multiplier", effect_domain="cardio",
            effect_value=1.0, quantity=3,
        )
        ok, err, gain = recycle_gear(self.user, ug.pk, 2)
        self.assertTrue(ok, err)
        self.assertEqual(gain, 30)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.scraps, 30)
        ug.refresh_from_db()
        self.assertEqual(ug.quantity, 1)

        ok, err, gain = recycle_gear(self.user, ug.pk, 1)
        self.assertTrue(ok, err)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.scraps, 45)
        self.assertFalse(UserGear.objects.filter(pk=ug.pk).exists())

    def test_scrap_shop_state_filters_by_weekday(self):
        today = timezone.localdate().weekday()
        other = (today + 1) % 7
        ScrapShopItem.objects.create(
            slug="today_deal", name="Today Deal", cost_scraps=10,
            available_days=[today], reward_type="tokens", reward_value=40,
        )
        ScrapShopItem.objects.create(
            slug="other_deal", name="Other Deal", cost_scraps=10,
            available_days=[other], reward_type="stamina", reward_value=1,
        )
        body = self.client.get("/scrap/shop/state").json()
        slugs = [i["slug"] for i in body["scrap_shop"]["offering"]]
        self.assertIn("today_deal", slugs)
        self.assertNotIn("other_deal", slugs)

    def test_buy_scrap_item_grants_tokens_and_deducts(self):
        from core.services.combat import buy_scrap_item

        today = timezone.localdate().weekday()
        ScrapShopItem.objects.create(
            slug="tokdeal", name="Token Deal", cost_scraps=20,
            available_days=[today], reward_type="tokens", reward_value=40,
        )
        self.profile.scraps = 50
        self.profile.save(update_fields=["scraps"])
        before = self.profile.tokens
        result, err = buy_scrap_item(self.user, "tokdeal")
        self.assertIsNone(err)
        self.assertEqual(result["tokens"], 40)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.scraps, 30)
        self.assertEqual(self.profile.tokens, before + 40)

    def test_scrap_recycle_endpoint(self):
        ug = self._give_gear(
            slug="junk2", name="Junk2", slot="head", rarity="common",
            effect_type="domain_multiplier", effect_domain="strength", effect_value=1.0,
        )
        resp = self.client.post(
            "/scrap/recycle", data={"gear_id": ug.pk, "quantity": 1},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["scraps_gained"], 5)
        self.assertFalse(UserGear.objects.filter(pk=ug.pk).exists())

    def test_loadout_state_reports_scrap_values(self):
        # Armor surfaced in the Loadout panel carries scrap info so the UI can
        # offer a recycle action on owned, unequipped gear.
        self._give_gear(
            slug="scrapcar", name="Scrap Car", slot="head", rarity="epic",
            effect_type="domain_multiplier", effect_domain="cardio",
            effect_value=1.2, quantity=2,
        )
        resp = self.client.get("/loadout/state")
        body = resp.json()
        owned = body.get("owned") or []
        match = next((o for o in owned if o["slug"] == "scrapcar"), None)
        self.assertIsNotNone(match)
        self.assertEqual(match["scrap_value"], 40)      # epic
        self.assertEqual(match["total_scraps"], 80)     # 40 * 2
        self.assertEqual(body["wallet"]["scraps"], self.profile.scraps)


class PvEDailyStatDamageTests(TestCase):
    """Tests for PvE campaign damage calculations powered by daily tracked stats."""

    def setUp(self):
        from core.services.combat import profile

        self.user = User.objects.create_user(username="pve_tester", password="pw")
        self.client.login(username="pve_tester", password="pw")
        self.profile = profile(self.user)
        self.today = timezone.localdate()

    def test_cardio_damage_aggregation(self):
        from core.services.combat import base_damage_for

        # Two cardio logs today: 300 cal and 250 cal = 550 cal -> 55 damage
        RawActivityLog.objects.create(
            user=self.user,
            source=Provider.GARMIN,
            event_type="endurance",
            payload={"date": str(self.today), "total_calories_burned": 300.0, "total_duration_minutes": 30},
            occurred_at=timezone.now(),
        )
        RawActivityLog.objects.create(
            user=self.user,
            source=Provider.PELOTON,
            event_type="cardio",
            payload={"date": str(self.today), "calories": 250.0, "duration": 25},
            occurred_at=timezone.now(),
        )
        dmg = base_damage_for(Campaign.CARDIO, self.user, on_date=self.today)
        self.assertEqual(dmg, 55)

    def test_strength_damage_aggregation(self):
        from core.services.combat import base_damage_for

        # Two strength sessions: 5,000 lbs and 3,500 lbs = 8,500 lbs -> 8 damage (round(8.5))
        RawActivityLog.objects.create(
            user=self.user,
            source=Provider.LIFTOSAUR,
            event_type="strength",
            payload={
                "date": str(self.today),
                "total_volume_lbs": 5000.0,
                "exercises": [{"name": "Squat", "reps": 5, "sets": 5, "weight": 200}],
            },
            occurred_at=timezone.now(),
        )
        RawActivityLog.objects.create(
            user=self.user,
            source=Provider.SPARKYFITNESS,
            event_type="weightlifting",
            payload={"date": str(self.today), "volume_lbs": 3500.0},
            occurred_at=timezone.now(),
        )
        dmg = base_damage_for(Campaign.STRENGTH, self.user, on_date=self.today)
        self.assertEqual(dmg, 8)

    def test_hydration_damage_aggregation_and_perfect_bonus(self):
        from core.services.combat import base_damage_for

        # Hydration under goal: 60 oz with goal 100 oz -> 6 damage
        RawActivityLog.objects.create(
            user=self.user,
            source=Provider.SPARKYFITNESS,
            event_type="hydration",
            payload={
                "date": str(self.today),
                "water_goal": 100.0,
                "water_intake_entries": [{"amount": 40.0}, {"amount": 20.0}],
            },
            occurred_at=timezone.now(),
        )
        dmg = base_damage_for(Campaign.HYDRATION, self.user, on_date=self.today)
        self.assertEqual(dmg, 6)

        # Add another 50 oz -> total 110 oz >= 100 oz goal -> 11 * 2 = 22 damage
        RawActivityLog.objects.create(
            user=self.user,
            source=Provider.GARMIN,
            event_type="water",
            payload={"date": str(self.today), "water_goal": 100.0, "amount": 50.0},
            occurred_at=timezone.now(),
        )
        dmg_perfect = base_damage_for(Campaign.HYDRATION, self.user, on_date=self.today)
        self.assertEqual(dmg_perfect, 22)

    def test_nutrition_damage_and_calorie_overage(self):
        from core.services.combat import base_damage_for, _is_over_calories

        # Nutrition: 120g protein with 150g goal, 1800 cals with 2000 goal
        RawActivityLog.objects.create(
            user=self.user,
            source=Provider.SPARKYFITNESS,
            event_type="nutrition",
            payload={
                "date": str(self.today),
                "goals": {"protein": 150.0, "calories": 2000.0},
                "food_entries": [
                    {"name": "Chicken", "protein": 90.0, "calories": 1200.0},
                    {"name": "Shake", "protein": 30.0, "calories": 600.0},
                ],
            },
            occurred_at=timezone.now(),
        )
        # Protein pct = 120/150 = 80% -> base damage = int(0.8 * (120 / 10)) = 9
        dmg = base_damage_for(Campaign.NUTRITION, self.user, on_date=self.today)
        self.assertEqual(dmg, 9)
        self.assertFalse(_is_over_calories(self.user, on_date=self.today))

        # Add food that pushes over calories -> 2300 cals > 2000 goal
        RawActivityLog.objects.create(
            user=self.user,
            source=Provider.GARMIN,
            event_type="food",
            payload={"date": str(self.today), "calories": 500.0, "protein": 10.0},
            occurred_at=timezone.now(),
        )
        self.assertTrue(_is_over_calories(self.user, on_date=self.today))

    def test_sleep_damage_calculation(self):
        from core.services.combat import base_damage_for

        RawActivityLog.objects.create(
            user=self.user,
            source=Provider.GARMIN,
            event_type="sleep",
            payload={"date": str(self.today), "sleep_hours": 8.0, "rem_pct": 20, "deep_pct": 20},
            occurred_at=timezone.now(),
        )
        dmg = base_damage_for(Campaign.SLEEP, self.user, on_date=self.today)
        self.assertEqual(dmg, 10)

    def test_campaign_api_includes_daily_base_damage(self):
        # Create cardio activity
        RawActivityLog.objects.create(
            user=self.user,
            source=Provider.GARMIN,
            event_type="endurance",
            payload={"date": str(self.today), "total_calories_burned": 500.0},
            occurred_at=timezone.now(),
        )
        resp = self.client.get("/api/v1/battle/campaign/cardio/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["today_base_damage"], 50)
        self.assertGreater(data["est_damage_per_attack"], 0)


class Phase9CleanupTests(TestCase):
    """Regression tests for the docs/15 cleanup: bulk discounts, generic crates
    and the loadout equip/unequip round-trip."""

    def setUp(self):
        self.user = User.objects.create_user(username="cleanup", password="pw")
        self.client.login(username="cleanup", password="pw")
        self.pack = GearPackDef.objects.create(
            slug="bulk_pack", name="Bulk Pack", price_tokens=100, draws=2,
            domains=[], guaranteed_min_rarity="common", sort_order=1,
        )
        for s in ("bulk_a", "bulk_b"):
            GearItemDef.objects.create(
                slug=s, name=s, rarity="common", effect_type="domain_multiplier",
                effect_domain="strength", effect_value=1.1, pack=self.pack, weight=100,
            )

    def test_bulk_price_discount_tiers(self):
        from core.services.combat import bulk_price

        cases = [(1, 100, 0), (3, 270, 10), (5, 425, 15), (10, 800, 20)]
        for qty, cost, pct in cases:
            got_cost, got_pct = bulk_price(100, qty)
            self.assertEqual((got_cost, got_pct), (cost, pct))

    def test_open_pack_bulk_draws_and_spends(self):
        from core.services.combat import open_pack_bulk, profile

        ok, err, payload = open_pack_bulk(self.user, self.pack, 3, rng=lambda: 0.01)
        self.assertTrue(ok, err)
        self.assertEqual(payload["cost"], 270)
        self.assertEqual(payload["discount_pct"], 10)
        self.assertEqual(len(payload["manifest"]), 6)  # 3 copies * 2 draws
        self.assertEqual(profile(self.user).tokens, 300 - 270)

    def test_generic_crate_pulls_whole_catalog_and_guarantees_rarity(self):
        from core.services.combat import open_pack

        crate = GearPackDef.objects.create(
            slug="gen_crate", name="Gen Crate", price_tokens=150, draws=1,
            domains=[], guaranteed_min_rarity="rare", is_generic=True,
        )
        GearItemDef.objects.create(
            slug="other_item", name="Other Item", rarity="common",
            effect_type="domain_multiplier", effect_domain="hydration",
            effect_value=1.0, pack=None, weight=100,
        )
        ok, err, manifest = open_pack(self.user, crate, rng=lambda: 0.01)
        self.assertTrue(ok, err)
        self.assertEqual(len(manifest), 1)
        self.assertEqual(manifest[0]["rarity"], "rare")  # guaranteed bump

    def test_shop_open_bulk_endpoint(self):
        resp = self.client.post(
            "/shop/open", data={"pack_slug": "bulk_pack", "quantity": 3},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["quantity"], 3)
        self.assertEqual(body["cost"], 270)
        self.assertEqual(len(body["manifest"]), 6)

    def test_loadout_unequip_endpoint(self):
        gear = GearItemDef.objects.create(
            slug="eq_item", name="Eq Item", slot="head", rarity="common",
            effect_type="domain_multiplier", effect_domain="strength",
            effect_value=1.0, pack=self.pack,
        )
        ug = UserGear.objects.create(user=self.user, gear_def=gear, rarity="common", equipped_slot="head")
        resp = self.client.post(
            "/loadout/unequip", data={"gear_id": ug.pk},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])
        ug.refresh_from_db()
        self.assertIsNone(ug.equipped_slot)

        resp = self.client.post(
            "/loadout/equip", data={"gear_id": ug.pk},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        ug.refresh_from_db()
        self.assertEqual(ug.equipped_slot, "head")

    def test_pvp_state_includes_power_breakdown_and_new_slots(self):
        # Equipping into a brand-new slot (chest) works and feeds the PvP power audit.
        GearItemDef.objects.create(
            slug="pw", name="Pw", slot="chest", rarity="epic",
            effect_type="domain_multiplier", effect_domain="strength",
            effect_value=1.5, pack=self.pack,
        )
        ug = UserGear.objects.create(
            user=self.user, gear_def=GearItemDef.objects.get(slug="pw"),
            rarity="epic", equipped_slot="chest",
        )
        resp = self.client.get("/loadout/state")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["equipped"]["chest"]["name"], "Pw")
        self.assertTrue(any(o["slug"] == "pw" and o["equipped"] for o in body["owned"]))

        resp = self.client.get("/pvp/state")
        self.assertEqual(resp.status_code, 200)
        me = resp.json().get("me") or {}
        self.assertIn("power", me)
        self.assertIn("consistency", me)
        self.assertIn("per_campaign", me)
        self.assertGreaterEqual(me["power"], 0)

    def test_loadout_state_reveals_unequipped_candidates(self):
        gear = GearItemDef.objects.create(
            slug="candidate_item", name="Candidate Item", slot="chest", rarity="rare",
            effect_type="domain_multiplier", effect_domain="strength",
            effect_value=1.0, pack=self.pack,
        )
        UserGear.objects.create(user=self.user, gear_def=gear, rarity="rare")
        resp = self.client.get("/loadout/state")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("equipped", body)
        self.assertTrue(any(c["slug"] == "candidate_item" for c in body["candidates"]))

    def test_loadout_state_carries_item_detail_fields(self):
        """The Inventory page's item popups need description + when/how acquired."""
        gear = GearItemDef.objects.create(
            slug="detail_item", name="Detail Item", slot="legs", rarity="epic",
            effect_type="domain_multiplier", effect_domain="strength",
            effect_value=1.3, pack=self.pack,
            description="Sturdy greaves that help you squat deeper and stronger.",
        )
        ug = UserGear.objects.create(
            user=self.user, gear_def=gear, rarity="epic",
            equipped_slot="legs", quantity=1,
        )

        resp = self.client.get("/loadout/state")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()

        owned_item = next(o for o in body["owned"] if o["slug"] == "detail_item")
        self.assertEqual(owned_item["description"], "Sturdy greaves that help you squat deeper and stronger.")
        self.assertEqual(owned_item["pack_name"], "Bulk Pack")
        self.assertEqual(owned_item["quantity"], 1)
        self.assertTrue(owned_item["obtained_at"])
        self.assertTrue(owned_item["equipped"])

        equipped_item = body["equipped"]["legs"]
        self.assertEqual(equipped_item["description"], "Sturdy greaves that help you squat deeper and stronger.")
        self.assertEqual(equipped_item["pack_name"], "Bulk Pack")
        self.assertTrue(equipped_item["obtained_at"])

        # Items without a pack report a null origin (front-end shows a default note).
        loose = GearItemDef.objects.create(
            slug="loose_item", name="Loose Item", slot="head", rarity="common",
            effect_type="domain_multiplier", effect_domain="hydration",
            effect_value=1.0, pack=None, description="A no-pack drop.",
        )
        UserGear.objects.create(user=self.user, gear_def=loose, rarity="common")
        resp = self.client.get("/loadout/state")
        loose_item = next(o for o in resp.json()["owned"] if o["slug"] == "loose_item")
        self.assertIsNone(loose_item["pack_name"])
        self.assertEqual(loose_item["description"], "A no-pack drop.")
class OnboardingFlowTests(TestCase):
    """docs/17 #91 - guided first-flight onboarding completion endpoint."""

    def setUp(self):
        self.user = User.objects.create_user(username="onb", password="pw")
        self.client.login(username="onb", password="pw")

    def test_onboarding_starts_unset_and_completes_idempotently(self):
        # A fresh account has the flag off and it is reported to the dashboard.
        r = self.client.get("/api/v1/dashboard/state")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["onboarded"])

        # Finishing / skipping the walkthrough flips the flag on.
        r = self.client.post("/api/v1/onboarded")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["onboarded"])

        # The dashboard now reflects it so the tour will not re-trigger.
        r = self.client.get("/api/v1/dashboard/state")
        self.assertTrue(r.json()["onboarded"])

        # Setting it again is a no-op (idempotent server-side).
        r = self.client.post("/api/v1/onboarded")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["onboarded"])

    def test_onboarding_requires_login(self):
        self.client.logout()
        r = self.client.post("/api/v1/onboarded")
        self.assertIn(r.status_code, (302, 403))


class QuickLogTests(TestCase):
    """Roadmap Item #1: Manual quick-logging fallback for habit tracking."""

    def setUp(self):
        self.user = User.objects.create_user(username="logger", password="pw")
        self.client.login(username="logger", password="pw")

    def test_quick_log_hydration(self):
        resp = self.client.post(
            "/log/quick/",
            data=json.dumps({"category": "hydration", "amount": 64, "goal": 64}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["category"], "hydration")
        self.assertGreater(data["xp_awarded"], 0)
        self.assertIsNotNone(data["skill_tree"])
        self.assertEqual(data["skill_tree"]["modality"], "hydration")

        # Verify RawActivityLog persisted
        log = RawActivityLog.objects.get(pk=data["created_log_ids"][0])
        self.assertEqual(log.source, Provider.MANUAL)
        self.assertEqual(log.event_type, "hydration")
        self.assertTrue(log.processed)

    def test_quick_log_nutrition(self):
        resp = self.client.post(
            "/log/quick/",
            data=json.dumps({
                "category": "nutrition",
                "calories": 650,
                "protein": 55,
                "protein_hit": True,
                "under_calorie": True,
                "food_name": "Chicken Breast Bowl",
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["category"], "nutrition")
        self.assertGreater(data["xp_awarded"], 0)
        self.assertEqual(data["skill_tree"]["modality"], "nutrition")

    def test_quick_log_cardio(self):
        resp = self.client.post(
            "/log/quick/",
            data=json.dumps({
                "category": "cardio",
                "minutes": 45,
                "intensity": "high",
                "workout_type": "Morning Run",
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertGreater(data["xp_awarded"], 0)
        self.assertEqual(data["skill_tree"]["modality"], "endurance")

    def test_quick_log_strength(self):
        resp = self.client.post(
            "/log/quick/",
            data=json.dumps({
                "category": "strength",
                "volume_lbs": 12500,
                "duration_minutes": 60,
                "program": "Bench & Squat Power",
                "pr": True,
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertGreater(data["xp_awarded"], 0)
        self.assertEqual(data["skill_tree"]["modality"], "strength")

    def test_quick_log_sleep(self):
        resp = self.client.post(
            "/log/quick/",
            data=json.dumps({"category": "sleep", "sleep_hours": 8.0}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertGreater(data["xp_awarded"], 0)
        self.assertEqual(data["skill_tree"]["modality"], "recovery")

    def test_quick_log_scale(self):
        resp = self.client.post(
            "/log/quick/",
            data=json.dumps({"category": "scale", "weight_lbs": 178.4, "body_fat": 14.2}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["category"], "scale")
        self.assertTrue(RawActivityLog.objects.filter(user=self.user, event_type="scale").exists())

    def test_quick_log_validations(self):
        # Invalid JSON
        r = self.client.post("/log/quick/", data="not-json", content_type="application/json")
        self.assertEqual(r.status_code, 400)

        # Missing category
        r = self.client.post("/log/quick/", data=json.dumps({}), content_type="application/json")
        self.assertEqual(r.status_code, 400)

        # Invalid category
        r = self.client.post("/log/quick/", data=json.dumps({"category": "invalid_xyz"}), content_type="application/json")
        self.assertEqual(r.status_code, 400)

        # Zero / invalid values
        r = self.client.post("/log/quick/", data=json.dumps({"category": "hydration", "amount": 0}), content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_quick_log_requires_auth(self):
        self.client.logout()
        resp = self.client.post(
            "/log/quick/",
            data=json.dumps({"category": "sleep", "sleep_hours": 7.5}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 302)


class HistoricalQueueTests(TestCase):
    """Roadmap Item #2: Missing habit logs scanner and backfill queue."""

    def setUp(self):
        self.user = User.objects.create_user(username="hist_user", password="pw")
        self.client.login(username="hist_user", password="pw")

    def test_missing_days_detected(self):
        from core.services.historical_queue import find_missing_habit_days

        today = timezone.localdate()
        two_days_ago = today - timedelta(days=2)

        # Log hydration 2 days ago
        RawActivityLog.objects.create(
            user=self.user,
            source=Provider.MANUAL,
            event_type="hydration",
            payload={"water": 64},
            occurred_at=timezone.make_aware(timezone.datetime.combine(two_days_ago, timezone.datetime.min.time())),
        )

        missing = find_missing_habit_days(self.user, days=7)
        self.assertTrue(len(missing) > 0)

        # Check the day with partial log
        day_2 = next(d for d in missing if d["days_ago"] == 2)
        self.assertTrue(day_2["has_hydration"])
        self.assertFalse(day_2["has_nutrition"])
        self.assertEqual(day_2["missing"], ["nutrition"])

    def test_missing_logs_queue_endpoint(self):
        resp = self.client.get("/queue/missing-logs/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertIn("missing_days", data)
        self.assertEqual(data["days_scanned"], 7)

    def test_backfill_via_quick_log(self):
        today = timezone.localdate()
        target_date_str = (today - timedelta(days=3)).isoformat()

        resp = self.client.post(
            "/log/quick/",
            data=json.dumps({
                "category": "hydration",
                "amount": 75,
                "date": target_date_str,
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        log = RawActivityLog.objects.get(pk=resp.json()["created_log_ids"][0])
        self.assertEqual(log.occurred_at.date().isoformat(), target_date_str)


class DataSourcePreferenceTests(TestCase):
    """Roadmap Item #3: Data source selection preferences."""

    def setUp(self):
        self.user = User.objects.create_user(username="pref_user", password="pw")
        self.client.login(username="pref_user", password="pw")

    def test_get_and_update_source_preferences(self):
        # Default preferences
        r = self.client.get("/profile/sources/")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["source_preferences"]["hydration"], "sparkyfitness")

        # Update preferences
        r2 = self.client.post(
            "/profile/sources/",
            data=json.dumps({
                "hydration": "health_connect",
                "nutrition": "sparkyfitness",
                "endurance": "garmin",
            }),
            content_type="application/json",
        )
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["source_preferences"]["hydration"], "health_connect")
        self.assertEqual(r2.json()["source_preferences"]["endurance"], "garmin")


class SparkyInputTests(TestCase):
    """Roadmap Item #4: SparkyFitness API food search and direct inputs."""

    def setUp(self):
        self.user = User.objects.create_user(username="sparky_in", password="pw")
        self.client.login(username="sparky_in", password="pw")

    def test_search_foods_client_and_view(self):
        from core.services.sparky_client import SparkyFitnessClient

        client = SparkyFitnessClient()
        # Query chicken
        results = client.search_foods("", "chicken")
        self.assertTrue(len(results) > 0)
        self.assertTrue(any("Chicken" in item["name"] for item in results))

        # View endpoint
        r = self.client.get("/foods/search/?q=chicken")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data["success"])
        self.assertTrue(len(data["results"]) > 0)

    def test_direct_water_and_food_post_client(self):
        from core.services.sparky_client import SparkyFitnessClient

        client = SparkyFitnessClient()
        water_res = client.post_water_intake("", 1500, "2026-08-20")
        self.assertEqual(water_res["water_ml"], 1500.0)

        food_res = client.post_food_entry("", "Grilled Salmon", 450, 42.0)
        self.assertEqual(food_res["food_name"], "Grilled Salmon")
        self.assertEqual(food_res["protein"], 42.0)


class MarketplaceTests(TestCase):
    """Roadmap Item #5: Player gear marketplace."""

    def setUp(self):
        self.seller = User.objects.create_user(username="merchant", password="pw")
        self.buyer = User.objects.create_user(username="shopper", password="pw")
        self.gear_def = GearItemDef.objects.create(
            slug="mkt_helm",
            name="Marketplace Helm",
            slot="head",
            rarity="rare",
            icon="fa-helmet-safety",
            effect_type="domain_multiplier",
            effect_domain="strength",
            effect_value=1.5,
        )
        self.user_gear = UserGear.objects.create(
            user=self.seller,
            gear_def=self.gear_def,
            rarity="rare",
            equipped_slot=None,
        )

    def test_list_and_buy_gear_with_tokens(self):
        from core.services.marketplace import buy_marketplace_item, list_gear_item
        from core.services.combat import profile as combat_profile

        # Give buyer tokens
        b_prof = combat_profile(self.buyer)
        b_prof.tokens = 500
        b_prof.save()

        s_prof = combat_profile(self.seller)
        s_prof.tokens = 50
        s_prof.save()

        # List item
        listing, err = list_gear_item(self.seller, self.user_gear.id, "tokens", 100)
        self.assertIsNone(err)
        self.assertIsNotNone(listing)
        self.assertTrue(listing.is_active)

        # Buy item
        res, err = buy_marketplace_item(self.buyer, listing.id)
        self.assertIsNone(err)
        self.assertTrue(res["success"])

        # Check balances: 100 tokens price, 5 token fee -> seller gets +95
        b_prof.refresh_from_db()
        s_prof.refresh_from_db()
        self.assertEqual(b_prof.tokens, 400)
        self.assertEqual(s_prof.tokens, 145)

        # Check gear ownership transferred to buyer
        self.user_gear.refresh_from_db()
        self.assertEqual(self.user_gear.user, self.buyer)

    def test_cannot_list_equipped_gear(self):
        from core.services.marketplace import list_gear_item

        self.user_gear.equipped_slot = "head"
        self.user_gear.save()

        listing, err = list_gear_item(self.seller, self.user_gear.id, "tokens", 50)
        self.assertIsNotNone(err)
        self.assertIn("equipped", err.lower())

    def test_cancel_listing(self):
        from core.services.marketplace import cancel_marketplace_listing, list_gear_item

        listing, _ = list_gear_item(self.seller, self.user_gear.id, "scraps", 30)
        self.assertTrue(listing.is_active)

        cancelled, err = cancel_marketplace_listing(self.seller, listing.id)
        self.assertIsNone(err)
        self.assertFalse(cancelled.is_active)

    def test_marketplace_state_endpoint(self):
        from core.services.marketplace import list_gear_item
        list_gear_item(self.seller, self.user_gear.id, "tokens", 120)

        self.client.login(username="shopper", password="pw")
        r = self.client.get("/marketplace/state")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(len(data["listings"]) >= 1)
        self.assertEqual(data["listings"][0]["gear"]["name"], "Marketplace Helm")


class SecurityHeadersTests(TestCase):
    """Roadmap Item #6: Production security headers and hardening."""

    def test_security_headers_present(self):
        resp = self.client.get("/login/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Content-Security-Policy", resp.headers)
        self.assertIn("X-Content-Type-Options", resp.headers)
        self.assertEqual(resp.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("Referrer-Policy", resp.headers)
        self.assertEqual(resp.headers["Referrer-Policy"], "strict-origin-when-cross-origin")


class StreakFreezeTests(TestCase):
    """Roadmap Item #7: Flamingo Ice Shield / Streak Freeze."""

    def setUp(self):
        self.user = User.objects.create_user(username="freezer", password="pw")
        self.client.login(username="freezer", password="pw")
        self.shield_def = GearItemDef.objects.create(
            slug="flamingo_ice_shield",
            name="Flamingo Ice Shield",
            slot="head",
            rarity="rare",
            effect_type="streak_freeze",
            effect_domain="recovery",
            effect_value=1.0,
            is_consumable=True,
            max_stack=5,
        )

    def test_buy_streak_freeze_from_scrap_shop(self):
        from core.services.combat import buy_scrap_item, profile as combat_profile

        today = timezone.localdate().weekday()
        ScrapShopItem.objects.create(
            slug="scrap_streak_freeze",
            name="Flamingo Streak Freeze",
            cost_scraps=75,
            available_days=[today],
            reward_type=ScrapShopItem.RewardType.STREAK_FREEZE,
            reward_value=1,
        )

        p = combat_profile(self.user)
        p.scraps = 150
        p.save()

        res, err = buy_scrap_item(self.user, "scrap_streak_freeze")
        self.assertIsNone(err)
        self.assertEqual(res["streak_freeze"], 1)

        p.refresh_from_db()
        self.assertEqual(p.scraps, 75)
        self.assertEqual(p.active_buffs["streak_freeze_count"], 1)

        # Inventory has consumable item
        ug = UserGear.objects.filter(user=self.user, gear_def=self.shield_def).first()
        self.assertIsNotNone(ug)
        self.assertEqual(ug.quantity, 1)

    def test_consume_streak_freeze_consumable(self):
        from core.services.combat import consume_consumable, profile as combat_profile

        ug = UserGear.objects.create(
            user=self.user,
            gear_def=self.shield_def,
            rarity="rare",
            quantity=1,
        )
        p = combat_profile(self.user)
        ok, err = consume_consumable(p, self.user, ug.id)
        self.assertTrue(ok)
        self.assertIsNone(err)

        p.refresh_from_db()
        self.assertTrue(p.active_buffs["streak_freeze_active"])
        self.assertEqual(p.active_buffs["streak_freeze_count"], 1)
        self.assertFalse(UserGear.objects.filter(pk=ug.id).exists())


class SmartRemindersAndPushNotificationTests(TestCase):
    """Mobile Push Notifications and Intelligent Habit Reminders Test Suite."""

    def setUp(self):
        self.user = User.objects.create_user(username="notify_user", password="pw")
        self.user.streak = 5
        self.user.save()
        self.client.login(username="notify_user", password="pw")

    def test_notification_preferences_get_and_update(self):
        from core.services.smart_reminders import (
            get_user_notification_preferences,
            update_user_notification_preferences,
        )

        # Default prefs
        prefs = get_user_notification_preferences(self.user)
        self.assertTrue(prefs["enabled"])
        self.assertTrue(prefs["food_reminders"])
        self.assertEqual(prefs["quiet_hours_start"], "22:00")

        # Update via service
        updated = update_user_notification_preferences(
            self.user,
            {"food_reminders": False, "quiet_hours_start": "23:00"},
        )
        self.assertFalse(updated["food_reminders"])
        self.assertEqual(updated["quiet_hours_start"], "23:00")

        # Update via endpoint
        r = self.client.post(
            "/notifications/preferences/",
            data=json.dumps({"hydration_reminders": False, "enabled": True}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data["success"])
        self.assertFalse(data["preferences"]["hydration_reminders"])

    def test_push_device_registration(self):
        from core.models import PushDevice

        r = self.client.post(
            "/notifications/register/",
            data=json.dumps({
                "token": "fcm_token_1234567890",
                "platform": "android",
                "device_name": "Pixel 8 Pro",
            }),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["success"])

        device = PushDevice.objects.get(token="fcm_token_1234567890")
        self.assertEqual(device.user, self.user)
        self.assertEqual(device.platform, "android")
        self.assertTrue(device.is_active)

    def test_intelligent_reminders_evaluation(self):
        from datetime import datetime, time
        from core.services.smart_reminders import evaluate_smart_reminders

        # Simulate 1:30 PM (13:30) with no food logged today
        fixed_time = timezone.make_aware(datetime.combine(timezone.localdate(), time(13, 30)))
        prompts = evaluate_smart_reminders(self.user, now=fixed_time)

        self.assertTrue(len(prompts) > 0)
        categories = [p["category"] for p in prompts]
        self.assertIn("food", categories)
        self.assertIn("hydration", categories)

    def test_intelligent_reminders_quiet_hours(self):
        from datetime import datetime, time
        from core.services.smart_reminders import evaluate_smart_reminders

        # Simulate 11:30 PM (23:30) which is inside default quiet hours (22:00 to 07:00)
        quiet_time = timezone.make_aware(datetime.combine(timezone.localdate(), time(23, 30)))
        prompts = evaluate_smart_reminders(self.user, now=quiet_time)
        self.assertEqual(prompts, [])

    def test_dispatch_push_notification_and_test_endpoint(self):
        from core.models import PushDevice, PushNotificationLog
        from core.services.smart_reminders import dispatch_push_notification, register_push_device

        register_push_device(self.user, "device_abc", platform="ios")

        # Dispatch via service
        log_entry, err = dispatch_push_notification(
            self.user,
            "workout",
            "Time to Train!",
            "Get your reps in today.",
        )
        self.assertIsNone(err)
        self.assertIsNotNone(log_entry)
        self.assertEqual(log_entry.category, "workout")

        # Dispatch via test endpoint
        r = self.client.post(
            "/notifications/test/",
            data=json.dumps({"category": "hydration", "title": "Test Sip", "body": "Drink water"}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["success"])

        # Check notification history
        r_hist = self.client.get("/notifications/history/")
        self.assertEqual(r_hist.status_code, 200)
        data = r_hist.json()
        self.assertTrue(len(data["notifications"]) >= 2)


class CelebrationAndLevelUpTests(TestCase):
    """Roadmap Item #8: Gamified Level-Up and Badge Unlock Celebrations."""

    def setUp(self):
        self.user = User.objects.create_user(username="level_champ", password="pw")
        self.client.login(username="level_champ", password="pw")

    def test_quick_log_triggers_level_up_and_bonus_tokens(self):
        from core.models import SkillTree, Modality
        from core.services.combat import profile as combat_profile

        # Setup SkillTree with 80 XP (Level 1)
        st, _ = SkillTree.objects.get_or_create(
            user=self.user,
            modality=Modality.HYDRATION,
            defaults={"level": 1, "xp": 80, "total_xp": 80},
        )
        st.level = 1
        st.xp = 80
        st.save()

        p = combat_profile(self.user)
        initial_tokens = p.tokens

        # Quick log hydration (adds 50 XP -> total 130 XP -> Level 2)
        resp = self.client.post(
            "/log/quick/",
            data=json.dumps({
                "category": "hydration",
                "water_oz": 64,
                "goal": 64,
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertIn("level_ups", data)
        self.assertEqual(len(data["level_ups"]), 1)

        lvl_up = data["level_ups"][0]
        self.assertEqual(lvl_up["modality"], "hydration")
        self.assertEqual(lvl_up["old_level"], 1)
        self.assertEqual(lvl_up["new_level"], 2)
        self.assertEqual(lvl_up["bonus_tokens"], 25)

        # Profile gained 10 goal tokens + 25 level up bonus tokens
        p.refresh_from_db()
        self.assertEqual(p.tokens, initial_tokens + 10 + 25)


class SynthesizedAudioAndSoundEffectsTests(TestCase):
    """Roadmap Item #9: Web Audio Synthesized Sound Effects & Audio Toggle."""

    def setUp(self):
        self.user = User.objects.create_user(username="audio_user", password="pw")
        self.client.login(username="audio_user", password="pw")

    def test_audio_static_asset_and_template_integration(self):
        import os
        from django.conf import settings

        # Verify static audio.js exists and has Web Audio synthesis functions
        audio_js_path = os.path.join(settings.BASE_DIR, "core", "static", "core", "js", "audio.js")
        self.assertTrue(os.path.exists(audio_js_path))
        with open(audio_js_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("playXpChime", content)
        self.assertIn("playLevelUpFanfare", content)
        self.assertIn("playBadgeFanfare", content)
        self.assertIn("playGachaRoll", content)
        self.assertIn("ffAudioToggle", content)

    def test_dashboard_and_profile_templates_contain_audio_controls(self):
        # Dashboard template contains audio script
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8")
        self.assertRegex(html, r"audio(\.[0-9a-f]+)?\.js")

        # Profile template contains sound effects card & toggle
        resp_prof = self.client.get("/profile/")
        self.assertEqual(resp_prof.status_code, 200)
        prof_html = resp_prof.content.decode("utf-8")
        self.assertIn("Sound Effects", prof_html)
        self.assertIn("profile-sound-toggle", prof_html)


class BountyBoardAndFitnessDuelsTests(TestCase):
    """Roadmap Item N8: Interactive Fitness Bounty Board & 1v1 Duels."""

    def setUp(self):
        self.user1 = User.objects.create_user(username="player_one", password="pw1")
        self.user2 = User.objects.create_user(username="player_two", password="pw2")

        from core.services.combat import profile as combat_profile
        self.prof1 = combat_profile(self.user1)
        self.prof1.tokens = 500
        self.prof1.scraps = 100
        self.prof1.save()

        self.prof2 = combat_profile(self.user2)
        self.prof2.tokens = 500
        self.prof2.scraps = 100
        self.prof2.save()

        self.client1 = self.client_class()
        self.client1.login(username="player_one", password="pw1")

        self.client2 = self.client_class()
        self.client2.login(username="player_two", password="pw2")

    def test_bounties_state_and_daily_system_bounties(self):
        from core.services.bounties import get_bounties_state
        state = get_bounties_state(self.user1)

        self.assertIn("user_balance", state)
        self.assertEqual(state["user_balance"]["tokens"], 500)
        self.assertIn("target_types", state)
        self.assertIn("open_board", state)
        # Verify daily system bounties from SirFluffington are seeded
        self.assertGreaterEqual(len(state["open_board"]), 3)
        self.assertTrue(any(b["is_system"] for b in state["open_board"]))

    def test_create_solo_contract_and_escrow(self):
        from core.models import Bounty, BountyParticipant
        from core.services.bounties import create_bounty

        ok, res = create_bounty(
            user=self.user1,
            bounty_type=Bounty.BountyType.SOLO,
            target_type=Bounty.TargetType.WATER_ML,
            target_value=3000,
            duration_hours=24,
            wager_tokens=50,
            wager_scraps=10,
        )
        self.assertTrue(ok)
        self.prof1.refresh_from_db()
        # Wagers deducted into escrow
        self.assertEqual(self.prof1.tokens, 450)
        self.assertEqual(self.prof1.scraps, 90)

        bounty = Bounty.objects.get(id=res["bounty_id"])
        self.assertEqual(bounty.status, Bounty.Status.ACTIVE)
        self.assertEqual(bounty.bounty_type, Bounty.BountyType.SOLO)
        self.assertEqual(bounty.target_value, 3000)

        # Participant created
        self.assertTrue(BountyParticipant.objects.filter(bounty=bounty, user=self.user1).exists())

    def test_create_and_accept_1v1_duel(self):
        from core.models import Bounty, BountyParticipant, PushNotificationLog
        from core.services.bounties import accept_bounty, create_bounty

        ok, res = create_bounty(
            user=self.user1,
            bounty_type=Bounty.BountyType.DUEL,
            target_type=Bounty.TargetType.STEPS,
            target_value=12000,
            duration_hours=24,
            wager_tokens=100,
            opponent_username="player_two",
        )
        self.assertTrue(ok)
        bounty_id = res["bounty_id"]

        # Push notification dispatched to opponent
        self.assertTrue(
            PushNotificationLog.objects.filter(
                user=self.user2,
                category=PushNotificationLog.Category.BOUNTY,
            ).exists()
        )

        # Opponent accepts duel
        ok2, res2 = accept_bounty(bounty_id, self.user2)
        self.assertTrue(ok2)

        self.prof1.refresh_from_db()
        self.prof2.refresh_from_db()
        self.assertEqual(self.prof1.tokens, 400)
        self.assertEqual(self.prof2.tokens, 400)

        bounty = Bounty.objects.get(id=bounty_id)
        self.assertEqual(bounty.status, Bounty.Status.ACTIVE)
        self.assertEqual(bounty.participants.count(), 2)

    def test_bounty_evaluation_and_claim_reward(self):
        from core.models import Bounty, BountyParticipant, RawActivityLog
        from core.services.bounties import claim_bounty_reward, create_bounty, evaluate_user_bounties

        ok, res = create_bounty(
            user=self.user1,
            bounty_type=Bounty.BountyType.SOLO,
            target_type=Bounty.TargetType.STRENGTH_VOLUME,
            target_value=10000,
            duration_hours=24,
            wager_tokens=50,
        )
        bounty_id = res["bounty_id"]
        bounty = Bounty.objects.get(id=bounty_id)

        # Log strength activity within window
        now = timezone.now()
        RawActivityLog.objects.create(
            user=self.user1,
            source="manual",
            event_type="strength",
            payload={"total_volume_lbs": 12000, "duration_minutes": 45},
            occurred_at=now,
        )

        evaluate_user_bounties(self.user1, now)

        part = BountyParticipant.objects.get(bounty=bounty, user=self.user1)
        self.assertEqual(part.current_value, 12000)
        self.assertTrue(part.is_completed)

        bounty.refresh_from_db()
        self.assertEqual(bounty.status, Bounty.Status.COMPLETED)
        self.assertEqual(bounty.winner, self.user1)

        # Claim payout
        ok_claim, claim_res = claim_bounty_reward(bounty_id, self.user1, now)
        self.assertTrue(ok_claim)
        self.assertGreater(claim_res["tokens_awarded"], 50)
        self.assertGreater(claim_res["xp_awarded"], 0)

        self.prof1.refresh_from_db()
        self.assertEqual(self.prof1.tokens, 450 + claim_res["tokens_awarded"])

    def test_cancel_bounty_and_refund(self):
        from core.models import Bounty
        from core.services.bounties import cancel_bounty, create_bounty

        ok, res = create_bounty(
            user=self.user1,
            bounty_type=Bounty.BountyType.OPEN,
            target_type=Bounty.TargetType.PROTEIN_G,
            target_value=150,
            duration_hours=24,
            wager_tokens=75,
            wager_scraps=25,
        )
        bounty_id = res["bounty_id"]
        self.prof1.refresh_from_db()
        self.assertEqual(self.prof1.tokens, 425)
        self.assertEqual(self.prof1.scraps, 75)

        # Cancel and refund
        ok_cancel, cancel_res = cancel_bounty(bounty_id, self.user1)
        self.assertTrue(ok_cancel)

        self.prof1.refresh_from_db()
        self.assertEqual(self.prof1.tokens, 500)
        self.assertEqual(self.prof1.scraps, 100)

        bounty = Bounty.objects.get(id=bounty_id)
        self.assertEqual(bounty.status, Bounty.Status.CANCELLED)

    def test_bounties_http_api_endpoints(self):
        # GET state
        res = self.client1.get("/bounties/state")
        self.assertEqual(res.status_code, 200)
        json_data = res.json()
        self.assertTrue(json_data["success"])

        # POST create open bounty
        res_create = self.client1.post(
            "/bounties/create",
            data=json.dumps({
                "bounty_type": "open",
                "target_type": "steps",
                "target_value": 8000,
                "duration_hours": 12,
                "wager_tokens": 20,
            }),
            content_type="application/json",
        )
        self.assertEqual(res_create.status_code, 200)
        bounty_id = res_create.json()["bounty"]["bounty_id"]

        # POST cancel
        res_cancel = self.client1.post(f"/bounties/{bounty_id}/cancel")
        self.assertEqual(res_cancel.status_code, 200)
        self.assertTrue(res_cancel.json()["success"])







