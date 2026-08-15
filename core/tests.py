"""Tests for the Flamingo Fitness gamification + API layers.

Run with:  python manage.py test core
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from core.models import (
    BaseBuilding,
    BaseBuildingDef,
    BadgeDef,
    BaseResource,
    BossConfig,
    DailyReadiness,
    Modality,
    Provider,
    RawActivityLog,
    SkillTree,
    UserBadge,
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
# ---------------------------------------------------------------------------
# Base-building economy math (SimpleTestCase)
# ---------------------------------------------------------------------------
class BaseEconomyMathTests(SimpleTestCase):
    def test_streak_multiplier(self):
        from core.services.base_economy import streak_multiplier
        self.assertEqual(streak_multiplier(0), 1.0)
        self.assertEqual(streak_multiplier(5), 1.25)
        self.assertEqual(streak_multiplier(10), 1.5)
        self.assertEqual(streak_multiplier(20), 1.5)

    def test_xp_dividend(self):
        from core.services.base_economy import xp_dividend
        self.assertEqual(xp_dividend(0), 0)
        self.assertEqual(xp_dividend(19), 0)
        self.assertEqual(xp_dividend(20), 1)
        self.assertEqual(xp_dividend(39), 1)
        self.assertEqual(xp_dividend(40), 2)

    def test_crit_chance(self):
        from core.services.base_economy import CRIT_CHANCE
        self.assertEqual(CRIT_CHANCE, 0.05)

    def test_production_plan_staff_and_modality(self):
        from core.services.base_economy import production_plan, STAFF_BONUS, MODALITY_BUFF
        # Use a tiny 0-day elapsed so base is 0, but multipliers still apply
        # to non-zero base when elapsed > 0. This just sanity-checks the knobs.
        self.assertEqual(STAFF_BONUS, 1.10)
        self.assertEqual(MODALITY_BUFF, 1.20)


# ---------------------------------------------------------------------------
# Base-building DB/integration tests
# ---------------------------------------------------------------------------
class BaseEconomyFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="baseuser", password="pw", streak=3)
        self.resources, _ = BaseResource.objects.get_or_create(user=self.user)

    def test_apply_rest_day_bonus_once_per_date(self):
        from datetime import date
        from core.services.base_economy import apply_rest_day_bonus
        on_date = date(2025, 1, 1)
        DailyReadiness.objects.create(
            user=self.user, date=on_date, streak_requirement=DailyReadiness.StreakRequirement.REST_DAY,
            score=0,
        )
        first = apply_rest_day_bonus(self.resources, self.user, on_date=on_date)
        self.assertGreater(first, 0)
        self.resources.refresh_from_db()
        second = apply_rest_day_bonus(self.resources, self.user, on_date=on_date)
        self.assertEqual(second, 0)

    def test_modality_buff_and_production_plan(self):
        from core.services.base_economy import log_modality_workout, production_plan
        from django.utils import timezone
        def_obj = BaseBuildingDef.objects.create(
            slug="deck", name="Deck", base_cost_materials=10, base_cost_energy=1,
            base_duration_hours=1, materials_per_day=10, xp_bonus_pct=0,
            requires_base_level=0, modality_affinity="cardio", is_active=True, sort_order=1,
        )
        b = BaseBuilding.objects.create(user=self.user, building_def=def_obj, level=1, last_produced_at=timezone.now())
        log_modality_workout(self.resources, "cardio")
        planned = production_plan(b, self.user.streak, self.resources.active_buffs or {}, synergies=[])
        self.assertGreaterEqual(planned, 0)

    def test_evolve_building_requires_level_3(self):
        from core.services.base_economy import evolve_building
        def_obj = BaseBuildingDef.objects.create(
            slug="cabana", name="Cabana", base_cost_materials=10, base_cost_energy=1,
            base_duration_hours=1, materials_per_day=5, xp_bonus_pct=0,
            requires_base_level=0, branch_choices={"Materials": "cabana_mat", "XP": "cabana_xp"},
            is_active=True, sort_order=2,
        )
        b = BaseBuilding.objects.create(user=self.user, building_def=def_obj, level=2)
        ok, err = evolve_building(b, "cabana_mat")
        self.assertFalse(ok)
        b.level = 3
        b.save(update_fields=["level"])
        branch_def = BaseBuildingDef.objects.create(
            slug="cabana_mat", name="Cabana Materials", base_cost_materials=10, base_cost_energy=1,
            base_duration_hours=1, materials_per_day=8, xp_bonus_pct=0,
            requires_base_level=0, is_active=True, sort_order=3,
        )
        ok, err = evolve_building(b, "cabana_mat")
        self.assertTrue(ok)
        b.refresh_from_db()
        self.assertEqual(b.building_def.slug, "cabana_mat")

    def test_blueprint_drop_on_pr(self):
        from core.services.gamification import _handle_strength
        from unittest.mock import patch
        self.assertEqual(self.resources.blueprints.get("golden_flamingo", 0), 0)
        log = RawActivityLog.objects.create(
            user=self.user, source=Provider.LIFTOSAUR, event_type="strength",
            payload={"sets": 3, "total_volume_lbs": 10000, "exercise": "squat", "pr": True},
        )
        with patch("random.random", return_value=0.01):
            _handle_strength(log)
        self.resources.refresh_from_db()
        self.assertEqual(self.resources.blueprints.get("golden_flamingo", 0), 1)

class BaseAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="baseapi", password="pw", streak=2)
        self.client.login(username="baseapi", password="pw")
        # Seed a buildable def + a micro-build def.
        self.lawn = BaseBuildingDef.objects.create(
            slug="lawn_chairs", name="Lawn Chairs", base_cost_materials=0, base_cost_energy=0,
            base_duration_hours=0, materials_per_day=5, xp_bonus_pct=0,
            requires_base_level=0, is_active=True, sort_order=1,
        )
        self.cabana = BaseBuildingDef.objects.create(
            slug="cabana", name="Cabana", base_cost_materials=20, base_cost_energy=5,
            base_duration_hours=2, materials_per_day=10, xp_bonus_pct=0,
            requires_base_level=0, branch_choices={"Materials": "cabana_mat", "XP": "cabana_xp"},
            is_active=True, sort_order=2,
        )

    def test_base_state_requires_login(self):
        self.client.logout()
        resp = self.client.get("/base/")
        self.assertEqual(resp.status_code, 302)

    def test_base_state_shape(self):
        resp = self.client.get("/base/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("resources", body)
        self.assertIn("buildings", body)
        self.assertIn("unlockable", body)
        self.assertEqual(body["base_level"], 0)

    def test_start_micro_builds_immediately(self):
        resp = self.client.post("/base/start", data={"slug": "lawn_chairs"}, content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["base_level"], 1)
        self.assertEqual(len(body["buildings"]), 1)
        self.assertEqual(body["buildings"][0]["level"], 1)
        self.assertIn(body["buildings"][0]["status"], {"idle", "built"})

    def test_start_400_on_missing_slug(self):
        resp = self.client.post("/base/start", data={}, content_type="application/json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.json())

    def test_collect_404_on_bad_id(self):
        resp = self.client.post("/base/collect", data={"id": 999}, content_type="application/json")
        self.assertEqual(resp.status_code, 404)

    def test_customize_400_on_bad_color(self):
        b = BaseBuilding.objects.create(user=self.user, building_def=self.lawn, level=1)
        resp = self.client.post("/base/customize", data={"id": b.pk, "color": "red"}, content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_staff_and_unstaff(self):
        # Phase 8 (docs/13): staffing requires a REAL, accepted friend.
        friend = User.objects.create_user(username="basefriend", password="pw")
        send_friend_request(self.user, "basefriend")
        respond_friend_request(friend, self.user.pk, accept=True)

        b = BaseBuilding.objects.create(user=self.user, building_def=self.lawn, level=1)
        resp = self.client.post("/base/staff", data={"id": b.pk, "friend_id": friend.pk}, content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        b.refresh_from_db()
        self.assertEqual(b.staff_friend_id, friend.pk)
        resp = self.client.post("/base/staff", data={"id": b.pk, "friend_id": None}, content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        b.refresh_from_db()
        self.assertIsNone(b.staff_friend_id)

    def test_evolve_requires_level_3(self):
        b = BaseBuilding.objects.create(user=self.user, building_def=self.cabana, level=2)
        resp = self.client.post("/base/evolve", data={"id": b.pk, "chosen_slug": "cabana_mat"}, content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_milestone_idempotent(self):
        resp = self.client.post("/base/milestone", data={}, content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["celebrated"])

    def test_csrf_403_without_token(self):
        # Django's CSRF middleware rejects POSTs without the token before the view runs.
        from django.test import Client
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.login(username="baseapi", password="pw")
        resp = csrf_client.post("/base/start", data={"slug": "lawn_chairs"}, content_type="application/json")
        self.assertEqual(resp.status_code, 403)
# ---------------------------------------------------------------------------
# Phase 7 gamification hooks (docs/09 §10): modality buffs, blueprint drops,
# XP-bonus scaling from XP buildings.
# ---------------------------------------------------------------------------
class BaseGamificationHookTests(TestCase):
    """Cover the Phase 7 hooks grafted onto gamification.py (Step 23)."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="hookuser", password="pw", streak=3
        )
        self.resources, _ = BaseResource.objects.get_or_create(user=self.user)

    def test_cardio_log_sets_cardio_buff(self):
        from core.services import process_log

        raw = RawActivityLog.objects.create(
            user=self.user, source=Provider.PELOTON, event_type="cardio",
            payload={"minutes": 45, "intensity": "zone4"},
        )
        process_log(raw)
        self.resources.refresh_from_db()
        self.assertIn("cardio_buff_expiry", self.resources.active_buffs or {})

    def test_strength_log_sets_strength_buff(self):
        from core.services import process_log

        raw = RawActivityLog.objects.create(
            user=self.user, source=Provider.LIFTOSAUR, event_type="strength",
            payload={"total_volume_lbs": 15000, "completed": True},
        )
        process_log(raw)
        self.resources.refresh_from_db()
        self.assertIn("strength_buff_expiry", self.resources.active_buffs or {})

    def test_strength_pr_rolls_blueprint_drop(self):
        from unittest.mock import patch

        from core.services import process_log

        with patch("core.services.base_economy.random.random", return_value=0.01):
            raw = RawActivityLog.objects.create(
                user=self.user, source=Provider.LIFTOSAUR, event_type="strength",
                payload={"total_volume_lbs": 15000, "completed": True, "pr": True},
            )
            process_log(raw)
        self.resources.refresh_from_db()
        self.assertEqual(self.resources.blueprints.get("golden_flamingo", 0), 1)

    def test_xp_bonus_scales_entries_from_xp_building(self):
        BaseBuildingDef.objects.create(
            slug="vip_cabana", name="VIP Cabana", base_cost_materials=10,
            base_cost_energy=1, base_duration_hours=1, materials_per_day=1,
            xp_bonus_pct=10, requires_base_level=0, is_active=True, sort_order=1,
        )
        def_obj = BaseBuildingDef.objects.get(slug="vip_cabana")
        # base_xp_bonus_pct = 10 * level 2 = 20%.
        BaseBuilding.objects.create(user=self.user, building_def=def_obj, level=2)

        from core.services import process_log

        raw = RawActivityLog.objects.create(
            user=self.user, source=Provider.GARMIN, event_type="cardio",
            payload={"minutes": 45, "intensity": "zone2"},  # 45 XP before scaling
        )
        entries = process_log(raw)
        self.assertEqual(sum(e.amount for e in entries), int(round(45 * 1.20)))

    def test_xp_bonus_caps_at_25(self):
        from core.services.base_economy import base_xp_bonus_pct

        BaseBuildingDef.objects.create(
            slug="gold_statue", name="Gold Statue", base_cost_materials=1,
            base_cost_energy=1, base_duration_hours=1, materials_per_day=1,
            xp_bonus_pct=30, requires_base_level=0, is_active=True, sort_order=1,
        )
        def_obj = BaseBuildingDef.objects.get(slug="gold_statue")
        BaseBuilding.objects.create(user=self.user, building_def=def_obj, level=1)
        self.assertEqual(base_xp_bonus_pct(self.user), 25)


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
            "first_steps", "ten_day_flame", "perfect_week", "blueprint_hunter",
            "base_tycoon", "all_modality_master", "early_bird", "night_owl",
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

    def test_blueprint_hunter(self):
        from core.services.badges import check_badges

        resources, _ = BaseResource.objects.get_or_create(user=self.user)
        resources.blueprints = {"a": 1, "b": 1, "c": 1, "d": 1, "e": 1}
        resources.save()
        newly = check_badges(self.user)
        self.assertIn("blueprint_hunter", newly)

    def test_base_tycoon(self):
        from core.services.badges import check_badges

        # (user, building_def) is unique per the model, so base level 25 must be
        # reached with 25 distinct buildings each at level 1.
        for i in range(25):
            def_obj = BaseBuildingDef.objects.create(
                slug="hut_%d" % i, name="Hut %d" % i,
                base_cost_materials=1, base_cost_energy=1,
                base_duration_hours=1, materials_per_day=1,


                xp_bonus_pct=0, requires_base_level=0,
                is_active=True, sort_order=i,
            )
            BaseBuilding.objects.create(
                user=self.user, building_def=def_obj, level=1
            )
        newly = check_badges(self.user)
        self.assertIn("base_tycoon", newly)

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
        train = next(h for h in body["history"] if h["label"] == "Training day")
        self.assertEqual(train["amount"], "+1")
        rest = next(h for h in body["history"] if h["label"] == "Rest day")
        self.assertEqual(rest["amount"], "frozen")

    def test_materials_history_includes_perfect_macros_and_harvest(self):
        # Perfect macros grant +10 materials (also +50 Nutrition XP today).
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
        # Backdate a 40-XP workout so yesterday's harvest row shows up too.
        entry = XPLedger.objects.create(
            user=self.user, modality=Modality.STRENGTH,
            amount=40, description="Test workout",
        )
        XPLedger.objects.filter(pk=entry.pk).update(
            created_at=timezone.now() - timedelta(days=1)
        )

        resp = self.client.get("/stats/materials/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["stat"], "materials")
        # +10 macros + 2 minted by today's harvest (50 XP / 20).
        self.assertEqual(body["value"], 12)
        macros = next(h for h in body["history"] if h["label"] == "Perfect macros")
        self.assertEqual(macros["amount"], "+10")
        harvests = [h for h in body["history"] if h["label"] == "Daily XP harvest"]
        self.assertEqual(len(harvests), 2)  # yesterday (40 XP) + today (50 XP)
        self.assertTrue(all(h["amount"] == "+2" for h in harvests))

    def test_energy_rest_day_bonus_history(self):
        DailyReadiness.objects.create(
            user=self.user, date=timezone.localdate(), score=30,
            streak_requirement=DailyReadiness.StreakRequirement.REST_DAY,
        )
        resp = self.client.get("/stats/energy/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["stat"], "energy")
        # The view refreshes resources, granting the +25 rest-day spike.
        self.assertEqual(body["value"], 25)
        bonus = next(
            h for h in body["history"] if h["label"] == "Rest-day energy bonus"
        )
        self.assertEqual(bonus["amount"], "+25")
        fact_labels = [f["label"] for f in body["facts"]]
        self.assertIn("Energy cap", fact_labels)
        self.assertIn("Passive regen", fact_labels)



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

        resources = BaseResource.objects.get(user=self.user)
        self.assertEqual(resources.time_speedups, WEEKLY_REWARDS[1]["time_speedups"])
        self.assertEqual(resources.materials, WEEKLY_REWARDS[1]["materials"])

    def test_close_week_is_idempotent(self):
        week = ensure_current_week()
        self._xp(self.user, 50)
        close_league_week(week)
        self.assertEqual(close_league_week(week), [])
        self.assertEqual(LeagueResult.objects.filter(week=week).count(), 1)
        # Rank-1 reward paid exactly once - the re-run must not double-pay.
        self.assertEqual(
            BaseResource.objects.get(user=self.user).time_speedups,
            WEEKLY_REWARDS[1]["time_speedups"],
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

    # ---- Base staff validation (real friends only) ----
    def test_base_staff_requires_real_friend(self):
        building_def = BaseBuildingDef.objects.create(
            slug="hut_staff", name="Hut", base_cost_materials=0,
            base_cost_energy=0, base_duration_hours=0,
        )
        building = BaseBuilding.objects.create(
            user=self.user, building_def=building_def, level=1
        )
        # Non-friend rejected.
        resp = self.client.post(
            "/base/staff", data={"id": building.pk, "friend_id": self.other.pk},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        # Real friend accepted.
        self._make_friends_with_other()
        resp = self.client.post(
            "/base/staff", data={"id": building.pk, "friend_id": self.other.pk},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        building.refresh_from_db()
        self.assertEqual(building.staff_friend_id, self.other.pk)
        # Null un-staffs.
        resp = self.client.post(
            "/base/staff", data={"id": building.pk, "friend_id": None},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        building.refresh_from_db()
        self.assertIsNone(building.staff_friend_id)

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


