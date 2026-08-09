"""Tests for the Flamingo Fitness gamification + API layers.

Run with:  python manage.py test core
"""

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from core.models import (
    BaseBuilding,
    BaseBuildingDef,
    BaseResource,
    BossConfig,
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
        b = BaseBuilding.objects.create(user=self.user, building_def=self.lawn, level=1)
        resp = self.client.post("/base/staff", data={"id": b.pk, "friend_id": 7}, content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        b.refresh_from_db()
        self.assertEqual(b.staff_friend_id, 7)
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

