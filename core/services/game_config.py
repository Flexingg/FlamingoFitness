"""Load ``config/gameplay.json`` into a dict for owner-tunable balance knobs.

All game/balancing numbers (the "admin / instance owner" tuning constants) live
in ``config/gameplay.json`` instead of Python - mirroring how the content
catalogs live in ``config/seeds/*.json``. Services import :data:`GAMEPLAY` and
bind their module-level constants from it, so an owner can retune the economy,
stamina, gacha odds, combat, leagues, etc. without touching code.

This module has no Django model dependency and is safe to import anywhere (even
before ``django.setup()``).
"""

import json
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"

with (CONFIG_DIR / "gameplay.json").open("r", encoding="utf-8") as _fh:
    GAMEPLAY = json.load(_fh)
