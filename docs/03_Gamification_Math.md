🧮 Gamification Math (The Rulebook)

AI Context: Formulas are implemented in `core/services/gamification.py` (docs/03). The engine (`process_payload` / `process_log`) reads `RawActivityLog` payloads and creates `XPLedger` entries, then advances the matching `SkillTree` automatically. One skill-tree level = `XP_PER_LEVEL = 100` XP.

The Asymmetric XP System (Base Multipliers)

1 XP = Roughly 1 minute of moderate effort.

Endurance - Peloton / Garmin Cardio (`endurance_xp`)

Zone 2/3 Cardio: Minutes × 1.0 XP

Zone 4/5 (HIIT): Minutes × 1.5 XP

Example: 45 min Peloton class at high intensity = 68 XP.

Endurance - SparkyFitness Exercise Entries (`summarize_endurance`)

Used by `/api/v1/endurance/`. XP is calorie-based, not minute-based:

xp = max(10, int(total_calories / 10)) when calories > 0, else 0

materials = 5 when total_calories >= 500, else 0

Example: 630 kcal day = +63 XP (and +5 Base Materials).

Strength (Liftosaur) (`strength_xp`, `session_time_xp`)

Base Volume: 1 XP per 1,000 lbs moved (volume).

Completion Bonus: +20 XP for finishing a programmed workout.

Time Bonus: +1 XP per 30 minutes in the gym (`session_time_xp`).

Phase 8 — Leagues & Challenges (docs/13, constants in core/services/leagues.py & challenges.py)

League tiers (pure function of weekly Effort XP):

- bronze 0+ · silver 100+ · gold 300+ · diamond 600+ · flamingo_legend 1000+

Weekly close rewards (paid to the ranked leaderboard when the week closes; additive only):

- Rank 1: +5 Time Speed-ups, +25 Materials
- Rank 2: +3 Time Speed-ups, +15 Materials
- Rank 3: +1 Time Speed-up, +10 Materials

Challenge metric "calories_burned" (default challenge, window = 30 days):

- Progress = SUM(endurance payload.total_calories_burned) + SUM(cardio payload.calories)
  over RawActivityLog rows in the last window_days calendar days (incl. today).
- Exactly ONE challenge may be active at a time (Challenge.save() deactivates the rest).
- No stored progress - the board is derived live on every read.


Example: 22,000 lb volume + completion + 55 min = 22 + 20 + 1 = 43 XP.

PR Boss (admin-configurable benchmarks)

Each admin `BossConfig` defines a benchmark like "Bench Press 1.5x bodyweight."
Threshold = latest bodyweight (SparkyFitness) x multiplier. When your best lift
(heaviest set or Epley est. 1RM) meets it, you "Conquer" the boss, which also
unlocks the boss-fight 2x XP reward and +5 "Time Speed-ups".

Recovery (Garmin Sleep / Body Battery) (`sleep_xp`, `body_battery_xp`)

Sleep Goal: 8 hours = 50 XP. (Pro-rated: 5-8h = 20 XP, < 5 hours = 0 XP).

Body Battery Charge: +1 XP for every point recovered overnight.

Nutrition (SparkyFitness macros) (`nutrition_xp`)

Perfect Macros: protein goal met AND under calorie limit = +50 XP (Nutrition Tree) and +10 Base Materials.

Hydration (SparkyFitness water intake) (`_handle_hydration`)

Perfect Hydration = total water intake >= water goal.

Reward: +30 XP (Hydration Tree) and +5 Base Materials per day.

Boss Fights & Perfect Lessons

Perfect Macros: Hitting protein goal exactly while under calorie limit = +50 XP (Nutrition Tree) and generates 10 "Base Materials".

Boss Fight (Weekly PR): Hitting a new 1RM or top 10% Peloton output yields a 2x multiplier for that workout's XP and generates 5 "Time Speed-ups" for the base-builder.