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

Strength (Liftosaur) (`strength_xp`)

Base Volume: 1 XP per 1,000 lbs moved (volume).

Completion Bonus: +20 XP for finishing a programmed workout.

Example: 15,000 lb volume workout + completion = 35 XP.

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