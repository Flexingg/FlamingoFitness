"""Create demo user accounts (admin + player) and integrations.

Usage:
    python manage.py create_demo_accounts

Creates:
  * an admin superuser  (admin / adminpass123)
  * a demo player       (player1 / playerpass123)
  * active Garmin / Peloton / Liftosaur / SparkyFitness integrations for player1
  * the Phase 9 (docs/15 §8) Gacha packs + gear catalog + campaign bosses
  * a demo PlayerProfile wallet + starter loadout + gyms for PvP
  * default PR Boss benchmarks (BossConfig)
  * the default Phase 8 challenge ("Calorie Torch"), the current open league
    week, a demo friendship (player1 <-> admin) and the "Flamingo Fam" flock

This command is idempotent and safe to run on every container startup.
It does NOT run any mock pollers or create activity data.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from core.models import (
    BossConfig,
    CampaignBoss,
    Challenge,
    Flock,
    FlockMembership,
    Friendship,
    GearItemDef,
    GearPackDef,
    Gym,
    PlayerProfile,
    Provider,
    UserGear,
    UserIntegration,
)

User = get_user_model()

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "adminpass123"

PLAYER_USERNAME = "player1"
PLAYER_PASSWORD = "playerpass123"

"""
Full seed data for Phase 9: Gacha packs, gear catalog, and campaign bosses.
Contains the original seed items plus 50 new additions for each category.
"""

# ==========================================
# PACKS (Total: 59)
# ==========================================
DEFAULT_PACKS = [
    # --- Original Packs ---
    {"slug": "starter_pack", "name": "Starter Pack", "price_tokens": 100,
     "draws": 2, "domains": [], "guaranteed_min_rarity": "common", "sort_order": 1},
    {"slug": "rare_crate", "name": "Rare Crate", "price_tokens": 150,
     "draws": 1, "domains": [], "guaranteed_min_rarity": "rare", "is_generic": True,
     "icon": "fa-box", "sort_order": 2,
     "description": "A no-frills crate that guarantees at least a Rare from the whole catalog."},
    {"slug": "epic_crate", "name": "Epic Crate", "price_tokens": 400,
     "draws": 1, "domains": [], "guaranteed_min_rarity": "epic", "is_generic": True,
     "icon": "fa-box", "sort_order": 3,
     "description": "Guarantees at least an Epic - bulk-buying makes it far better value."},
    {"slug": "iron_roost", "name": "Iron Roost", "price_tokens": 100,
     "draws": 1, "domains": ["strength"], "guaranteed_min_rarity": "common", "sort_order": 4},
    {"slug": "alchemist_pack", "name": "Alchemist's Pack", "price_tokens": 250,
     "draws": 3, "domains": ["nutrition", "hydration"], "guaranteed_min_rarity": "rare", "sort_order": 5},
    {"slug": "cardio_storm", "name": "Cardio Storm", "price_tokens": 100,
     "draws": 1, "domains": ["cardio"], "guaranteed_min_rarity": "common", "sort_order": 6},
    {"slug": "slumber_serum", "name": "Slumber Serum", "price_tokens": 100,
     "draws": 1, "domains": ["sleep"], "guaranteed_min_rarity": "common", "sort_order": 7},
    {"slug": "legendary_vault", "name": "Legendary Vault", "price_tokens": 500,
     "draws": 5, "domains": [], "guaranteed_min_rarity": "epic", "sort_order": 8},
    {"slug": "legendary_crate", "name": "Legendary Crate", "price_tokens": 800,
     "draws": 1, "domains": [], "guaranteed_min_rarity": "legendary", "is_generic": True,
     "icon": "fa-gem", "sort_order": 9,
     "description": "One guaranteed Legendary from the whole catalog. The lucky dip of a lifetime."},

    # --- New Strength Packs ---
    {"slug": "chalk_bag", "name": "Chalk Bag", "price_tokens": 80, "draws": 1, "domains": ["strength"], "guaranteed_min_rarity": "common", "sort_order": 10},
    {"slug": "powerlifter_stash", "name": "Powerlifter's Stash", "price_tokens": 200, "draws": 2, "domains": ["strength"], "guaranteed_min_rarity": "rare", "sort_order": 11},
    {"slug": "barbell_case", "name": "Barbell Case", "price_tokens": 150, "draws": 1, "domains": ["strength"], "guaranteed_min_rarity": "rare", "sort_order": 12},
    {"slug": "titan_vault", "name": "Titan's Vault", "price_tokens": 450, "draws": 3, "domains": ["strength"], "guaranteed_min_rarity": "epic", "sort_order": 13},
    {"slug": "berserker_crate", "name": "Berserker Crate", "price_tokens": 300, "draws": 2, "domains": ["strength"], "guaranteed_min_rarity": "rare", "sort_order": 14},
    {"slug": "plate_hoarder_box", "name": "Plate Hoarder Box", "price_tokens": 120, "draws": 1, "domains": ["strength"], "guaranteed_min_rarity": "common", "sort_order": 15},
    {"slug": "kettlebell_cache", "name": "Kettlebell Cache", "price_tokens": 250, "draws": 2, "domains": ["strength"], "guaranteed_min_rarity": "rare", "sort_order": 16},
    {"slug": "strongman_sack", "name": "Strongman's Sack", "price_tokens": 350, "draws": 3, "domains": ["strength"], "guaranteed_min_rarity": "rare", "sort_order": 17},
    {"slug": "anvil_drop", "name": "Anvil Drop", "price_tokens": 600, "draws": 1, "domains": ["strength"], "guaranteed_min_rarity": "legendary", "sort_order": 18},
    {"slug": "muscle_mystery_box", "name": "Muscle Mystery Box", "price_tokens": 100, "draws": 3, "domains": ["strength"], "guaranteed_min_rarity": "common", "sort_order": 19},

    # --- New Cardio Packs ---
    {"slug": "sprinter_pouch", "name": "Sprinter's Pouch", "price_tokens": 90, "draws": 1, "domains": ["cardio"], "guaranteed_min_rarity": "common", "sort_order": 20},
    {"slug": "marathon_bag", "name": "Marathon Bag", "price_tokens": 220, "draws": 2, "domains": ["cardio"], "guaranteed_min_rarity": "rare", "sort_order": 21},
    {"slug": "trailblazer_pack", "name": "Trailblazer's Pack", "price_tokens": 300, "draws": 3, "domains": ["cardio"], "guaranteed_min_rarity": "rare", "sort_order": 22},
    {"slug": "vo2_max_crate", "name": "VO2 Max Crate", "price_tokens": 500, "draws": 3, "domains": ["cardio"], "guaranteed_min_rarity": "epic", "sort_order": 23},
    {"slug": "treadmill_treasure", "name": "Treadmill Treasure", "price_tokens": 150, "draws": 1, "domains": ["cardio"], "guaranteed_min_rarity": "rare", "sort_order": 24},
    {"slug": "cyclist_satchel", "name": "Cyclist's Satchel", "price_tokens": 180, "draws": 2, "domains": ["cardio"], "guaranteed_min_rarity": "common", "sort_order": 25},
    {"slug": "swimmer_cache", "name": "Swimmer's Cache", "price_tokens": 250, "draws": 2, "domains": ["cardio"], "guaranteed_min_rarity": "rare", "sort_order": 26},
    {"slug": "endurance_vault", "name": "Endurance Vault", "price_tokens": 650, "draws": 1, "domains": ["cardio"], "guaranteed_min_rarity": "legendary", "sort_order": 27},
    {"slug": "jump_rope_box", "name": "Jump Rope Box", "price_tokens": 80, "draws": 1, "domains": ["cardio"], "guaranteed_min_rarity": "common", "sort_order": 28},
    {"slug": "aero_crate", "name": "Aero Crate", "price_tokens": 350, "draws": 2, "domains": ["cardio"], "guaranteed_min_rarity": "epic", "sort_order": 29},

    # --- New Nutrition Packs ---
    {"slug": "snack_box", "name": "Snack Box", "price_tokens": 70, "draws": 1, "domains": ["nutrition"], "guaranteed_min_rarity": "common", "sort_order": 30},
    {"slug": "protein_pouch", "name": "Protein Pouch", "price_tokens": 160, "draws": 2, "domains": ["nutrition"], "guaranteed_min_rarity": "common", "sort_order": 31},
    {"slug": "macro_crate", "name": "Macro Crate", "price_tokens": 280, "draws": 2, "domains": ["nutrition"], "guaranteed_min_rarity": "rare", "sort_order": 32},
    {"slug": "keto_chest", "name": "Keto Chest", "price_tokens": 320, "draws": 3, "domains": ["nutrition"], "guaranteed_min_rarity": "rare", "sort_order": 33},
    {"slug": "vegan_vault", "name": "Vegan Vault", "price_tokens": 320, "draws": 3, "domains": ["nutrition"], "guaranteed_min_rarity": "rare", "sort_order": 34},
    {"slug": "butcher_bag", "name": "Butcher's Bag", "price_tokens": 400, "draws": 2, "domains": ["nutrition"], "guaranteed_min_rarity": "epic", "sort_order": 35},
    {"slug": "farmer_crate", "name": "Farmer's Crate", "price_tokens": 150, "draws": 1, "domains": ["nutrition"], "guaranteed_min_rarity": "rare", "sort_order": 36},
    {"slug": "harvest_box", "name": "Harvest Box", "price_tokens": 200, "draws": 2, "domains": ["nutrition"], "guaranteed_min_rarity": "rare", "sort_order": 37},
    {"slug": "chef_stash", "name": "Chef's Stash", "price_tokens": 550, "draws": 3, "domains": ["nutrition"], "guaranteed_min_rarity": "epic", "sort_order": 38},
    {"slug": "golden_apple_crate", "name": "Golden Apple Crate", "price_tokens": 700, "draws": 1, "domains": ["nutrition"], "guaranteed_min_rarity": "legendary", "sort_order": 39},

    # --- New Hydration Packs ---
    {"slug": "puddle_pouch", "name": "Puddle Pouch", "price_tokens": 60, "draws": 1, "domains": ["hydration"], "guaranteed_min_rarity": "common", "sort_order": 40},
    {"slug": "splash_bag", "name": "Splash Bag", "price_tokens": 120, "draws": 2, "domains": ["hydration"], "guaranteed_min_rarity": "common", "sort_order": 41},
    {"slug": "bottle_box", "name": "Bottle Box", "price_tokens": 180, "draws": 1, "domains": ["hydration"], "guaranteed_min_rarity": "rare", "sort_order": 42},
    {"slug": "canteen_crate", "name": "Canteen Crate", "price_tokens": 260, "draws": 2, "domains": ["hydration"], "guaranteed_min_rarity": "rare", "sort_order": 43},
    {"slug": "river_sack", "name": "River Sack", "price_tokens": 350, "draws": 3, "domains": ["hydration"], "guaranteed_min_rarity": "rare", "sort_order": 44},
    {"slug": "ocean_chest", "name": "Ocean Chest", "price_tokens": 480, "draws": 2, "domains": ["hydration"], "guaranteed_min_rarity": "epic", "sort_order": 45},
    {"slug": "aqua_crate", "name": "Aqua Crate", "price_tokens": 200, "draws": 2, "domains": ["hydration"], "guaranteed_min_rarity": "rare", "sort_order": 46},
    {"slug": "hydro_box", "name": "Hydro Box", "price_tokens": 150, "draws": 1, "domains": ["hydration"], "guaranteed_min_rarity": "rare", "sort_order": 47},
    {"slug": "tsunami_vault", "name": "Tsunami Vault", "price_tokens": 600, "draws": 3, "domains": ["hydration"], "guaranteed_min_rarity": "epic", "sort_order": 48},
    {"slug": "fountain_of_youth", "name": "Fountain of Youth", "price_tokens": 750, "draws": 1, "domains": ["hydration"], "guaranteed_min_rarity": "legendary", "sort_order": 49},

    # --- New Sleep Packs ---
    {"slug": "nap_bag", "name": "Nap Bag", "price_tokens": 80, "draws": 1, "domains": ["sleep"], "guaranteed_min_rarity": "common", "sort_order": 50},
    {"slug": "snooze_box", "name": "Snooze Box", "price_tokens": 160, "draws": 2, "domains": ["sleep"], "guaranteed_min_rarity": "common", "sort_order": 51},
    {"slug": "dream_crate", "name": "Dream Crate", "price_tokens": 240, "draws": 1, "domains": ["sleep"], "guaranteed_min_rarity": "rare", "sort_order": 52},
    {"slug": "slumber_sack", "name": "Slumber Sack", "price_tokens": 300, "draws": 3, "domains": ["sleep"], "guaranteed_min_rarity": "rare", "sort_order": 53},
    {"slug": "rem_vault", "name": "REM Vault", "price_tokens": 450, "draws": 2, "domains": ["sleep"], "guaranteed_min_rarity": "epic", "sort_order": 54},
    {"slug": "nightmare_box", "name": "Nightmare Box", "price_tokens": 200, "draws": 2, "domains": ["sleep"], "guaranteed_min_rarity": "rare", "sort_order": 55},
    {"slug": "lullaby_crate", "name": "Lullaby Crate", "price_tokens": 180, "draws": 1, "domains": ["sleep"], "guaranteed_min_rarity": "rare", "sort_order": 56},
    {"slug": "midnight_stash", "name": "Midnight Stash", "price_tokens": 350, "draws": 3, "domains": ["sleep"], "guaranteed_min_rarity": "rare", "sort_order": 57},
    {"slug": "mattress_chest", "name": "Mattress Chest", "price_tokens": 550, "draws": 3, "domains": ["sleep"], "guaranteed_min_rarity": "epic", "sort_order": 58},
    {"slug": "sandman_vault", "name": "Sandman's Vault", "price_tokens": 800, "draws": 1, "domains": ["sleep"], "guaranteed_min_rarity": "legendary", "sort_order": 59},
]

# ==========================================
# GEAR ITEMS (Total: 60)
# ==========================================
DEFAULT_GEAR = [
    # --- Original Gear ---
    {"slug": "rook_helm", "name": "Rook Helm", "slot": "head", "rarity": "common",
     "icon": "fa-hat-cowboy", "effect_type": "domain_multiplier", "effect_domain": "strength", "effect_value": 1.05,
     "pack": "iron_roost", "weight": 100},
    {"slug": "beach_bandana", "name": "Beach Bandana", "slot": "head", "rarity": "common",
     "icon": "fa-hat-cowboy", "effect_type": "domain_multiplier", "effect_domain": "cardio", "effect_value": 1.05,
     "pack": "cardio_storm", "weight": 100},
    {"slug": "leviathan_cuirass", "name": "Leviathan Cuirass", "slot": "chest", "rarity": "epic",
     "icon": "fa-shirt", "effect_type": "domain_multiplier", "effect_domain": "strength", "effect_value": 1.7,
     "pack": "iron_roost", "weight": 30},
    {"slug": "swift_wind_band", "name": "Swift Wind Band", "slot": "accessory", "rarity": "epic",
     "icon": "fa-ring", "effect_type": "domain_multiplier", "effect_domain": "cardio", "effect_value": 1.8,
     "pack": "cardio_storm", "weight": 30},
    {"slug": "gauntlets_of_recharge", "name": "Gauntlets of Recharge", "slot": "left_hand", "rarity": "legendary",
     "icon": "fa-hand-fist", "effect_type": "synergy", "effect_domain": "strength", "effect_value": 2.5,
     "requires_sleep_efficiency": 0.85, "pack": "legendary_vault", "weight": 5},
    {"slug": "dumbbell_shield", "name": "Dumbbell Shield", "slot": "right_hand", "rarity": "epic",
     "icon": "fa-shield-halved", "effect_type": "domain_multiplier", "effect_domain": "strength", "effect_value": 1.6,
     "pack": "iron_roost", "weight": 25, "description": "A weight-plated tower shield that anchors your right hand."},
    {"slug": "oak_leg_plates", "name": "Oak Leg Plates", "slot": "legs", "rarity": "rare",
     "icon": "fa-person", "effect_type": "domain_multiplier", "effect_domain": "strength", "effect_value": 1.4,
     "pack": "iron_roost", "weight": 35, "description": "Sturdy leg greaves that help you squat deeper and stronger."},
    {"slug": "swift_stompers", "name": "Swift Stompers", "slot": "feet", "rarity": "rare",
     "icon": "fa-shoe-prints", "effect_type": "domain_multiplier", "effect_domain": "cardio", "effect_value": 1.3,
     "pack": "cardio_storm", "weight": 35, "description": "Feather-light runners that keep your cadence high."},
    {"slug": "pre_workout_nectar", "name": "Pre-Workout Nectar", "slot": "", "rarity": "rare",
     "icon": "fa-flask", "effect_type": "double_domain", "effect_domain": "cardio", "effect_value": 2.0,
     "is_consumable": True, "max_stack": 9, "pack": "alchemist_pack", "weight": 40},
    {"slug": "macro_potion", "name": "Macro-Potion", "slot": "", "rarity": "rare",
     "icon": "fa-vial", "effect_type": "shield_overage", "effect_value": 1.0,
     "is_consumable": True, "max_stack": 9, "pack": "alchemist_pack", "weight": 40},

    # --- New Strength Gear ---
    {"slug": "chalk_dusted_wraps", "name": "Chalk-Dusted Wraps", "slot": "left_hand", "rarity": "common",
     "icon": "fa-hand", "effect_type": "domain_multiplier", "effect_domain": "strength", "effect_value": 1.1,
     "pack": "chalk_bag", "weight": 90},
    {"slug": "iron_core_belt", "name": "Iron Core Belt", "slot": "accessory", "rarity": "rare",
     "icon": "fa-ring", "effect_type": "domain_multiplier", "effect_domain": "strength", "effect_value": 1.35,
     "pack": "powerlifter_stash", "weight": 40},
    {"slug": "titanium_knees", "name": "Titanium Knee Sleeves", "slot": "legs", "rarity": "epic",
     "icon": "fa-socks", "effect_type": "domain_multiplier", "effect_domain": "strength", "effect_value": 1.65,
     "pack": "titan_vault", "weight": 25},
    {"slug": "barbell_collar_ring", "name": "Barbell Collar Ring", "slot": "accessory", "rarity": "rare",
     "icon": "fa-ring", "effect_type": "domain_multiplier", "effect_domain": "strength", "effect_value": 1.25,
     "pack": "barbell_case", "weight": 50},
    {"slug": "berserker_war_paint", "name": "Berserker War Paint", "slot": "head", "rarity": "rare",
     "icon": "fa-mask", "effect_type": "synergy", "effect_domain": "strength", "effect_value": 1.5,
     "requires_sleep_efficiency": 0.8, "pack": "berserker_crate", "weight": 45},
    {"slug": "heavy_plate_mail", "name": "Heavy Plate Mail", "slot": "chest", "rarity": "epic",
     "icon": "fa-shirt", "effect_type": "domain_multiplier", "effect_domain": "strength", "effect_value": 1.6,
     "pack": "plate_hoarder_box", "weight": 30},
    {"slug": "kettlebell_pendant", "name": "Kettlebell Pendant", "slot": "accessory", "rarity": "common",
     "icon": "fa-gem", "effect_type": "domain_multiplier", "effect_domain": "strength", "effect_value": 1.15,
     "pack": "kettlebell_cache", "weight": 85},
    {"slug": "atlas_stones", "name": "Miniature Atlas Stones", "slot": "right_hand", "rarity": "rare",
     "icon": "fa-cubes", "effect_type": "domain_multiplier", "effect_domain": "strength", "effect_value": 1.4,
     "pack": "strongman_sack", "weight": 40},
    {"slug": "hammer_of_the_gods", "name": "Hammer of the Gods", "slot": "right_hand", "rarity": "legendary",
     "icon": "fa-hammer", "effect_type": "synergy", "effect_domain": "strength", "effect_value": 2.8,
     "requires_sleep_efficiency": 0.9, "pack": "anvil_drop", "weight": 5},
    {"slug": "smelling_salts", "name": "Smelling Salts", "slot": "", "rarity": "common",
     "icon": "fa-flask", "effect_type": "double_domain", "effect_domain": "strength", "effect_value": 2.0,
     "is_consumable": True, "max_stack": 5, "pack": "muscle_mystery_box", "weight": 60},

    # --- New Cardio Gear ---
    {"slug": "windbreaker_jacket", "name": "Windbreaker Jacket", "slot": "chest", "rarity": "common",
     "icon": "fa-shirt", "effect_type": "domain_multiplier", "effect_domain": "cardio", "effect_value": 1.1,
     "pack": "sprinter_pouch", "weight": 90},
    {"slug": "marathon_bib", "name": "Marathon Bib", "slot": "chest", "rarity": "rare",
     "icon": "fa-id-card", "effect_type": "domain_multiplier", "effect_domain": "cardio", "effect_value": 1.3,
     "pack": "marathon_bag", "weight": 50},
    {"slug": "trail_dust_boots", "name": "Trail Dust Boots", "slot": "feet", "rarity": "rare",
     "icon": "fa-shoe-prints", "effect_type": "domain_multiplier", "effect_domain": "cardio", "effect_value": 1.4,
     "pack": "trailblazer_pack", "weight": 45},
    {"slug": "lung_expansion_mask", "name": "Lung Expansion Mask", "slot": "head", "rarity": "epic",
     "icon": "fa-mask-ventilator", "effect_type": "domain_multiplier", "effect_domain": "cardio", "effect_value": 1.7,
     "pack": "vo2_max_crate", "weight": 25},
    {"slug": "treadmill_key", "name": "Treadmill Safety Key", "slot": "accessory", "rarity": "common",
     "icon": "fa-key", "effect_type": "domain_multiplier", "effect_domain": "cardio", "effect_value": 1.15,
     "pack": "treadmill_treasure", "weight": 80},
    {"slug": "aerodynamic_helmet", "name": "Aerodynamic Helmet", "slot": "head", "rarity": "rare",
     "icon": "fa-helmet-safety", "effect_type": "domain_multiplier", "effect_domain": "cardio", "effect_value": 1.35,
     "pack": "cyclist_satchel", "weight": 45},
    {"slug": "hydrodynamic_goggles", "name": "Hydrodynamic Goggles", "slot": "head", "rarity": "rare",
     "icon": "fa-glasses", "effect_type": "synergy", "effect_domain": "cardio", "effect_value": 1.5,
     "requires_sleep_efficiency": 0.8, "pack": "swimmer_cache", "weight": 40},
    {"slug": "hermes_winged_sandals", "name": "Hermes' Winged Sandals", "slot": "feet", "rarity": "legendary",
     "icon": "fa-feather", "effect_type": "synergy", "effect_domain": "cardio", "effect_value": 2.5,
     "requires_sleep_efficiency": 0.85, "pack": "endurance_vault", "weight": 5},
    {"slug": "beaded_jump_rope", "name": "Beaded Jump Rope", "slot": "right_hand", "rarity": "common",
     "icon": "fa-link", "effect_type": "domain_multiplier", "effect_domain": "cardio", "effect_value": 1.1,
     "pack": "jump_rope_box", "weight": 85},
    {"slug": "energy_gel", "name": "Energy Gel", "slot": "", "rarity": "rare",
     "icon": "fa-box-open", "effect_type": "double_domain", "effect_domain": "cardio", "effect_value": 2.0,
     "is_consumable": True, "max_stack": 10, "pack": "aero_crate", "weight": 50},

    # --- New Nutrition Gear ---
    {"slug": "apple_core_pendant", "name": "Apple Core Pendant", "slot": "accessory", "rarity": "common",
     "icon": "fa-apple-whole", "effect_type": "domain_multiplier", "effect_domain": "nutrition", "effect_value": 1.1,
     "pack": "snack_box", "weight": 90},
    {"slug": "whey_shaker_shield", "name": "Whey Shaker Shield", "slot": "left_hand", "rarity": "rare",
     "icon": "fa-blender", "effect_type": "domain_multiplier", "effect_domain": "nutrition", "effect_value": 1.35,
     "pack": "protein_pouch", "weight": 45},
    {"slug": "calorie_counter_watch", "name": "Calorie Counter Watch", "slot": "accessory", "rarity": "epic",
     "icon": "fa-stopwatch", "effect_type": "domain_multiplier", "effect_domain": "nutrition", "effect_value": 1.6,
     "pack": "macro_crate", "weight": 30},
    {"slug": "avocado_armor", "name": "Avocado Armor", "slot": "chest", "rarity": "rare",
     "icon": "fa-shield", "effect_type": "domain_multiplier", "effect_domain": "nutrition", "effect_value": 1.4,
     "pack": "keto_chest", "weight": 40},
    {"slug": "leafy_greens_crown", "name": "Leafy Greens Crown", "slot": "head", "rarity": "rare",
     "icon": "fa-leaf", "effect_type": "synergy", "effect_domain": "nutrition", "effect_value": 1.5,
     "requires_sleep_efficiency": 0.8, "pack": "vegan_vault", "weight": 45},
    {"slug": "butchers_cleaver", "name": "Butcher's Cleaver", "slot": "right_hand", "rarity": "epic",
     "icon": "fa-kitchen-set", "effect_type": "domain_multiplier", "effect_domain": "nutrition", "effect_value": 1.65,
     "pack": "butcher_bag", "weight": 25},
    {"slug": "pitchfork_of_harvest", "name": "Pitchfork of Harvest", "slot": "right_hand", "rarity": "rare",
     "icon": "fa-tractor", "effect_type": "domain_multiplier", "effect_domain": "nutrition", "effect_value": 1.3,
     "pack": "farmer_crate", "weight": 50},
    {"slug": "cornucopia", "name": "Horn of Plenty", "slot": "left_hand", "rarity": "rare",
     "icon": "fa-carrot", "effect_type": "domain_multiplier", "effect_domain": "nutrition", "effect_value": 1.45,
     "pack": "harvest_box", "weight": 40},
    {"slug": "michelin_star_apron", "name": "Michelin Star Apron", "slot": "chest", "rarity": "epic",
     "icon": "fa-shirt", "effect_type": "synergy", "effect_domain": "nutrition", "effect_value": 1.8,
     "requires_sleep_efficiency": 0.85, "pack": "chef_stash", "weight": 20},
    {"slug": "ambrosia_nectar", "name": "Ambrosia Nectar", "slot": "", "rarity": "legendary",
     "icon": "fa-wine-glass", "effect_type": "shield_overage", "effect_value": 2.0,
     "is_consumable": True, "max_stack": 3, "pack": "golden_apple_crate", "weight": 5},

    # --- New Hydration Gear ---
    {"slug": "raindrop_ring", "name": "Raindrop Ring", "slot": "accessory", "rarity": "common",
     "icon": "fa-droplet", "effect_type": "domain_multiplier", "effect_domain": "hydration", "effect_value": 1.1,
     "pack": "puddle_pouch", "weight": 90},
    {"slug": "water_balloon_bombs", "name": "Water Balloon Bombs", "slot": "right_hand", "rarity": "common",
     "icon": "fa-bomb", "effect_type": "domain_multiplier", "effect_domain": "hydration", "effect_value": 1.15,
     "pack": "splash_bag", "weight": 85},
    {"slug": "insulated_flask", "name": "Insulated Flask", "slot": "left_hand", "rarity": "rare",
     "icon": "fa-bottle-water", "effect_type": "domain_multiplier", "effect_domain": "hydration", "effect_value": 1.35,
     "pack": "bottle_box", "weight": 45},
    {"slug": "canteen_bandolier", "name": "Canteen Bandolier", "slot": "chest", "rarity": "rare",
     "icon": "fa-toolbox", "effect_type": "domain_multiplier", "effect_domain": "hydration", "effect_value": 1.4,
     "pack": "canteen_crate", "weight": 40},
    {"slug": "river_stone_amulet", "name": "River Stone Amulet", "slot": "accessory", "rarity": "rare",
     "icon": "fa-gem", "effect_type": "synergy", "effect_domain": "hydration", "effect_value": 1.5,
     "requires_sleep_efficiency": 0.8, "pack": "river_sack", "weight": 45},
    {"slug": "trident_of_the_tides", "name": "Trident of the Tides", "slot": "right_hand", "rarity": "epic",
     "icon": "fa-arrow-up", "effect_type": "domain_multiplier", "effect_domain": "hydration", "effect_value": 1.7,
     "pack": "ocean_chest", "weight": 25},
    {"slug": "aqua_lung", "name": "Aqua Lung", "slot": "chest", "rarity": "rare",
     "icon": "fa-lungs", "effect_type": "domain_multiplier", "effect_domain": "hydration", "effect_value": 1.45,
     "pack": "aqua_crate", "weight": 35},
    {"slug": "hydro_pump_gauntlets", "name": "Hydro Pump Gauntlets", "slot": "left_hand", "rarity": "epic",
     "icon": "fa-hand-fist", "effect_type": "domain_multiplier", "effect_domain": "hydration", "effect_value": 1.6,
     "pack": "hydro_box", "weight": 30},
    {"slug": "tsunami_cape", "name": "Tsunami Cape", "slot": "chest", "rarity": "epic",
     "icon": "fa-water", "effect_type": "synergy", "effect_domain": "hydration", "effect_value": 1.85,
     "requires_sleep_efficiency": 0.85, "pack": "tsunami_vault", "weight": 20},
    {"slug": "holy_water_vial", "name": "Holy Water Vial", "slot": "", "rarity": "legendary",
     "icon": "fa-vial", "effect_type": "double_domain", "effect_domain": "hydration", "effect_value": 3.0,
     "is_consumable": True, "max_stack": 5, "pack": "fountain_of_youth", "weight": 5},

    # --- New Sleep Gear ---
    {"slug": "cotton_nightcap", "name": "Cotton Nightcap", "slot": "head", "rarity": "common",
     "icon": "fa-hat-wizard", "effect_type": "domain_multiplier", "effect_domain": "sleep", "effect_value": 1.1,
     "pack": "nap_bag", "weight": 90},
    {"slug": "snooze_button_shield", "name": "Snooze Button Shield", "slot": "left_hand", "rarity": "common",
     "icon": "fa-clock", "effect_type": "domain_multiplier", "effect_domain": "sleep", "effect_value": 1.15,
     "pack": "snooze_box", "weight": 85},
    {"slug": "dreamcatcher_earrings", "name": "Dreamcatcher Earrings", "slot": "accessory", "rarity": "rare",
     "icon": "fa-ring", "effect_type": "domain_multiplier", "effect_domain": "sleep", "effect_value": 1.35,
     "pack": "dream_crate", "weight": 45},
    {"slug": "heavy_blanket_cloak", "name": "Heavy Blanket Cloak", "slot": "chest", "rarity": "rare",
     "icon": "fa-bed", "effect_type": "domain_multiplier", "effect_domain": "sleep", "effect_value": 1.4,
     "pack": "slumber_sack", "weight": 40},
    {"slug": "rem_goggles", "name": "R.E.M. Goggles", "slot": "head", "rarity": "epic",
     "icon": "fa-vr-cardboard", "effect_type": "synergy", "effect_domain": "sleep", "effect_value": 1.7,
     "requires_sleep_efficiency": 0.9, "pack": "rem_vault", "weight": 25},
    {"slug": "night_terror_ward", "name": "Night Terror Ward", "slot": "accessory", "rarity": "rare",
     "icon": "fa-shield", "effect_type": "domain_multiplier", "effect_domain": "sleep", "effect_value": 1.45,
     "pack": "nightmare_box", "weight": 40},
    {"slug": "lullaby_music_box", "name": "Lullaby Music Box", "slot": "right_hand", "rarity": "rare",
     "icon": "fa-music", "effect_type": "domain_multiplier", "effect_domain": "sleep", "effect_value": 1.3,
     "pack": "lullaby_crate", "weight": 50},
    {"slug": "midnight_slippers", "name": "Midnight Slippers", "slot": "feet", "rarity": "epic",
     "icon": "fa-shoe-prints", "effect_type": "domain_multiplier", "effect_domain": "sleep", "effect_value": 1.6,
     "pack": "midnight_stash", "weight": 30},
    {"slug": "memory_foam_armor", "name": "Memory Foam Armor", "slot": "chest", "rarity": "epic",
     "icon": "fa-shirt", "effect_type": "synergy", "effect_domain": "sleep", "effect_value": 1.8,
     "requires_sleep_efficiency": 0.85, "pack": "mattress_chest", "weight": 25},
    {"slug": "sandman_dust", "name": "Sandman's Dust", "slot": "", "rarity": "legendary",
     "icon": "fa-cloud", "effect_type": "double_domain", "effect_domain": "sleep", "effect_value": 2.5,
     "is_consumable": True, "max_stack": 9, "pack": "sandman_vault", "weight": 5},
]

# ==========================================
# CAMPAIGN BOSSES (Total: 57)
# ==========================================
DEFAULT_CAMPAIGN_BOSSES = [
    # --- Original Bosses ---
    ("cardio", "ghastly_recliner", "The Ghastly Recliner", 2000, "endurance", [], [], {}),
    ("strength", "sir_skip_a_leg", "Sir Skip-a-Leg", 1500, "strength", [], ["strength"], {}),
    ("strength", "iron_couch_king", "The Iron Couch King", 2500, "strength", [], ["strength"], {}),
    ("strength", "deadlift_djinn", "The Deadlift Djinn", 4000, "strength", ["strength"], [], {}),
    ("nutrition", "carbo_hydra", "The Carbo-Hydra", 600, "nutrition", [], [], {"heal_on_overage": True}),
    ("hydration", "the_dehydrator", "The Dehydrator", 800, "hydration", ["hydration"], [], {"front_load_water_noon": True}),
    ("sleep", "restless_wraith", "The Restless Wraith", 300, "recovery", [], ["sleep"], {}),

    # --- New Cardio Bosses (10) ---
    ("cardio", "breathless_brute", "The Breathless Brute", 2200, "endurance", ["strength"], ["cardio"], {}),
    ("cardio", "pace_breaker", "The Pace Breaker", 2800, "endurance", ["nutrition"], [], {}),
    ("cardio", "the_stitch", "The Side Stitch", 3200, "endurance", ["hydration"], ["cardio"], {}),
    ("cardio", "lactic_lord", "Lactic Acid Lord", 4000, "endurance", ["sleep"], ["strength"], {}),
    ("cardio", "treadmill_tyrant", "Treadmill Tyrant", 4500, "endurance", ["strength"], ["cardio"], {}),
    ("cardio", "distance_demon", "The Distance Demon", 5000, "endurance", ["nutrition", "hydration"], ["cardio"], {}),
    ("cardio", "exhaustion_elemental", "Exhaustion Elemental", 6000, "endurance", ["sleep"], ["cardio", "strength"], {}),
    ("cardio", "sluggish_slime", "The Sluggish Slime", 6500, "endurance", ["cardio"], [], {}),
    ("cardio", "lazy_lout", "The Lazy Lout", 7200, "endurance", ["strength"], ["sleep"], {}),
    ("cardio", "sedentary_sphinx", "The Sedentary Sphinx", 8500, "endurance", ["cardio"], ["nutrition"], {}),

    # --- New Strength Bosses (10) ---
    ("strength", "prawn_posture", "The Prawn Posture", 1800, "strength", ["cardio"], ["strength"], {}),
    ("strength", "ego_lifter", "The Ego Lifter", 2200, "strength", ["sleep"], ["strength"], {}),
    ("strength", "half_rep_horror", "Half-Rep Horror", 2800, "strength", ["nutrition"], [], {}),
    ("strength", "spotter_ghost", "The Spotter Ghost", 3500, "strength", ["strength"], ["cardio"], {}),
    ("strength", "barbell_beast", "Barbell Bending Beast", 4200, "strength", ["hydration"], ["strength"], {}),
    ("strength", "frail_phantom", "The Frail Phantom", 4800, "strength", ["nutrition"], ["strength"], {}),
    ("strength", "atrophy_assassin", "Atrophy Assassin", 5500, "strength", ["cardio", "strength"], ["sleep"], {}),
    ("strength", "gravity_giant", "The Gravity Giant", 6500, "strength", ["strength"], ["strength"], {}),
    ("strength", "heavy_hand", "The Heavy Hand", 7500, "strength", ["sleep"], ["strength"], {}),
    ("strength", "doms_destroyer", "DOMS Destroyer", 9000, "strength", ["hydration", "sleep"], ["strength"], {}),

    # --- New Nutrition Bosses (10) ---
    ("nutrition", "sugar_crash", "The Sugar Crash", 800, "nutrition", ["sleep"], ["nutrition"], {"heal_on_overage": True}),
    ("nutrition", "fast_food_fiend", "Fast Food Fiend", 1200, "nutrition", ["cardio"], ["nutrition"], {}),
    ("nutrition", "trans_fat_troll", "Trans-Fat Troll", 1600, "nutrition", ["strength"], ["nutrition"], {}),
    ("nutrition", "calorie_creeper", "The Calorie Creeper", 2000, "nutrition", ["cardio"], [], {"heal_on_overage": True}),
    ("nutrition", "binge_banshee", "The Binge Banshee", 2500, "nutrition", ["hydration"], ["nutrition"], {}),
    ("nutrition", "sodium_serpent", "The Sodium Serpent", 3000, "nutrition", ["hydration"], ["nutrition"], {}),
    ("nutrition", "cholesterol_chimera", "Cholesterol Chimera", 3500, "nutrition", ["cardio", "strength"], ["nutrition"], {}),
    ("nutrition", "snack_snatcher", "The Snack Snatcher", 4000, "nutrition", ["sleep"], ["nutrition"], {}),
    ("nutrition", "candy_king", "The Candy King", 5000, "nutrition", ["nutrition"], ["nutrition"], {"heal_on_overage": True}),
    ("nutrition", "gluttonous_gargoyle", "Gluttonous Gargoyle", 6500, "nutrition", ["strength"], ["nutrition"], {"heal_on_overage": True}),

    # --- New Hydration Bosses (10) ---
    ("hydration", "dry_druid", "The Dry Druid", 1000, "hydration", ["hydration"], ["strength"], {"front_load_water_noon": True}),
    ("hydration", "parched_phantom", "The Parched Phantom", 1400, "hydration", ["nutrition"], ["hydration"], {}),
    ("hydration", "dehydrated_demon", "Dehydrated Demon", 1800, "hydration", ["hydration"], ["cardio"], {"front_load_water_noon": True}),
    ("hydration", "cola_cultist", "The Cola Cultist", 2200, "hydration", ["nutrition"], ["hydration"], {}),
    ("hydration", "sugar_drink_siren", "Sugar-Drink Siren", 2800, "hydration", ["hydration", "nutrition"], ["strength"], {}),
    ("hydration", "desert_djinn", "The Desert Djinn", 3500, "hydration", ["hydration"], ["hydration"], {"front_load_water_noon": True}),
    ("hydration", "sunburned_specter", "Sunburned Specter", 4200, "hydration", ["sleep"], ["hydration"], {}),
    ("hydration", "cottonmouth_creature", "Cottonmouth Creature", 5000, "hydration", ["hydration"], ["cardio"], {}),
    ("hydration", "drought_dragon", "The Drought Dragon", 6000, "hydration", ["hydration"], ["hydration"], {"front_load_water_noon": True}),
    ("hydration", "barren_baron", "The Barren Baron", 7500, "hydration", ["hydration"], ["hydration", "strength"], {"front_load_water_noon": True}),

    # --- New Sleep Bosses (10) ---
    ("sleep", "tossing_turner", "The Tossing Turner", 500, "recovery", ["cardio"], ["sleep"], {}),
    ("sleep", "midnight_scroller", "The Midnight Scroller", 800, "recovery", ["sleep"], ["strength"], {}),
    ("sleep", "caffeine_creeper", "The Caffeine Creeper", 1200, "recovery", ["hydration"], ["sleep"], {}),
    ("sleep", "snoring_siren", "The Snoring Siren", 1600, "recovery", ["strength"], ["sleep"], {}),
    ("sleep", "apnea_specter", "Sleep Apnea Specter", 2000, "recovery", ["cardio"], ["sleep"], {}),
    ("sleep", "restless_rogue", "The Restless Rogue", 2500, "recovery", ["nutrition"], ["sleep"], {}),
    ("sleep", "blue_light_behemoth", "Blue-Light Behemoth", 3200, "recovery", ["sleep"], ["sleep"], {}),
    ("sleep", "waking_wight", "The Waking Wight", 4000, "recovery", ["hydration"], ["sleep"], {}),
    ("sleep", "insomnia_imp", "The Insomnia Imp", 5000, "recovery", ["sleep"], ["cardio"], {}),
    ("sleep", "sleepwalker_king", "The Sleepwalker King", 6500, "recovery", ["sleep"], ["sleep"], {}),
]
class Command(BaseCommand):
    def handle(self, *args, **options):
        # Admin superuser
        admin, admin_created = User.objects.get_or_create(
            username=ADMIN_USERNAME,
            defaults={"is_staff": True, "is_superuser": True, "email": "admin@example.com"},
        )
        if admin_created:
            admin.set_password(ADMIN_PASSWORD)
            admin.save()
            self.stdout.write(self.style.SUCCESS(f"Created superuser: {ADMIN_USERNAME} / {ADMIN_PASSWORD}"))
        else:
            self.stdout.write(f"Superuser '{ADMIN_USERNAME}' already exists.")

        # Demo player
        player, player_created = User.objects.get_or_create(
            username=PLAYER_USERNAME,
            defaults={"email": "player1@example.com", "streak": 12},
        )
        if player_created:
            player.set_password(PLAYER_PASSWORD)
            player.save()
            self.stdout.write(self.style.SUCCESS(f"Created player: {PLAYER_USERNAME} / {PLAYER_PASSWORD}"))
        else:
            self.stdout.write(f"Player '{PLAYER_USERNAME}' already exists.")

        # Phase 9 packs, gear catalog & campaign bosses (idempotent by slug).
        created_packs = 0
        for defaults in list(DEFAULT_PACKS):
            defaults = dict(defaults)
            slug = defaults.pop("slug")
            _, created = GearPackDef.objects.get_or_create(slug=slug, defaults=defaults)
            created_packs += int(created)

        created_gear = 0
        gear_packs = {p.slug: p for p in GearPackDef.objects.all()}
        for entry in list(DEFAULT_GEAR):
            d = dict(entry)
            slug = d.pop("slug")
            pack_slug = d.pop("pack", None)
            d["pack"] = gear_packs.get(pack_slug) if pack_slug else None
            _, created = GearItemDef.objects.get_or_create(slug=slug, defaults=d)
            created_gear += int(created)

        created_bosses = 0
        order_by_campaign = {}
        for (campaign, slug, name, hp, element, weak, res, mech) in DEFAULT_CAMPAIGN_BOSSES:
            # Sequential per-campaign sort_order so conquering auto-advances to
            # the next boss in the campaign (docs/15 §5.4).
            order_by_campaign[campaign] = order_by_campaign.get(campaign, 0) + 1
            _, created = CampaignBoss.objects.get_or_create(
                slug=slug,
                defaults={"campaign": campaign, "name": name, "hp_total": hp,
                          "element": element, "weaknesses": weak,
                          "resistances": res, "mechanics": mech,
                          "sort_order": order_by_campaign[campaign]},
            )
            created_bosses += int(created)

        # Demo wallet + starter loadout (idempotent).
        PlayerProfile.objects.get_or_create(user=player)

        def _give_gear(slug, slot=None):
            gd = GearItemDef.objects.get(slug=slug)
            quantity = gd.max_stack if gd.is_consumable else 1
            own, _ = UserGear.objects.update_or_create(
                user=player, gear_def=gd,
                defaults={"rarity": gd.rarity, "quantity": quantity},
            )
            if slot is not None:
                UserGear.objects.filter(user=player, equipped_slot=slot).update(equipped_slot=None)
                own.equipped_slot = slot
                own.save(update_fields=["equipped_slot"])

        _give_gear("rook_helm", "head")
        _give_gear("leviathan_cuirass", "chest")
        _give_gear("swift_wind_band", "accessory")
        # A few unequipped pieces so the Inventory has things to equip straight away.
        _give_gear("dumbbell_shield")
        _give_gear("oak_leg_plates")
        _give_gear("swift_stompers")
        _give_gear("pre_workout_nectar")
        _give_gear("macro_potion")

        # Gyms for both demo users so PvP is alive on first boot.
        for u, nm in ((player, "Flamingo Arena"), (admin, "Iron Roost Gym")):
            Gym.objects.get_or_create(owner=u, defaults={"name": nm, "terrain": "strength"})

        # Active integrations so the pollers (and SparkyFitness bodyweight for
        # the PR Boss) have something to iterate.
        created_integrations = 0
        for provider in (Provider.GARMIN, Provider.PELOTON, Provider.LIFTOSAUR, Provider.SPARKYFITNESS):
            _, created = UserIntegration.objects.get_or_create(
                user=player,
                provider=provider,
                defaults={"is_active": True},
            )
            created_integrations += int(created)

        # Seed default admin-configurable PR Boss benchmarks (idempotent).
        default_bosses = [
            ("Bench Press", "Bench Press", 1.5),
            ("Squat", "Squat", 2.0),
            ("Deadlift", "Deadlift", 2.5),
            ("Overhead Press", "Overhead Press", 1.0),
        ]
        created_pr_bosses = 0
        for name, match, mult in default_bosses:
            _, created = BossConfig.objects.get_or_create(
                name=name,
                defaults={"exercise_match": match, "bodyweight_multiplier": mult},
            )
            created_pr_bosses += int(created)

        self.stdout.write(f"Gacha packs ensured ({created_packs} newly created).")
        self.stdout.write(f"Gear catalog ensured ({created_gear} newly created).")
        self.stdout.write(f"Campaign bosses ensured ({created_bosses} newly created).")
        self.stdout.write(f"PR Boss benchmarks ensured ({created_pr_bosses} newly created).")
        self.stdout.write(f"Integrations ensured ({created_integrations} newly created).")
        self._seed_phase8_social(admin, player)
        self.stdout.write(self.style.SUCCESS("Demo accounts created."))

    def _seed_phase8_social(self, admin, player):
        """Phase 8 (docs/13 §8): default challenge, league week, friendship,
        and the demo flock. Idempotent - safe on every startup."""
        from core.services.leagues import ensure_current_week

        # 1. The single default challenge: calories burned in the last 30 days.
        challenge, created = Challenge.objects.get_or_create(
            slug="calories_burned_30d",
            defaults={
                "name": "Calorie Torch",
                "description": "Most calories burned in the last 30 days. "
                "Every workout counts - keep the flame alive!",
                "icon": "fa-fire-flame-curved",
                "metric": Challenge.Metric.CALORIES_BURNED,
                "window_days": 30,
                "is_active": True,
                "sort_order": 1,
            },
        )
        if not created and not challenge.is_active:
            challenge.is_active = True
            challenge.save(update_fields=["is_active"])

        # 2. Ensure the current open league week exists (lazy-close stale ones).
        week = ensure_current_week()

        # 3. Demo friendship: player1 -> admin (accepted).
        Friendship.objects.get_or_create(
            from_user=player,
            to_user=admin,
            defaults={"status": Friendship.Status.ACCEPTED},
        )

        # 4. Demo flock "Flamingo Fam" owned by player1, admin as member.
        flock = Flock.objects.filter(name="Flamingo Fam").first()
        if flock is None:
            flock = Flock.objects.create(name="Flamingo Fam", created_by=player)
        FlockMembership.objects.get_or_create(
            user=player,
            defaults={"flock": flock, "role": FlockMembership.Role.OWNER},
        )
        FlockMembership.objects.get_or_create(
            user=admin,
            defaults={"flock": flock, "role": FlockMembership.Role.MEMBER},
        )

        self.stdout.write(
            f"Phase 8 social ensured (challenge='{challenge.slug}', "
            f"week={week.week_start}, flock='{flock.name}')."
        )

