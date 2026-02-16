"""
Derive player absence/injury data from game logs and rosters.

Instead of relying on an external injury API, this script identifies
player absences by comparing the team roster to game participants.
If a rostered player doesn't appear in the game log for a game their
team played, they were absent (injured, rested, suspended, etc.).

This approach is reliable, requires no external API calls, and naturally
captures all types of absences.

Prerequisites:
    Run collect_player_stats.py first to generate:
    - backend/data/raw/player_game_logs.csv
    - backend/data/raw/rosters.csv

Output:
    backend/data/raw/player_absences.csv  (~60,000 rows)
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from backend.scripts.utils import setup_logging, RAW_DIR

OUTPUT_ABSENCES = str(RAW_DIR / "player_absences.csv")

logger = setup_logging("collect_injury_data")


def load_raw_data() -> tuple:
    """Load game logs and rosters from raw CSV files.

    Returns:
        Tuple of (game_logs DataFrame, rosters DataFrame).

    Raises:
        FileNotFoundError: If required input files don't exist.
    """
    game_logs_path = RAW_DIR / "player_game_logs.csv"
    rosters_path = RAW_DIR / "rosters.csv"

    if not game_logs_path.exists():
        raise FileNotFoundError(
            f"Game logs not found at {game_logs_path}. "
            "Run collect_player_stats.py first."
        )
    if not rosters_path.exists():
        raise FileNotFoundError(
            f"Rosters not found at {rosters_path}. "
            "Run collect_player_stats.py first."
        )

    game_logs = pd.read_csv(game_logs_path)
    rosters = pd.read_csv(rosters_path)

    # Ensure game_date is datetime
    game_logs["game_date"] = pd.to_datetime(game_logs["game_date"])

    # Normalize season format: roster uses starting year (2022) while
    # game logs use "2022-23" format. Convert roster to match game logs.
    def normalize_season(s):
        s_str = str(s).strip()
        if "-" in s_str:
            return s_str  # Already in "2022-23" format
        # Convert "2022" -> "2022-23"
        try:
            year = int(s_str)
            next_year = str(year + 1)[-2:]  # "23"
            return f"{year}-{next_year}"
        except ValueError:
            return s_str

    rosters["season"] = rosters["season"].apply(normalize_season)
    logger.info(f"Roster seasons after normalization: {sorted(rosters['season'].unique())}")

    logger.info(f"Loaded {len(game_logs)} game log rows, {len(rosters)} roster rows")
    return game_logs, rosters


def get_team_games(game_logs: pd.DataFrame, team_id: int, season: str) -> pd.DataFrame:
    """Get all unique games played by a specific team in a season.

    Args:
        game_logs: Full game logs DataFrame.
        team_id: NBA team ID.
        season: Season string (e.g., '2022-23').

    Returns:
        DataFrame with unique game_id and game_date pairs for this team-season.
    """
    mask = (game_logs["team_id"] == team_id) & (game_logs["season"] == season)
    team_games = game_logs.loc[mask, ["game_id", "game_date"]].drop_duplicates()
    return team_games


def derive_absences(game_logs: pd.DataFrame, rosters: pd.DataFrame) -> pd.DataFrame:
    """Identify player absences by comparing rosters to game participants.

    For each team-season, compares the full roster against who actually
    played in each game. Any rostered player not in the game log for a
    game their team played is marked as absent.

    Args:
        game_logs: Full game logs DataFrame.
        rosters: Full rosters DataFrame.

    Returns:
        DataFrame of all player absences.
    """
    absence_records = []
    seasons = rosters["season"].unique()

    # Pre-build a lookup: (game_id, team_id) -> set of player_ids who played
    logger.info("Building game participation lookup...")
    played_lookup = (
        game_logs.groupby(["game_id", "team_id"])["player_id"]
        .apply(set)
        .to_dict()
    )

    # Build roster name lookup: player_id -> player_name
    name_lookup = dict(zip(rosters["player_id"], rosters["player_name"]))

    # Build team abbr lookup from rosters
    team_abbr_lookup = dict(zip(rosters["team_id"], rosters["team_abbr"]))

    for season in sorted(seasons):
        season_rosters = rosters[rosters["season"] == season]
        team_ids = season_rosters["team_id"].unique()

        for team_id in team_ids:
            team_abbr = team_abbr_lookup.get(team_id, "???")

            # Get all players on this team's roster for this season
            roster_mask = (
                (season_rosters["team_id"] == team_id)
            )
            roster_players = set(season_rosters.loc[roster_mask, "player_id"])

            # Get all games this team played
            team_games = get_team_games(game_logs, team_id, season)

            team_absences = 0
            for _, game_row in team_games.iterrows():
                game_id = game_row["game_id"]
                game_date = game_row["game_date"]

                # Who played in this game for this team?
                played_players = played_lookup.get((game_id, team_id), set())

                # Who was absent?
                absent_players = roster_players - played_players

                for player_id in absent_players:
                    absence_records.append({
                        "player_id": player_id,
                        "player_name": name_lookup.get(player_id, "Unknown"),
                        "team_id": team_id,
                        "team_abbr": team_abbr,
                        "game_id": game_id,
                        "game_date": game_date,
                        "season": season,
                        "status": "OUT",
                    })
                    team_absences += 1

            logger.info(
                f"Processed {team_abbr} {season}: "
                f"{team_absences} absences across {len(team_games)} games"
            )

    absences = pd.DataFrame(absence_records)
    logger.info(f"Total raw absences: {len(absences)}")
    return absences


def filter_trade_absences(absences: pd.DataFrame, game_logs: pd.DataFrame) -> pd.DataFrame:
    """Remove false absences caused by mid-season trades.

    A player traded from Team A to Team B mid-season appears on both
    rosters. Without filtering, they'd show as "absent" from Team B
    for all games before the trade (and vice versa).

    We define a player's tenure on a team by the date range of their
    game log entries, with a 30-day buffer at the end for late-season
    injuries.

    Players with zero game log entries for a team-season (e.g., injured
    all season) have their absences retained.

    Args:
        absences: Raw absences DataFrame.
        game_logs: Full game logs DataFrame.

    Returns:
        Filtered absences DataFrame with trade artifacts removed.
    """
    if absences.empty:
        return absences

    logger.info("Filtering trade-related false absences...")
    original_count = len(absences)

    # Compute each player's date range per team-season from game logs
    tenure = (
        game_logs.groupby(["player_id", "team_id", "season"])["game_date"]
        .agg(["min", "max"])
        .reset_index()
        .rename(columns={"min": "first_game", "max": "last_game"})
    )

    # Add 30-day buffer to last_game for end-of-season injury coverage
    tenure["last_game_buffered"] = tenure["last_game"] + pd.Timedelta(days=30)

    # Merge tenure info onto absences
    absences = absences.merge(
        tenure,
        on=["player_id", "team_id", "season"],
        how="left",
    )

    # Keep absences where:
    # 1. Player has no game log entries (first_game is NaN) — they were
    #    on the roster but never played (injured all season, two-way, etc.)
    # 2. The absence date falls within the player's tenure on that team
    absences["game_date"] = pd.to_datetime(absences["game_date"])
    keep_mask = (
        absences["first_game"].isna()  # No game log entries: keep all absences
        | (
            (absences["game_date"] >= absences["first_game"])
            & (absences["game_date"] <= absences["last_game_buffered"])
        )
    )
    filtered = absences[keep_mask].copy()

    # Drop the tenure columns (no longer needed)
    filtered = filtered.drop(columns=["first_game", "last_game", "last_game_buffered"])

    removed = original_count - len(filtered)
    logger.info(f"Removed {removed} trade-related false absences ({len(filtered)} remaining)")
    return filtered


def add_absence_context(absences: pd.DataFrame) -> pd.DataFrame:
    """Add streak and cumulative absence counts.

    For each absence, computes:
    - games_missed_streak: Consecutive games missed ending at this game
    - season_games_missed: Total games missed this season up to this date

    Args:
        absences: Filtered absences DataFrame.

    Returns:
        Absences DataFrame enriched with context columns.
    """
    if absences.empty:
        return absences

    logger.info("Computing absence streaks and cumulative counts...")

    # Sort by player, team, date for streak calculation
    absences = absences.sort_values(["player_id", "team_id", "season", "game_date"])

    # Cumulative games missed this season (simple rank within group)
    absences["season_games_missed"] = (
        absences.groupby(["player_id", "team_id", "season"]).cumcount() + 1
    )

    # Games missed streak: count consecutive absences
    # We need to know the team's game schedule to determine consecutive games.
    # A simpler approach: within each (player, team, season), if the previous
    # absence was the immediately preceding team game, increment the streak.
    # Since absences are already ordered and only contain games the team played,
    # consecutive rows for the same player-team-season represent consecutive
    # missed games.
    streaks = []
    prev_key = None
    streak = 0

    for _, row in absences.iterrows():
        key = (row["player_id"], row["team_id"], row["season"])
        if key == prev_key:
            streak += 1
        else:
            streak = 1
            prev_key = key
        streaks.append(streak)

    absences["games_missed_streak"] = streaks

    return absences


def main():
    """Run the absence derivation pipeline."""
    logger.info("=" * 60)
    logger.info("Starting player absence derivation")
    logger.info("=" * 60)

    # Load raw data
    game_logs, rosters = load_raw_data()

    # Derive raw absences
    absences = derive_absences(game_logs, rosters)

    # Filter out trade artifacts
    absences = filter_trade_absences(absences, game_logs)

    # Add streak and cumulative context
    absences = add_absence_context(absences)

    # Save output
    absences.to_csv(OUTPUT_ABSENCES, index=False)

    # Print summary
    logger.info("\n" + "=" * 60)
    logger.info("ABSENCE DERIVATION COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Total absences: {len(absences)}")

    if absences.empty:
        logger.warning("No absences detected! Check season format matching.")
        return

    logger.info(f"Unique players affected: {absences['player_id'].nunique()}")

    if not absences.empty:
        avg_per_team_season = absences.groupby(["team_abbr", "season"]).size().mean()
        logger.info(f"Average absences per team-season: {avg_per_team_season:.0f}")

        # Top 10 most absent players
        top_absent = (
            absences.groupby(["player_name", "player_id"])
            .size()
            .sort_values(ascending=False)
            .head(10)
        )
        logger.info("\nTop 10 players by total games missed:")
        for (name, _), count in top_absent.items():
            logger.info(f"  {name}: {count} games")

    logger.info(f"\nOutput: {OUTPUT_ABSENCES}")


if __name__ == "__main__":
    main()
