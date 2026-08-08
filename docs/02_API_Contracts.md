🔌 API Contracts

AI Context: This is a Django REST Framework (or lightweight Django JSONResponse) API spec. The Vanilla JS frontend will consume these. All endpoints require authentication (Session/Cookie based since frontend is served by Django).

Frontend Consumption APIs

GET /api/v1/dashboard/state

Returns the complete user state to render the UI.
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
    "endurance": { "level": 2, "progress_pct": 10 }
  }
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

Endpoint for HA to send local events (e.g., smart scale reading, fridge opened).
Payload:

{
  "entity_id": "sensor.smart_scale",
  "state": "85.2",
  "attributes": {"unit": "kg"}
}
