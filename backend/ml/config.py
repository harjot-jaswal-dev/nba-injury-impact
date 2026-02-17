"""
Shared constants, feature lists, and helpers for the ML pipeline.

Single source of truth for feature definitions, paths, and serialization.
"""

import numpy as np
import pandas as pd
from pathlib import Path

from backend.scripts.utils import PROJECT_ROOT, PROCESSED_DIR

# ──────────────────────────────────────────────
# Path Constants
# ──────────────────────────────────────────────

MODELS_DIR = PROJECT_ROOT / "backend" / "models"
ML_DIR = PROJECT_ROOT / "backend" / "ml"

# ──────────────────────────────────────────────
# Train/Test Split
# ──────────────────────────────────────────────

SPLIT_DATE = "2024-10-01"

# ──────────────────────────────────────────────
# Minimum games for role qualification (matches process_data.py)
# ──────────────────────────────────────────────

MIN_GAMES_FOR_ROLE = 20

# ──────────────────────────────────────────────
# Feature Lists
# ──────────────────────────────────────────────

# Baseline features (37 total) — NO injury context
BASELINE_FEATURES = [
    # Season rolling averages (11)
    "season_avg_pts", "season_avg_ast", "season_avg_reb",
    "season_avg_stl", "season_avg_blk", "season_avg_tov",
    "season_avg_fg_pct", "season_avg_ft_pct", "season_avg_fg3_pct",
    "season_avg_plus_minus", "season_avg_minutes",
    # Last-5 averages (6)
    "last5_avg_pts", "last5_avg_ast", "last5_avg_reb",
    "last5_avg_minutes", "last5_avg_fg_pct", "last5_avg_plus_minus",
    # Last-10 averages (6)
    "last10_avg_pts", "last10_avg_ast", "last10_avg_reb",
    "last10_avg_minutes", "last10_avg_fg_pct", "last10_avg_plus_minus",
    # Home/away splits (3)
    "home_avg_pts", "away_avg_pts", "home_away_pts_diff",
    # Per-opponent averages (3)
    "vs_opp_avg_pts", "vs_opp_avg_reb", "vs_opp_avg_ast",
    # Trend/context (4 numeric)
    "minutes_trend", "games_played_season", "age", "experience",
    # Derived binary (1)
    "is_home",
    # Position dummies (3)
    "pos_G", "pos_F", "pos_C",
]

# Injury features (17 additional for ripple model)
INJURY_FEATURES = [
    # Binary absence (6)
    "n_starters_out",
    "starter_1_out", "starter_2_out", "starter_3_out",
    "starter_4_out", "starter_5_out",
    # Role-based (6)
    "ball_handler_out", "primary_scorer_out",
    "primary_rebounder_out", "primary_defender_out",
    "sixth_man_out", "n_rotation_players_out",
    # Talent loss (4)
    "total_pts_lost", "total_ast_lost",
    "total_reb_lost", "total_minutes_lost",
    # Config experience (1)
    "games_with_this_config",
]

# Combined features for ripple model (54 total)
RIPPLE_FEATURES = BASELINE_FEATURES + INJURY_FEATURES

# Target columns
TARGET_COLS = [
    "target_pts", "target_ast", "target_reb", "target_stl",
    "target_blk", "target_fg_pct", "target_ft_pct", "target_minutes",
]

# Short stat names (for display)
STAT_NAMES = ["pts", "ast", "reb", "stl", "blk", "fg_pct", "ft_pct", "minutes"]

# ──────────────────────────────────────────────
# Data Loading
# ──────────────────────────────────────────────

def load_processed_data() -> pd.DataFrame:
    """Load the processed player data CSV.

    Returns:
        DataFrame with game_date parsed as datetime.

    Raises:
        FileNotFoundError: If processed data doesn't exist.
    """
    csv_path = PROCESSED_DIR / "processed_player_data.csv"
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Processed data not found at {csv_path}. "
            "Run 'python -m backend.scripts.process_data' first."
        )
    return pd.read_csv(csv_path, parse_dates=["game_date"])


# ──────────────────────────────────────────────
# Numpy Serialization Helper (Critical Fix #3)
# ──────────────────────────────────────────────

def serialize_prediction(obj):
    """Recursively convert numpy types to native Python for JSON serialization.

    Used by every public function in predict.py to ensure all return values
    are JSON-serializable without scattered float() casts.

    Args:
        obj: Any Python/numpy object (dict, list, scalar, array).

    Returns:
        The same structure with all numpy types converted to native Python.
    """
    if isinstance(obj, dict):
        return {k: serialize_prediction(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [serialize_prediction(item) for item in obj]
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, (np.floating,)):
        return round(float(obj), 1)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj
