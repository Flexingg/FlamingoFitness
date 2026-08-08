"""Service layer for Flamingo Fitness.

Exposes the gamification and readiness engines to views, tasks and admin.
"""

from .api_clients import (  # noqa: F401
    GarminClient,
    LiftosaurClient,
    PelotonClient,
    get_client,
)
from .sparky_client import SparkyFitnessClient  # noqa: F401
from .gamification import (  # noqa: F401
    XP_PER_LEVEL,
    process_log,
    process_payload,
    summarize_hydration,
    summarize_nutrition,
)
from .readiness import (  # noqa: F401
    compute_readiness,
    compute_readiness_for_all_users,
)
