"""
Unified prediction pipeline for the NBA Injury Impact Analyzer.

Imported by the API — not run standalone. Exposes 4 public functions:
  - predict_baseline()
  - predict_with_injuries()
  - get_ripple_effect()
  - simulate_injury()

Uses the SAME feature builder as training (Critical Fix #1).
All return values pass through serialize_prediction() (Critical Fix #3).
"""

import hashlib
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import joblib

from backend.ml.config import (
    MODELS_DIR, PROCESSED_DIR, STAT_NAMES, TARGET_COLS,
    MIN_GAMES_FOR_ROLE, INJURY_FEATURES,
    load_processed_data, serialize_prediction,
)
from backend.ml.feature_builder import build_feature_vector

logger = logging.getLogger("predict")


# ──────────────────────────────────────────────
# ModelStore Singleton — Lazy Loading
# ──────────────────────────────────────────────

class ModelStore:
    """Lazy-loading singleton for models, feature lists, and data."""

    def __init__(self):
        self._baseline_models = None
        self._ripple_models = None
        self._baseline_features = None
        self._ripple_features = None
        self._ripple_metadata = None
        self._player_data = None

    def _check_file(self, path, hint):
        if not path.exists():
            raise FileNotFoundError(
                f"File not found: {path}. Run '{hint}' first."
            )

    def get_baseline_models(self) -> dict:
        if self._baseline_models is None:
            self._baseline_models = {}
            for stat in STAT_NAMES:
                path = MODELS_DIR / f"baseline_{stat}.joblib"
                self._check_file(path, "python -m backend.ml.baseline_model")
                self._baseline_models[stat] = joblib.load(path)
        return self._baseline_models

    def get_ripple_models(self) -> dict:
        if self._ripple_models is None:
            self._ripple_models = {}
            for stat in STAT_NAMES:
                path = MODELS_DIR / f"ripple_{stat}.joblib"
                self._check_file(path, "python -m backend.ml.ripple_model")
                self._ripple_models[stat] = joblib.load(path)
        return self._ripple_models

    def get_baseline_features(self) -> list:
        if self._baseline_features is None:
            path = MODELS_DIR / "baseline_features.json"
            self._check_file(path, "python -m backend.ml.baseline_model")
            with open(path) as f:
                self._baseline_features = json.load(f)
        return self._baseline_features

    def get_ripple_features(self) -> list:
        if self._ripple_features is None:
            path = MODELS_DIR / "ripple_features.json"
            self._check_file(path, "python -m backend.ml.ripple_model")
            with open(path) as f:
                self._ripple_features = json.load(f)
        return self._ripple_features

    def get_ripple_metadata(self) -> dict:
        if self._ripple_metadata is None:
            path = MODELS_DIR / "ripple_metadata.json"
            if path.exists():
                with open(path) as f:
                    self._ripple_metadata = json.load(f)
            else:
                self._ripple_metadata = {"chosen_approach": "A"}
        return self._ripple_metadata

    def get_player_data(self) -> pd.DataFrame:
        if self._player_data is None:
            self._player_data = load_processed_data()
        return self._player_data


store = ModelStore()


# ──────────────────────────────────────────────
# Internal Helpers
# ──────────────────────────────────────────────

def _get_player_row(player_id: int, date: str = None) -> pd.Series:
    """Get the most recent data row for a player.

    Handles: unknown player, traded mid-season, date filtering.
    """
    df = store.get_player_data()
    player_df = df[df["player_id"] == player_id]

    if player_df.empty:
        raise ValueError(f"Player {player_id} not found in processed data")

    # Filter to most recent team (handles mid-season trades — Critical Fix #2)
    latest_row = player_df.sort_values("game_date").iloc[-1]
    most_recent_team = latest_row["team_abbr"]
    player_df = player_df[player_df["team_abbr"] == most_recent_team]

    if date is not None:
        date_dt = pd.to_datetime(date)
        player_df = player_df[player_df["game_date"] < date_dt]
        if player_df.empty:
            raise ValueError(
                f"No data for player {player_id} before {date}"
            )

    # Return the most recent row
    return player_df.sort_values("game_date").iloc[-1]


def _get_player_name(player_id: int) -> str:
    """Look up player name from data."""
    df = store.get_player_data()
    player_df = df[df["player_id"] == player_id]
    if player_df.empty:
        return f"Unknown ({player_id})"
    return player_df.iloc[-1]["player_name"]


def _build_row_data(player_id: int, opponent_team: str,
                    home_or_away: str, date: str = None,
                    injury_context: dict = None) -> dict:
    """Build a row_data dict for feature construction.

    Uses the same data structure as the processed CSV rows,
    so build_feature_vector() produces identical features to training.
    """
    row = _get_player_row(player_id, date)
    row_data = row.to_dict()

    # Override home/away
    row_data["home_away"] = home_or_away.upper()

    # Override opponent-specific averages if opponent provided
    if opponent_team:
        df = store.get_player_data()
        player_df = df[df["player_id"] == player_id]

        # Filter by most recent team
        most_recent_team = row_data.get("team_abbr")
        if most_recent_team:
            player_df = player_df[player_df["team_abbr"] == most_recent_team]

        opp_df = player_df[player_df["opponent"] == opponent_team]

        if date:
            opp_df = opp_df[opp_df["game_date"] < pd.to_datetime(date)]

        if not opp_df.empty:
            latest_opp = opp_df.sort_values("game_date").iloc[-1]
            for col in ["vs_opp_avg_pts", "vs_opp_avg_reb", "vs_opp_avg_ast"]:
                if col in latest_opp.index and pd.notna(latest_opp[col]):
                    row_data[col] = latest_opp[col]
        else:
            # Fall back to season averages (Critical Fix #2)
            logger.warning(
                f"No opponent history for player {player_id} vs {opponent_team}. "
                f"Falling back to season averages."
            )
            row_data["_matchup_data"] = "unavailable"

    # Merge injury context (or default to zeros)
    if injury_context:
        for key, val in injury_context.items():
            row_data[key] = val
    else:
        # Zero out all injury features (healthy team scenario)
        for feat in INJURY_FEATURES:
            row_data[feat] = 0

    return row_data


def _predict_stats(row_data: dict, model_type: str = "baseline") -> dict:
    """Run prediction using the feature builder and models.

    Args:
        row_data: Dict with all column values.
        model_type: "baseline" or "ripple".

    Returns:
        Dict mapping stat_name -> predicted value.
    """
    if model_type == "baseline":
        models = store.get_baseline_models()
        feature_list = store.get_baseline_features()
    else:
        models = store.get_ripple_models()
        feature_list = store.get_ripple_features()

    # Build feature vector using the SAME function as training (Critical Fix #1)
    features = build_feature_vector(row_data, feature_list)

    # Check feature count
    if len(features) != len(feature_list):
        raise ValueError(
            f"Feature count mismatch: expected {len(feature_list)}, "
            f"got {len(features)}."
        )

    # Check if ripple model uses Approach B (delta model)
    is_delta_model = (
        model_type == "ripple"
        and store.get_ripple_metadata().get("chosen_approach") == "B"
    )

    # Mapping from stat name to season_avg column for Approach B
    stat_to_avg = {
        "pts": "season_avg_pts", "ast": "season_avg_ast",
        "reb": "season_avg_reb", "stl": "season_avg_stl",
        "blk": "season_avg_blk", "fg_pct": "season_avg_fg_pct",
        "ft_pct": "season_avg_ft_pct", "minutes": "season_avg_minutes",
    }

    predictions = {}
    for stat in STAT_NAMES:
        model = models[stat]
        pred = model.predict(features.reshape(1, -1))[0]

        if is_delta_model:
            # Approach B predicts delta (actual - season_avg).
            # Add season_avg back to get absolute prediction.
            avg_col = stat_to_avg[stat]
            season_avg = row_data.get(avg_col, 0) or 0
            pred = float(season_avg) + pred

        predictions[stat] = pred

    return predictions


# ──────────────────────────────────────────────
# Injury Context Computation (Critical Fix #6)
# ──────────────────────────────────────────────

def _compute_injury_context(team_abbr: str, absent_player_ids: list,
                            date: str = None) -> dict:
    """Compute injury context features matching process_data.py logic exactly.

    Mirrors the logic from process_data.py:404-579:
    - Starter identification: top 5 by avg_minutes among qualified players
    - Role assignment: ball_handler (highest AST), scorer (highest PTS),
      rebounder (highest REB), defender (highest STL+BLK), sixth_man
    - Uses cumulative season_avg_* from CSV (inference approximation)

    Args:
        team_abbr: Team abbreviation (e.g., "LAL").
        absent_player_ids: List of absent player IDs.
        date: Optional date for filtering.

    Returns:
        Dict with all 17 injury context feature values.
    """
    df = store.get_player_data()
    absent_set = set(absent_player_ids)

    if not absent_set:
        # No absences — all zeros
        return {feat: 0 for feat in INJURY_FEATURES}

    # Get players currently on this team, using current_team column
    # (handles traded players — only includes players whose most recent
    # game was for this team, not players who left mid-season)
    if "current_team" in df.columns:
        current_player_ids = df.loc[
            df["current_team"] == team_abbr, "player_id"
        ].unique()
        team_df = df[
            (df["player_id"].isin(current_player_ids))
            & (df["team_abbr"] == team_abbr)
        ].copy()
    else:
        team_df = df[df["team_abbr"] == team_abbr].copy()
    if date:
        team_df = team_df[team_df["game_date"] < pd.to_datetime(date)]

    if team_df.empty:
        logger.warning(f"No data for team {team_abbr}")
        return {feat: 0 for feat in INJURY_FEATURES}

    # Get each player's latest row (approximates their current season averages)
    # Group by player and take the last row's season averages
    latest_season = team_df["season"].iloc[-1]
    season_df = team_df[team_df["season"] == latest_season]

    # Get per-player stats from their last row this season
    player_stats = []
    for pid, pgroup in season_df.groupby("player_id"):
        last_row = pgroup.sort_values("game_date").iloc[-1]
        player_stats.append({
            "player_id": pid,
            "avg_pts": last_row.get("season_avg_pts", 0) or 0,
            "avg_ast": last_row.get("season_avg_ast", 0) or 0,
            "avg_reb": last_row.get("season_avg_reb", 0) or 0,
            "avg_stl": last_row.get("season_avg_stl", 0) or 0,
            "avg_blk": last_row.get("season_avg_blk", 0) or 0,
            "avg_minutes": last_row.get("season_avg_minutes", 0) or 0,
            "games_played": last_row.get("games_played_season", 0) or 0,
        })

    if not player_stats:
        return {feat: 0 for feat in INJURY_FEATURES}

    stats_df = pd.DataFrame(player_stats)

    # Filter to qualified players (>= MIN_GAMES_FOR_ROLE games)
    qualified = stats_df[stats_df["games_played"] >= MIN_GAMES_FOR_ROLE].copy()

    if qualified.empty:
        # Not enough qualified players — use all (matches process_data.py fallback)
        qualified = stats_df.copy()

    # Sort by avg_minutes descending (matches process_data.py ordering)
    qualified = qualified.sort_values("avg_minutes", ascending=False)

    # Starters = top 5 by avg_minutes among qualified
    # (matches process_data.py: if fewer than 5, use all qualified)
    if len(qualified) < 5:
        starters = qualified
    else:
        starters = qualified.head(5)
    starter_ids = starters["player_id"].tolist()

    # Pad to 5 if fewer
    while len(starter_ids) < 5:
        starter_ids.append(-1)

    # Starter absence flags
    n_starters_out = sum(1 for sid in starter_ids[:5] if sid in absent_set)
    starter_flags = {
        f"starter_{i+1}_out": int(starter_ids[i] in absent_set)
        for i in range(5)
    }

    # Role assignment among starters (matches process_data.py)
    starter_df = starters.copy()
    ball_handler_out = 0
    primary_scorer_out = 0
    primary_rebounder_out = 0
    primary_defender_out = 0
    sixth_man_out = 0

    if not starter_df.empty:
        # Ball handler: starter with highest avg_ast
        handler_id = starter_df.loc[starter_df["avg_ast"].idxmax(), "player_id"]
        if handler_id in absent_set:
            ball_handler_out = 1

        # Primary scorer: starter with highest avg_pts
        scorer_id = starter_df.loc[starter_df["avg_pts"].idxmax(), "player_id"]
        if scorer_id in absent_set:
            primary_scorer_out = 1

        # Primary rebounder: starter with highest avg_reb
        rebounder_id = starter_df.loc[starter_df["avg_reb"].idxmax(), "player_id"]
        if rebounder_id in absent_set:
            primary_rebounder_out = 1

        # Primary defender: starter with highest avg_stl + avg_blk
        starter_df = starter_df.copy()
        starter_df["avg_stl_blk"] = starter_df["avg_stl"] + starter_df["avg_blk"]
        defender_id = starter_df.loc[starter_df["avg_stl_blk"].idxmax(), "player_id"]
        if defender_id in absent_set:
            primary_defender_out = 1

    # Sixth man: non-starter with highest avg_minutes (among qualified)
    non_starters = qualified[~qualified["player_id"].isin(starter_ids[:5])]
    if not non_starters.empty:
        sixth_man_id = non_starters.sort_values("avg_minutes", ascending=False).iloc[0]["player_id"]
        if sixth_man_id in absent_set:
            sixth_man_out = 1

    # Rotation players out (top 8 by minutes)
    rotation_ids = set(qualified.head(8)["player_id"].tolist())
    n_rotation_out = len(absent_set & rotation_ids)

    # Talent loss metrics (sum averages for all absent players in qualified set)
    total_pts_lost = 0.0
    total_ast_lost = 0.0
    total_reb_lost = 0.0
    total_minutes_lost = 0.0

    for _, prow in qualified.iterrows():
        if prow["player_id"] in absent_set:
            total_pts_lost += prow["avg_pts"] or 0
            total_ast_lost += prow["avg_ast"] or 0
            total_reb_lost += prow["avg_reb"] or 0
            total_minutes_lost += prow["avg_minutes"] or 0

    # games_with_this_config lookup (Critical Fix #4)
    config_experience = _lookup_config_experience(team_abbr, absent_player_ids)

    return {
        "n_starters_out": n_starters_out,
        **starter_flags,
        "ball_handler_out": ball_handler_out,
        "primary_scorer_out": primary_scorer_out,
        "primary_rebounder_out": primary_rebounder_out,
        "primary_defender_out": primary_defender_out,
        "sixth_man_out": sixth_man_out,
        "n_rotation_players_out": n_rotation_out,
        "total_pts_lost": round(total_pts_lost, 2),
        "total_ast_lost": round(total_ast_lost, 2),
        "total_reb_lost": round(total_reb_lost, 2),
        "total_minutes_lost": round(total_minutes_lost, 2),
        "games_with_this_config": config_experience,
    }


def _lookup_config_experience(team_abbr: str,
                              absent_player_ids: list) -> int:
    """Look up how many times this exact injury config appeared in the data.

    Computes the injury_config_hash and looks it up in the processed CSV
    rather than defaulting to 0 (Critical Fix #4).
    """
    sorted_absent = sorted(absent_player_ids)
    if not sorted_absent:
        return 0

    config_str = ",".join(str(pid) for pid in sorted_absent)
    config_hash = hashlib.md5(config_str.encode()).hexdigest()[:12]

    df = store.get_player_data()
    team_df = df[df["team_abbr"] == team_abbr]

    if "injury_config_hash" not in team_df.columns:
        return 0

    matching = team_df[team_df["injury_config_hash"] == config_hash]

    if matching.empty:
        return 0

    # Return the max games_with_this_config seen (last occurrence)
    return int(matching["games_with_this_config"].max())


# ──────────────────────────────────────────────
# Public API Functions
# ──────────────────────────────────────────────

def predict_baseline(player_id: int, opponent_team: str,
                     home_or_away: str, date: str = None) -> dict:
    """Predict player stats using baseline model (no injury context).

    Args:
        player_id: NBA player ID.
        opponent_team: Opponent team abbreviation (e.g., "BOS").
        home_or_away: "HOME" or "AWAY".
        date: Optional date string (YYYY-MM-DD). Uses latest data if None.

    Returns:
        Dict with player_id, player_name, predictions dict.

    Raises:
        ValueError: If player not found or no data before date.
        FileNotFoundError: If models not trained yet.
    """
    row_data = _build_row_data(player_id, opponent_team, home_or_away, date)
    predictions = _predict_stats(row_data, model_type="baseline")

    result = {
        "player_id": player_id,
        "player_name": _get_player_name(player_id),
        "predictions": predictions,
    }

    if row_data.get("_matchup_data") == "unavailable":
        result["matchup_data"] = "unavailable"

    return serialize_prediction(result)


def predict_with_injuries(player_id: int, opponent_team: str,
                          home_or_away: str, date: str = None,
                          absent_player_ids: list = None) -> dict:
    """Predict player stats with injury context.

    Args:
        player_id: NBA player ID.
        opponent_team: Opponent team abbreviation.
        home_or_away: "HOME" or "AWAY".
        date: Optional date string.
        absent_player_ids: List of absent player IDs on the same team.

    Returns:
        Dict with player_id, player_name, predictions, injury_context.
    """
    absent_player_ids = absent_player_ids or []

    # Get player's team
    row = _get_player_row(player_id, date)
    team_abbr = row["team_abbr"]

    # Compute injury context (Critical Fix #6)
    injury_context = _compute_injury_context(
        team_abbr, absent_player_ids, date
    )

    row_data = _build_row_data(
        player_id, opponent_team, home_or_away, date,
        injury_context=injury_context,
    )

    predictions = _predict_stats(row_data, model_type="ripple")

    result = {
        "player_id": player_id,
        "player_name": _get_player_name(player_id),
        "predictions": predictions,
        "injury_context": injury_context,
    }

    if row_data.get("_matchup_data") == "unavailable":
        result["matchup_data"] = "unavailable"

    return serialize_prediction(result)


def get_ripple_effect(team: str, absent_player_ids: list,
                      opponent_team: str, home_or_away: str,
                      date: str = None) -> dict:
    """Get the ripple effect of injuries on all active team players.

    For each active player on the team, computes:
    - Baseline prediction (healthy team scenario)
    - Injury prediction (with absences)
    - Ripple effect (difference)

    Args:
        team: Team abbreviation (e.g., "LAL").
        absent_player_ids: List of absent player IDs.
        opponent_team: Opponent team abbreviation.
        home_or_away: "HOME" or "AWAY".
        date: Optional date string.

    Returns:
        Dict with team, absent_players, injury_context, player_predictions.
    """
    absent_set = set(absent_player_ids)

    # Compute injury context once for the team
    injury_context = _compute_injury_context(team, absent_player_ids, date)

    # Get all active players currently on the team
    df = store.get_player_data()

    # Use current_team to find players whose most recent game was for this team
    if "current_team" in df.columns:
        current_player_ids = df.loc[
            df["current_team"] == team, "player_id"
        ].unique()
        team_df = df[
            (df["player_id"].isin(current_player_ids))
            & (df["team_abbr"] == team)
        ]
    else:
        team_df = df[df["team_abbr"] == team]

    if date:
        team_df = team_df[team_df["game_date"] < pd.to_datetime(date)]

    if team_df.empty:
        raise ValueError(f"No data for team {team}")

    # Get unique active players (not in absent list)
    latest_season = team_df["season"].iloc[-1]
    season_df = team_df[team_df["season"] == latest_season]
    player_ids = season_df["player_id"].unique()
    active_ids = [pid for pid in player_ids if pid not in absent_set]

    # Get absent player names
    absent_players = []
    for pid in absent_player_ids:
        absent_players.append({
            "player_id": pid,
            "player_name": _get_player_name(pid),
        })

    player_predictions = []
    for pid in active_ids:
        try:
            # Baseline (no injuries)
            baseline_row = _build_row_data(pid, opponent_team, home_or_away, date)
            baseline_preds = _predict_stats(baseline_row, model_type="ripple")

            # With injuries
            injury_row = _build_row_data(
                pid, opponent_team, home_or_away, date,
                injury_context=injury_context,
            )
            injury_preds = _predict_stats(injury_row, model_type="ripple")

            # Ripple effect = difference
            ripple_effect = {
                stat: injury_preds[stat] - baseline_preds[stat]
                for stat in STAT_NAMES
            }

            player_predictions.append({
                "player_id": pid,
                "player_name": _get_player_name(pid),
                "baseline": baseline_preds,
                "with_injuries": injury_preds,
                "ripple_effect": ripple_effect,
            })
        except (ValueError, KeyError) as e:
            logger.warning(f"Skipping player {pid}: {e}")
            continue

    result = {
        "team": team,
        "absent_players": absent_players,
        "injury_context": injury_context,
        "player_predictions": player_predictions,
    }

    return serialize_prediction(result)


def simulate_injury(player_id_to_injure: int,
                    game_context: dict) -> dict:
    """Simulate the ripple effect of a specific player being injured.

    Auto-determines the team from the player's data, then calls
    get_ripple_effect() with that player as the sole absence.

    Args:
        player_id_to_injure: ID of the player to simulate as injured.
        game_context: Dict with "opponent", "home_or_away", optional "date".

    Returns:
        Same structure as get_ripple_effect().
    """
    # Determine team from player
    df = store.get_player_data()
    player_df = df[df["player_id"] == player_id_to_injure]

    if player_df.empty:
        raise ValueError(
            f"Player {player_id_to_injure} not found in processed data"
        )

    # Use most recent team (prefer current_team if available)
    latest = player_df.sort_values("game_date").iloc[-1]
    team = latest.get("current_team", latest["team_abbr"])

    opponent = game_context.get("opponent", "")
    home_or_away = game_context.get("home_or_away", "HOME")
    date = game_context.get("date")

    return get_ripple_effect(
        team=team,
        absent_player_ids=[player_id_to_injure],
        opponent_team=opponent,
        home_or_away=home_or_away,
        date=date,
    )
