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
A: `BossConfig` rows (admin-configurable) define benchmarks as `exercise_match` + `bodyweight_multiplier`. Threshold = SparkyFitness bodyweight x multiplier. `/api/v1/boss/` compares the user's best est. 1RM for the match against the threshold; conquering triggers boss-fight 2x XP + Time Speed-ups. Bodyweight comes from SparkyFitness `scale`/check-in RawActivityLog payloads (`weight`).

Q: Why did Liftosaur raw logs appear "never generated"?
A: The profile's Link & Sync originally delegated to the Celery `poll_liftosaur` task, which silently swallowed errors and gave no feedback. Fix: `profile()` (core/views.py) now calls `LiftosaurClient().fetch(integration, days=30)` directly and persists results through `core/tasks.py ingest_results()` synchronously, showing "Synced N day(s) of data." Note `DEMO=False` means a blank API key yields no data (by design).

