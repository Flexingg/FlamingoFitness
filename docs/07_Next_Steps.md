📋 Next Steps: AI Agent Build Sequence

AI Context: This document outlines the 20-step build sequence for the "Flamingo Fitness" application. When completing a step, refer to the corresponding documentation in the docs/ folder for exact specifications.

Phase 1: Infrastructure & Scaffolding

Goal: Get the basic skeleton of the app running in Docker.

[ ] Step 1: Project Initialization: Create the base Django project (django-admin startproject flamingo_fitness) and set up the folder structure.

[ ] Step 2: Docker Compose Setup: Generate the docker-compose.yml file as specified in 05_docker_infrastructure.md (include Postgres, Redis, Django Web, Celery Worker, Celery Beat).

[ ] Step 3: Dependency Management: Create the requirements.txt file (Django, psycopg2-binary, redis, celery, requests, gunicorn).

[ ] Step 4: Database Configuration: Update settings.py to use PostgreSQL (via environment variables) and configure Redis as the caching/Celery broker backend.

Phase 2: Core Data Models

Goal: Build the Postgres database schema. (Reference: 01_database_schema.md)

[ ] Step 5: User Models: Implement the custom User model (extending AbstractUser) and the UserIntegration model for storing API credentials.

[ ] Step 6: ELT & Ledger Models: Implement the RawActivityLog (using JSONField) and the XPLedger models.

[ ] Step 7: Gamification Models: Implement the SkillTree and DailyReadiness models.

[ ] Step 8: Django Admin: Create admin.py configurations for all models so we can easily view and manipulate data via the Django admin panel during development. Create the initial database migrations.

Phase 3: Data Ingestion & Async Workers

Goal: Set up the Celery pipelines to pull data from external APIs without blocking the main web thread.

[ ] Step 9: Celery Configuration: Initialize Celery in the Django project (celery.py and __init__.py) routing tasks to the Redis broker.

[ ] Step 10: Mock API Clients: Create a services/api_clients.py file with mock classes for Garmin, Peloton, and Liftosaur that return dummy JSON data representing real payloads.

[ ] Step 11: Polling Tasks: Write the Celery tasks (tasks.py) that iterate through UserIntegration records, call the mock API clients, and save the results into RawActivityLog.

[ ] Step 12: Celery Beat Schedule: Configure the Celery Beat schedule in settings.py to run the polling tasks at regular intervals (e.g., Garmin every 2 hours, Peloton every 4 hours).

Phase 4: Gamification Service Layer

Goal: Convert raw JSON payloads into XP and update user state. (Reference: 03_gamification_math.md)

[ ] Step 13: XP Calculator Service: Create services/gamification.py. Write functions to parse RawActivityLog JSON payloads and generate XPLedger entries based on the Endurance, Strength, and Recovery math.

[ ] Step 14: Skill Tree Progression Logic: Write the function that listens for new XPLedger entries and updates the user's SkillTree levels and XP balances.

[ ] Step 15: Readiness Engine: Write the logic that parses morning Garmin Body Battery/Sleep payloads to generate the DailyReadiness record (mandating rest days or heavy training).

Phase 5: API Endpoints

Goal: Expose the backend data to the frontend. (Reference: 02_api_contracts.md)

[ ] Step 16: Dashboard API: Create the GET /api/v1/dashboard/state endpoint using Django's JsonResponse to serve the user's stats, readiness, and skill tree data.

[ ] Step 17: Leaderboard API: Create the GET /api/v1/leaderboard/weekly endpoint that aggregates the XPLedger to return the asymmetric competitive rankings.

[ ] Step 18: Home Assistant Webhook: Create the POST /api/v1/webhooks/home-assistant endpoint to accept inbound data from the smart home. (Reference: 06_home_assistant_spec.md)

Phase 6: Frontend Integration & PWA

Goal: Bring the Miami/Duolingo UI to life with real data. (Reference: 04_frontend_architecture.md)

[ ] Step 19: Django Templates Setup: Move the existing standalone index.html prototype into Django's template directory and configure the root URL to serve it.

[ ] Step 20: Vanilla JS Data Fetching & PWA: Replace the static HTML data with a vanilla JavaScript fetch() call to /api/v1/dashboard/state on page load. Finally, add the manifest.json and basic service-worker.js to make the app installable on iOS/Android.