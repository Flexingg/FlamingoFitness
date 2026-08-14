🗄️ Flamingo Fitness Database Schema (PostgreSQL)

AI Context: Django ORM models live in `core/models.py`. PostgreSQL (via `psycopg2`). Migrations live in `core/migrations/`. Run `python manage.py makemigrations core && python manage.py migrate` after model changes.

Custom User

`core.User(AbstractUser)`

- username, email, password (inherited)
- streak: PositiveIntegerField (consecutive-day streak, protected by readiness)
- avatar: URLField (dicebear default)

`@property total_xp` = SUM(XPLedger.amount) for the user.

`Modality` TextChoices (skill-tree tracks)

- strength
- endurance
- nutrition
- hydration  (NEW)
- recovery

`Provider` TextChoices (external data sources)

- garmin
- peloton
- liftosaur
- sparkyfitness
- home_assistant

UserIntegration

Per-user API credential storage (one row per user/provider).

- user FK -> User (related_name="integrations")
- provider CharField(choices=Provider)
- credentials JSONField (OAuth tokens / API keys)
- is_active Bool default True
- last_polled DateTime null
- UniqueConstraint("user", "provider") = unique_user_provider

RawActivityLog (JSONB ELT inbox)

Webhooks and pollers drop unprocessed JSON here.

- user FK -> User (related_name="raw_logs")
- source CharField(choices=Provider)
- event_type CharField (e.g. "cardio", "strength", "sleep", "macro", "hydration", "endurance")
- payload JSONField (raw vendor JSON; see docs/10 & docs/11 for shapes)
- occurred_at DateTime (when the activity actually happened)
- processor_version CharField (for idempotent re-processing)
- processed Bool default False

XPLedger

- user FK -> User (related_name="xp_entries")
- modality CharField(choices=Modality)
- amount Int (positive = award, negative = correction)
- description CharField (reason string)
- created_at DateTime (auto)
- Indexes on (user, created_at) and (modality)

SkillTree

Per-user, per-modality progression.

- user FK -> User (related_name="skill_trees")
- modality CharField(choices=Modality)
- level PositiveInteger default 1
- xp PositiveInteger (XP *within* the current level, 0..XP_PER_LEVEL)
- total_xp PositiveInteger (lifetime XP in this modality)
- UniqueConstraint("user","modality") = unique_user_modality
- @property progress_pct = int(xp / XP_PER_LEVEL * 100)

DailyReadiness

Readiness engine output (sleep + body battery).

Phase 8 — Leagues, Challenges & Flocks (migration `0007`, docs/13)

`LeagueTier` TextChoices (weekly tiers by Effort XP)

- bronze / silver / gold / diamond / flamingo_legend

LeagueWeek

- week_start DateField unique (Monday, local)
- status CharField (open / closed) default open
- closed_at DateTime null
- @property week_end = week_start + 6 days

LeagueResult (per-user snapshot written when a week closes)

- week FK -> LeagueWeek (related_name="results")
- user FK -> User (related_name="league_results")
- xp Int, rank PositiveInt, tier CharField(choices=LeagueTier)
- reward JSONField default dict (e.g. {"time_speedups": 5, "materials": 25})
- UniqueConstraint("week", "user") = unique_week_user_result

Challenge (admin-configurable rolling challenges)

- slug SlugField unique, name, description, icon
- metric CharField choices (calories_burned) default calories_burned
- window_days PositiveInt default 30
- is_active Bool default True — `save()` deactivates all others (single-active)
- sort_order Int

Friendship

- from_user FK -> User (related_name="friend_requests_sent")
- to_user FK -> User (related_name="friend_requests_received")
- status CharField (pending / accepted) default pending
- UniqueConstraint("from_user", "to_user") = unique_friendship_direction
- Friends = accepted row in EITHER direction

Flock

- name CharField(80), icon CharField(60) default "fa-dove"
- created_by FK -> User (SET_NULL, null) related_name="flocks_created"

FlockMembership

- flock FK -> Flock (related_name="memberships")
- user OneToOne -> User (related_name="flock_membership") — one flock per user
- role CharField (owner / member) default member

FlockInvite

- flock FK -> Flock (related_name="invites")
- user FK -> User (related_name="flock_invites")
- invited_by FK -> User (SET_NULL, null) related_name="flock_invites_sent"
- status CharField (pending / accepted / declined) default pending
- UniqueConstraint("flock", "user") = unique_flock_invite


- `StreakRequirement` TextChoices: REST_DAY ("rest_day"), TRAIN ("train")
- user FK -> User (related_name="readiness_records")
- date DateField
- score PositiveInteger (0-100)
- streak_requirement CharField(default=TRAIN)
- message TextField
- body_battery PositiveInteger null
- sleep_hours Float null
- UniqueConstraint("user", "date")

BaseResource

Base-building meta-game resources.

- user OneToOne -> User (related_name="base_resources")
- materials PositiveInteger default 0
- energy PositiveInteger default 0
- time_speedups PositiveInteger default 0

BossConfig (admin-configurable PR Boss benchmarks)

A boss is a bodyweight-based lift benchmark, e.g. "Bench Press 1.5x bodyweight."

- name CharField (boss display name)
- exercise_match CharField (substring matched case-insensitively against Liftosaur exercise names)
- bodyweight_multiplier Float default 1.5 (threshold = bodyweight x multiplier)
- unit CharField default "lb"
- is_active Bool default True
- sort_order Int default 0
