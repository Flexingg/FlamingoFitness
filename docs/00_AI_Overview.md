🦩 Vibe Coding Overview: Project "Flamingo Fitness"

📖 The Main Idea

This project is a Duolingo-style fitness web app designed to incentivize healthy behavior through gamification. It aggregates disparate health data (sleep, nutrition, water intake, exercise/workouts, weightlifting, Peloton, Garmin) into a centralized PostgreSQL database.

Instead of just showing charts, the app uses this data to drive behavioral mechanics:

Readiness-Adjusted Streaks: Rest days are mandated or granted based on recovery metrics.

Modality Skill Trees: Progression tracks for Strength, Endurance, Nutrition, Hydration, and Recovery with interactive day-detail views, XP progress bars, and a bodyweight-based PR Boss benchmark panel.

Base-Building Meta-Game: XP and macros translate into resources to build a virtual idle base (e.g., building out a Miami beach club).

Asymmetric Leaderboards: A unified "Effort XP" allows users doing different activities to compete fairly.

Boss Fights & Perfect Lessons: Gamifying hard workout days and precision macro/hydration tracking.

🛠️ The Tech Stack (The Framework)

To keep the project lightweight, deployable, and easy to maintain, we are strictly using the following stack. AI Constraints: Do not introduce unnecessary frameworks (e.g., React, Vue, Node.js) unless explicitly requested.

Infrastructure: Docker Compose, designed to be deployed and managed via Portainer. Redis + Celery for async background polling. Demo account creation (`create_demo_accounts`) runs automatically on startup.

Database: PostgreSQL (using JSONB for flexible ELT webhook ingestion).

Backend: Python / Django. Handles data transformation, XP math, auth, demo environment gating (`DEMO` variable), and serves the REST APIs / Views.

Frontend: Vanilla HTML5, CSS3 (CSS Variables/Flexbox/Grid), and modular vanilla JavaScript (`dashboard.js`, `nutrition.js`, `hydration.js`, `endurance.js`). No heavy frontend frameworks.

Mobile Delivery: Progressive Web App (PWA). Mobile-first design, strictly utilizing a manifest.json and Service Workers.

Future Integration: Home Assistant (Webhooks/REST/MQTT) for smart home environmental triggers.

🗂️ AI Guidance Documentation Suite

docs/01_Database_Schema.md: The PostgreSQL/Django schema (User, RawActivityLog, XPLedger, SkillTree, DailyReadiness).

docs/02_API_Contracts.md: The REST API endpoints (`/dashboard/state`, `/nutrition/`, `/hydration/`, `/endurance/`, `/leaderboard/weekly`, webhooks).

docs/03_Gamification_Math.md: The "Effort XP" rulebook across all modalities.

docs/04_Frontend_Architecture.md: Guidelines for Vanilla JS component structure, Miami/Flamingo design tokens, modal detail views, and PWA setup.

docs/05_Docker_Infrastructure.md: The docker-compose.yml specs, environment variables, and network configurations.

docs/06_Home_Assistant_Spec.md: The blueprint for Home Assistant.

docs/07_Next_Steps.md: The roadmap and completed build sequence status.

docs/08_Questions.md: Living decision log and architecture choices.

docs/10_Sparky_Fitness_Integration.md: SparkyFitness API client, polling tasks, payload field mapping, and modality state endpoints.

docs/11_Liftosaur_Integration.md: Liftosaur API client and workout parser spec.
