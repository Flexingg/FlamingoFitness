# 🧠 Flamingo Fitness — Brainstormed Feature Bank (docs/17)

> *A living, app-wide idea bank of **feature ideas, big and small.** Each idea is
> tagged with an effort estimate and a concrete "how to integrate" that names the
> **actual** models / services / endpoints / JS controllers already in the repo —
> so a future AI or reviewer can pick one up and build it with existing patterns
> (no new frameworks, per docs/00). Nothing here is implemented yet; treat the
> whole file as a brainstorm for review.
>
> **Effort legend**
> - 🟢 **Small — mostly additive**, uses current hooks. A new widget, a query
>   change, a rule tweak, an empty-state.
> - 🟡 **Medium** — one new model/endpoint/panel on the standard pattern.
> - 🔴 **Large** — a new subsystem or a meaningful rule-sheet change.

---

## 0. Current reality (so ideas never collide with what ships)

Re-verified against the live codebase (models, `core/urls.py`,
`core/services/__init__.py`, `core/tasks.py`, `core/static/core/js/*`):

**Already implemented:**
- **5 skill trees** (strength / endurance / nutrition / hydration / recovery) +
  readiness engine (`DailyReadiness`) + streak + readiness-protected rest days.
- **PR Boss** (`BossConfig`, `GET /api/v1/boss/`) — bodyweight-based benchmarks.
- **Phase 9 combat core (docs/15 + docs/16):** tokens / stamina / **scraps**
  (`PlayerProfile`), gacha packs (`GearPackDef`), gear catalog
  (`GearItemDef` + `effect_params` with `flat_bonus` / `scales_with` /
  `stamina_cap` / `token_multiplier` etc.), owned items (`UserGear`),
  rotating **Scrap Shop** (`ScrapShopItem`), PvE campaign sieges
  (`CampaignBoss` / `CampaignProgress` / `BattleLog`), PvP gyms
  (`Gym` / `GymOccupation` / `PvPMatch`). Endpoints: `shop/*`, `scrap/*`,
  `loadout/*`, `equip/unequip`, `battle/*`, `pvp/*`.
- **Social:** friends (`Friendship`), flocks (`Flock*`), weekly leagues
  (`LeagueWeek` / `LeagueResult`), single-active challenges (`Challenge`).
- **Badges** (`BadgeDef` / `UserBadge` + `core/services/badges.py`) and
  stat explainers (`core/services/stat_explainers.py`).
- **Theme** (light / dark / device — migration `0008`) + SPA `router.js`.
- **Integrations:** SparkyFitness (`sparky_client.py`), Liftosaur
  (`liftosaur_client.py`), Garmin / Peloton (`api_clients.py`).
- **Celery beat:** `poll_garmin` / `poll_peloton` / `poll_liftosaur` /
  `poll_sparkyfitness` / `compute_readiness_for_all` / `tick_combat_daily` /
  `close_league_week_task`. Config-driven seeds in `config/seeds/*.json`,
  loaded idempotently by `create_demo_accounts`.

**Gone / planned removals:**
- The Phase 7 **base-building economy was ripped out** (docs/15) — no
  `BaseResource` / `BaseBuilding` models, no `/base/*`. Ideas below do **not**
  bring it back; they extend the token/stamina/loot loop.

**Documented but NOT yet wired:**
- The **Home Assistant webhook** appears only in a views docstring — no live
  route. Section 8 treats HA as greenfield.

**Re-use map (the "existing patterns" every idea leans on):** `XPLedger` /
`SkillTree` / `DailyReadiness` / `BossConfig` / `PlayerProfile`
(tokens·stamina·scraps·buffs) / `UserGear` / `CampaignBoss`+`CampaignProgress` /
`Gym`+`PvPMatch` / `Friendship`+`Flock*` / `LeagueWeek`+`LeagueResult` /
`Challenge` / `BadgeDef`+`UserBadge`, the `core/services/{gamification,combat,
readiness,leagues,challenges,social,badges,stat_explainers}.py` modules, the
vanilla controllers `dashboard/nutrition/hydration/endurance/strength/boss/
recovery/shop/loadout/battle/pvp/leagues/badges/router/theme.js`,
`config/seeds/*.json`, and the Celery beat table.
---

## 1. New data integrations & sync — items 1–10

1. **Apple Health / HealthKit inbound sync** [🟡] — Pull steps, workouts and
   sleep into the ledger even without a wearable day. Practical slice is
   importing exported Health XML/CSV or a share target.
   **Integrate:** new `Provider` choice + `event_type`s (`steps`, `workout`) →
   `RawActivityLog`; reuse `summarize_endurance` / `summarize_sleep`; a
   `health_client.py` mirroring `SparkyFitnessClient`.

2. **Withings / Nokia smart-scale + body-fat sync** [🟡] — Bodyweight, body-fat
   %, HR, and steps from Withings. Bosses key off `_latest_bodyweight()`;
   richer weight history also feeds the Weightlifting and Nutrition domains.
   **Integrate:** a `withings_client.py` emitting a `scale` `RawActivityLog`
   (same shape as Sparky's), a `poll_withings` beat task, and swallow the
   `scale` payload in `views.py _latest_bodyweight()`.

3. **Fitbit OAuth integration** [🔴] — Steps, sleep stages, resting HR as
   additional readiness inputs.
   **Integrate:** `Provider` enum + OAuth on `/profile/`, `fitbit_client.py`,
   `poll_fitbit` beat task, extend `core/services/readiness.py` inputs.

4. **Google Health Connect (Android aggregator)** [🔴] — One Android connector
   that surfaces workouts, sleep, steps, and body metrics from any app.
   **Integrate:** a `healthconnect_client.py` mapping payloads onto the existing
   `event_type`s (`cardio`, `sleep`, `scale`, `endurance`), same ingest path.

5. **Manual quick-log fallback** [🟡] — Tap-to-log water, a food/macro snapshot,
   workout minutes, or weight for days the wearable isn't worn — keeps streaks
   alive without hard-coding XP.
   **Integrate:** new `POST /log/{water|nutrition|endurance|scale}` endpoints
   that write `RawActivityLog` and run the existing `process_log` handlers
   exactly like a webhook. Quick-log is the PWA's biggest day-one retention lever.

6. **CSV / JSON history import (backfill)** [🟢] — One-time import of a
   spreadsheet or Liftosaur export so new users don't start from zero.
   **Integrate:** an `import_history` management command wrapping the shared
   `core/tasks.py ingest_results` (dedup already keyed on
   `(user, source, event_type, occurred_at)`).

7. **Barcode / food-photo capture surfaced from SparkyFitness** [🟡] — Sparky
   already has `/foods/barcode` + AI food-photo vision. Add a "scan & log" UI so
   Nutrition XP and perfect-macro checks don't depend on manual entry.
   **Integrate:** a nutrition quick-add panel calling Sparky `/foods/barcode`
   and posting a `/food-entries` (or a `POST /log/nutrition` fed through
   `_handle_macro`).

8. **Fasting & metabolic window tracking** [🟢] — Log fasting windows; shape
   hydration/macro micro-goals around eating windows.
   **Integrate:** a `fasting` `RawActivityLog` `event_type` + a summarizer; feed
   timed window checks (see #71) and a fasting badge (section 7).

9. **Mood & perceived exertion (RPE) logging** [🟢] — Daily mood + session RPE
   correlated against readiness; a small, honest-logging XP reward.
   **Integrate:** `mood` / `rpe` `event_type`s → a summary used by the Recovery
   node detail and a mood-sync badge rule in `badges.py`.

10. **Adaptive TDEE & self-taught calorie goals** [🟡] — Keep `calories_goal` /
    `protein_goal` fresh using Sparky `/adaptive-tdee` so "perfect macros" stays
    fair and meaningfully targeted.
    **Integrate:** a nightly beat task that refreshes the goals read by
    `summarize_nutrition` and the perfect-macro check in `gamification.py`.

---

## 2. Core loop: XP, streaks, readiness & PR — items 11–22

11. **Rest-day "carry token" bank** [🟢] — On a mandated rest day, unmet
    training converts into a token that doubles **next** day's siege damage,
    reinforcing "rest = recharge" without allowing farming.
    **Integrate:** a dated `active_buffs` key on `PlayerProfile`; `combat.
    compute_attack` multiplies base damage when the carry token is set.

12. **Streak shields / streak-saver consumables** [🟢] — A rarely granted item
    that protects a streak when readiness or life misfires.
    **Integrate:** a `PlayerProfile` wipeable buff + a guard wherever
    `User.streak` is recomputed/decremented.

13. **Effort decay for leaderboards (skill trees stay permanent)** [🟢] —
    Lifetime `SkillTree.xp` stays, but league/leaderboard scores weight recent
    activity (rolling 4-week half-life) so a month-old XP dump can't dominate.
    **Integrate:** a query change in `core/services/leagues.py` `weekly_xp_rows`
    / `weekly_xp_map` — no schema change.

14. **Readiness-scaled XP cap on rest days** [🟢] — Gentle cap on *new training
    XP* logged on a rest day, paired with a 2×-tomorrow carry token (#11) so it
    feels like a reward, not a punishment.
    **Integrate:** a scaling hook in `gamification.py process_payload` gated on
    `DailyReadiness` (mirrors the old `base_xp_bonus_pct` pattern).

15. **Perfect-week bonus** [🟢] — All 7 daily readiness requirements met in a
    week = a one-time streak bump + token payout.
    **Integrate:** a badge-style check over `DailyReadiness` + `award_tokens`
    and a `LeagueResult`-independent payout.

16. **Skill-tree mastery emblems & XP→token overflow** [🟢] — When a tree hits a
    cap level (e.g. 10), show a mastery emblem and reroute overshoot into tokens.
    **Integrate:** `SkillTree` + `PlayerProfile`; a rule in `apply_to_skill_tree`
    that mints `award_tokens` once `total_xp` crosses the cap.

17. **Like-with-like effort leaderboard filter** [🟡] ✅ Implemented (docs/02, docs/14) — Alongside the asymmetric
    XP board, let users compare only strength, only cardio, only hydration, etc.
    **Integrate:** `leaderboard_weekly` gains a `kind` filter over
    `RawActivityLog` / `XPLedger.modality`; a tab in the Leagues panel.

18. **Auto-rest-day → Home Assistant "Easy Day" + calm theme** [🟢] — When
    readiness mandates a rest day, the house goes calm and the PWA switches to a
    relaxed palette (ties section 8).
    **Integrate:** a `readiness` side-effect calling an outbound HA hook and
    toggling `theme.js`.

19. **Readiness-aware pacing nudges at the right time** [🟡] — Push/remind *only*
    when the day's requirement is unmet near its window (never nudge on a rest
    day — that's the point).
    **Integrate:** a beat task reading `DailyReadiness.streak_requirement` +
    today's `RawActivityLog`, dispatching via the push system (#83).

20. **Streak milestone flavor beats (3/5/7/10)** [🟢] — Named streak milestones
    each fire confetti + a toast + a small token bonus.
    **Integrate:** reuse the milestone-toast + `canvas-confetti` pattern in
    `dashboard.js`; a streak side-effect in `gamification.py`.

21. **Ambient weekly goal ring** [🟢] — A gentle, self-set weekly XP target with
    a progress ring on the dashboard — motivational, non-competitive.
    **Integrate:** a `weekly_goal` int on `PlayerProfile` + a dashboard widget
    computed from weekly `XPLedger`; no leaderboard changes.

22. **Seasonal PR Boss rotation with themed drops** [🟢] — Rotate the
    `BossConfig` lineup each season (theme-renamed bosses, themed drops).
    **Integrate:** `BossConfig.sort_order`/`is_active` + seasonal seeding in
    `create_demo_accounts`; `boss.js` renders the active roster.

---

## 3. Combat core: PvE sieges & campaign bosses — items 23–36

23. **Flock raid bosses (group sieges)** [🟡] — A giant boss whose HP is chipped
    by a whole flock's combined volume across the week (docs/12 §4). Conquering
    pays every participant.
    **Integrate:** `CampaignBoss` gains a `kind` (`solo`|`raid`); a `FlockSiege`
    model; `battle_attack` accepts a flock-scope; reward via `award_tokens`.

24. **Boss counter-mechanics by weekday / element** [🟢] — Bosses "fight back":
    some attacks are stamina-neutral, some heal the boss on certain days, adding
    light strategy without a full combat system.
    **Integrate:** richer `CampaignBoss.mechanics` + `combat.attack_boss`;
    show the banner in `battle.js`.

25. **Boss scouting & weakness UI** [🟢] — Reveal weaknesses/resistances clearly
    before you attack so loadouts are informed.
    **Integrate:** `battle_campaign` payload already has the boss; expose
    `weaknesses`/`resistances` and render chips in `battle.js`.

26. **Multi-boss gauntlet chains + escalating rewards** [🟡] — Consecutive
    conquests within a campaign pay escalating tokens ("kill streak").
    **Integrate:** `CampaignProgress` chain counter + `award_tokens` scaling on
    conquest; a progress strip in `battle.js`.

27. **Campaign seasons with rotating boss rosters** [🟡] — "Cardio season",
    "Squat season" etc., with different bosses each window.
    **Integrate:** `CampaignBoss.is_active`/`sort_order` + a season scheduler;
    `create_demo_accounts` seeds rosters; `battle_state` shows the current one.

28. **Pity / guaranteed-conquest timeline** [🟢] — After N sieges, show explicit
    "guaranteed win in X more damage" so long fights feel winnable.
    **Integrate:** `CampaignProgress` + a derived `remaining_to_guarantee` in
    `battle_state`; an HP/guarantee bar in `battle.js`.

29. **Free attack preview (no stamina cost)** [🟢] — Show today's predicted
    damage and boss heal before committing a stamina.
    **Integrate:** `battle_campaign` returns a preview via `combat.compute_attack`
    without deducting stamina; "Predicted damage" readout.

30. **Stamina refresh extras ("second wind")** [🟢] — A rest-day stamina bonus
    and a scenario that can refund a used stamina with the right consumable.
    **Integrate:** `combat.refresh_stamina` (rest-day bonus already in docs/15)
    + the existing `stamina_refund` consumable type (docs/16).

31. **Boss-weakness-aware loadout bonuses** [🟡] — Gear that boosts damage
    specifically against a boss's weakness domain, making the loadout matter.
    **Integrate:** `total_gear_multiplier(domain)` crossed with
    `boss_vulnerability(domain)` in `compute_attack`; a hint in `loadout.js`.

32. **Server-wide mega-boss** [🔴] — Everyone chips the same global boss HP;
    the killing blow pays a jackpot, everyone gets a participation reward.
    **Integrate:** a shared `CampaignProgress` (or `GlobalRaid` model) +
    `BattleLog` aggregation; a loot-distribution task.

33. **Per-campaign siege leaderboards** [🟢] ✅ Implemented (docs/17 #33) — Rank most damage dealt to the
    current boss among friends + flock.
    **Implemented:** new nullable `BattleLog.boss` FK (migration `0013`) so damage
    is attributed to a boss; `GET /api/v1/battle/leaderboard/{campaign}` aggregates
    `BattleLog.total_damage` among self + friends + flockmates via `_campaign_peers`;
    `battle.js` "Leaderboard" button reuses the `leagues.js` rank-row UI.

34. **Siege kill timeline / diary** [🟢] — A browsable history of boss conquests
    and halved bosses per campaign.
    **Integrate:** `BattleLog` + a simple `battle/history` endpoint + a list in
    `battle.js`.

35. **Mid-attack consumable use** [🟡] — Spend an active consumable during an
    attack for a tactical edge (double damage, shield the boss heal).
    **Integrate:** `battle_attack` accepts optional consumable ids →
    `combat.consume_consumable` before `compute_attack`.

36. **Boss regeneration after idle** [🟢] — Bosses slowly regenerate HP if
    untouched for ~48h to keep sieges current.
    **Integrate:** `tick_combat_daily` heals `CampaignProgress` when the last
    `BattleLog` is old; a "weakened" flavor note if recently hit.

---

## 4. PvP & territory — items 37–46

37. **Flock-owned gyms / shared defense** [🟡] — Docs/15 explicitly deferred
    "Flock defense" — this is the natural extension: a Gym owned by a flock, any
    member defends.
    **Integrate:** `Gym` gains a `flock` FK; `pvp_attack` resolves the defender
    snapshot from flock members; occupation shared across members.

38. **PvP seasonal ladders & reset** [🟡] — Monthly PvP ladder with placement
    rewards; lifetime PvP stats are preserved.
    **Integrate:** a `PvPSeason` month table + `PvPMatch` aggregation +
    `PlayerProfile.pvp_wins/pvp_losses` (fields exist).

39. **Gym revenge mechanic** [🟢] — A losing defender can re-challenge the
    conqueror within 24h to win their turf back.
    **Integrate:** `PvPMatch` + a dated revenge-eligibility flag; a button in
    `pvp.js`.

40. **Gym hold-streak tiering** [🟢] — Holding a gym continuously raises its
    token yield up to a plateau (motivates defense, still capped).
    **Integrate:** `GymOccupation` held-duration → yield multiplier in
    `pay_gym_yields`.

41. **Attack report cards** [🟢] — After a fight, show the full matchup math:
    element wheel, consistency gap, loadout comparison, and why you won/lost.
    **Integrate:** `pvp_state` returns a breakdown; `pvp.js` renders a report
    card with coaching tips.

42. **Anti-toxicity ceasefire** [🟢] — Cooldown against attacking the same
    player repeatedly, or a "truce" when close friends.
    **Integrate:** a `PvPMatch` recency check + `Friendship` guard in
    `pvp_attack`.

43. **Terrain-mapped gyms** [🟢] — Gym terrain (per `Element`) ties the element
    wheel to campaign domains, making placement strategic.
    **Integrate:** `Gym.terrain` already exists; ensure the UI states it and
    `combat` uses the wheel explicitly.

44. **Weekend PvP tournaments (brackets)** [🔴] — Friends/flocks enter a
    weekend bracket for placement rewards and bragging rights.
    **Integrate:** a `Tournament` + `TournamentMatch` model, a beat scheduler,
    and bracket rendering in `pvp.js`.

45. **Optional token staking duels** [🟡] — Winner-takes-all token stake on a
    head-to-head (capped per day to avoid farming).
    **Integrate:** `PvPMatch.token_stake` (field exists) + `spend_tokens` on
    challenge, `award_tokens` to the winner.

46. **PvP consistency/loadout coaching visibility** [🟢] — Show *why* you lost
    (7-day consistency vs loadout) so players know what to fix.
    **Integrate:** `pvp_state` includes defender-power decomposition; `pvp.js`
    renders tips ("Your Cardio zone is weak — check your Endurance gear").

---

## 5. Shop, gacha, items & scrap economy — items 47–56

47. **Item crafting / combining** [🟡] — Merge N items of the same slot+rarity
    into one of the next rarity — a primary dupe sink.
    **Integrate:** a `POST /shop/craft` + `combat.craft_gear`; require selected
    `UserGear` rows; show recipes in `shop.js`.

48. **Gift / trade items between friends** [🟡] — Send a duplicate item to a
    friend instead of scraping it.
    **Integrate:** validate via `social.friends_of`; transfer `UserGear`
    ownership in a POST; reuse `leagues.js`'s friend picker.

49. **Gear sets & set bonuses** [🟡] — Equipping 2–3 items from a themed set
    grants a synergy multiplier.
    **Integrate:** a `set_key` on `GearItemDef` + a set table in
    `total_gear_multiplier` (the synergy evaluator already exists conceptually).

50. **Enchantment / upgrade stones** [🟡] — Boost an item's `effect_value` up to
    a cap using scraps or tokens.
    **Integrate:** `GearItemDef` max-upgrades + `combat.upgrade_gear`; UI in
    `loadout.js`.

51. **Daily free pack + first-draw discount meter** [🟢] — A free-pull cadence
    and an odds/meter readout on packs for retention.
    **Integrate:** `PlayerProfile.last_free_pack` + counters; `shop_state`
    returns eligibility; `open_pack` grants the free one.

52. **Scrap Shop richer rotation & bundles** [🟢] — Time-limited bundles beyond
    single offers that visibly rotate (docs/16 §4 already has day-of-week).
    **Integrate:** extend `ScrapShopItem` with bundle fields; render
    countdown/bundles in `shop.js`.

53. **Cosmetic gear & themed loadout display** [🟢] — Zero-stat cosmetics and
    themed avatar/loadout display, for fun and value.
    **Integrate:** an `is_cosmetic` flag on `GearItemDef` + render in
    `loadout.js`; optional avatar tie-in.

54. **Full item detail popover** [🟢] — Complete stat card: effect type, pack
    source, craft recipes, synergy hints, description (docs/16 §1).
    **Integrate:** `shop.js`/`loadout.js` modal reading `description` +
    `effect_params`; reuses the shared `#modal`.

55. **Collection / codex completion tracking** [🟢] — "Collect all of Iron
    Roost" progress + reward.
    **Integrate:** `UserGear` vs `GearItemDef` per pack aggregation + a codex
    endpoint + a `badges.py` rule and a panel.

56. **Hard gacha pity counter** [🟢] — Guarantee a top-rarity after N pulls so
    unlucky streaks stay motivating.
    **Integrate:** `PlayerProfile` pull counters read by `open_pack`; show
    "N pulls until guaranteed" in `shop.js`.

---

## 6. Social: friends, flocks, leagues & challenges — items 57–66

57. **Flock quests / co-op challenges** [🟡] — A group objective ("flock burns
    10,000 kcal together") with a shared reward.
    **Integrate:** a `flock_scope` variant of `Challenge` (or a `FlockQuest`
    model) + renders on the `leagues.js` Flock tab.

58. **Flock-to-flock rivalry weeks** [🟡] — Two flocks race a weekly XP target;
    the winner gets flock-wide tokens.
    **Integrate:** a `Rivalry` model + `weekly_xp_map` aggregation + a banner on
    the Leagues panel.

59. **In-app friend chat / activity reactions** [🔴] — Lightweight messaging or
    emoji reactions on each other's log entries.
    **Integrate:** a `Message`/`Reaction` model + `social.js` panel; friend
    validation via `social.friends_of`.

60. **Weekly "report card" share card** [🟡] — An auto-generated image summarising
    the week (XP, tier, boss kills, streak, PRs) for sharing.
    **Integrate:** a report-render endpoint + `navigator.share`/download in
    `dashboard.js`; reuses data already computed by `leagues.py`/stats.

61. **Activity-mix titles** [🟢] — Derived ranks like "The Endurance Owl" or
    "Hydration Hero" from skill-tree proportions.
    **Integrate:** a title resolver over `SkillTree` proportions + profile
    display; zero new schema.

62. **Mentoring / accountability pairs** [🟢] — Match a new user with a veteran;
    shared weekly check-in and gentle reminders.
    **Integrate:** a mentor flag on `Friendship` + a lightweight weekly in-app
    check-in (#73).

63. **Allied invasion boost** [🟡] — Friends/flockmates boost each other's siege
    damage while raiding the same boss (ties #23).
    **Integrate:** `battle_attack` optionally latches an active ally (flock)
    loadout contribution.

64. **Flock banners & customization** [🟢] — Let flocks pick a banner/icon.
    **Integrate:** `Flock.icon` exists; add a color/banner and render on the
    Flock tab.

65. **Friend mini-leaderboard strip on dashboard** [🟢] — "Your friends this
    week" at the top for peer pressure without global competition.
    **Integrate:** `dashboard_state` adds a friend `weekly_xp` list (reuse
    `weekly_xp_map`).

66. **Server-wide seasonal team challenge** [🔴] — A global challenge that
    randomly teams participants into teams for a survival-style objective.
    **Integrate:** a `Team` model + rebalanced `Challenge`; reward distribution
    across teams; render in `leagues.js`.

---

## 7. Badges, stats, insights & reporting — items 67–76

67. **Monthly "State of the Flamingo" report** [🟡] — A visual monthly summary:
    XP, calories, sleep, PRs, badges earned, boss kills.
    **Integrate:** an insights endpoint aggregating existing tables + a report
    viewer/share card; reuses stat + leagues data.

68. **PR & est‑1RM timeline** [🟢] — History of every best lift with a progress
    sparkline (the boss panel already shows `best_lifts`).
    **Integrate:** a PR-history endpoint from `views` strength/boss data;
    sparklines in `boss.js`.

69. **Sleep & readiness trends** [🟢] — Sleep-debt/efficiency trends surfaced on
    the Recovery node.
    **Integrate:** `summarize_sleep` + `recovery_state` add mini trend charts to
    `recovery.js`.

70. **Nutrition trend sparklines** [🟢] — 7-day protein adherence and
    calorie-goal "on track" indicators.
    **Integrate:** extend `nutrition_state.history` output; render mini-charts
    in `nutrition.js`.

71. **Timed hydration windows** [🟢] — Split the day into morning/midday/
    afternoon/evening windows from `water_intake_entries[].time`; clearing each
    window pays +XP (raises "perfect lesson" moments to ~4/day, docs/12 #8b).
    **Integrate:** `_handle_hydration`/`summarize_hydration` computes per-window
    cleared + bonus; a badge for a "full water day".

72. **Personal data export (JSON/CSV)** [🟢] — GDPR-style export of
    `RawActivityLog`/`XPLedger`/gear/badges.
    **Integrate:** a management command + a profile button streaming a CSV/JSON.

73. **Weekly digest (in-app inbox or email)** [🟡] — A recap pushed to a simple
    PWA inbox on Monday.
    **Integrate:** extend `close_league_week_task` payload + a
    `Notification`/`Inbox` model + a digest template.

74. **Anomaly flags for honesty (anti-farming)** [🟡] — Flag implausible activity
    spikes for review (docs/12 §6c) and surface a gentle notice.
    **Integrate:** a velocity check on ingest + a `reviewed` flag on
    `RawActivityLog` + an admin review view.

75. **Cross-correlation insights** [🟡] — "Sleeping >7h improved your next-day
    calorie burn by X%" — lightweight derived correlations.
    **Integrate:** a reporting service over already-stored `RawActivityLog`
    (sleep → next-day endurance); hint cards on the dashboard.

76. **Goal-setting dashboard** [🟡] — Set weight/PR/habit goals, see progress,
    and earn tokens on completion.
    **Integrate:** `PlayerProfile` goal fields + a dashboard widget + a
    conversion hook on goal met.

---

## 8. Home Assistant & smart home — items 77–82

77. **Wire the documented HA webhook** [🟢] — The webhook is only a docstring;
    make it a live route that ingests smart-home events into the ELT pipeline.
    **Integrate:** `core/views.py` + `core/urls.py`
    `POST /api/v1/webhooks/home-assistant` → write `RawActivityLog` → run the
    same gamification handlers.

78. **NFC gym tap → warm-up streak combo** [🟡] — Tapping the gym NFC tag within
    N minutes of the expected workout grants a stacking XP multiplier (docs/06).
    **Integrate:** HA webhook `workout_started` → a `PlayerProfile` combo buff
    consumed by `process_payload`'s XP scaling.

79. **Smart-bed deep-sleep REST bonus** [🟡] — When HA reports a deep-sleep pad
    session *and* readiness says rest day, grant the rest-day stamina bonus an
    extra overflow chip.
    **Integrate:** HA webhook `deep_sleep` + `combat.refresh_stamina` rest-day
    bonus path.

80. **Streak-danger vs victory house lighting/sound** [🟡] — Red lights at 8 PM
    when the streak is at risk; a Flamingo victory jingle when the daily
    requirement is met by 9 PM (docs/06 outbound).
    **Integrate:** outbound HA REST calls from readiness + dashboard side-effects
    (boss/readiness hooks in `gamification.py`).

81. **Boss "arena mode" kitchen lights** [🟢] — On an engaged raid, kitchen
    lights pulse during expected training windows.
    **Integrate:** `CampaignProgress` engaged-state + an outbound HA automation.

82. **Voice/NFC quick-log of water & meals via HA** [🟡] — "Hey, I drank a glass"
    → HA → the hydration/macro handlers.
    **Integrate:** HA webhook → `RawActivityLog` hydration/nutrition handlers
    (same path as #77).

---

## 9. PWA, mobile, push, offline & sharing — items 83–90

83. **Web Push notifications** [🔴] — Streak reminders, boss respawn, league
    close — driven by readiness so it never nags on rest days (#19).
    **Integrate:** VAPID + a subscription table; a push task fed by beat
    results; `service-worker.js` handles `push` events.

84. **Home-screen shortcuts/actions** [🟢] — "Quick-log water" and "Attack boss"
    as installable PWA shortcuts (docs/12 #10c).
    **Integrate:** `manifest.json` shortcuts + `router.js` deeplinks to the
    quick-log/`battle` panels.

85. **Offline-first quick-log queue** [🟡] — Sync quick taps while offline and
    replay them on reconnect.
    **Integrate:** a `service-worker.js` outbox + a `POST /log/batch`
    (idempotent `ingest_results`) so replays never double-XP.

86. **Share-on-social capability** [🟢] — Share weekly cards / raids via the
    PWA `navigator.share`/Web Share (ties #60).
    **Integrate:** move the report card into a shareable asset + wire in
    `dashboard.js`.

87. **Install polish: icon set & splash** [🟢] — Complete PWA install metadata.
    **Integrate:** `manifest.json` icons + service-worker precache.

88. **Glanceable app widgets/shortcut views** [🟡] — Terse summary views for
    quick check-ins.
    **Integrate:** a lightweight `GET /api/v1/summary` + PWA/shortcut views in
    `dashboard.js`.

89. **Deep-link cards for campaigns/bosses/leagues** [🟢] — Share a URL that
    opens the right panel.
    **Integrate:** `router.js` routes + optional URL params on panels.

90. **Background sync on reconnect** [🟡] — Flush pending polls/logs the moment
    the device is back online.
    **Integrate:** a `service-worker.js` `sync` event + `ingest_results` batch.

---

## 10. UI/UX, theme, polish & accessibility — items 91–95

91. **Guided first-flight onboarding** [🟢] ✅ Implemented — A short walkthrough explaining the
    loop (skill trees → tokens → loot → sieges → PvP) so new users get oriented.
    **Integrate:** a modal sequence in `dashboard.js` + an `onboarded` flag;
    reuse existing panels.
    **Implemented:** `PlayerProfile.onboarded` (migration `0014`) + `POST /api/v1/onboarded`; a 5-step
    modal tour in `dashboard.js` (triggered from `onboarded === false`, deep-links to the Shop / Battle
    / PvP panels) that persists completion on finish **or** skip.

92. **Consistent empty states & "why no data" hints** [🟢] ✅ Implemented — Every panel tells
    you *why* it's empty and what to link/do (docs/04 philosophy).
    **Integrate:** each `render*` empty branch in every controller + a
    "Link X" CTA.
    **Implemented:** the shared `window.showEmptyState()` / `emptyStateHTML()` component (dashboard.js)
    now drives the empty branch of every panel (skill trees + boss + recovery + badges + leagues + battle
    + loadout + shop + pvp) with a consistent "why + Link X" card.

93. **Reduced-motion + accessibility pass** [🟢] — Honor `prefers-reduced-motion`,
    add ARIA labels, and check contrast of the neon palette.
    **Integrate:** CSS `@media (prefers-reduced-motion)` in `dashboard.css`;
    focus styles; `theme.js` contrast-safe variants.

94. **i18n-ready string layer** [🟡] — Centralize user-facing strings so
    localization is a follow-up, not a rewrite.
    **Integrate:** a `strings.js` table + template placeholders; no framework.

95. **Dark/light/device theme polish** [🟢] — `Theme` model (migration `0008`)
    exists; finish theme-aware neon/contrast across every panel.
    **Integrate:** `theme.js` + CSS vars per docs/09 day/night pattern.

---

## 11. Economy balance, admin, ops & misc — items 96–100

96. **Tuning dashboard & audit log** [🟢] — Document and change-lock the economy
    constants so tuning is reviewable.
    **Integrate:** an admin read-only view over the `core/services/combat.py`
    constants + a changelog model; seed diffs.

97. **Seasonal soft-reset of PvP/leagues** [🟡] — Reset competitive standings
    each season while preserving lifetime stats.
    **Integrate:** `LeagueWeek`/`LeagueResult` rollover + a `PvPSeason`; keep
    `PlayerProfile.pvp_wins/losses`, `SkillTree.total_xp` permanent.

98. **Multi-device sync cursor hardening** [🟡] — Per-provider sync cursors so
    multiple devices don't re-ingest or clobber each other.
    **Integrate:** extend `UserIntegration` with a `cursor` field; reuse
    `ingest_results` dedup (docs/10 self-healing).

99. **Opt-in analytics & events** [🔴] — Self-hosted, privacy-friendly events for
    retention tuning.
    **Integrate:** an `EventLog` model written from views/services + an admin
    dashboard; always opt-in.

100. **Feature flags & config-driven gating** [🟢] — Turn experimental features
     on/off per user or globally from the admin.
     **Integrate:** a `FeatureFlag` table + settings gating read by views; gates
     the 🔴-tier experiments above before they're permanent.

---

## 12. Recommended first slices (for an implementer)

Grouped by payoff/effort — all additive, and each names its existing hooks above.

- **Tier 1 (🟢, high value, low risk):** #5 manual quick-log, #11 rest-day
  carry token, #13 effort decay, #15 perfect-week, #51 daily free pack + pity
  #56, #77 wire the HA webhook, #61 activity-mix titles, #68 PR timeline.
- **Tier 2 (🟡):** #23 flock raid bosses, #2 Withings scale, #47 crafting,
  #57 flock quests, #37 flock gyms, #34 siege timeline, #10 adaptive TDEE.
- **Tier 3 (🔴, biggest systems):** #83 web push, #59 friend chat/reactions,
  #44 PvP tournaments, #32 server-wide mega-boss, #99 opt-in analytics.

**Validation gate** (matching the repo convention): any implemented idea should
ship with `python manage.py test core --settings=flamingo_fitness.test_settings`
green, `node --check core/static/core/js/<controller>.js`, and a docs sweep of
`docs/00/01/02/03/07/08/12/13/15/16` where its integration touches them.

