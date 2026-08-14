# 🏆 Phase 8 Plan: Leagues, Challenges & Flocks ("Social Flamingo")

> **STATUS: IMPLEMENTED** — built as Phase 8 (Steps 29–36, docs/07).
> Migration `0007`, `core/services/leagues.py` + `challenges.py` +
> `social.py`, the ten `/leagues|challenges|social|friends|flocks` endpoints,
> `core/static/core/js/leagues.js` (Board / Challenge / Flock tabs), the
> real-friend base-staff picker, the Monday `close_league_week_task` beat
> task, the demo seeding (Calorie Torch challenge + Flamingo Fam flock), and
> the test classes listed in §10 all exist. The checkboxes in `docs/07` are
> ticked to match. Original spec follows below.
>
> **UI tune-up (avatar uploads + streamlined boards):** the Leagues / Challenges
> / Flock panels now render a graceful default-avatar fallback for any blank or
> broken picture, an empty-state hint on the weekly board until you bank XP, and
> a clickable top-nav avatar. Players can upload their own profile picture from
> `/profile/` — `POST /api/v1/profile/avatar` persists the file under
> `MEDIA_ROOT` (`core/services/avatar.py`, magic-byte validation, no Pillow) and
> keeps the DiceBear default. The WhiteNoise middleware is subclassed
> (`flamingo_fitness/whitenoise.py`) so gunicorn serves `/media/*` in production.
> New tests: `AvatarUploadTests` in `core/tests.py`.
>
> **AI Context:** follow existing patterns — models in `core/models.py` +
> numbered migration; service modules re-exported from
> `core/services/__init__.py` (docs/08 ImportError lesson); vanilla-JS panel
> controllers (`loadX` / `backToX` / `renderX`); lazy per-panel APIs behind
> `@login_required` + CSRF meta-token POSTs (docs/08); seeding in
> `create_demo_accounts.py` (idempotent, auto-runs at web startup);
> validation loop `python manage.py test core
> --settings=flamingo_fitness.test_settings` + `node --check`.
>
> Grounded in docs/12 idea-bank items **#1** (Seasons / Ranked Leagues —
> completes parked `Step 8b`) and **#3** (Flamingo Flocks + real-friend
> staff). Purely additive: no existing reward amounts change.

---

## 1. Overview & Goals

Today the "Leagues" bottom-nav tab only pops a once-per-week modal listing the
top-5 of `GET /api/v1/leaderboard/weekly` (rolling 7-day XP). Phase 8 turns it
into a real destination with three tabs:

1. **Leaderboard (Leagues)** — a calendar-week league with live ranks, tier
   badges (Bronze → Flamingo Legend), the current user highlighted, and
   persisted weekly history + rewards when the week closes (the parked
   `Step 8b` payoff).
2. **Challenges** — admin-configurable, rolling-window community challenges.
   **Rule: exactly one challenge is active at a time.** The seeded default is
   **"Calorie Torch — most calories burned in the last 30 days"**, derived
   from data we already store (`RawActivityLog` endurance/cardio payloads).
3. **Flock (social)** — find players, send/accept friend requests, and form
   **Flocks** (groups of 1–8) with a shared weekly XP mini-leaderboard.
   Real friends also replace the Phase 7 *mocked* base-staff list
   (docs/12 §3): the Base "Staff" picker now offers actual friends, and
   `POST /base/staff` validates the pick.

North stars from docs/12: more recurring reasons to return (weekly close +
rolling challenge), and retention via people (friends/flocks helping each
other's bases).

## 2. The Core Loop

```text
train / log activities           -> Effort XP (existing)
open Leagues tab                 -> live weekly league board w/ tier + your rank
week closes (Monday beat/lazy)   -> ranks snapshot, top-3 rewards paid,
                                    result rows persist as history
challenge always on              -> rolling-30d calories-burned board;
                                    every sync re-ranks everyone live
find friends / accept requests   -> friends list powers Flock invites +
                                    real base-staff (+10% yield, existing math)
create/join a Flock              -> shared weekly XP mini-leaderboard
```

## 3. Rulebook Math (new constants for docs/03)

All tunables live as named constants at the top of
`core/services/leagues.py` / `challenges.py`.

### 3.1 League tiers (by weekly XP, live + snapshot)

| Tier             | Weekly XP ≥ |
|------------------|-------------|
| `bronze`         | 0           |
| `silver`         | 100         |
| `gold`           | 300         |
| `diamond`        | 600         |
| `flamingo_legend`| 1000        |

Promotion/relegation state-machines are deliberately **out of scope** for the
first slice (tiers are a pure function of weekly XP — no stored movement).

### 3.2 Weekly close rewards (existing sinks — additive only)

| Rank | Reward                                  |
|------|-----------------------------------------|
| 1    | +5 time_speedups, +25 materials         |
| 2    | +3 time_speedups, +15 materials         |
| 3    | +1 time_speedup,  +10 materials         |

Paid via the existing `award_resources` helper; the snapshot row stores the
reward dict so history can display it.

### 3.3 Challenge metric: `calories_burned` (window = 30 days)

Progress = over `RawActivityLog` rows with `occurred_at` in the last
`window_days` calendar days (including today):

- `event_type="endurance"` → `payload.total_calories_burned`
- `event_type="cardio"`    → `payload.calories`

Same derivation style as `core/services/badges.py _cardio_stats` — no new
ingestion. The challenge leaderboard is computed live (read-compute) over all
users; at household scale this is cheap and always fresh.

### 3.4 The "only one active challenge" rule

`Challenge.save()` deactivates every other row when `is_active=True` —
enforced at the model layer so the admin can't accidentally activate two.

## 4. Data Model Changes (`core/models.py` + migration `0007`)

### 4.1 `LeagueWeek` — one row per calendar week (parks Step 8b)

```python
class LeagueWeek(models.Model):
    week_start = models.DateField(unique=True)   # Monday (local)
    status     = models.CharField(choices=open/closed, default="open")
    closed_at  = models.DateTimeField(null=True, blank=True)
    class Meta: ordering = ["-week_start"]
```

### 4.2 `LeagueResult` — per-user snapshot written at week close

```python
class LeagueResult(models.Model):
    week   = FK(LeagueWeek, related_name="results", CASCADE)
    user   = FK(User, related_name="league_results", CASCADE)
    xp     = IntegerField(default=0)
    rank   = PositiveIntegerField(default=0)
    tier   = CharField(choices=tier choices, default="bronze")
    reward = JSONField(default=dict)   # {"time_speedups": 5, "materials": 25}
    unique(week, user)
```

### 4.3 `Challenge` — admin-configurable rolling challenges

```python
class Challenge(models.Model):
    slug        = SlugField(unique=True)
    name        = CharField(80)
    description = TextField(blank=True)
    icon        = CharField(60, default="fa-fire-flame-curved")
    metric      = CharField(choices=[("calories_burned", "Calories Burned")])
    window_days = PositiveIntegerField(default=30)
    is_active   = BooleanField(default=True)  # save() keeps exactly one active
    sort_order  = IntegerField(default=0)
    created_at  = DateTimeField(auto_now_add=True)
```

### 4.4 Social: `Friendship`, `Flock`, `FlockMembership`, `FlockInvite`

```python
class Friendship(models.Model):
    from_user = FK(User, related_name="friend_requests_sent", CASCADE)
    to_user   = FK(User, related_name="friend_requests_received", CASCADE)
    status    = CharField(pending | accepted, default="pending")
    created_at / updated_at
    unique(from_user, to_user)
    # A pair is "friends" iff an accepted row exists in either direction.

class Flock(models.Model):
    name       = CharField(80)
    icon       = CharField(60, default="fa-dove")
    created_by = FK(User, SET_NULL, null=True, related_name="flocks_created")
    created_at

class FlockMembership(models.Model):
    flock = FK(Flock, related_name="memberships", CASCADE)
    user  = OneToOne(User, related_name="flock_membership", CASCADE)  # one flock per user
    role  = CharField(owner | member, default="member")
    joined_at

class FlockInvite(models.Model):
    flock  = FK(Flock, related_name="invites", CASCADE)
    user   = FK(User, related_name="flock_invites", CASCADE)
    status = pending | accepted | declined
    unique(flock, user)
```

> **Gotcha:** `JSONField(default=dict)` must pass the *callable* `dict`
> (classic Django pitfall, docs/09). `FlockMembership.user` is a `OneToOne`
> so "leave/join" logic never juggles multiple memberships.

## 5. Service Layer

Three new modules, all re-exported from `core/services/__init__.py`
(docs/08 endurance-500 lesson). Every time-sensitive helper accepts
`now=None`; dates use `timezone.localdate()`.

### 5.1 `core/services/leagues.py`

- Constants: `LEAGUE_TIERS` ordered thresholds, `WEEKLY_REWARDS`
  `{1: {...}, 2: {...}, 3: {...}}`, `LEAGUE_TOP_N_REWARDED = 3`.
- `week_start_for(on_date)` → Monday of that local week.
- `tier_for_xp(xp)` → tier key.
- `weekly_xp_rows(since, until=None)` → `[{user, xp}, ...]` sorted desc via
  `XPLedger` aggregation (same query shape as `leaderboard_weekly`).
- `ensure_current_week(now=None)` → the open `LeagueWeek` for the current
  Monday; lazily **closes any stale open weeks first** (so a beat outage
  never loses a week).
- `close_league_week(week, now=None)` → snapshot ranks/tiers into
  `LeagueResult`, pay `WEEKLY_REWARDS` via `award_resources`, mark closed.
  Idempotent (no-op on a closed week).
- `league_state(user, now=None)` → full `GET /leagues/` payload (§6.1).

### 5.2 `core/services/challenges.py`

- `calories_burned_in_window(user, days, now=None)` → int (§3.3).
- `active_challenge()` → the (single) active `Challenge` or None.
- `challenge_leaderboard(challenge, now=None)` → all users ranked by
  window-progress (zero-score users omitted except the requester, so the
  panel always shows "you").
- `challenge_state(user, now=None)` → `GET /challenges/` payload (§6.2).

### 5.3 `core/services/social.py`

Friends:
- `send_friend_request(from_user, username)` → `(ok, error_or_friendship)`.
  Rules: no friending yourself; if the *reverse* pending request exists it
  is **auto-accepted** (both sides asked); duplicate accepted/pending rows
  are friendly 400s, not 500s.
- `respond_friend_request(user, from_user_id, accept)` — only the recipient
  can respond.
- `remove_friend(user, friend_id)` — deletes the accepted row (either dir).
- `friends_of(user)` → queryset of accepted friend `User`s.
- `search_users(query, viewer, limit=10)` → username icontains, excludes the
  viewer, annotates relationship state.

Flocks (up to 8 members per docs/12):
- `FLOCK_MAX_MEMBERS = 8`.
- `create_flock(user, name)` → owner membership; 400 if already in a flock.
- `invite_to_flock(inviter, user_id)` → only an owner invites, only friends,
  target must be flockless; upserts a pending invite.
- `respond_flock_invite(user, flock_id, accept)` → joins (capacity check) or
  declines.
- `leave_flock(user)` → last member leaving deletes the flock (keeps DB tidy).
- `flock_weekly_standings(flock, now=None)` → member rows with XP since the
  current `week_start` (shared mini-leaderboard, docs/12 §3).
- `social_state(user, q=None, now=None)` → `GET /social/` payload (§6.3).

Base-staff hook: `base_staff` view validates `friend_id` against
`friends_of(request.user)` — null still un-staffs.

## 6. API Contracts (`core/views.py` + `core/urls.py`)

All under `/api/v1/` (and `/` — core.urls is mounted at both), session-auth,
`@login_required`. POSTs are `@require_POST` + JSON body via the existing
`_load_base_post_body`, errors via `_json_error(message, status)`.

### 6.1 `GET /api/v1/leagues/`

```json
{
  "week": { "week_start": "2026-08-10", "week_end": "2026-08-16",
            "status": "open", "days_left": 3 },
  "tiers": [ {"tier": "flamingo_legend", "label": "Flamingo Legend", "min_xp": 1000} ],
  "my_tier": "gold",
  "my_rank": 2,
  "leaderboard": [
    { "rank": 1, "username": "player1", "avatar": "...", "xp": 450,
      "tier": "gold", "is_you": false }
  ],
  "history": [
    { "week_start": "2026-08-03", "rank": 1, "xp": 510, "tier": "diamond",
      "reward": { "time_speedups": 5, "materials": 25 } }
  ]
}
```

The legacy `GET /leaderboard/weekly` endpoint stays untouched (dashboard
auto-popup still uses it).

### 6.2 `GET /api/v1/challenges/`

```json
{
  "challenge": {
    "slug": "calories_burned_30d", "name": "Calorie Torch",
    "description": "Most calories burned in the last 30 days.",
    "icon": "fa-fire-flame-curved", "metric": "calories_burned",
    "window_days": 30, "unit": "kcal"
  },
  "my_progress": 6320,
  "leaderboard": [
    { "rank": 1, "username": "player1", "avatar": "...", "progress": 6320, "is_you": true }
  ]
}
```

`challenge` is `null` when none is active (UI shows an empty state).

### 6.3 `GET /api/v1/social/?q=` (optional search term)

```json
{
  "friends": [ { "id": 2, "username": "admin", "avatar": "...",
                 "weekly_xp": 120, "same_flock": true } ],
  "incoming_requests": [ { "id": 3, "username": "newbie", "avatar": "..." } ],
  "outgoing_requests": [ { "id": 4, "username": "someone", "avatar": "..." } ],
  "flock": {
    "id": 1, "name": "Flamingo Fam", "icon": "fa-dove", "member_count": 2,
    "max_members": 8, "my_role": "owner", "weekly_total_xp": 570,
    "members": [ { "id": 2, "username": "admin", "avatar": "...",
                   "role": "member", "weekly_xp": 120, "is_you": false } ]
  },
  "flock_invites": [ { "id": 2, "name": "Beach Squad", "icon": "fa-dove",
                       "member_count": 3, "invited_by": "admin" } ],
  "search_results": [ { "id": 5, "username": "randy", "avatar": "...",
                        "relationship": "none" } ]
}
```

`relationship` ∈ `none | pending_out | pending_in | friends`.

### 6.4 Mutating endpoints

| Endpoint | Body | Behavior / errors |
|----------|------|-------------------|
| `POST /friends/request`  | `{"username": "randy"}` | Creates pending (or auto-accepts reverse). 404 unknown user; 400 self/duplicate. |
| `POST /friends/respond`  | `{"user_id": 3, "action": "accept"\|"decline"}` | Recipient-only. 404 when no pending request. |
| `POST /friends/remove`   | `{"user_id": 2}` | Deletes accepted friendship. 404 when not friends. |
| `POST /flocks/create`    | `{"name": "Beach Squad"}` | 400: already in a flock / blank name / >80 chars. |
| `POST /flocks/invite`    | `{"user_id": 2}` | Owner-only; target must be a friend without a flock. |
| `POST /flocks/respond`   | `{"flock_id": 1, "action": "accept"\|"decline"}` | Capacity check → 400 "Flock is full". |
| `POST /flocks/leave`     | `{}` | Last member leaving deletes the flock. |

Every mutating view returns the fresh `social_state(request.user)` snapshot
(same pattern as the `/base/*` endpoints) so the UI re-renders without a
second fetch.

### 6.5 `core/urls.py` additions

```python
# Phase 8: Leagues, Challenges & Flocks
path("leagues/", views.leagues_state, name="leagues_state"),
path("challenges/", views.challenges_state, name="challenges_state"),
path("social/", views.social_state, name="social_state"),
path("friends/request", views.friends_request, name="friends_request"),
path("friends/respond", views.friends_respond, name="friends_respond"),
path("friends/remove", views.friends_remove, name="friends_remove"),
path("flocks/create", views.flocks_create, name="flocks_create"),
path("flocks/invite", views.flocks_invite, name="flocks_invite"),
path("flocks/respond", views.flocks_respond, name="flocks_respond"),
path("flocks/leave", views.flocks_leave, name="flocks_leave"),
```

## 7. Frontend (Vanilla JS, Miami/Duolingo polish)

### 7.1 Files touched

- `core/templates/core/dashboard.html` — new `<section id="leagues-view">`
  with a 3-tab header (Leaderboard / Challenges / Flock), `#leagues-content`
  container, a generic `#friend-picker-modal` overlay (used by base staff +
  flock invites), `nav-leagues` onclick switched to `loadLeagues()`,
  `leagues.js` script tag.
- `core/static/core/js/leagues.js` — **NEW** controller (model on
  `badges.js` / `recovery.js` contract: `loadX` / `backToX` / `renderX`,
  functions on `window.*`).
- `core/static/core/js/dashboard.js` — the `nav-leagues` click listener
  delegates to `window.loadLeagues` when present (the boot-time auto-popup
  modal stays as-is, docs/08 throttle key untouched).
- `core/static/core/js/base.js` — Staff action opens the real-friend picker
  (fetch `/api/v1/social/`, list `friends`) instead of `prompt()`; POSTs the
  chosen `friend_id` to `/base/staff` (docs/12 §3 payoff).
- `core/static/core/css/dashboard.css` — leagues tab bar, rank rows
  (top-3 medals, `.row-you` highlight), tier chips (bronze…legend colors),
  challenge progress bar reusing `.nutrition-xp-bar*`, flock cards, friend
  picker modal.

### 7.2 `leagues.js` behavior

- `window.loadLeagues()` — hide `#skill-tree` + other panels, show
  `#leagues-view`, default tab `leaderboard`, fetch lazily per tab.
- `window.switchLeaguesTab(tab)` — `leaderboard | challenges | flock`;
  each fetches its endpoint (`/api/v1/leagues/`, `/api/v1/challenges/`,
  `/api/v1/social/`) and renders into `#leagues-content`.
- `window.backToLeaguesPlan()` — back to the skill tree.
- Leaderboard render: week range + days-left chip, rows with rank medals
  (🥇🥈🥉 for top 3), avatar, username, XP, tier chip; your row gets
  `.row-you`; below: "Past weeks" history cards (rank/tier/reward).
- Challenges render: challenge card (icon, name, description, window), your
  progress bar (`my_progress` vs leader's progress), full ranked list.
- Flock render (stacked cards):
  1. **Find friends** — search input → `GET /social/?q=` → result rows with
     Add ✓ / Pending states.
  2. **Friend requests** — incoming Accept/Decline buttons, outgoing Pending.
  3. **Friends** — list with weekly XP; owner sees "Invite to flock" on
     flockless friends; Remove button.
  4. **Your Flock** — member standings + weekly total, Leave button; or a
     Create-Flock form (name input + button); or invite cards
     (Accept/Decline) when flockless.
- All POSTs: `fetch(url, { method:'POST', credentials:'same-origin',
  headers: {'Content-Type':'application/json','X-CSRFToken': csrfToken()},
  body: JSON.stringify(payload) })` — the CSRF meta tag already exists
  (docs/08). Non-ok responses surface `body.error` in a small toast/hint.

### 7.3 Staff picker (`#friend-picker-modal`)

Generic list modal: title + rows; base.js calls
`window.openFriendPicker({ title, friends, onPick })` after fetching
`/api/v1/social/`; picking posts `/base/staff {id, friend_id}`. An "Un-staff"
row posts `friend_id: null`.

### 7.4 Validation loop

`node --check core/static/core/js/leagues.js` (and `base.js`,
`dashboard.js`) after every edit — docs/04 "learned the hard way" rule: read
the *real* payload keys from §6, never port by renaming.

## 8. Admin & Seeding

- `core/admin.py`: register `LeagueWeek`, `LeagueResult`, `Challenge`,
  `Friendship`, `Flock`, `FlockMembership`, `FlockInvite` (list_display /
  list_filter / search_fields per existing style).
- `create_demo_accounts` extensions (idempotent, `get_or_create`):
  1. Default challenge: slug `calories_burned_30d`, name **Calorie Torch**,
     metric `calories_burned`, `window_days=30`, `is_active=True`.
  2. Ensure the current open `LeagueWeek` exists (via `ensure_current_week`).
  3. Accepted friendship `player1 → admin`.
  4. Flock **"Flamingo Fam"** owned by `player1` with `admin` as member, so
     the social tab, flock leaderboard and base staff picker are alive on
     first boot.

## 9. Celery / Beat

- `core/tasks.py`: `close_league_week_task` (shared_task) → closes any open
  week whose `week_start` is before the current Monday (`close_league_week`
  snapshots + pays rewards), then `ensure_current_week()` opens the new one.
- `settings.py` `CELERY_BEAT_SCHEDULE`: `"close-league-weekly"` —
  `crontab(minute=35, hour=0, day_of_week=1)`. The view layer also calls
  `ensure_current_week()` lazily, so a beat outage never breaks the panel.
  Everything is idempotent by stored dates/status.

## 10. Tests (`core/tests.py` additions)

**Pure math (`SimpleTestCase`):**
- `tier_for_xp` boundaries (0/99/100/299/300/599/600/999/1000).
- `week_start_for` returns Monday for every weekday input.

**DB / integration (`TestCase`):**
- Leagues: `ensure_current_week` creates the Monday row and is idempotent;
  `close_league_week` writes ranked `LeagueResult`s with tiers, pays top-3
  rewards into `BaseResource`, no-ops on re-run; stale open weeks close
  lazily when a later week is ensured.
- Challenges: `calories_burned_in_window` sums endurance
  (`total_calories_burned`) + cardio (`calories`) inside the window and
  excludes older rows; activating a second challenge deactivates the first
  (single-active rule); `challenge_state` leaderboard ordering + `is_you`.
- Social: request → pending → accept = friends both sides; reverse pending
  auto-accepts; decline removes; self/duplicate errors; search excludes self
  and tags relationship; flock create/invite/accept/leave incl. capacity
  (9th member rejected), owner-only invite, non-friend invite error,
  last-member-leave deletes the flock; flock weekly standings order.
- Base staff: `friend_id` of a non-friend → 400; a real friend → ok.

**API:** auth redirects; `GET /leagues/`, `/challenges/`, `/social/` shapes;
POST happy paths + 400 contracts; CSRF-403 test for one new POST
(`Client(enforce_csrf_checks=True)` pattern from `BaseAPITests`).

**Frontend:** `node --check` for `leagues.js` + edited `base.js` /
`dashboard.js`.

## 11. Known Gotchas ("learned the hard way")

- **Re-exports.** Every helper used outside its module must be re-exported
  from `core/services/__init__.py` (docs/08 endurance 500).
- **CSRF.** Every new POST sends `X-CSRFToken` from the meta tag; test 403
  explicitly (docs/08).
- **Friendship direction.** A pair can have at most one row per direction —
  always query both directions (`Q(from_user=a, to_user=b) | Q(...reversed)`)
  and never assume who initiated.
- **One flock per user.** `FlockMembership.user` is a OneToOne; every
  create/accept path must first check `hasattr(user, "flock_membership")`.
- **Timezones.** Weeks are local (`timezone.localdate()`); XP window queries
  convert the Monday date to an aware midnight datetime, consistent with the
  `timezone.now()` comparisons used elsewhere.
- **Don't change existing rewards / endpoints.** `/leaderboard/weekly` and
  the dashboard auto-popup stay byte-compatible; Phase 8 is additive.
- **Idempotency.** Week close, challenge activation, demo seeding all guard
  on stored state so the beat task and startup command are safe to re-run.
- **SQLite test runs.** Local `.env` points Postgres at the Docker `db`
  host; use `--settings=flamingo_fitness.test_settings` outside Docker.

## 12. Detailed Step-by-Step Coding Plan (Steps 29–36)

Steps map to new `docs/07_Next_Steps.md` Phase 8 checkboxes. Run the test
suite + `node --check` at the end of each step.

- **Step 29 — Models:** add the seven §4 models, makemigrations/migrate
  (`0007`), register in admin. Done-when: `manage.py check` + existing suite
  green.
- **Step 30 — Services:** `leagues.py` → `challenges.py` → `social.py`,
  re-export from `services/__init__.py`. Done-when: importable via
  `from core.services import ...`.
- **Step 31 — Views & API:** the §6 endpoints + urls + `base_staff` friend
  validation. Done-when: `TestClient` walkthrough of every happy path +
  documented 400/404 shapes.
- **Step 32 — Seeding & admin:** `create_demo_accounts` extensions (§8).
  Done-when: running the command twice is idempotent; demo pair are friends
  in one flock; default challenge active.
- **Step 33 — Celery:** `close_league_week_task` + beat entry (§9).
- **Step 34 — Frontend logic:** `leagues.js` controller + template section +
  nav rewire; `base.js` staff picker; `dashboard.js` delegation.
- **Step 35 — Frontend UI:** CSS for tabs/ranks/tiers/challenge bars/flock
  cards/picker modal (420px shell, mobile-first).
- **Step 36 — Tests & docs:** §10 test classes; full suite green;
  `node --check`; docs sweep (`00/01/02/03/07/08/12` + README phase blurb).

### Definition of Done

1. `manage.py check` + `manage.py test core
   --settings=flamingo_fitness.test_settings` green (all pre-existing tests
   untouched).
2. Leagues tab opens a real panel: live weekly board with tiers, your rank
   highlighted, and persisted history after a week closes.
3. Exactly one challenge active by default — *Calorie Torch* (calories
   burned, last 30 days) — with a live ranked board.
4. Players can search, send/accept friend requests, create/join Flocks, see
   a flock mini-leaderboard, and staff base buildings with real friends.
5. `docs/07` Phase 8 checkboxes, `docs/08` decision log and this file's
   status reflect the implemented reality.

