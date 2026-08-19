# File Map by Feature

> A comprehensive file-location reference for the Flamingo Fitness codebase,
> organized by feature area. Use this guide to quickly find the files that
> belong to a specific subsystem. All paths are relative to the repo root
> (`C:\RandallEngineering\FlamingoFitness`).

---

## 1. Base / Infra (Django project shell, config, deployment)

| File | Purpose |
|---|---|
| `flamingo_fitness/__init__.py` | Package marker |
| `flamingo_fitness/asgi.py` | ASGI entrypoint |
| `flamingo_fitness/wsgi.py` | WSGI entrypoint |
| `flamingo_fitness/settings.py` | Main Django settings (apps, DB, cache, Celery beat schedule, media) |
| `flamingo_fitness/test_settings.py` | Overrides for unit-test runs |
| `flamingo_fitness/urls.py` | Root URLconf (includes `core.urls`) |
| `flamingo_fitness/celery.py` | Celery application bootstrap |
| `flamingo_fitness/whitenoise.py` | Subclassed WhiteNoise to serve `/media/` files |
| `Dockerfile` | Container image definition |
| `docker-compose.yml` | Orchestration (web + db + redis + celery worker + celery beat) |
| `.env` | Local secrets / environment variables |
| `.env.example` | Template for `.env` |
| `.dockerignore` | Docker build context exclusions |
| `.gitignore` | Git exclusions |
| `manage.py` | Django management CLI |
| `requirements.txt` | Python dependencies |

---

## 2. Frontend - Templates & Static Assets

### 2.1 HTML Template

| File | Purpose |
|---|---|
| `core/templates/core/dashboard.html` | Single-page app shell - loads every JS controller, defines the top-nav, skill-tree, bottom-nav, and all panel/modal shells |

### 2.2 CSS

| File | Purpose |
|---|---|
| `core/static/core/css/dashboard.css` | All app styles (Miami/Duolingo bubbly theme, skill-tree, panels, nav, modals, toast) |
| `core/static/core/css/auth.css` | Login / signup page styles |

### 2.3 JavaScript Controllers (loaded in order from `dashboard.html`)

| File | Purpose / API endpoints consumed |
|---|---|
| `core/static/core/js/dashboard.js` | Main controller - fetches `GET /api/v1/dashboard/state`, renders top-nav stats, readiness card, skill-tree nodes, leaderboard modal, modal helpers, bottom-nav tab switching |
| `core/static/core/js/nutrition.js` | Nutrition panel - `GET /api/v1/nutrition/` |
| `core/static/core/js/hydration.js` | Hydration panel - `GET /api/v1/hydration/` |
| `core/static/core/js/endurance.js` | Endurance panel - `GET /api/v1/endurance/` |
| `core/static/core/js/strength.js` | Strength panel - `GET /api/v1/strength/` |
| `core/static/core/js/boss.js` | PR Boss panel - `GET /api/v1/boss/` |
| `core/static/core/js/recovery.js` | Recovery panel - `GET /api/v1/recovery/` |
| `core/static/core/js/badges.js` | Achievement badges panel - `GET /api/v1/badges/` |
| `core/static/core/js/leagues.js` | Leagues / Challenges / Flock panel - `GET /api/v1/leagues/`, `GET /api/v1/challenges/`, `GET /api/v1/social/`, POST friends & flock actions; implements the friend picker modal |
| `core/static/core/js/shop.js` | Gacha Shop + Scrap Shop - `GET /api/v1/shop/state`, `POST /shop/open|consume`, `GET /api/v1/scrap/shop/state`, `POST /scrap/recycle`, `/scrap/shop/buy` |
| `core/static/core/js/loadout.js` | Loadout panel - `GET /api/v1/loadout/state`, `POST /loadout/equip|unequip` |
| `core/static/core/js/battle.js` | PvE siege panel - `GET /api/v1/battle/state`, `/battle/campaign/{campaign}`, `POST /battle/engage|attack` |
| `core/static/core/js/pvp.js` | PvP Gym panel - `GET /api/v1/pvp/state`, `POST /pvp/defend|attack` |
| `core/static/core/js/stat_info.js` | Top-nav stat explainer modal - `GET /api/v1/stats/{streak,tokens,stamina}/` |

### 2.4 PWA

| File | Purpose |
|---|---|
| `core/static/core/manifest.json` | PWA manifest (installable app) |
| `core/static/core/service-worker.js` | Offline / instant-loading service worker |
| `core/static/core/icons/icon-192.svg` | App icon |

---

## 3. Python Views (API & Pages)

All views live in a single file: `core/views.py`.

| View function | Route | Feature |
|---|---|---|
| `signup` | `GET/POST /api/v1/signup/` | Auth |
| `profile` | `GET/POST /api/v1/profile/` | Auth / Integrations |
| `avatar_upload` | `POST /api/v1/profile/avatar` | Auth |
| `dashboard_page` | `GET /` | Dashboard page |
| `dashboard_state` | `GET /api/v1/dashboard/state` | Dashboard |
| `leaderboard_weekly` | `GET /api/v1/leaderboard/weekly` (+ optional `?kind=` like-with-like filter, docs/17 #17) | Dashboard |
| `nutrition_state` | `GET /api/v1/nutrition/` | Dashboard |
| `hydration_state` | `GET /api/v1/hydration/` | Dashboard |
| `endurance_state` | `GET /api/v1/endurance/` | Dashboard |
| `strength_state` | `GET /api/v1/strength/` | Dashboard |
| `boss_state` | `GET /api/v1/boss/` | Dashboard |
| `recovery_state` | `GET /api/v1/recovery/` | Dashboard |
| `battle_state` | `GET /api/v1/battle/state` | Battle (PvE) |
| `battle_campaign` | `GET /api/v1/battle/campaign/{campaign}` | Battle (PvE) |
| `battle_engage` | `POST /api/v1/battle/engage` | Battle (PvE) |
| `battle_attack` | `POST /api/v1/battle/attack` | Battle (PvE) |
| `battle_leaderboard` | `GET /api/v1/battle/leaderboard/{campaign}` (docs/17 #33) | Battle (PvE) |
| `battle_history` | `GET /api/v1/battle/history/{campaign}` (docs/17 #34) | Battle (PvE) |
| `shop_state` | `GET /api/v1/shop/state` | Shop |
| `shop_open` | `POST /api/v1/shop/open` | Shop |
| `shop_consume` | `POST /api/v1/shop/consume` | Shop |
| `scrap_recycle` | `POST /api/v1/scrap/recycle` | Scrap Shop |
| `scrap_shop` | `GET /api/v1/scrap/shop/state` | Scrap Shop |
| `scrap_buy` | `POST /api/v1/scrap/shop/buy` | Scrap Shop |
| `loadout_state` | `GET /api/v1/loadout/state` | Loadout |
| `loadout_equip` | `POST /api/v1/loadout/equip` | Loadout |
| `loadout_unequip` | `POST /api/v1/loadout/unequip` | Loadout |
| `pvp_state` | `GET /api/v1/pvp/state` | PvP |
| `pvp_defend` | `POST /api/v1/pvp/defend` | PvP |
| `pvp_attack` | `POST /api/v1/pvp/attack` | PvP |
| `leagues_state` | `GET /api/v1/leagues/` | Leagues |
| `challenges_state` | `GET /api/v1/challenges/` | Challenges |
| `social_state_view` | `GET /api/v1/social/` | Social |
| `friends_request` | `POST /api/v1/friends/request` | Social |
| `friends_respond` | `POST /api/v1/friends/respond` | Social |
| `friends_remove` | `POST /api/v1/friends/remove` | Social |
| `flocks_create` | `POST /api/v1/flocks/create` | Social |
| `flocks_invite` | `POST /api/v1/flocks/invite` | Social |
| `flocks_respond` | `POST /api/v1/flocks/respond` | Social |
| `flocks_leave` | `POST /api/v1/flocks/leave` | Social |
| `badges_state` | `GET /api/v1/badges/` | Badges |
| `stat_info` | `GET /api/v1/stats/{stat}/` | Stat Explainers |
| `home_assistant_webhook` | `POST /api/v1/webhooks/home-assistant` | Home Assistant |

---

## 4. URL Routing

| File | Purpose |
|---|---|
| `flamingo_fitness/urls.py` | Root URLconf - routes requests to `core.urls` |
| `core/urls.py` | All feature URL patterns (auth, dashboard, battle, shop, loadout, pvp, leagues, challenges, social, badges, stat explainers, HA webhook) |
---

## 5. Models (Database Schema)

All models live in `core/models.py`.

| Model | Table (approx.) | Feature |
|---|---|---|
| `User` | `core_user` | Auth - custom user with streak + avatar |
| `UserIntegration` | `core_userintegration` | Integrations - API credentials per provider |
| `RawActivityLog` | `core_rawactivitylog` | Ingestion - ELT inbox for all external data |
| `XPLedger` | `core_xpledger` | Gamification - immutable XP ledger |
| `SkillTree` | `core_skilltree` | Dashboard - per-user per-modality level/XP |
| `DailyReadiness` | `core_dailyreadiness` | Dashboard - readiness score per day |
| `BossConfig` | `core_bossconfig` | Dashboard - PR Boss definition |
| `PlayerProfile` | `core_playerprofile` | Combat - token/stamina/scraps wallet + conquest/PvP counters |
| `GearPackDef` | `core_gearpackdef` | Shop - purchasable Gacha pack/crate |
| `GearItemDef` | `core_gearitemdef` | Shop - gear/consumable catalog |
| `UserGear` | `core_usergear` | Shop - owned gear / consumable stacks |
| `ScrapShopItem` | `core_scrapshopitem` | Shop - rotating scrap offers |
| `CampaignBoss` | `core_campaignboss` | Battle - PvE boss definition |
| `CampaignProgress` | `core_campaignprogress` | Battle - per-user siege progress |
| `BattleLog` | `core_battlelog` | Battle - one attack result |
| `Gym` | `core_gym` | PvP - player's home turf |
| `GymOccupation` | `core_gymoccupation` | PvP - who holds a gym |
| `PvPMatch` | `core_pvpmatch` | PvP - resolved gym battle |
| `BadgeDef` | `core_badgedef` | Badges - badge catalog |
| `UserBadge` | `core_userbadge` | Badges - per-user awarded badges |
| `LeagueWeek` | `core_leagueweek` | Leagues - weekly periods |
| `LeagueResult` | `core_leagueresult` | Leagues - rank/tier/reward snapshots |
| `Challenge` | `core_challenge` | Challenges - rolling community goals |
| `Friendship` | `core_friendship` | Social - friend requests / friendships |
| `Flock` | `core_flock` | Social - group entity |
| `FlockMembership` | `core_flockmembership` | Social - user-to-flock membership |
| `FlockInvite` | `core_flockinvite` | Social - pending invitations |

---

## 6. Service Layer

All core business logic lives in `core/services/`. Public symbols are re-exported via `core/services/__init__.py`.

### 6.1 Gamification

| File | Key exports | Feature |
|---|---|---|
| `core/services/gamification.py` | `process_log`, `process_payload`, `summarize_*` (endurance/hydration/nutrition/sleep/strength), `XP_PER_LEVEL` | Dashboard - XP award, modality summaries |

### 6.2 Readiness

| File | Key exports | Feature |
|---|---|---|
| `core/services/readiness.py` | `compute_readiness`, `compute_readiness_for_all_users` | Dashboard - Garmin Readiness score |
### 6.3 Combat (Tokens, Gacha, Battle & PvP)

| File | Key exports | Feature |
|---|---|---|
| `core/services/combat.py` | `profile`, `award_tokens`, `spend_tokens`, `daily_token_harvest`, `refresh_stamina`, `open_pack`, `total_gear_multiplier`, `compute_attack`, `engage_boss`, `attack_boss`, `set_defense`, `attack_gym`, `pay_gym_yields`, `scrap_value`, `recycle_gear`, `scrap_shop_state`, `buy_scrap_item`, plus many constants & helpers | Combat, Shop, Battle & PvP |

### 6.4 Leagues

| File | Key exports | Feature |
|---|---|---|
| `core/services/leagues.py` | `league_state`, `close_league_week`, `ensure_current_week`, `tier_for_xp`, `weekly_xp_map`, `weekly_xp_rows`; constants `LEAGUE_TIERS`, `LEAGUE_TOP_N_REWARDED`, `WEEKLY_REWARDS` | Leagues |

### 6.5 Challenges

| File | Key exports | Feature |
|---|---|---|
| `core/services/challenges.py` | `challenge_state`, `active_challenge`, `calories_burned_in_window`, `metric_progress` | Challenges |

### 6.6 Social (Friends & Flocks)

| File | Key exports | Feature |
|---|---|---|
| `core/services/social.py` | `social_state`, `send_friend_request`, `respond_friend_request`, `remove_friend`, `friends_of`, `create_flock`, `invite_to_flock`, `respond_flock_invite`, `leave_flock`, `search_users`; constant `FLOCK_MAX_MEMBERS` | Social |

### 6.7 Badges

| File | Key exports | Feature |
|---|---|---|
| `core/services/badges.py` | `badges_state` | Badges |

### 6.8 Stat Explainers

| File | Key exports | Feature |
|---|---|---|
| `core/services/stat_explainers.py` | `STAT_KEYS`, `explain_stat` | Stat Explainers |

### 6.9 Avatar

| File | Key exports | Feature |
|---|---|---|
| `core/services/avatar.py` | `save_avatar`, `reset_avatar`, `avatar_url`, `DEFAULT_AVATAR` | Auth / Profile |

### 6.10 API Clients (External Integrations)

| File | Key exports | Feature |
|---|---|---|
| `core/services/api_clients.py` | `GarminClient`, `PelotonClient`, `get_client` | Integrations |
| `core/services/sparky_client.py` | `SparkyFitnessClient` | Integrations |
| `core/services/liftosaur_client.py` | `LiftosaurClient` | Integrations |
---

## 7. Background Tasks (Celery)

All tasks live in `core/tasks.py`. Schedules are configured in `flamingo_fitness/settings.py` (`CELERY_BEAT_SCHEDULE`).

| Task | Schedule | Feature |
|---|---|---|
| `poll_garmin` | every 2h | Integrations |
| `poll_peloton` | every 4h | Integrations |
| `poll_liftosaur` | every 6h | Integrations |
| `sync_liftosaur_for_user` | on-demand (from profile) | Integrations |
| `poll_sparkyfitness` | every 4h | Integrations |
| `compute_readiness_for_all` | daily @ 06:15 | Dashboard |
| `tick_combat_daily` | daily @ 00:10 | Combat (tokens / stamina / gym yields) |
| `close_league_week_task` | weekly Mon 00:35 | Leagues |

---

## 8. Admin Interface

| File | Purpose |
|---|---|
| `core/admin.py` | Django admin registrations for all app models - list/edit/filter/search configs |

---

## 9. Forms

| File | Form classes | Feature |
|---|---|---|
| `core/forms.py` | `SignupForm`, `SparkyLinkForm`, `LiftosaurLinkForm` | Auth / Integrations |

---

## 10. Tests

| File | Purpose |
|---|---|
| `core/tests.py` | All unit tests |

---

## 11. Seed / Demo Data

| File | Purpose |
|---|---|
| `core/management/commands/seed_demo.py` | `manage.py seed_demo` - seeds badge catalog, boss configs, and the Phase 9 combat catalog |
| `core/management/commands/create_demo_accounts.py` | `manage.py create_demo_accounts` - creates `player1` and related demo data |
---

## 12. Documentation (`docs/`)

| File | Content |
|---|---|
| `docs/00_AI_Overview.md` | Project overview for AI coding assistants |
| `docs/01_Database_Schema.md` | Detailed schema reference |
| `docs/02_API_Contracts.md` | API contract reference |
| `docs/03_Gamification_Math.md` | XP / leveling / streak math |
| `docs/04_Frontend_Architecture.md` | Frontend architecture notes |
| `docs/05_Docker_Infrastructure.md` | Docker / deployment notes |
| `docs/06_Home_Assistant_Spec.md` | Home Assistant webhook spec |
| `docs/07_Next_Steps.md` | Build sequence & roadmap |
| `docs/08_Questions.md` | Open design questions |
| `docs/09_Base_Building_Meta_Game-Now_Cancelled.md` | Base-building design (CANCELLED - replaced by Phase 9 combat) |
| `docs/10_Sparky_Fitness_Integration.md` | SparkyFitness integration notes |
| `docs/11_Liftosaur_Integration.md` | Liftosaur integration notes |
| `docs/12_Gamification_Ideas_Roadmap.md` | Future gamification ideas |
| `docs/13_Leagues_Challenges_Flocks.md` | Phase 8 social features design |
| `docs/14_File_Map_by_Feature.md` | **This file** |
| `docs/liftosaur_api_spec.md` | Liftosaur API spec reference |
| `docs/sparky_fitness_open_api_spec_json.json` | SparkyFitness OpenAPI spec |

---

## 13. Utility / Scratch Scripts

| File | Purpose |
|---|---|
| `_fix_nav.py` | Untracked one-off script (not part of the app) |

---

## Quick Reference - "Where is the {feature} code?"

| Feature | Python Views | Service Layer | JS Controller | Models |
|---|---|---|---|---|
| **Auth / Profile** | `views.signup`, `views.profile`, `views.avatar_upload` | `services/avatar.py` | `dashboard.js` (top-nav) | `User` |
| **Dashboard** | `views.dashboard_state`, `views.dashboard_page`, `views.leaderboard_weekly` | `services/gamification.py`, `services/readiness.py` | `dashboard.js`, `nutrition.js`, `hydration.js`, `endurance.js`, `strength.js`, `recovery.js`, `boss.js` | `SkillTree`, `DailyReadiness`, `BossConfig` |
| **Combat / Battle** | `views.battle_*` (4 endpoints) | `services/combat.py` | `battle.js` | `CampaignBoss`, `CampaignProgress`, `BattleLog` |
| **Shop / Scrap** | `views.shop_*`, `views.scrap_*` | `services/combat.py` | `shop.js` | `GearPackDef`, `GearItemDef`, `UserGear`, `ScrapShopItem` |
| **Loadout** | `views.loadout_*` | `services/combat.py` | `loadout.js` | `UserGear`, `GearItemDef` |
| **PvP** | `views.pvp_*` (3 endpoints) | `services/combat.py` | `pvp.js` | `Gym`, `GymOccupation`, `PvPMatch` |
| **Leagues** | `views.leagues_state` | `services/leagues.py` | `leagues.js` | `LeagueWeek`, `LeagueResult` |
| **Challenges** | `views.challenges_state` | `services/challenges.py` | `leagues.js` | `Challenge` |
| **Social** | `views.social_state_view`, `friends_*`, `flocks_*` (7 endpoints) | `services/social.py` | `leagues.js` | `Friendship`, `Flock`, `FlockMembership`, `FlockInvite` |
| **Badges** | `views.badges_state` | `services/badges.py` | `badges.js` | `BadgeDef`, `UserBadge` |
| **Stat Explainers** | `views.stat_info` | `services/stat_explainers.py` | `stat_info.js` | (derived from existing data) |
| **Integrations** | (via profile view + tasks) | `services/api_clients.py`, `sparky_client.py`, `liftosaur_client.py` | - | `UserIntegration` |
| **Home Assistant** | `views.home_assistant_webhook` | `services/gamification.py` (`process_log`) | - | `RawActivityLog` |
