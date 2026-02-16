"""
Collect NBA player game logs and roster data using nba_api.

Uses the bulk PlayerGameLogs endpoint to pull all players' game logs
for an entire season in one API call (3 calls total for 3 seasons).
Also pulls roster data for all 30 teams across 3 seasons.

Supports resumable collection via checkpoints — if interrupted,
re-running the script picks up where it left off.

Output files:
    backend/data/raw/player_game_logs.csv  (~90,000 rows)
    backend/data/raw/rosters.csv           (~1,500 rows)
"""

import sys
import time
from pathlib import Path

import pandas as pd
from nba_api.stats.endpoints import PlayerGameLogs, CommonTeamRoster
from nba_api.stats.static import teams

# Add project root to path so we can import utils
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from backend.scripts.utils import (
    setup_logging,
    load_checkpoint,
    save_checkpoint,
    rate_limited_api_call,
    RAW_DIR,
    CHECKPOINT_DIR,
)

# --- Configuration ---
SEASONS = ["2022-23", "2023-24", "2024-25"]
SEASON_TYPE = "Regular Season"

CHECKPOINT_FILE = str(CHECKPOINT_DIR / "collect_stats_checkpoint.json")
OUTPUT_GAME_LOGS = str(RAW_DIR / "player_game_logs.csv")
OUTPUT_ROSTERS = str(RAW_DIR / "rosters.csv")

# Minimum rows expected from a single-season bulk call.
# A full NBA regular season has ~30,000 player-game rows.
# If we get fewer than this, the bulk endpoint likely failed.
MIN_ROWS_PER_SEASON = 1000

logger = setup_logging("collect_player_stats")


def extract_opponent(matchup: str) -> str:
    """Extract opponent team abbreviation from a matchup string.

    The MATCHUP column looks like 'LAL vs. BOS' (home) or 'LAL @ BOS' (away).
    We extract the opponent (the team on the right side).

    Args:
        matchup: The matchup string from nba_api.

    Returns:
        The opponent's team abbreviation (e.g., 'BOS').
    """
    if " vs. " in matchup:
        return matchup.split(" vs. ")[1].strip()
    elif " @ " in matchup:
        return matchup.split(" @ ")[1].strip()
    return ""


def collect_game_logs_bulk(checkpoint: dict) -> pd.DataFrame:
    """Collect game logs using the bulk PlayerGameLogs endpoint.

    PlayerGameLogs (plural) returns ALL players' game logs for an entire
    season in a single API call, making this dramatically faster than
    the per-player approach.

    Args:
        checkpoint: Current checkpoint state dict.

    Returns:
        DataFrame with all game logs across requested seasons.
    """
    completed_seasons = checkpoint.get("game_logs_completed", [])
    all_dfs = []

    # Load any previously saved partial data
    if Path(OUTPUT_GAME_LOGS).exists() and completed_seasons:
        existing = pd.read_csv(OUTPUT_GAME_LOGS)
        all_dfs.append(existing)
        logger.info(f"Loaded {len(existing)} existing game log rows from checkpoint")

    for season in SEASONS:
        if season in completed_seasons:
            logger.info(f"Skipping season {season} (already collected)")
            continue

        logger.info(f"Collecting game logs for season {season}...")
        start_time = time.time()

        endpoint = rate_limited_api_call(
            PlayerGameLogs,
            season_nullable=season,
            season_type_nullable=SEASON_TYPE,
        )
        df = endpoint.get_data_frames()[0]

        elapsed = time.time() - start_time
        logger.info(f"Collected game logs for season {season}: {len(df)} rows ({elapsed:.1f}s)")

        # Validate: a full season should have many thousands of rows
        if len(df) < MIN_ROWS_PER_SEASON:
            logger.warning(
                f"Season {season} returned only {len(df)} rows (expected >={MIN_ROWS_PER_SEASON}). "
                f"Bulk endpoint may have failed — will need fallback."
            )
            return pd.DataFrame()  # Signal to caller to use fallback

        # Derive home/away from the MATCHUP column
        # 'LAL vs. BOS' means LAL is home; 'LAL @ BOS' means LAL is away
        df["HOME_AWAY"] = df["MATCHUP"].apply(
            lambda m: "HOME" if " vs. " in str(m) else "AWAY"
        )

        # Extract opponent abbreviation
        df["OPPONENT"] = df["MATCHUP"].apply(extract_opponent)

        all_dfs.append(df)

        # Checkpoint after each season
        completed_seasons.append(season)
        checkpoint["game_logs_completed"] = completed_seasons
        save_checkpoint(CHECKPOINT_FILE, checkpoint)

    if not all_dfs:
        return pd.DataFrame()

    combined = pd.concat(all_dfs, ignore_index=True)

    # Select and rename columns to our canonical schema
    column_map = {
        "PLAYER_NAME": "player_name",
        "PLAYER_ID": "player_id",
        "TEAM_ID": "team_id",
        "TEAM_ABBREVIATION": "team_abbr",
        "GAME_ID": "game_id",
        "GAME_DATE": "game_date",
        "MATCHUP": "matchup",
        "OPPONENT": "opponent",
        "WL": "win_loss",
        "HOME_AWAY": "home_away",
        "MIN": "minutes",
        "PTS": "pts",
        "AST": "ast",
        "REB": "reb",
        "OREB": "oreb",
        "DREB": "dreb",
        "STL": "stl",
        "BLK": "blk",
        "TOV": "tov",
        "FGM": "fgm",
        "FGA": "fga",
        "FG_PCT": "fg_pct",
        "FG3M": "fg3m",
        "FG3A": "fg3a",
        "FG3_PCT": "fg3_pct",
        "FTM": "ftm",
        "FTA": "fta",
        "FT_PCT": "ft_pct",
        "PLUS_MINUS": "plus_minus",
        "PF": "pf",
        "SEASON_YEAR": "season",
    }

    # Only rename columns that exist in the DataFrame
    existing_cols = {k: v for k, v in column_map.items() if k in combined.columns}
    combined = combined.rename(columns=existing_cols)

    # Keep only the columns we want
    output_cols = list(existing_cols.values())
    combined = combined[[c for c in output_cols if c in combined.columns]]

    return combined


def collect_game_logs_per_player(checkpoint: dict, roster_df: pd.DataFrame) -> pd.DataFrame:
    """Fallback: collect game logs one player at a time.

    Used only if the bulk PlayerGameLogs endpoint fails. This is much
    slower (~50 minutes) but more reliable.

    Args:
        checkpoint: Current checkpoint state dict.
        roster_df: Roster DataFrame to get player IDs from.

    Returns:
        DataFrame with all game logs.
    """
    from nba_api.stats.endpoints import PlayerGameLog

    completed_players = set(
        tuple(x) for x in checkpoint.get("fallback_players_completed", [])
    )
    all_dfs = []

    # Load existing partial data
    if Path(OUTPUT_GAME_LOGS).exists() and completed_players:
        existing = pd.read_csv(OUTPUT_GAME_LOGS)
        all_dfs.append(existing)

    # Get unique player-season combos from roster
    player_seasons = roster_df[["player_id", "season"]].drop_duplicates()
    total = len(player_seasons)

    for idx, (_, row) in enumerate(player_seasons.iterrows()):
        player_id = int(row["player_id"])
        season = row["season"]
        key = (player_id, season)

        if key in completed_players:
            continue

        logger.info(f"Pulling game log for player {player_id}, season {season} ({idx + 1}/{total})")

        try:
            endpoint = rate_limited_api_call(
                PlayerGameLog,
                player_id=player_id,
                season=season,
                season_type_all_star=SEASON_TYPE,
            )
            df = endpoint.get_data_frames()[0]

            if not df.empty:
                df["SEASON_YEAR"] = season
                df["HOME_AWAY"] = df["MATCHUP"].apply(
                    lambda m: "HOME" if " vs. " in str(m) else "AWAY"
                )
                df["OPPONENT"] = df["MATCHUP"].apply(extract_opponent)
                all_dfs.append(df)

        except Exception as e:
            logger.error(f"Failed to collect player {player_id} season {season}: {e}")

        completed_players.add(key)
        checkpoint["fallback_players_completed"] = [list(x) for x in completed_players]

        # Save checkpoint every 50 players
        if len(completed_players) % 50 == 0:
            save_checkpoint(CHECKPOINT_FILE, checkpoint)

    save_checkpoint(CHECKPOINT_FILE, checkpoint)

    if not all_dfs:
        return pd.DataFrame()

    combined = pd.concat(all_dfs, ignore_index=True)

    # Apply the same column renaming as the bulk path
    column_map = {
        "Player_ID": "player_id",
        "PLAYER_NAME": "player_name",
        "TEAM_ID": "team_id",
        "TEAM_ABBREVIATION": "team_abbr",
        "Game_ID": "game_id",
        "GAME_DATE": "game_date",
        "MATCHUP": "matchup",
        "OPPONENT": "opponent",
        "WL": "win_loss",
        "HOME_AWAY": "home_away",
        "MIN": "minutes",
        "PTS": "pts",
        "AST": "ast",
        "REB": "reb",
        "OREB": "oreb",
        "DREB": "dreb",
        "STL": "stl",
        "BLK": "blk",
        "TOV": "tov",
        "FGM": "fgm",
        "FGA": "fga",
        "FG_PCT": "fg_pct",
        "FG3M": "fg3m",
        "FG3A": "fg3a",
        "FG3_PCT": "fg3_pct",
        "FTM": "ftm",
        "FTA": "fta",
        "FT_PCT": "ft_pct",
        "PLUS_MINUS": "plus_minus",
        "PF": "pf",
        "SEASON_YEAR": "season",
    }
    existing_cols = {k: v for k, v in column_map.items() if k in combined.columns}
    combined = combined.rename(columns=existing_cols)
    output_cols = list(existing_cols.values())
    combined = combined[[c for c in output_cols if c in combined.columns]]

    return combined


def collect_rosters(checkpoint: dict) -> pd.DataFrame:
    """Collect roster data for all 30 NBA teams across all seasons.

    Uses CommonTeamRoster endpoint. Provides player demographics
    like age, position, height, weight, and experience.

    Args:
        checkpoint: Current checkpoint state dict.

    Returns:
        DataFrame with all roster data.
    """
    completed_rosters = set(
        tuple(x) for x in checkpoint.get("rosters_completed", [])
    )
    all_dfs = []

    # Load existing partial data
    if Path(OUTPUT_ROSTERS).exists() and completed_rosters:
        existing = pd.read_csv(OUTPUT_ROSTERS)
        all_dfs.append(existing)
        logger.info(f"Loaded {len(existing)} existing roster rows from checkpoint")

    nba_teams = teams.get_teams()
    total_calls = len(nba_teams) * len(SEASONS)
    call_count = len(completed_rosters)

    for team in nba_teams:
        team_id = team["id"]
        team_abbr = team["abbreviation"]
        team_name = team["full_name"]

        for season in SEASONS:
            key = (team_id, season)
            if key in completed_rosters:
                continue

            call_count += 1
            logger.info(
                f"Roster for {team_name} {season}: "
                f"(call {call_count}/{total_calls})"
            )

            try:
                endpoint = rate_limited_api_call(
                    CommonTeamRoster,
                    team_id=team_id,
                    season=season,
                )
                df = endpoint.get_data_frames()[0]

                if not df.empty:
                    df["team_abbreviation"] = team_abbr
                    df["team_name"] = team_name
                    all_dfs.append(df)
                    logger.info(f"  -> {len(df)} players")

            except Exception as e:
                logger.error(f"Failed to collect roster for {team_name} {season}: {e}")

            completed_rosters.add(key)
            checkpoint["rosters_completed"] = [list(x) for x in completed_rosters]
            save_checkpoint(CHECKPOINT_FILE, checkpoint)

    if not all_dfs:
        return pd.DataFrame()

    combined = pd.concat(all_dfs, ignore_index=True)

    # Select and rename columns
    column_map = {
        "PLAYER_ID": "player_id",
        "PLAYER": "player_name",
        "TeamID": "team_id",
        "team_abbreviation": "team_abbr",
        "team_name": "team_name",
        "POSITION": "position",
        "HEIGHT": "height",
        "WEIGHT": "weight",
        "BIRTH_DATE": "birth_date",
        "AGE": "age",
        "EXP": "experience",
        "SEASON": "season",
        "NUM": "jersey_number",
    }
    existing_cols = {k: v for k, v in column_map.items() if k in combined.columns}
    combined = combined.rename(columns=existing_cols)
    output_cols = list(existing_cols.values())
    combined = combined[[c for c in output_cols if c in combined.columns]]

    return combined


def main():
    """Run the full player stats and roster collection pipeline."""
    # Ensure output directories exist
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    checkpoint = load_checkpoint(CHECKPOINT_FILE)
    logger.info("=" * 60)
    logger.info("Starting NBA player stats collection")
    logger.info(f"Seasons: {SEASONS}")
    logger.info(f"Estimated time: ~4 minutes (bulk) or ~50 minutes (fallback)")
    logger.info("=" * 60)

    # --- Collect game logs ---
    logger.info("\n--- Phase 1: Collecting game logs (bulk approach) ---")
    game_logs = collect_game_logs_bulk(checkpoint)

    # If bulk approach failed, try per-player fallback
    if game_logs.empty and not checkpoint.get("game_logs_completed"):
        logger.warning("Bulk collection returned no data. Trying per-player fallback...")
        logger.warning("This will be much slower (~50 minutes). Be patient.")

        # We need rosters first to know which players to fetch
        logger.info("Collecting rosters first (needed for fallback)...")
        rosters = collect_rosters(checkpoint)
        rosters.to_csv(OUTPUT_ROSTERS, index=False)

        game_logs = collect_game_logs_per_player(checkpoint, rosters)
    else:
        # --- Collect rosters ---
        logger.info("\n--- Phase 2: Collecting rosters ---")
        rosters = collect_rosters(checkpoint)
        rosters.to_csv(OUTPUT_ROSTERS, index=False)

    # Save game logs
    if not game_logs.empty:
        game_logs.to_csv(OUTPUT_GAME_LOGS, index=False)

    # --- Print summary ---
    logger.info("\n" + "=" * 60)
    logger.info("COLLECTION COMPLETE")
    logger.info("=" * 60)

    if not game_logs.empty:
        logger.info(f"Game logs: {len(game_logs)} rows")
        logger.info(f"  Unique players: {game_logs['player_id'].nunique()}")
        logger.info(f"  Unique teams: {game_logs['team_abbr'].nunique()}")
        logger.info(f"  Date range: {game_logs['game_date'].min()} to {game_logs['game_date'].max()}")
        for season in SEASONS:
            season_count = len(game_logs[game_logs["season"] == season])
            logger.info(f"  Season {season}: {season_count} rows")
    else:
        logger.error("No game log data was collected!")

    if not rosters.empty:
        logger.info(f"\nRosters: {len(rosters)} rows")
        logger.info(f"  Unique players: {rosters['player_id'].nunique()}")
    else:
        logger.error("No roster data was collected!")

    logger.info(f"\nOutput files:")
    logger.info(f"  {OUTPUT_GAME_LOGS}")
    logger.info(f"  {OUTPUT_ROSTERS}")

    # Clean up checkpoint on successful completion
    checkpoint_path = Path(CHECKPOINT_FILE)
    if checkpoint_path.exists():
        checkpoint_path.unlink()
        logger.info("Checkpoint file cleaned up (collection complete)")


if __name__ == "__main__":
    main()
