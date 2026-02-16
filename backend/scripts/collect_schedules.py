"""
Collect NBA game schedules.

Derives the historical schedule from game logs (games already played)
and fetches future games from the NBA CDN endpoint for the current season.

Prerequisites:
    Run collect_player_stats.py first to generate:
    - backend/data/raw/player_game_logs.csv

Output:
    backend/data/raw/schedule.csv  (~3,700 rows)
"""

import sys
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from backend.scripts.utils import setup_logging, RAW_DIR

OUTPUT_SCHEDULE = str(RAW_DIR / "schedule.csv")

# NBA CDN endpoint for the current season schedule
NBA_SCHEDULE_URL = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"

logger = setup_logging("collect_schedules")


def derive_historical_schedule(game_logs: pd.DataFrame) -> pd.DataFrame:
    """Extract the game schedule from historical game log data.

    Each unique (game_id, game_date) in the game logs represents a
    completed game. We determine home/away from the home_away column.

    Args:
        game_logs: Full game logs DataFrame.

    Returns:
        DataFrame with one row per game (game_id, game_date, home_team,
        away_team, season, status='completed').
    """
    logger.info("Deriving historical schedule from game logs...")

    # Get home teams: rows where home_away == 'HOME'
    home = game_logs[game_logs["home_away"] == "HOME"][
        ["game_id", "game_date", "team_abbr", "season"]
    ].drop_duplicates(subset=["game_id"])
    home = home.rename(columns={"team_abbr": "home_team"})

    # Get away teams: rows where home_away == 'AWAY'
    away = game_logs[game_logs["home_away"] == "AWAY"][
        ["game_id", "team_abbr"]
    ].drop_duplicates(subset=["game_id"])
    away = away.rename(columns={"team_abbr": "away_team"})

    # Merge home and away
    schedule = home.merge(away, on="game_id", how="inner")
    schedule["status"] = "completed"

    # Sort by date
    schedule["game_date"] = pd.to_datetime(schedule["game_date"])
    schedule = schedule.sort_values("game_date")

    logger.info(f"Found {len(schedule)} historical games")
    return schedule[["game_id", "game_date", "home_team", "away_team", "season", "status"]]


def fetch_current_season_schedule() -> pd.DataFrame:
    """Fetch the current season schedule from the NBA CDN.

    The NBA CDN provides the full schedule including future games.
    We extract game details from the JSON response.

    Returns:
        DataFrame with scheduled games, or empty DataFrame if fetch fails.
    """
    logger.info("Fetching current season schedule from NBA CDN...")

    try:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Referer": "https://www.nba.com/",
        }
        response = requests.get(NBA_SCHEDULE_URL, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        logger.warning(f"Failed to fetch NBA schedule: {e}")
        logger.warning("Continuing with historical data only (no future games)")
        return pd.DataFrame()
    except ValueError as e:
        logger.warning(f"Failed to parse NBA schedule JSON: {e}")
        return pd.DataFrame()

    # Parse the JSON structure
    # Structure: leagueSchedule.gameDates[].games[]
    records = []
    league_schedule = data.get("leagueSchedule", {})
    game_dates = league_schedule.get("gameDates", [])

    for date_entry in game_dates:
        games = date_entry.get("games", [])
        for game in games:
            # Only include regular season games
            # Game status: 1 = scheduled, 2 = in progress, 3 = final
            game_status_id = game.get("gameStatus", 0)

            home_team = game.get("homeTeam", {})
            away_team = game.get("awayTeam", {})

            record = {
                "game_id": game.get("gameId", ""),
                "game_date": game.get("gameDateTimeUTC", "")[:10],  # Extract date part
                "home_team": home_team.get("teamTricode", ""),
                "away_team": away_team.get("teamTricode", ""),
                "season": league_schedule.get("seasonYear", ""),
                "status": "scheduled" if game_status_id == 1 else "completed",
            }
            records.append(record)

    if not records:
        logger.warning("No games found in NBA CDN response")
        return pd.DataFrame()

    schedule = pd.DataFrame(records)
    schedule["game_date"] = pd.to_datetime(schedule["game_date"])

    # Filter to only future/scheduled games (we already have historical from game logs)
    scheduled = schedule[schedule["status"] == "scheduled"]
    logger.info(f"Found {len(scheduled)} future scheduled games from CDN")

    return scheduled


def main():
    """Run the schedule collection pipeline."""
    logger.info("=" * 60)
    logger.info("Starting schedule collection")
    logger.info("=" * 60)

    # Load game logs
    game_logs_path = RAW_DIR / "player_game_logs.csv"
    if not game_logs_path.exists():
        raise FileNotFoundError(
            f"Game logs not found at {game_logs_path}. "
            "Run collect_player_stats.py first."
        )

    game_logs = pd.read_csv(game_logs_path)
    game_logs["game_date"] = pd.to_datetime(game_logs["game_date"])

    # Get historical schedule from game logs
    historical = derive_historical_schedule(game_logs)

    # Get future games from NBA CDN
    future = fetch_current_season_schedule()

    # Combine historical and future
    if not future.empty:
        # Format the season column to match our convention
        # CDN may use '2024-25' or '2024' — normalize if needed
        combined = pd.concat([historical, future], ignore_index=True)
        # Deduplicate in case CDN returns some already-completed games
        combined = combined.drop_duplicates(subset=["game_id"], keep="first")
    else:
        combined = historical

    combined = combined.sort_values("game_date").reset_index(drop=True)

    # Save
    combined.to_csv(OUTPUT_SCHEDULE, index=False)

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("SCHEDULE COLLECTION COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Total games: {len(combined)}")
    completed = len(combined[combined["status"] == "completed"])
    scheduled = len(combined[combined["status"] == "scheduled"])
    logger.info(f"  Completed: {completed}")
    logger.info(f"  Scheduled (upcoming): {scheduled}")
    logger.info(f"  Date range: {combined['game_date'].min()} to {combined['game_date'].max()}")

    if "season" in combined.columns:
        for season in sorted(combined["season"].unique()):
            count = len(combined[combined["season"] == season])
            logger.info(f"  Season {season}: {count} games")

    logger.info(f"\nOutput: {OUTPUT_SCHEDULE}")


if __name__ == "__main__":
    main()
