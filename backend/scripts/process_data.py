"""
Process raw NBA data into ML-ready features.

Reads raw game logs, rosters, and absences, then engineers features
for predicting player stats. The most important features are the
injury context features — encoding which teammates are missing and
how that affects available talent.

Prerequisites:
    Run these scripts first:
    - collect_player_stats.py  (generates player_game_logs.csv, rosters.csv)
    - collect_injury_data.py   (generates player_absences.csv)

Output:
    backend/data/processed/processed_player_data.csv  (~90K rows x ~73 cols)
    backend/data/processed/feature_dictionary.md       (feature documentation)
"""

import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from backend.scripts.utils import setup_logging, RAW_DIR, PROCESSED_DIR

OUTPUT_DATA = str(PROCESSED_DIR / "processed_player_data.csv")
OUTPUT_FEATURES = str(PROCESSED_DIR / "feature_dictionary.md")

logger = setup_logging("process_data")

# Stat columns used for rolling averages
STAT_COLS = ["pts", "ast", "reb", "stl", "blk", "tov",
             "fg_pct", "ft_pct", "fg3_pct", "plus_minus", "minutes"]

# Subset of stat columns for last-N game averages (most important stats)
KEY_STAT_COLS = ["pts", "ast", "reb", "minutes", "fg_pct", "plus_minus"]

# Minimum games played to qualify for role detection
MIN_GAMES_FOR_ROLE = 20


# ──────────────────────────────────────────────
# Phase 1: Loading and Cleaning
# ──────────────────────────────────────────────

def load_and_clean() -> tuple:
    """Load and clean all raw data files.

    Handles missing values, deduplicates, standardizes types, and sorts.
    Always joins on player_id (never player_name) to avoid name mismatches
    between endpoints.

    Returns:
        Tuple of (game_logs, rosters, absences) DataFrames.
    """
    logger.info("Loading raw data...")

    game_logs = pd.read_csv(RAW_DIR / "player_game_logs.csv")
    rosters = pd.read_csv(RAW_DIR / "rosters.csv")
    absences = pd.read_csv(RAW_DIR / "player_absences.csv")

    logger.info(f"  Game logs: {len(game_logs)} rows")
    logger.info(f"  Rosters: {len(rosters)} rows")
    logger.info(f"  Absences: {len(absences)} rows")

    # --- Parse dates ---
    game_logs["game_date"] = pd.to_datetime(game_logs["game_date"])
    absences["game_date"] = pd.to_datetime(absences["game_date"])

    # --- Normalize roster season format ---
    # Roster uses starting year (2022) while game logs use "2022-23"
    def normalize_season(s):
        s_str = str(s).strip()
        if "-" in s_str:
            return s_str
        try:
            year = int(s_str)
            return f"{year}-{str(year + 1)[-2:]}"
        except ValueError:
            return s_str

    rosters["season"] = rosters["season"].apply(normalize_season)

    # --- Handle missing values ---
    # Shooting percentages are NaN when a player had 0 attempts
    for col in ["fg_pct", "fg3_pct", "ft_pct"]:
        if col in game_logs.columns:
            game_logs[col] = game_logs[col].fillna(0.0)

    # Minutes and plus_minus: fill NaN with 0
    for col in ["minutes", "plus_minus"]:
        if col in game_logs.columns:
            game_logs[col] = game_logs[col].fillna(0.0)

    # --- Convert minutes to numeric ---
    # nba_api sometimes returns minutes as "MM:SS" string format
    if game_logs["minutes"].dtype == object:
        def parse_minutes(val):
            if pd.isna(val):
                return 0.0
            val = str(val)
            if ":" in val:
                parts = val.split(":")
                return float(parts[0]) + float(parts[1]) / 60
            try:
                return float(val)
            except ValueError:
                return 0.0
        game_logs["minutes"] = game_logs["minutes"].apply(parse_minutes)

    # --- Deduplicate ---
    # Same player appearing twice for same game (shouldn't happen but be safe)
    before = len(game_logs)
    game_logs = game_logs.drop_duplicates(subset=["player_id", "game_id"], keep="first")
    dupes_removed = before - len(game_logs)
    if dupes_removed > 0:
        logger.warning(f"Removed {dupes_removed} duplicate game log rows")

    # --- Sort ---
    game_logs = game_logs.sort_values(["player_id", "game_date"]).reset_index(drop=True)

    # --- Strip whitespace from string columns ---
    for col in ["player_name", "team_abbr"]:
        if col in game_logs.columns:
            game_logs[col] = game_logs[col].str.strip()
        if col in rosters.columns:
            rosters[col] = rosters[col].str.strip()

    # --- Data quality flags ---
    null_counts = game_logs[STAT_COLS].isnull().sum()
    has_nulls = null_counts[null_counts > 0]
    if len(has_nulls) > 0:
        logger.warning(f"Remaining null values in stat columns:\n{has_nulls}")

    logger.info("Data cleaning complete")
    return game_logs, rosters, absences


# ──────────────────────────────────────────────
# Phase 2: Role Detection
# ──────────────────────────────────────────────

def detect_player_roles(game_logs: pd.DataFrame, rosters: pd.DataFrame) -> pd.DataFrame:
    """Detect player roles (starter, ball handler, scorer, etc.) per team-season.

    Uses stats-based detection:
    - Starters: top 5 by average minutes (min 20 games)
    - Primary ball handler: starter with highest avg AST
    - Primary scorer: starter with highest avg PTS
    - Primary rebounder: starter with highest avg REB
    - Primary defender: starter with highest avg (STL + BLK)
    - Sixth man: non-starter with highest avg minutes (min 20 games)

    A player can hold multiple roles (e.g., primary scorer AND ball handler).

    Args:
        game_logs: Cleaned game logs DataFrame.
        rosters: Cleaned rosters DataFrame.

    Returns:
        DataFrame indexed by (player_id, team_id, season) with role flags
        and season averages.
    """
    logger.info("Detecting player roles...")

    # Compute per-player season averages
    player_avgs = (
        game_logs.groupby(["player_id", "team_id", "season"])
        .agg(
            avg_pts=("pts", "mean"),
            avg_ast=("ast", "mean"),
            avg_reb=("reb", "mean"),
            avg_stl=("stl", "mean"),
            avg_blk=("blk", "mean"),
            avg_minutes=("minutes", "mean"),
            games_played=("game_id", "count"),
        )
        .reset_index()
    )

    # Filter to players with enough games for role assignment
    qualified = player_avgs[player_avgs["games_played"] >= MIN_GAMES_FOR_ROLE].copy()

    # Initialize role columns
    qualified["is_starter"] = False
    qualified["role_ball_handler"] = False
    qualified["role_scorer"] = False
    qualified["role_rebounder"] = False
    qualified["role_defender"] = False
    qualified["role_sixth_man"] = False

    # Defensive metric
    qualified["avg_stl_blk"] = qualified["avg_stl"] + qualified["avg_blk"]

    # Assign roles per team-season
    for (team_id, season), group in qualified.groupby(["team_id", "season"]):
        if len(group) < 5:
            # Not enough qualified players; mark top players as starters anyway
            starter_ids = group.nlargest(len(group), "avg_minutes").index
        else:
            starter_ids = group.nlargest(5, "avg_minutes").index

        # Mark starters
        qualified.loc[starter_ids, "is_starter"] = True

        # Role detection among starters
        starters = qualified.loc[starter_ids]
        if not starters.empty:
            # Primary ball handler: highest AST among starters
            top_ast = starters["avg_ast"].max()
            qualified.loc[
                starter_ids[starters["avg_ast"] == top_ast],
                "role_ball_handler"
            ] = True

            # Primary scorer: highest PTS among starters
            top_pts = starters["avg_pts"].max()
            qualified.loc[
                starter_ids[starters["avg_pts"] == top_pts],
                "role_scorer"
            ] = True

            # Primary rebounder: highest REB among starters
            top_reb = starters["avg_reb"].max()
            qualified.loc[
                starter_ids[starters["avg_reb"] == top_reb],
                "role_rebounder"
            ] = True

            # Primary defender: highest STL+BLK among starters
            top_def = starters["avg_stl_blk"].max()
            qualified.loc[
                starter_ids[starters["avg_stl_blk"] == top_def],
                "role_defender"
            ] = True

        # Sixth man: non-starter with highest minutes
        non_starters = group.loc[~group.index.isin(starter_ids)]
        if not non_starters.empty:
            sixth_man_idx = non_starters["avg_minutes"].idxmax()
            qualified.loc[sixth_man_idx, "role_sixth_man"] = True

    # Merge position and age from rosters
    roster_info = rosters[["player_id", "team_id", "season", "position", "age"]].drop_duplicates(
        subset=["player_id", "team_id", "season"]
    )
    # Convert season format if needed (rosters may use different format)
    qualified = qualified.merge(roster_info, on=["player_id", "team_id", "season"], how="left")

    # Also include unqualified players (with no roles) for the averages
    unqualified = player_avgs[player_avgs["games_played"] < MIN_GAMES_FOR_ROLE].copy()
    for col in ["is_starter", "role_ball_handler", "role_scorer",
                "role_rebounder", "role_defender", "role_sixth_man"]:
        unqualified[col] = False
    unqualified["avg_stl_blk"] = unqualified["avg_stl"] + unqualified["avg_blk"]
    unqualified = unqualified.merge(roster_info, on=["player_id", "team_id", "season"], how="left")

    roles = pd.concat([qualified, unqualified], ignore_index=True)

    # Summary
    n_starters = roles["is_starter"].sum()
    n_handlers = roles["role_ball_handler"].sum()
    n_scorers = roles["role_scorer"].sum()
    logger.info(
        f"Role detection complete: {n_starters} starters, {n_handlers} ball handlers, "
        f"{n_scorers} scorers across {roles[['team_id', 'season']].drop_duplicates().shape[0]} team-seasons"
    )

    return roles


# ──────────────────────────────────────────────
# Phase 3: Player Features
# ──────────────────────────────────────────────

def build_player_features(game_logs: pd.DataFrame, rosters: pd.DataFrame) -> pd.DataFrame:
    """Build player-level features for each game.

    All features use ONLY data available BEFORE the game (no future leakage).
    Uses .shift(1) to exclude the current game from all rolling calculations.

    Args:
        game_logs: Cleaned game logs DataFrame (sorted by player_id, game_date).
        rosters: Cleaned rosters DataFrame.

    Returns:
        game_logs DataFrame with new feature columns added.
    """
    logger.info("Building player features...")
    df = game_logs.copy()

    # Group by player-season for most features
    group = df.groupby(["player_id", "season"], group_keys=False)

    # --- Season rolling averages ---
    # expanding().mean().shift(1) gives the average of all prior games this season
    logger.info("  Computing season rolling averages...")
    for col in STAT_COLS:
        df[f"season_avg_{col}"] = group[col].transform(
            lambda x: x.expanding().mean().shift(1)
        )

    # --- Last-5 and Last-10 game averages ---
    logger.info("  Computing last-5 and last-10 game averages...")
    for col in KEY_STAT_COLS:
        df[f"last5_avg_{col}"] = group[col].transform(
            lambda x: x.rolling(5, min_periods=1).mean().shift(1)
        )
        df[f"last10_avg_{col}"] = group[col].transform(
            lambda x: x.rolling(10, min_periods=1).mean().shift(1)
        )

    # --- Home/away splits ---
    logger.info("  Computing home/away splits...")
    # Compute season averages for home and away games separately
    # We need a more careful approach: for each row, compute the player's
    # average PTS in prior home or away games this season.
    df["_is_home"] = (df["home_away"] == "HOME").astype(int)

    # Home average pts (expanding mean of pts in home games, shifted)
    df["_home_pts"] = df["pts"] * df["_is_home"]
    df["_home_count"] = df["_is_home"]
    df["_home_pts_cumsum"] = group["_home_pts"].transform(lambda x: x.cumsum().shift(1))
    df["_home_count_cumsum"] = group["_home_count"].transform(lambda x: x.cumsum().shift(1))
    df["home_avg_pts"] = df["_home_pts_cumsum"] / df["_home_count_cumsum"].replace(0, np.nan)

    # Away average pts
    df["_is_away"] = 1 - df["_is_home"]
    df["_away_pts"] = df["pts"] * df["_is_away"]
    df["_away_count"] = df["_is_away"]
    df["_away_pts_cumsum"] = group["_away_pts"].transform(lambda x: x.cumsum().shift(1))
    df["_away_count_cumsum"] = group["_away_count"].transform(lambda x: x.cumsum().shift(1))
    df["away_avg_pts"] = df["_away_pts_cumsum"] / df["_away_count_cumsum"].replace(0, np.nan)

    df["home_away_pts_diff"] = df["home_avg_pts"] - df["away_avg_pts"]

    # Clean up temp columns
    temp_cols = [c for c in df.columns if c.startswith("_")]
    df = df.drop(columns=temp_cols)

    # --- Per-opponent historical averages ---
    logger.info("  Computing per-opponent averages...")
    if "opponent" in df.columns:
        opp_group = df.groupby(["player_id", "opponent"], group_keys=False)
        for col in ["pts", "reb", "ast"]:
            df[f"vs_opp_avg_{col}"] = opp_group[col].transform(
                lambda x: x.expanding().mean().shift(1)
            )

    # --- Minutes trend ---
    # Slope of linear regression on minutes over last 10 games
    logger.info("  Computing minutes trend...")

    def compute_slope(x):
        """Compute the slope of a linear fit over the window."""
        n = len(x)
        if n < 3:  # Need at least 3 points for a meaningful trend
            return 0.0
        indices = np.arange(n)
        # Use polyfit for efficiency
        try:
            slope = np.polyfit(indices, x, 1)[0]
            return slope
        except (np.linalg.LinAlgError, ValueError):
            return 0.0

    df["minutes_trend"] = group["minutes"].transform(
        lambda x: x.rolling(10, min_periods=3).apply(compute_slope, raw=True).shift(1)
    )

    # --- Games played this season ---
    df["games_played_season"] = group.cumcount()  # 0-indexed count before this game

    # --- Merge roster info (age, experience, position) ---
    logger.info("  Merging roster demographics...")
    roster_info = rosters[["player_id", "team_id", "season", "age", "experience", "position"]].copy()
    roster_info = roster_info.drop_duplicates(subset=["player_id", "team_id", "season"])

    # Convert experience: 'R' (rookie) -> 0, otherwise int
    if "experience" in roster_info.columns:
        roster_info["experience"] = roster_info["experience"].apply(
            lambda x: 0 if str(x).upper() == "R" else pd.to_numeric(x, errors="coerce")
        )

    df = df.merge(roster_info, on=["player_id", "team_id", "season"], how="left",
                  suffixes=("", "_roster"))

    # Use roster age if we don't already have it
    if "age_roster" in df.columns:
        df["age"] = df["age"].fillna(df["age_roster"])
        df = df.drop(columns=["age_roster"])

    logger.info(f"  Player features complete: {df.shape[1]} columns")
    return df


# ──────────────────────────────────────────────
# Phase 4: Injury Context Features (THE CORE)
# ──────────────────────────────────────────────

def build_injury_context_features(
    game_logs: pd.DataFrame,
    absences: pd.DataFrame,
    roles: pd.DataFrame,
) -> pd.DataFrame:
    """Build injury context features — the foundation of the Injury Ripple Effect.

    For each player-game row, this function encodes which TEAMMATES were
    absent, what roles they filled, and how much talent was lost. These
    features allow the ML model to learn how a player's stats change
    depending on who else is or isn't playing.

    Performance: uses pre-computed lookup dicts to avoid row-by-row
    iteration over ~90K rows.

    Args:
        game_logs: Game logs with player features already added.
        absences: Player absences DataFrame.
        roles: Player roles DataFrame from detect_player_roles().

    Returns:
        game_logs DataFrame with injury context feature columns added.
    """
    logger.info("Building injury context features (this is the critical part)...")
    df = game_logs.copy()

    # --- Pre-compute lookup structures for performance ---

    # Lookup: (game_id, team_id) -> set of absent player_ids
    logger.info("  Building absence lookup...")
    absence_lookup = {}
    for _, row in absences.iterrows():
        key = (row["game_id"], row["team_id"])
        if key not in absence_lookup:
            absence_lookup[key] = set()
        absence_lookup[key].add(row["player_id"])

    # Lookup: (team_id, season) -> list of (player_id, role_data) sorted by avg_minutes desc
    logger.info("  Building role lookup...")
    role_lookup = {}
    for (team_id, season), group in roles.groupby(["team_id", "season"]):
        # Sort by avg_minutes descending for consistent starter ordering
        sorted_group = group.sort_values("avg_minutes", ascending=False)
        role_lookup[(team_id, season)] = sorted_group.to_dict("records")

    # Lookup: player_id -> {(team_id, season): role_dict}
    player_role_lookup = {}
    for _, row in roles.iterrows():
        pid = row["player_id"]
        if pid not in player_role_lookup:
            player_role_lookup[pid] = {}
        player_role_lookup[pid][(row["team_id"], row["season"])] = row.to_dict()

    # --- Track games per injury configuration for the experience feature ---
    # (team_id, config_hash) -> count of prior games
    config_counter = {}

    # --- Compute features for each unique (game_id, team_id) combination ---
    # Then merge back to the player-level DataFrame
    logger.info("  Computing per-game injury context...")

    # Get unique game-team combinations from the game logs
    game_team_combos = df[["game_id", "team_id", "season", "game_date"]].drop_duplicates()
    game_team_combos = game_team_combos.sort_values("game_date")

    injury_features_records = []

    for _, combo in game_team_combos.iterrows():
        game_id = combo["game_id"]
        team_id = combo["team_id"]
        season = combo["season"]

        # Who is absent for this team in this game?
        absent_ids = absence_lookup.get((game_id, team_id), set())

        # Get team roles for this season
        team_roles = role_lookup.get((team_id, season), [])

        # Identify starters (top 5 by minutes among qualified players)
        starters = [r for r in team_roles if r.get("is_starter", False)]
        # Pad to 5 if fewer starters detected
        while len(starters) < 5:
            starters.append({"player_id": -1})

        # Starter absence flags (ordered by avg_minutes descending)
        starter_flags = {}
        n_starters_out = 0
        for i, starter in enumerate(starters[:5]):
            is_out = int(starter["player_id"] in absent_ids)
            starter_flags[f"starter_{i+1}_out"] = is_out
            n_starters_out += is_out

        # Role-based absence flags
        ball_handler_out = 0
        scorer_out = 0
        rebounder_out = 0
        defender_out = 0
        sixth_man_out = 0

        for r in team_roles:
            pid = r["player_id"]
            if pid in absent_ids:
                if r.get("role_ball_handler", False):
                    ball_handler_out = 1
                if r.get("role_scorer", False):
                    scorer_out = 1
                if r.get("role_rebounder", False):
                    rebounder_out = 1
                if r.get("role_defender", False):
                    defender_out = 1
                if r.get("role_sixth_man", False):
                    sixth_man_out = 1

        # Rotation players out (top 8 by minutes)
        rotation_ids = set(r["player_id"] for r in team_roles[:8])
        n_rotation_out = len(absent_ids & rotation_ids)

        # Talent loss metrics
        total_pts_lost = 0.0
        total_ast_lost = 0.0
        total_reb_lost = 0.0
        total_minutes_lost = 0.0

        for r in team_roles:
            if r["player_id"] in absent_ids:
                total_pts_lost += r.get("avg_pts", 0) or 0
                total_ast_lost += r.get("avg_ast", 0) or 0
                total_reb_lost += r.get("avg_reb", 0) or 0
                total_minutes_lost += r.get("avg_minutes", 0) or 0

        # Configuration hash: deterministic hash of sorted absent player IDs
        sorted_absent = sorted(absent_ids)
        config_str = ",".join(str(pid) for pid in sorted_absent)
        config_hash = hashlib.md5(config_str.encode()).hexdigest()[:12] if sorted_absent else "healthy"

        # Games with this injury configuration (how experienced is the team with this lineup?)
        config_key = (team_id, config_hash)
        games_with_config = config_counter.get(config_key, 0)
        config_counter[config_key] = games_with_config + 1

        record = {
            "game_id": game_id,
            "team_id": team_id,
            "n_starters_out": n_starters_out,
            "ball_handler_out": ball_handler_out,
            "primary_scorer_out": scorer_out,
            "primary_rebounder_out": rebounder_out,
            "primary_defender_out": defender_out,
            "sixth_man_out": sixth_man_out,
            "n_rotation_players_out": n_rotation_out,
            "total_pts_lost": round(total_pts_lost, 2),
            "total_ast_lost": round(total_ast_lost, 2),
            "total_reb_lost": round(total_reb_lost, 2),
            "total_minutes_lost": round(total_minutes_lost, 2),
            "injury_config_hash": config_hash,
            "games_with_this_config": games_with_config,
            **starter_flags,
        }
        injury_features_records.append(record)

    injury_df = pd.DataFrame(injury_features_records)
    logger.info(f"  Computed injury context for {len(injury_df)} game-team combinations")

    # Merge back to player-level DataFrame
    df = df.merge(injury_df, on=["game_id", "team_id"], how="left")

    # Fill any missing injury features with 0 (games with no absence data)
    injury_cols = [c for c in injury_df.columns if c not in ["game_id", "team_id"]]
    for col in injury_cols:
        if col in df.columns and col != "injury_config_hash":
            df[col] = df[col].fillna(0)
    if "injury_config_hash" in df.columns:
        df["injury_config_hash"] = df["injury_config_hash"].fillna("healthy")

    logger.info(f"  Injury context features complete: {len(injury_cols)} new columns")
    return df


# ──────────────────────────────────────────────
# Phase 5: Target Variables
# ──────────────────────────────────────────────

def build_target_variables(df: pd.DataFrame) -> pd.DataFrame:
    """Create target variable columns with target_ prefix.

    The targets are the actual game stats the ML model will predict.

    Args:
        df: DataFrame with all features.

    Returns:
        DataFrame with target columns added.
    """
    logger.info("Building target variables...")
    target_map = {
        "pts": "target_pts",
        "ast": "target_ast",
        "reb": "target_reb",
        "stl": "target_stl",
        "blk": "target_blk",
        "fg_pct": "target_fg_pct",
        "ft_pct": "target_ft_pct",
        "minutes": "target_minutes",
    }
    for source, target in target_map.items():
        if source in df.columns:
            df[target] = df[source]

    return df


# ──────────────────────────────────────────────
# Phase 6: Feature Dictionary
# ──────────────────────────────────────────────

def generate_feature_dictionary():
    """Generate a markdown file documenting all features."""
    content = """# Feature Dictionary

## Overview

This document describes all features in the processed player dataset.
Each row represents one player-game: a single player's stats and context
for a single NBA game.

## Identifier Columns

| Feature | Type | Description |
|---------|------|-------------|
| player_id | int | NBA unique player ID |
| player_name | str | Player full name |
| team_id | int | NBA team ID |
| team_abbr | str | Team abbreviation (e.g., 'LAL') |
| game_id | str | NBA unique game ID |
| game_date | date | Game date |
| season | str | Season (e.g., '2022-23') |
| opponent | str | Opponent team abbreviation |
| matchup | str | Full matchup string (e.g., 'LAL vs. BOS') |
| win_loss | str | Game result: 'W' or 'L' |
| home_away | str | 'HOME' or 'AWAY' |

## Raw Game Stats

| Feature | Type | Description |
|---------|------|-------------|
| pts | float | Points scored |
| ast | float | Assists |
| reb | float | Total rebounds |
| oreb | float | Offensive rebounds |
| dreb | float | Defensive rebounds |
| stl | float | Steals |
| blk | float | Blocks |
| tov | float | Turnovers |
| fgm | float | Field goals made |
| fga | float | Field goals attempted |
| fg_pct | float | Field goal percentage (0-1) |
| fg3m | float | 3-point field goals made |
| fg3a | float | 3-point field goals attempted |
| fg3_pct | float | 3-point percentage (0-1) |
| ftm | float | Free throws made |
| fta | float | Free throws attempted |
| ft_pct | float | Free throw percentage (0-1) |
| plus_minus | float | Plus/minus for the game |
| pf | float | Personal fouls |
| minutes | float | Minutes played |

## Season Rolling Averages (11 features)

Computed as `expanding().mean().shift(1)` per (player_id, season).
Each value is the player's average of that stat in all PRIOR games
this season (excludes current game to prevent future leakage).

| Feature | Description |
|---------|-------------|
| season_avg_pts | Season average points |
| season_avg_ast | Season average assists |
| season_avg_reb | Season average rebounds |
| season_avg_stl | Season average steals |
| season_avg_blk | Season average blocks |
| season_avg_tov | Season average turnovers |
| season_avg_fg_pct | Season average FG% |
| season_avg_ft_pct | Season average FT% |
| season_avg_fg3_pct | Season average 3PT% |
| season_avg_plus_minus | Season average plus/minus |
| season_avg_minutes | Season average minutes |

## Last-5 Game Averages (6 features)

Computed as `rolling(5, min_periods=1).mean().shift(1)` per (player_id, season).
Captures recent form.

| Feature | Description |
|---------|-------------|
| last5_avg_pts | Average points over last 5 games |
| last5_avg_ast | Average assists over last 5 games |
| last5_avg_reb | Average rebounds over last 5 games |
| last5_avg_minutes | Average minutes over last 5 games |
| last5_avg_fg_pct | Average FG% over last 5 games |
| last5_avg_plus_minus | Average plus/minus over last 5 games |

## Last-10 Game Averages (6 features)

Same as last-5 but over a 10-game window.

| Feature | Description |
|---------|-------------|
| last10_avg_pts | Average points over last 10 games |
| last10_avg_ast | Average assists over last 10 games |
| last10_avg_reb | Average rebounds over last 10 games |
| last10_avg_minutes | Average minutes over last 10 games |
| last10_avg_fg_pct | Average FG% over last 10 games |
| last10_avg_plus_minus | Average plus/minus over last 10 games |

## Home/Away Splits (3 features)

| Feature | Type | Description |
|---------|------|-------------|
| home_avg_pts | float | Player's average PTS in prior home games this season |
| away_avg_pts | float | Player's average PTS in prior away games this season |
| home_away_pts_diff | float | home_avg_pts - away_avg_pts |

## Per-Opponent Averages (3 features)

Computed as `expanding().mean().shift(1)` per (player_id, opponent)
across ALL seasons in the dataset. Captures matchup-specific tendencies.

| Feature | Description |
|---------|-------------|
| vs_opp_avg_pts | Career average PTS vs this opponent |
| vs_opp_avg_reb | Career average REB vs this opponent |
| vs_opp_avg_ast | Career average AST vs this opponent |

## Trend & Context (5 features)

| Feature | Type | Description |
|---------|------|-------------|
| minutes_trend | float | Slope of linear fit on minutes over last 10 games. Positive = gaining minutes. |
| games_played_season | int | Number of games played this season before this game |
| age | float | Player age for this season |
| experience | int | Years of NBA experience (0 = rookie) |
| position | str | Position (G, F, C, G-F, F-C, etc.) |

## Injury Context Features (19 features) — THE CORE

These features encode the injury state of the player's TEAMMATES for
each game. They are the foundation of the Injury Ripple Effect model.

### Binary Absence Flags

| Feature | Type | Description |
|---------|------|-------------|
| n_starters_out | int | Count of team's starters who are absent (0-4) |
| starter_1_out | int | 1 if the starter with most avg minutes is absent |
| starter_2_out | int | 1 if the 2nd-most-minutes starter is absent |
| starter_3_out | int | 1 if the 3rd-most-minutes starter is absent |
| starter_4_out | int | 1 if the 4th-most-minutes starter is absent |
| starter_5_out | int | 1 if the 5th-most-minutes starter is absent |

### Role-Based Absence Flags

| Feature | Type | Description |
|---------|------|-------------|
| ball_handler_out | int | 1 if the primary ball handler (highest AST starter) is absent |
| primary_scorer_out | int | 1 if the primary scorer (highest PTS starter) is absent |
| primary_rebounder_out | int | 1 if the primary rebounder (highest REB starter) is absent |
| primary_defender_out | int | 1 if the primary defender (highest STL+BLK starter) is absent |
| sixth_man_out | int | 1 if the sixth man (top non-starter by minutes) is absent |
| n_rotation_players_out | int | Count of top-8-minutes players who are absent |

### Talent Loss Metrics

| Feature | Type | Description |
|---------|------|-------------|
| total_pts_lost | float | Sum of season avg PTS for all absent players |
| total_ast_lost | float | Sum of season avg AST for all absent players |
| total_reb_lost | float | Sum of season avg REB for all absent players |
| total_minutes_lost | float | Sum of season avg minutes for all absent players |

### Configuration Features

| Feature | Type | Description |
|---------|------|-------------|
| injury_config_hash | str | MD5 hash of sorted absent player IDs. Same hash = same lineup configuration. 'healthy' if no absences. |
| games_with_this_config | int | Number of prior games this team played with this exact set of absences. Higher = more lineup experience. |

## Target Variables (8 features)

These are the stats the ML model will predict. They are copies of the
raw game stats with a `target_` prefix.

| Feature | Description |
|---------|-------------|
| target_pts | Points to predict |
| target_ast | Assists to predict |
| target_reb | Rebounds to predict |
| target_stl | Steals to predict |
| target_blk | Blocks to predict |
| target_fg_pct | FG% to predict |
| target_ft_pct | FT% to predict |
| target_minutes | Minutes to predict |
"""
    with open(OUTPUT_FEATURES, "w") as f:
        f.write(content)
    logger.info(f"Feature dictionary saved to {OUTPUT_FEATURES}")


# ──────────────────────────────────────────────
# Main Pipeline
# ──────────────────────────────────────────────

def main():
    """Run the full data processing and feature engineering pipeline."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 60)
    logger.info("Starting data processing and feature engineering")
    logger.info("=" * 60)

    # Phase 1: Load and clean
    game_logs, rosters, absences = load_and_clean()

    # Phase 2: Detect player roles
    roles = detect_player_roles(game_logs, rosters)

    # Phase 3: Build player features
    df = build_player_features(game_logs, rosters)

    # Phase 4: Build injury context features
    df = build_injury_context_features(df, absences, roles)

    # Phase 5: Build target variables
    df = build_target_variables(df)

    # Phase 6: Assign current_team from each player's most recent game
    # team_abbr = the team for THAT specific game (historical, per-row)
    # current_team = the team from the player's MOST RECENT game (same for all rows)
    logger.info("Assigning current team from most recent game log...")
    latest_team = (
        df.sort_values("game_date")
        .groupby("player_id")["team_abbr"]
        .last()
        .rename("current_team")
    )
    df = df.merge(latest_team, on="player_id", how="left")
    df["current_team"] = df["current_team"].fillna(df["team_abbr"])

    n_traded = (
        df.groupby("player_id")["team_abbr"].nunique() > 1
    ).sum()
    logger.info(f"  Players with multiple teams in dataset: {n_traded}")

    # Drop rows where ALL season average features are NaN
    # (first game of the season — no prior data)
    season_avg_cols = [c for c in df.columns if c.startswith("season_avg_")]
    if season_avg_cols:
        all_nan_mask = df[season_avg_cols].isna().all(axis=1)
        dropped = all_nan_mask.sum()
        if dropped > 0:
            logger.info(f"Dropping {dropped} rows with no prior season data (first games)")
            df = df[~all_nan_mask]

    # Reset index
    df = df.reset_index(drop=True)

    # Save processed data
    df.to_csv(OUTPUT_DATA, index=False)
    logger.info(f"\nProcessed data saved to {OUTPUT_DATA}")

    # Generate feature dictionary
    generate_feature_dictionary()

    # --- Summary Statistics ---
    logger.info("\n" + "=" * 60)
    logger.info("PROCESSING COMPLETE — SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Total rows: {len(df)}")
    logger.info(f"Total columns: {df.shape[1]}")
    logger.info(f"Date range: {df['game_date'].min()} to {df['game_date'].max()}")
    logger.info(f"Unique players: {df['player_id'].nunique()}")
    logger.info(f"Unique teams: {df['team_abbr'].nunique()}")

    # Missing value summary
    null_cols = df.isnull().sum()
    null_cols = null_cols[null_cols > 0].sort_values(ascending=False)
    if len(null_cols) > 0:
        logger.info(f"\nColumns with missing values:")
        for col, count in null_cols.head(15).items():
            pct = count / len(df) * 100
            logger.info(f"  {col}: {count} ({pct:.1f}%)")

    # Injury context distribution
    if "n_starters_out" in df.columns:
        logger.info(f"\nDistribution of starters out:")
        dist = df["n_starters_out"].value_counts().sort_index()
        for n_out, count in dist.items():
            pct = count / len(df) * 100
            logger.info(f"  {int(n_out)} starters out: {count} games ({pct:.1f}%)")

    # Top 10 most common injury configs (excluding healthy)
    if "injury_config_hash" in df.columns:
        non_healthy = df[df["injury_config_hash"] != "healthy"]
        if not non_healthy.empty:
            top_configs = non_healthy["injury_config_hash"].value_counts().head(5)
            logger.info(f"\nTop 5 most common injury configurations (excluding healthy):")
            for config, count in top_configs.items():
                logger.info(f"  {config}: {count} player-games")

    logger.info(f"\nOutput files:")
    logger.info(f"  {OUTPUT_DATA}")
    logger.info(f"  {OUTPUT_FEATURES}")


if __name__ == "__main__":
    main()
