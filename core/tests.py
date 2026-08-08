"""Tests for the Flamingo Fitness gamification + API layers.

Run with:  python manage.py test core
"""

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from core.models import (
    BaseResource,
    DailyReadiness,
    Provider,
    RawActivityLog,
    SkillTree,
    UserIntegration,
    XPLedger,
)
from core.services.gamification import (
    XP_PER_LEVEL,
    body_battery_xp,
    endurance_xp,
    nutrition_xp,
    process_log,
    process_payload,
    sleep_xp,
    strength_xp,
)
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
        self.assertEqual(sleep_xp(8), 50)
        self.assertEqual(sleep_xp(9), 50)
        self.assertEqual(sleep_xp(6), 20)
        self.assertEqual(sleep_xp(4.5), 0)

    def test_body_battery_and_nutrition(self):
        self.assertEqual(body_battery_xp(62), 62)
        self.assertEqual(nutrition_xp(True), 50)
        self.assertEqual(nutrition_xp(False), 0)


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
        resources = BaseResource.objects.get(user=self.user)
        self.assertEqual(resources.time_speedups, 5)

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
        resources = BaseResource.objects.get(user=self.user)
        self.assertEqual(resources.materials, 10)

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
        resources = BaseResource.objects.get(user=self.user)
        self.assertEqual(resources.materials, 10)

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
        self.assertEqual(first["materials"], 10)
        self.assertEqual(first["protein_goal"], 180)
        self.assertEqual(first["calorie_goal"], 2400)
        self.assertEqual(len(first["food_entries"]), 3)

        # The most recent entry is surfaced as `today`.
        self.assertTrue(body["today"]["perfect"])
        self.assertEqual(body["today"]["xp"], 50)

        # Skill tree was credited for the perfect-macro XP.
        self.assertEqual(body["skill_tree"]["total_xp"], 50)
        self.assertEqual(body["skill_tree"]["progress_pct"], 50)


