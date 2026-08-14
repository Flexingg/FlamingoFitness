🗒️ Flamingo Fitness — Living Decision Log

AI Context: Architecture decisions and answers surfaced during implementation. Append new decisions here so a future AI doesn't repeat the same mistakes.

Q: What tech stack rules apply?
A: Vanilla HTML/CSS/JS on the frontend, Django + Postgres + Celery/Redis in Docker. No React/Vue/Node. See `00_AI_Overview.md`.

Q: How is demo vs real data handled?
A: Gated behind the `DEMO` env var (default `False`). `DEMO=True` makes `SparkyFitnessClient.fetch()` return realistic mock payloads and `create_demo_accounts` provisions demo users. Production (DEMO off) surfaces the "Link SparkyFitness" CTA.

Q: Demo logins?
A: `admin` / `adminpass123` (superuser) and `player1` / `playerpass123` (`core/management/commands/create_demo_accounts.py`). Idempotent; auto-runs on web container start.

Q: What is the ELT ingestion pattern?
A: Vendor payloads land as raw JSON in `RawActivityLog` (source, event_type, payload, occurred_at). The gamification service (`process_log` / `process_payload`) parses them, writes `XPLedger` rows, advances the matching `SkillTree`, and marks the log processed.

Q: Which skill-tree modalities exist?
A: strength, endurance, nutrition, hydration, recovery. `Modality` TextChoices in `core/models.py`. Strength and Recovery have no detail endpoint/view yet.

Q: Why did `/api/v1/endurance/` return a 500 at one point?
A: The view imported `summarize_endurance` from `core.services`, but it had not been re-exported in `core/services/__init__.py`. Every new `summarize_*` must be added to that __init__ import list.

Q: Why did the Endurance panel show a "Water 0/0 oz" bar?
A: `endurance.js` was created by copy-pasting `hydration.js` and only renaming identifiers — the rendering logic still read water fields. Lesson: when porting a controller, port the payload-fields-to-render mapping too, not just the function names. See `04_Frontend_Architecture.md`.

Q: Why did clicking the Endurance node do nothing?
A: The node had no click handler. Fix: put explicit `onclick="loadEndurance()"` on the node button in the template (more robust than only relying on a DOMContentLoaded `addEventListener`). Same applied to Nutrition/Hydration nodes.

Q: Which SparkyFitness payload fields matter that were easy to get wrong?
A: Meal name → `food_name`; diary day → `entry_date` (not `date`); exercise entries → `calories_burned`, `duration_minutes`. See `10_Sparky_Fitness_Integration.md`.

Q: How is the Weekly Leagues modal auto-popup throttled?
A: `localStorage` key `ff_last_league_modal`; it only auto-shows once per 7-day window (then it's manual via the nav).

Q: XP progression model?
A: One skill-tree level = 100 XP (`XP_PER_LEVEL`). `SkillTree.xp` tracks within-level XP; `progress_pct` = xp/100.

Q: How does the Strength skill tree award XP?
A: Liftosaur workouts: +1 XP per 1,000 lbs moved, +20 XP completion bonus, +1 XP per 30 minutes lifted. Parsed from `record.text` via `core/services/liftosaur_client.parse_history_record_text` (Epley est. 1RM: weight * (1 + reps/30)).

Q: How do PR Bosses work?

Q: How do Phase 8 leagues work (tiers / week close / rewards)?
A: `LeagueWeek` rows are Monday-anchored (`week_start_for`). `ensure_current_week()` lazily closes stale open weeks (snapshotting `LeagueResult` rank/tier rows and paying top-3 rewards: 5/3/1 speedups + 25/15/10 materials) and opens the current week, so a beat outage never loses a snapshot. Tiers are a pure function of weekly XP (0/100/300/600/1000 → bronze/silver/gold/diamond/flamingo_legend) - no stored promotion/relegation yet. The Monday beat task `close_league_week_task` does the same rollover; everything is idempotent by stored status/dates. The legacy rolling `GET /leaderboard/weekly` + dashboard auto-popup modal are untouched.

Q: Why is there only ever one active challenge, and what is the default?
A: `Challenge.save()` deactivates every other row when a challenge is activated (single-active rule at the model layer, admin-proof). `create_demo_accounts` seeds the default `calories_burned_30d` ("Calorie Torch"): calories burned in the last 30 days, derived live from `RawActivityLog` payloads (`endurance.total_calories_burned` + `cardio.calories`) - no stored progress, so every sync re-ranks the board. Progress window = last `window_days` calendar days including today.

Q: How do friendships handle direction?
A: A pair can hold at most one row per direction (`unique_friendship_direction`). "Friends" = an accepted row in EITHER direction - always query `Q(from_user=a, to_user=b) | Q(from_user=b, to_user=a)` (see `get_friendship`). Sending a request while a REVERSE pending request exists auto-accepts it (both sides asked). Declining deletes the pending row.

Q: What are the Flock rules?
A: Up to 8 members (`FLOCK_MAX_MEMBERS`), one flock per user (`FlockMembership.user` OneToOne), only owners invite, only friends can be invited, and invitees must be flockless. The last member leaving deletes the flock (cascades invites) to keep the DB tidy. Flock standings reuse the league week's XP window (`weekly_xp_map`).

Q: Why did the Phase 8 tests run so slowly at first, and why does base-staff now 400?
A: (1) PBKDF2 hashing ~0.5s per `create_user` made the suite take minutes - `flamingo_fitness/test_settings.py` (the local SQLite shim) now sets `PASSWORD_HASHERS = [MD5PasswordHasher]` so tests run in ~1 minute; Docker/prod keep real hashers. (2) `POST /base/staff` validates `friend_id` against REAL accepted friendships (docs/12 §3 retired the Phase 7 mocked staff list) - null still un-staffs; the old `test_staff_and_unstaff` was updated to create a real friend first.

Q: Why did BadgeTests start failing before Phase 8 even touched badges?
A: Pre-existing drift: `core/services/badges.py` (untracked at the time) had grown the catalog from 8 to 58 badges while the tests hard-coded 8/325. Fixed by deriving expectations from `BADGE_CATALOG` (`len(...)` / `sum(points)`) instead of magic numbers, so catalog growth never breaks tests again.

A: `BossConfig` rows (admin-configurable) define benchmarks as `exercise_match` + `bodyweight_multiplier`. Threshold = SparkyFitness bodyweight x multiplier. `/api/v1/boss/` compares the user's best est. 1RM for the match against the threshold; conquering triggers boss-fight 2x XP + Time Speed-ups. Bodyweight comes from SparkyFitness `scale`/check-in RawActivityLog payloads (`weight`).

Q: Why did Liftosaur raw logs appear "never generated"?
A: The profile's Link & Sync originally delegated to the Celery `poll_liftosaur` task, which silently swallowed errors and gave no feedback. Fix: `profile()` (core/views.py) now calls `LiftosaurClient().fetch(integration, days=30)` directly and persists results through `core/tasks.py ingest_results()` synchronously, showing "Synced N day(s) of data." Note `DEMO=False` means a blank API key yields no data (by design).
Q: Why did Liftosaur raw logs appear "never generated"?
A: The profile's Link & Sync originally delegated to the Celery `poll_liftosaur` task, which silently swallowed errors and gave no feedback. Fix: `profile()` (core/views.py) now calls `LiftosaurClient().fetch(integration, days=30)` directly and persists results through `core/tasks.py ingest_results()` synchronously, showing "Synced N day(s) of data." Note `DEMO=False` means a blank API key yields no data (by design).

Q: Why did skill trees show 0 XP for sub-100 XP grants (Phase 7 validation)?
A: `apply_to_skill_tree` only called `tree.save()` *inside* the level-up `while` loop, so any per-log XP under `XP_PER_LEVEL` (100) was mutated in memory but never persisted. Fix: save once after the loop (`tree.save(update_fields=["level","xp","total_xp"])`) for every grant. This surfaced as `test_cardio_log_generates_endurance_xp_and_updates_tree`, `test_skill_tree_level_up`, and `test_endpoint_returns_summary_and_history` all failing with 0 XP.

Q: How is the base-building economy kept fresh in production?
A: A daily Celery beat task `core.tasks.tick_base_economy_daily` (register in settings `CELERY_BEAT_SCHEDULE`: `crontab(minute=5, hour=0)`) wraps the pure `tick_base_economy()` helper: energy refill, daily XP→materials harvest, expired-buff cleanup, lazy construction completion, and whole-day auto-collect (no crits in the background — crits stay a manual-collect thrill). Every action is stamped by `last_*_date`/`energy_updated_at`, so it is idempotent and safe if run twice.

Q: What are the Phase 7 base-economy facts a future AI should not re-derive?
A: (1) Energy overflow: passive regen caps at `ENERGY_CAP=100` and never *reduces* a wallet already above the cap; the `REST_DAY_ENERGY_BONUS` (+25) *ignores* the cap and is gated per date via `last_rest_bonus_date`. (2) Production uses a whole-day floor (`elapsed_days // 1`), the streak multiplier `1 + min(streak,10)*0.05` (max 1.5x), `STAFF_BONUS=1.10`, and `MODALITY_BUFF=1.20` on unexpired affinity buffs. (3) Manual collect rolls `CRIT_CHANCE=0.05` (`was_crit` doubles yield). (4) A boss-PR strength log rolls a `BLUEPRINT_DROP_CHANCE=0.10` `golden_flamingo` drop. (5) XP bonuses from buildings are capped at `MAX_XP_BONUS_PCT=25`.

Q: This app only ever did GETs — how do the new POSTs avoid 403s?
A: Every new `fetch` POST sends `X-CSRFToken` read from a `<meta name="csrf-token" content="{{ csrf_token }}">` tag (added to `dashboard.html` `<head>`). Django's CSRF middleware validates the token before the view runs, so a POST without it returns 403 (asserted in `BaseAPITests.test_csrf_403_without_token`).

Q: Why add `seed_demo.py` alongside `create_demo_accounts.py`?
A: `create_demo_accounts.py` is the production startup command (idempotent: demo users, integrations, base catalog, demo instances, PR Boss benchmarks). `seed_demo.py` is a dev/standalone helper that first calls `create_demo_accounts` and then runs the mock pollers once (Garmin/Peloton/Liftosaur always; SparkyFitness only when `DEMO=True`) so the dashboard shows live-looking XP/skill-tree data. Keep the catalog + demo-instance seeding inside `create_demo_accounts` so first-boot stays alive in Docker/Portainer.

