# 🧭 Flamingo Fitness — Future Gamification Idea Bank & Roadmap (Phase 8+)

> **STATUS: PARTIALLY IMPLEMENTED** — items **#1 (Seasons / Ranked Leagues)**
> and **#3 (Flamingo Flocks + real-friend staff)** shipped as Phase 8
> (docs/13, migration 0007). Everything else below remains a brainstorm.
> This is a living idea bank written for human review. Each idea is grounded in
> **already-shipped** architecture (docs/00–11) so it can be built with existing
> patterns: Vanilla JS controllers + lazy per-panel APIs, Django `XPLedger` /
> `SkillTree` / `BaseResource` / `BossConfig` / `DailyReadiness`, the Phase 7
> base economy (`core/services/base_economy.py`), Home Assistant webhooks
> (docs/06), and the asymmetric XP rulebook (docs/03).
>
> **Clarity legend.** Every idea is tagged so a future AI / reviewer can triage:
> - 🟢 **Low effort / high value** — small, mostly additive, uses current hooks.
> - 🟡 **Medium** — new model or endpoint, but standard pattern.
> - 🔴 **High** — new subsystem or meaningful rule-sheet change.
> - 🎯 **"To build" seed** — the first slice an implementer should ship.

---

## 0. Why these ideas (the north stars)

The existing loop already has: streak + proficiency (`SkillTree`), a resource
economy with timers and sinks (`BaseResource`, `BaseBuildingDef`), rare drops
(blueprints), social-ish boosts (staff), boss-gated progression (`BossConfig`),
and a friendly household (Home Assistant). The ideas below extend that loop
*without* layering on new heavy frameworks — they all lean on the four engines
we already own:

1. **More recurring decision points** (quests, per-hour goals) — more "perfect
   lesson" moments per day.
2. **Deeper social glue** (guilds, group raids, real friend staff) — retention
   via people, not just mechanics.
3. **Cadence layers** (seasons/ranks, decay, milestones) — reasons to come back
   weekly and monthly, not just daily.
4. **The house as a co-player** (Home Assistant "plays") — environmental
   feedback that turns streaks and rest days physical.

---

## 1. 🎯 Seasons, Ranked Leagues & Weekly Reset (Phase 8 — "the 8b payoff")

> ✅ **IMPLEMENTED (Phase 8, docs/13)** — `LeagueWeek`/`LeagueResult` models,
> Monday close task with top-3 rewards, live tiered leaderboard panel.

> Directly completes the parked `[ ] Step 8b` in docs/07 (season / weekly
> leaderboard reset model). This is the single highest-leverage next system.

**Pitch.** Weekly leaderboards already exist (`GET /api/v1/leaderboard/weekly`),
but there is no persistence: no history, no ranks, no rewards. Turn each week
into a **mini-season** with a visible tier (Bronze → Silver → Gold → Diamond →
Flamingo Legend) and **promotion / relegation** based on weekly "Effort XP".

**Why it fits.** Additive to the existing `XPLedger`-based leaderboard query;
purely a new model + a weekly aggregation task (mirrors the `tick_base_economy`
beat pattern).

**What it touches.** `core/models.py` (`Season`, `LeagueMembership`),
`core/tasks.py` (weekly `close_league_week`), `GET /leaderboard/weekly` gains
`season`/`tier`, a new `GET /leaderboard/seasons/{id}` history, and a frontend
`js/leagues.js` panel (the Leagues tab is already wired in the bottom nav).

**Rewards (tie into existing sinks):** top-3 per league get `time_speedups` +
a `golden_flamingo`-style seasonal blueprint drop; relegation can *confer* a
streak-speedup "shield" so demotion feels recoverable, not punitive.

**First slice (🎯):** `Season` + `LeagueMembership` models, a weekly close
task that snapshots ranks and applies tier movement + rewards, and a seasons
endpoint. UI tiers can ship as a second pass.

- Effort: 🟡 (models + 1 beat task — no rule-sheet change).
---

## 2. 🎯 Daily & Weekly Quest Board ("The Flock Checklist")

**Pitch.** A rotating card of 3–5 short quests per day, like Duolingo's quests,
each paying a small amount of XP/materials. Examples:
- *"Hit your exact protein goal."* (+Nutrition XP)
- *"Log any 30-min cardio."* (+Endurance XP)
- *"Drink to 50% of your water goal by 3 PM."* (+Hydration XP + a base "Micro
  Oasis" collect glint)
- *"Finish one programmed workout."* (+20 bonus XP, doubles the existing
  completion bonus).
- Weekly: *"Train every modality at least once."* → pays a `time_speedup`.

**Why it fits.** The readiness engine + hydration/macro gamification (docs/03)
already compute *exactly* the signals quests need. It creates more "perfect
lesson" moments and gives new users a guided path.

**What it touches.** A `Quest` + `QuestInstance` model (one row per user/day or
per user/week), a daily generation beat, and a `GET /quests/` endpoint consumed
by a `js/quests.js` panel. Quest completion can be derived from existing
`RawActivityLog` / `XPLedger` so it needs **no** new ingestion.

**First slice (🎯):** 3 static daily quest templates gated on existing fields,
a completion-check helper in `gamification.py`, and one panel.

- Effort: 🟢 (mostly a derivation layer on data we already store).

---

## 3. Guilds / "Flamingo Flocks" (social layer + real staff)

> ✅ **IMPLEMENTED (Phase 8, docs/13)** — `Flock`/`FlockMembership`/
> `FlockInvite` + friends system, flock mini-leaderboard, and real-friend
> base staffing. Group Boss Raids (§4) remain unimplemented.

**Pitch.** Let users form small **flocks** (Duolingo-family sized, 3–8).
Flock features that reuse existing systems:
- **Flock quests** (group versions of §2) — "Flock total 2,000 XP this week."
- **Real friends replace mocked staff:** Phase 7's `staff_friend_id`
  (`/base/staff`) currently uses a *mocked* friend list. Making `staff` point at
  real flockmates means staffing another member's building grants *them* a
  +10% yield — a tiny, delightful "help your friend's cabana" loop.
- **Shared leaderboard within the flock.**

**Why it fits.** `BaseBuilding.staff_friend_id` and `evaluate_synergies` already
exist; this just connects staff to real users and adds a group aggregation.

**What it touches.** a `Flock` + `FlockMembership` model, a `GET /flock/` state
endpoint + `js/flock.js`, and updating `staff` to resolve real user IDs. No
changes to the economy math itself.

- Effort: 🟡 (one model, one panel, one staff-resolution change).

---

## 4. Group Boss Raids (multi-user PR Boss)

**Pitch.** A **Raid Boss** is a strength boss fought by a whole flock or
household: instead of matching *your* best est. 1RM against
`bodyweight × multiplier`, the raid threshold is matched against the **flock's
combined volume over a week** (e.g., "The House Squats 500,000 lbs in 7 days").
Weekly respawn; conquering pays the flock rafters of `time_speedups` and a
chance at seasonal blueprints (reuses `maybe_drop_blueprint`).

**Why it fits.** The `BossConfig`/`boss_state` pattern and the Liftosaur
`total_volume_lbs` aggregation already exist — this is a windowed, grouped
aggregation on top.

**What it touches.** Extends `BossConfig` with `kind` (`solo`|`raid`),
`aggregate` (`volume`|`xp`), and `window_days`; extends `GET /boss/` +
`boss.js` to render a raid progress bar; adds a weekly reset task.

- Effort: 🟡.

---

## 5. Achievement Badges & Derived Milestones

**Pitch.** A lightweight **badge** catalog derived from data we already count —
no new ingestion, just checks run when stats change (or lazily on the badges
endpoint). Examples:
- *"Perfect Week"* — all 7 daily readiness requirements met.
- *"10-Day Flame"* — 10-day streak (already tracked on `User.streak`).
- *"Base Tycoon"* — reach base level 25 (Phase 7 `base_level`).
- *"Blueprint Hunter"* — collect 5 blueprints.
- *"All-Modality Master"* — every skill tree at level 3+.
- *"Night Owl / Early Bird"* — log a workout in a given local-time window
  (the PWA already knows client local time for day/night).

**Why it fits.** It's a pure read-compute layer over `SkillTree` /
`BaseResource` / `User.streak` / `XPLedger`; no schema beyond a `BadgeDef` +
`UserBadge` grant table, and it gives profile pages and the "start of day"
toast obvious goals to chase.

**What it touches.** `BadgeDef`/`UserBadge` models, a `badges_state` endpoint,
`js/badges.js` panel; a `check_badges(user)` helper in a tiny new service or
inline in `gamification.py`.

- Effort: 🟢 (mostly read-only derivations + one grant table).
---

## 6. Pacing & Integrity: Decay, Difficulty Scaling & Anti-Farming

Three smaller rule-sheet evolutions (docs/03 territory) that protect the loop
long-term:

- **6a. Effort decay for the leaderboard (not for skill trees).** Keep
  lifetime `SkillTree.xp` permanent (feels fair), but make *leaderboard / rank*
  scores weight recent activity (a rolling 4-week half-life). This stops a
  month-old XP dump from dominating ranks and makes leagues (idea #1) stay
  competitive. Purely a query change in the leaderboard aggregation.
- **6b. Readiness-scaled XP (a gentle cap, not a punishment).** On a mandated
  rest day (docs/01 `DailyReadiness.streak_requirement == REST_DAY`), cap
  *new* training XP so gamers can't brute-force around readiness; instead offer
  a "2× tomorrow" carry token — reinforcing the rest-day = recharge fantasy
  the Phase 7 Recovery Pool already plants.
- **6c. Anti-farming anomaly detector.** The ELT inbox (`RawActivityLog`) + the
  Phase 7 `dedup`/`ingest_results` self-healing already lean on stored
  `occurred_at`. Add a cheap velocity check (e.g., an implausible number of
  medium/high-intensity minutes per day, or duplicate class IDs) that flags
  logs for review or withholds the boss-fight 2× until confirmed. Keeps the
  asymmetric leaderboard honest.

- Effort: 6a 🟢 · 6b 🟢 · 6c 🟡 (a scoring + review endpoint).

---

## 7. The House Plays: Home Assistant Environmental Synergy (extends docs/06)

**Pitch.** Turn the existing HA spec (docs/06) into *mechanics*, not just
notifications — the house becomes a co-player:

- **NFC gym tap → "Warm-up Streak" combo meter:** tapping the gym NFC tag
  within N minutes of your expected workout time grants a stacking 1.05× XP
  multiplier (capped), creating a reason to show up on time. (HA webhook
  `workout_started` already exists.)
- **Smart-bed REST bonus:** when HA reports a deep-sleep pad session *and*
  Garmin readiness says rest day, grant the Phase 7 rest-day energy bonus an
  extra overflow chip (ties the Recovery Pool to the physical bed).
- **Streak-danger lighting:** keep docs/06's 8 PM red lights, and add a
  *reward* counterpart — hitting your daily streak requirement by 9 PM plays a
  Flamingo "victory" jingle on Sonos/Alexa (ties to the PR-boss automation).
- **Boss raid "arena mode":** on a raid-week (idea #4), kitchen lights pulse
  during expected training windows.

**Why it fits.** The inbound HA webhook +
`process_log` already map entities to event types; these ideas just add a few
mapped `event_type`s and read them in `gamification.py` the way `cardio` /
`strength` are read today.

**What it touches.** More cases in `home_assistant_webhook` (core/views.py),
a couple of new handler contracts, and outbound HA calls (docs/06 §outbound)
from boss/readiness side-effects.

- Effort: 🟡 (webhook mapping + side-effects; needs a live HA to test).

---

## 8. Nutrition & Hydration Micro-Games (deeper "perfect lessons")

- **8a. Macro Bingo / Meal Streaks.** Per-meal goals (protein per meal is
  already derivable from SparkyFitness `food_entries`), a 7-day meal-log streak
  that pays +Nutrition/Hydration bonus and a base "Juice Bar" refresh
  (Phase 7 catalog).
- **8b. Timed hydration waves.** Instead of *daily* water total, split the day
  into 3–4 windows (morning / midday / afternoon / evening) using SparkyFitness
  `water_intake_entries[]` timestamps (already captured as `time`). Hitting the
  *right* window = +XP; missing a window = no penalty, just no bonus. Rewards
  pay the base's hydration-affinity stat. This raises the "perfect lesson"
  count per day from 1 (daily total) to ~4.
- **8c. Recipe / menu unlocks in the base.** As the Nutrition skill tree grows,
  unlock themed recipe cards (or a "Juice Bar menu") that render as flavor text
  + small permanent production/energy buffs — content-driven progression that
  reuses the `BaseBuildingDef` buff mechanism.

- Effort: 8a 🟢 · 8b 🟢 (read-only parsing of existing payloads) · 8c 🟡.
---

## 9. Progression Curves & Scaling (economy math quality-of-life)

Small tunable improvements to `docs/03` / `core/services/gamification.py` /
`base_economy.py` that keep numbers satisfying at high levels:

- **Diminishing returns on XP bonus buildings.** Already capped at
  `MAX_XP_BONUS_PCT = 25`; propose making the *contribution* of each additional
  XP building soften (concave curve) so chasing Level-9 Gold Statues stays
  meaningful but not mandatory.
- **Streak multiplier milestones with flavor.** Keep `STREAK_CAP_DAYS = 10`
  at 1.5×, but add named milestone beats (3/5/7/10 days) that each flash a
  milestone toast + confetti (the Phase 7 milestone system is already wired).
- **Materials->speedup conversion.** Add a small, capped exchange (e.g., 100
  materials → 1 speedup) as an extra sink so late-game wallets have purpose
  beyond prestige and to soften the "energy/time-speedup sinks are the core
  gap" note from docs/07.

- Effort: 🟢 (constant/curve tweaks + one exchange endpoint).

---

## 10. Push & PWA Lifecycle: Nudges That Respect Attention

- **10a. Smart streak reminders.** Push (Web Push — the PWA/service worker
  already exists) only when a requirement is unmet near its window (e.g., read
  readiness → if `TRAIN` and no workout logged by 6 PM, remind; if `REST_DAY`,
  *don't* nudge — that's the whole point).
- **10b. Boss respawn / league deadline notifications.** One push on boss
  respawn and one on league close (ties to ideas #1/#4) — a reason to open the
  PWA at a recurring cadence.
- **10c. Home-screen shortcut actions.** "Quick-log water" and "Collect base"
  as installable shortcuts so a 2-second tap keeps streaks alive.

- Effort: 10a 🟡 · 10b 🟢 (reuses existing beat tasks) · 10c 🟡.

---

## 11. (Doc-only) Recommended priorities for review

Grouped by what an implementer should pick up first — all additive, all using
existing patterns (Vanilla JS + Django JsonResponse + `XPLedger`/`SkillTree`/
`BaseResource`/`BossConfig`/`DailyReadiness` + the base economy + HA webhook).

**Tier 1 — ship first (🟢, high payoff, low risk):**
1. **Achievement Badges** (#5) — cheap, gives profiles + daily toasts goals.
2. **Daily & Weekly Quest Board** (#2) — more "perfect lesson" moments/day.
3. **Seasons / Ranked Leagues & weekly reset** (#1) — completes parked Step 8b,
   gives the weekly leaderboard persistence and a monthly reason to return.
4. **Readiness-scaled XP + rest-day carry token** (#6b) — reinforces the core
   rest-day fantasy, small rule edit.

**Tier 2 — next (🟡), once Tier 1 lands:**
5. **Flamingo Flocks (guilds) + real-friend staff** (#3) — turns the Phase 7
   staff mock into a social loop.
6. **Group Boss Raids** (#4) — gives flocks a shared weekly goal.
7. **Timed hydration waves** (#8b) — raises daily "perfect lesson" count.
8. **Push nudges** (#10) — retention without spam, tied to readiness.

**Tier 3 — polish / later (🟡–🔴):**
9. **Materials→speedup sink + concave XP bonus curve + streak flavor beats** (#9).
10. **The House Plays: HA environmental synergy** (#7) — best once a live HA
    instance exists to test.
11. **Anti-farming anomaly detector** (#6c) + effort decay (#6a) — integrity
    hardening as the user base grows.

---

## 12. Executive summary (for review)

Flamingo Fitness already ships a complete daily loop (streaks, five skill
trees, the Phase 7 base economy, PR bosses, readiness rest-days, asymmetric
leaderboards, Home Assistant hooks). The ideas above extend it **additively —
no new frameworks, no reward-amount changes**, and every one names the exact
existing model/endpoint/panel it builds on.

- **Highest-value, smallest-effort:** a **Seasons / Ranked Leagues** system
  (it literally finishes the parked `Step 8b`), a **Quest Board**, and
  **Achievement Badges** — all mostly read-compute layers over data we already
  store, none requiring new data ingestion.
- **Biggest retention lever:** the **social layer** — Flamingo Flocks,
  real-friend staff (replacing the Phase 7 mock), and **Group Boss Raids**.
- **Biggest "more fun per day" lever:** **timed hydration waves** and
  **Home Assistant "the house plays"** environmental feedback, which raise the
  number of satisfying "perfect lesson" moments and make the Miami vibe
  physical.
- **Biggest long-term stability lever:** **effort decay + anti-farming** to keep
  the asymmetric leaderboard fair as the user base grows.

Recommended next concrete deliverable: **Tier-1 items #1, #2, #5, #6b**, each
scoped as its own small commit with `python manage.py test core` +
`node --check` as the validation gate, following the docs/07 / docs/09
step-checkbox convention.