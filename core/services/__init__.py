"""Service layer for Flamingo Fitness.

Exposes the gamification and readiness engines to views, tasks and admin.
"""

from .api_clients import (  # noqa: F401
    GarminClient,
    PelotonClient,
    get_client,
)
from .sparky_client import SparkyFitnessClient  # noqa: F401
from .liftosaur_client import LiftosaurClient  # noqa: F401
from .gamification import (  # noqa: F401
    XP_PER_LEVEL,
    process_log,
    process_payload,
    summarize_endurance,
    summarize_hydration,
    summarize_nutrition,
    summarize_sleep,
    summarize_strength,
)
from .readiness import (  # noqa: F401
    compute_readiness,
    compute_readiness_for_all_users,
)
from .base_economy import (  # noqa: F401
    BLUEPRINT_DROP_CHANCE,
    BLUEPRINT_DROP_NAME,
    CRIT_CHANCE,
    ENERGY_CAP,
    ENERGY_PER_HOUR,
    MAX_XP_BONUS_PCT,
    MODALITY_BUFF,
    MODALITY_BUFF_HOURS,
    REST_DAY_ENERGY_BONUS,
    STAFF_BONUS,
    STREAK_CAP_DAYS,
    STREAK_STEP,
    XP_TO_MATERIALS,
    apply_rest_day_bonus,
    base_level,
    base_xp_bonus_pct,
    clear_expired_buffs,
    collect_building,
    complete_or_pending,
    daily_harvest,
    evaluate_synergies,
    evolve_building,
    log_modality_workout,
    maybe_drop_blueprint,
    modality_buff_active,
    production_plan,
    refresh_energy,
    refresh_resources,
    resource_dump,
    spend_speedups,
    start_construction,
    streak_multiplier,
    tick_base_economy,
    xp_dividend,
)
from .stat_explainers import STAT_KEYS, explain_stat  # noqa: F401
from .avatar import (  # noqa: F401
    DEFAULT_AVATAR,
    avatar_url,
    reset_avatar,
    save_avatar,
)
from .leagues import (  # noqa: F401
    LEAGUE_TIERS,
    LEAGUE_TOP_N_REWARDED,
    WEEKLY_REWARDS,
    close_league_week,
    ensure_current_week,
    league_state,
    tier_for_xp,
    week_start_for,
    weekly_xp_map,
    weekly_xp_rows,
)
from .challenges import (  # noqa: F401
    active_challenge,
    calories_burned_in_window,
    challenge_state,
    metric_progress,
)
from .social import (  # noqa: F401
    FLOCK_MAX_MEMBERS,
    create_flock,
    friends_of,
    get_friendship,
    invite_to_flock,
    leave_flock,
    membership_of,
    remove_friend,
    respond_flock_invite,
    respond_friend_request,
    search_users,
    send_friend_request,
    social_state,
)
