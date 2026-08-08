🔌 API Contracts

AI Context: Lightweight Django `JsonResponse` APIs (no DRF). The vanilla JS frontend consumes these via `fetch()`. All endpoints require authentication (Django session/cookie, served by the same project). All routes are prefixed `/api/v1/` and defined in `core/urls.py`.

Frontend Consumption APIs

GET /api/v1/dashboard/state

Returns the complete user state to render the dashboard shell.
Response:

{
  "user": { "username": "player1", "streak": 12 },
  "resources": { "materials": 150, "energy": 45 },
  "readiness": {
    "score": 42,
    "streak_requirement": "rest_day",
    "message": "Low battery! Streak is frozen today. Take a nap."
  },
  "skill_trees": {
    "strength": { "level": 4, "progress_pct": 85 },
    "endurance": { "level": 2, "progress_pct": 10 },
    "nutrition": { "level": 1, "progress_pct": 63 },
    "hydration": { "level": 1, "progress_pct": 40 }
  }
}

Each skill_tree entry carries: level, xp (within-level), total_xp, progress_pct.

GET /api/v1/nutrition/  (views.nutrition_state)

Returns today's nutrition summary, history, and the Nutrition skill-tree state.
Response:

{
  "linked": true,
  "demo": false,
  "today": {
    "date": "2026-08-07",
    "calories": 1980, "protein": 165, "carbs": 210, "fat": 60,
    "calories_goal": 2500, "protein_goal": 180,
    "perfect": false, "xp": 0, "materials": 0,
    "meals": [ { "name": "Breakfast", "calories": 520, "protein": 40 } ]
  },
  "history": [ ... same shape by day ... ],
  "skill_tree": { "level": 1, "xp": 63, "total_xp": 63, "progress_pct": 63 }
}

Meal `name` comes from SparkyFitness `food_name`; day keys come from `entry_date`.

GET /api/v1/hydration/  (views.hydration_state)

Returns today's water intake, history, and the Hydration skill-tree state.
Response:

{
  "linked": true,
  "demo": false,
  "today": {
    "date": "2026-08-07",
    "water": 84, "water_goal": 96, "water_pct": 88,
    "perfect": false, "xp": 0, "materials": 0,
    "water_intake_entries": [ { "time": "08:00", "amount": 24 } ]
  },
  "history": [ ... same shape by day ... ],
  "skill_tree": { "level": 1, "xp": 30, "total_xp": 30, "progress_pct": 30 }
}

GET /api/v1/endurance/  (views.endurance_state)

Returns SparkyFitness exercise entries and the Endurance skill-tree state.
Response:

{
  "linked": true,
  "demo": false,
  "today": {
    "date": "2026-08-07",
    "total_calories_burned": 630, "total_duration_minutes": 65,
    "exercise_count": 2, "xp": 63, "materials": 5,
    "exercise_entries": [
      { "name": "Morning Run", "calories_burned": 450, "duration_minutes": 35, "notes": "Zone 2 cardio" },
      { "name": "Evening Walk", "calories_burned": 180, "duration_minutes": 30, "notes": "Recovery walk" }
    ]
  },
  "history": [ ... same shape by day ... ],
  "skill_tree": { "level": 1, "xp": 63, "total_xp": 63, "progress_pct": 63 }
}

GET /api/v1/strength/  (views.strength_state)

Returns Liftosaur strength summaries (volume / duration / sets / PRs), the full
strength history, the strength skill-tree state, and whether Liftosaur is linked.
Response:

{
  "linked": true,
  "demo": false,
  "today": {
    "date": "2026-08-07",
    "program": "5/3/1", "day_name": "Squat Day",
    "duration_minutes": 55, "total_volume_lbs": 22000, "total_sets": 15,
    "exercise_count": 3, "xp": 43, "materials": 0, "pr": false, "completed": true,
    "exercises": [
      { "name": "Squat", "sets": 5, "reps": 5, "weight": 315, "unit": "lb",
        "volume_lbs": 7875, "est_1rm": 367.5 }
    ]
  },
  "history": [ ... same shape by day ... ],
  "best_lifts": [
    { "name": "Bench Press", "weight": 265, "reps": 5, "unit": "lb", "est_1rm": 309.2, "date": "2026-08-07" }
  ],
  "skill_tree": { "level": 1, "xp": 43, "total_xp": 43, "progress_pct": 43 }
}

GET /api/v1/boss/  (views.boss_state)

Compares the user's best lifts against admin-configured PR Boss bodyweight
benchmarks (BossConfig). Response:

{
  "bodyweight": 180.0,
  "linked_liftosaur": true,
  "bosses": [
    { "name": "Bench Press", "exercise_match": "Bench Press", "multiplier": 1.5,
      "goal": 270.0, "best_lift": 309.2, "conquered": true, "progress_pct": 100 }
  ]
}

GET /api/v1/leaderboard/weekly

Returns the asymmetric XP leaderboard.
Response:

{
  "leaderboard": [
    {"username": "player1", "total_xp": 450, "avatar": "/img/a1.png"},
    {"username": "housemate", "total_xp": 320, "avatar": "/img/a2.png"}
  ]
}

Integration APIs (Webhooks)

POST /api/v1/webhooks/home-assistant

Endpoint for Home Assistant to send local events (e.g., smart scale reading, fridge opened).
Payload:

{
  "entity_id": "sensor.smart_scale",
  "state": "85.2",
  "attributes": {"unit": "kg"}
}

