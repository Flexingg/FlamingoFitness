🦩 Vibe Coding Overview: Project "Flamingo Fitness"

📖 The Main Idea

This project is a Duolingo-style fitness web app designed to incentivize healthy behavior through gamification. It aggregates disparate health data (sleep, nutrition, weightlifting, Peloton, Garmin) into a centralized PostgreSQL database.

Instead of just showing charts, the app uses this data to drive behavioral mechanics:

Readiness-Adjusted Streaks: Rest days are mandated or granted based on recovery metrics.

Modality Skill Trees: Separate progression tracks for Strength, Endurance, Nutrition, and Recovery.

Base-Building Meta-Game: XP and macros translate into resources to build a virtual idle base (e.g., building out a Miami beach club).

Asymmetric Leaderboards: A unified "Effort XP" allows users doing different activities to compete fairly.

Boss Fights & Perfect Lessons: Gamifying hard workout days and precision macro tracking.

🛠️ The Tech Stack (The Framework)

To keep the project lightweight, deployable, and easy to maintain, we are strictly using the following stack. AI Constraints: Do not introduce unnecessary frameworks (e.g., React, Vue, Node.js) unless explicitly requested.

Infrastructure: Docker Compose, designed to be deployed and managed via Portainer. Redis + Celery for async background polling.

Database: PostgreSQL (using JSONB for flexible ELT webhook ingestion).

Backend: Python / Django. Handles data transformation, XP math, auth, and serves the API/Views.

Frontend: Vanilla HTML5, CSS3 (CSS Variables/Flexbox/Grid), and vanilla JavaScript. No heavy frontend frameworks.

Mobile Delivery: Progressive Web App (PWA). Mobile-first design, strictly utilizing a manifest.json and Service Workers.

Future Integration: Home Assistant (Webhooks/REST/MQTT) for smart home environmental triggers.

🗂️ AI Guidance Documentation Suite

docs/01_database_schema.md: The PostgreSQL/Django schema.

docs/02_api_contracts.md: The REST API endpoints.

docs/03_gamification_math.md: The "Effort XP" rulebook.

docs/04_frontend_architecture.md: [UPDATED] Guidelines for the Vanilla JS component structure, Miami/Flamingo design tokens, and PWA setup.

docs/05_docker_infrastructure.md: [UPDATED] The docker-compose.yml specs and network configurations.

docs/06_home_assistant_spec.md: The blueprint for Home Assistant.