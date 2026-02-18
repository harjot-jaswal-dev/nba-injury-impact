"""Read-only data access layer for CSV-based data.

Loads processed player data, rosters, absences, and schedule data into
memory at startup. Provides query methods used by route handlers.

THREAD SAFETY: The load_all() method builds new DataFrames in local
variables first, then swaps references via single-line assignments.
Python's GIL makes reference assignment atomic, so concurrent readers
always see either the old or new DataFrame — never a partial state.
"""

import logging
from typing import Optional

import pandas as pd

from backend.api.config import settings

logger = logging.getLogger("data_access")

VALID_TEAMS = [
    "ATL", "BKN", "BOS", "CHA", "CHI", "CLE", "DAL", "DEN", "DET", "GSW",
    "HOU", "IND", "LAC", "LAL", "MEM", "MIA", "MIL", "MIN", "NOP", "NYK",
    "OKC", "ORL", "PHI", "PHX", "POR", "SAC", "SAS", "TOR", "UTA", "WAS",
]


class DataStore:
    """In-memory store for CSV data. Supports thread-safe reload."""

    def __init__(self):
        self._processed_df: Optional[pd.DataFrame] = None
        self._rosters_df: Optional[pd.DataFrame] = None
        self._absences_df: Optional[pd.DataFrame] = None
        self._schedule_df: Optional[pd.DataFrame] = None

    def load_all(self):
        """Load all data files into memory.

        Builds new DataFrames in local vars first, then swaps references
        atomically (Python GIL guarantees single-line assignment is atomic).
        Concurrent readers see either old or new data, never partial.
        """
        # Build in locals first
        processed = self._load_csv(
            settings.PROCESSED_CSV, "processed data", parse_dates=["game_date"]
        )
        rosters = self._load_csv(settings.ROSTERS_CSV, "rosters")
        absences = self._load_csv(
            settings.ABSENCES_CSV, "absences", parse_dates=["game_date"]
        )
        schedule = self._load_csv(
            settings.SCHEDULE_CSV, "schedule", parse_dates=["game_date"],
            required=False,
        )

        # Atomic reference swaps — readers see old or new, never partial
        self._processed_df = processed
        self._rosters_df = rosters
        self._absences_df = absences
        self._schedule_df = schedule

        row_count = len(processed) if processed is not None else 0
        logger.info(f"Data loaded: {row_count} processed rows")

    @staticmethod
    def _load_csv(path, label, parse_dates=None, required=True):
        """Load a CSV file, returning None if missing and not required."""
        if not path.exists():
            if required:
                logger.warning(f"{label} CSV not found at {path}")
            return None
        try:
            df = pd.read_csv(path, parse_dates=parse_dates)
            logger.info(f"Loaded {label}: {len(df)} rows")
            return df
        except Exception as e:
            logger.error(f"Failed to load {label}: {e}")
            return None

    # ── Game Queries ────────────────────────────────────────────

    def get_upcoming_games(self, limit: int = 15) -> tuple[str, list[dict]]:
        """Return upcoming games from schedule, or recent completed as fallback.

        Returns (source, games_list) where source is "schedule" or
        "recent_completed" so the frontend knows if data is stale.
        """
        # Try schedule.csv first
        if self._schedule_df is not None and not self._schedule_df.empty:
            scheduled = self._schedule_df[self._schedule_df["status"] == "scheduled"]
            # Filter out placeholder games (play-in/finals) with no teams assigned
            scheduled = scheduled.dropna(subset=["home_team", "away_team"])
            if not scheduled.empty:
                upcoming = scheduled.sort_values("game_date").head(limit)
                games = [
                    {
                        "game_id": int(row["game_id"]),
                        "game_date": str(row["game_date"].date())
                        if hasattr(row["game_date"], "date")
                        else str(row["game_date"]),
                        "home_team": row["home_team"],
                        "away_team": row["away_team"],
                        "status": "scheduled",
                        "season": row.get("season", ""),
                    }
                    for _, row in upcoming.iterrows()
                ]
                return ("schedule", games)

        # Fallback: derive recent completed games from processed data
        if self._processed_df is not None and not self._processed_df.empty:
            df = self._processed_df
            # Get unique game_ids with their dates
            game_dates = (
                df.groupby("game_id")
                .agg({"game_date": "first"})
                .sort_values("game_date", ascending=False)
                .head(limit)
            )

            games = []
            for game_id, gd_row in game_dates.iterrows():
                game_rows = df[df["game_id"] == game_id]
                home_rows = game_rows[game_rows["home_away"] == "HOME"]
                away_rows = game_rows[game_rows["home_away"] == "AWAY"]
                home_team = (
                    home_rows["team_abbr"].iloc[0] if not home_rows.empty else "UNK"
                )
                away_team = (
                    away_rows["team_abbr"].iloc[0] if not away_rows.empty else "UNK"
                )
                games.append(
                    {
                        "game_id": int(game_id),
                        "game_date": str(gd_row["game_date"].date())
                        if hasattr(gd_row["game_date"], "date")
                        else str(gd_row["game_date"]),
                        "home_team": home_team,
                        "away_team": away_team,
                        "status": "completed",
                        "season": game_rows["season"].iloc[0]
                        if "season" in game_rows.columns
                        else "",
                    }
                )
            return ("recent_completed", games)

        return ("empty", [])

    def get_game_info(self, game_id: int) -> Optional[dict]:
        """Get game metadata by game_id from schedule or processed data."""
        # Try schedule first
        if self._schedule_df is not None and not self._schedule_df.empty:
            match = self._schedule_df[self._schedule_df["game_id"] == game_id]
            if not match.empty:
                row = match.iloc[0]
                home = row["home_team"]
                away = row["away_team"]
                # Skip placeholder games (play-in/finals) with no teams
                if pd.isna(home) or pd.isna(away):
                    return None
                return {
                    "game_id": int(row["game_id"]),
                    "game_date": str(row["game_date"].date())
                    if hasattr(row["game_date"], "date")
                    else str(row["game_date"]),
                    "home_team": home,
                    "away_team": away,
                    "status": row.get("status", "completed"),
                }

        # Fall back to processed data
        if self._processed_df is None or self._processed_df.empty:
            return None
        df = self._processed_df
        game_rows = df[df["game_id"] == game_id]
        if game_rows.empty:
            return None
        home_rows = game_rows[game_rows["home_away"] == "HOME"]
        away_rows = game_rows[game_rows["home_away"] == "AWAY"]
        sample = game_rows.iloc[0]
        return {
            "game_id": int(game_id),
            "game_date": str(sample["game_date"].date())
            if hasattr(sample["game_date"], "date")
            else str(sample["game_date"]),
            "home_team": home_rows["team_abbr"].iloc[0]
            if not home_rows.empty
            else "",
            "away_team": away_rows["team_abbr"].iloc[0]
            if not away_rows.empty
            else "",
            "status": "completed",
        }

    def get_key_players_for_game(
        self, game_id: int, min_minutes: float = 15.0,
        home_team: str = None, away_team: str = None,
    ) -> dict:
        """Get key players (avg 15+ min) for both teams in a game.

        For completed games, looks up players from processed data by game_id.
        For future/scheduled games (not in processed data), uses home_team
        and away_team hints to find each team's latest key players.

        Returns dict with home_team, away_team, home_players, away_players.
        Each player dict includes player_id, player_name, team_abbr.
        """
        result = {
            "home_team": home_team,
            "away_team": away_team,
            "home_players": [],
            "away_players": [],
        }
        if self._processed_df is None or self._processed_df.empty:
            return result

        df = self._processed_df
        game_rows = df[df["game_id"] == game_id]

        if not game_rows.empty:
            # Completed game — look up from processed data
            game_date = game_rows.iloc[0]["game_date"]

            for side in ("HOME", "AWAY"):
                side_rows = game_rows[game_rows["home_away"] == side]
                if side_rows.empty:
                    continue
                team_abbr = side_rows.iloc[0]["team_abbr"]
                key = "home" if side == "HOME" else "away"
                result[f"{key}_team"] = team_abbr

                # Find all players on this team up to the game date
                team_all = df[
                    (df["team_abbr"] == team_abbr)
                    & (df["game_date"] <= game_date)
                ]
                # Get the latest row per player to check season_avg_minutes
                latest_per_player = (
                    team_all.sort_values("game_date")
                    .groupby("player_id")
                    .last()
                )
                key_players = latest_per_player[
                    latest_per_player["season_avg_minutes"] >= min_minutes
                ]
                result[f"{key}_players"] = [
                    {
                        "player_id": int(pid),
                        "player_name": row["player_name"],
                        "team_abbr": team_abbr,
                    }
                    for pid, row in key_players.iterrows()
                ]
        elif home_team and away_team:
            # Future game — use team hints to find latest key players
            for key, team_abbr in [("home", home_team), ("away", away_team)]:
                team_all = df[df["team_abbr"] == team_abbr]
                if team_all.empty:
                    continue
                latest_per_player = (
                    team_all.sort_values("game_date")
                    .groupby("player_id")
                    .last()
                )
                key_players = latest_per_player[
                    latest_per_player["season_avg_minutes"] >= min_minutes
                ]
                result[f"{key}_players"] = [
                    {
                        "player_id": int(pid),
                        "player_name": row["player_name"],
                        "team_abbr": team_abbr,
                    }
                    for pid, row in key_players.iterrows()
                ]

        return result

    # ── Absence Queries ─────────────────────────────────────────

    def get_recent_absences(
        self, team_abbr: str, near_date: str = None
    ) -> list[int]:
        """Get player_ids who were recently absent for a team.

        Looks at the most recent game date in the absences data for that team.
        """
        if self._absences_df is None or self._absences_df.empty:
            return []
        team_abs = self._absences_df[self._absences_df["team_abbr"] == team_abbr]
        if team_abs.empty:
            return []
        if near_date:
            team_abs = team_abs[
                team_abs["game_date"] <= pd.to_datetime(near_date)
            ]
        if team_abs.empty:
            return []
        latest_date = team_abs["game_date"].max()
        recent = team_abs[team_abs["game_date"] == latest_date]
        return [int(pid) for pid in recent["player_id"].unique()]

    def get_absence_data_date(self, team_abbr: str) -> Optional[str]:
        """Return the date of the most recent absence record for a team.

        Used to show freshness indicator: 'Injury data as of: YYYY-MM-DD'.
        """
        if self._absences_df is None or self._absences_df.empty:
            return None
        team_abs = self._absences_df[self._absences_df["team_abbr"] == team_abbr]
        if team_abs.empty:
            return None
        latest = team_abs["game_date"].max()
        return str(latest.date()) if hasattr(latest, "date") else str(latest)

    # ── Player Queries ──────────────────────────────────────────

    def search_players(
        self, team: str = None, search: str = None
    ) -> list[dict]:
        """Search players by team and/or name substring.

        Returns list of dicts with player summary info.
        """
        if self._processed_df is None or self._processed_df.empty:
            return []

        df = self._processed_df
        # Get the latest row per player (most recent season data)
        latest = df.sort_values("game_date").groupby("player_id").last().reset_index()

        if team:
            latest = latest[latest["team_abbr"] == team.upper()]
        if search:
            mask = latest["player_name"].str.contains(search, case=False, na=False)
            latest = latest[mask]

        results = []
        for _, row in latest.head(100).iterrows():  # cap at 100 results
            results.append(
                {
                    "player_id": int(row["player_id"]),
                    "player_name": row["player_name"],
                    "team_abbr": row["team_abbr"],
                    "position": _safe_val(row.get("position")),
                    "season_avg_pts": _safe_float(row.get("season_avg_pts")),
                    "season_avg_ast": _safe_float(row.get("season_avg_ast")),
                    "season_avg_reb": _safe_float(row.get("season_avg_reb")),
                    "season_avg_minutes": _safe_float(
                        row.get("season_avg_minutes")
                    ),
                }
            )
        return results

    def get_player_detail(self, player_id: int) -> Optional[dict]:
        """Get detailed player info combining processed + roster data."""
        if self._processed_df is None or self._processed_df.empty:
            return None

        df = self._processed_df
        player_df = df[df["player_id"] == player_id]
        if player_df.empty:
            return None

        latest = player_df.sort_values("game_date").iloc[-1]

        # Season averages from the latest row
        season_averages = {
            "pts": _safe_float(latest.get("season_avg_pts")),
            "ast": _safe_float(latest.get("season_avg_ast")),
            "reb": _safe_float(latest.get("season_avg_reb")),
            "stl": _safe_float(latest.get("season_avg_stl")),
            "blk": _safe_float(latest.get("season_avg_blk")),
            "fg_pct": _safe_float(latest.get("season_avg_fg_pct")),
            "ft_pct": _safe_float(latest.get("season_avg_ft_pct")),
            "minutes": _safe_float(latest.get("season_avg_minutes")),
        }

        # Last 5 games
        last_5 = player_df.sort_values("game_date").tail(5)
        last_5_games = [
            {
                "game_date": str(row["game_date"].date())
                if hasattr(row["game_date"], "date")
                else str(row["game_date"]),
                "opponent": row.get("opponent", ""),
                "pts": _safe_float(row.get("pts")),
                "ast": _safe_float(row.get("ast")),
                "reb": _safe_float(row.get("reb")),
                "minutes": _safe_float(row.get("minutes")),
                "fg_pct": _safe_float(row.get("fg_pct")),
            }
            for _, row in last_5.iterrows()
        ]

        result = {
            "player_id": int(player_id),
            "player_name": latest["player_name"],
            "team_abbr": latest["team_abbr"],
            "position": _safe_val(latest.get("position")),
            "age": _safe_float(latest.get("age")),
            "experience": _safe_val(latest.get("experience")),
            "season_averages": season_averages,
            "last_5_games": last_5_games,
        }

        # Enrich with roster data if available
        if self._rosters_df is not None and not self._rosters_df.empty:
            roster_row = self._rosters_df[
                self._rosters_df["player_id"] == player_id
            ]
            if not roster_row.empty:
                if "season" in roster_row.columns:
                    r = roster_row.sort_values("season").iloc[-1]
                else:
                    r = roster_row.iloc[-1]
                result["team_name"] = _safe_val(r.get("team_name"))
                result["height"] = _safe_val(r.get("height"))
                result["weight"] = _safe_val(r.get("weight"))
                result["jersey_number"] = _safe_val(r.get("jersey_number"))

        return result

    def get_all_teams(self) -> list[dict]:
        """Return all 30 NBA teams with basic info."""
        if self._processed_df is None or self._processed_df.empty:
            return [{"team_abbr": t, "player_count": 0} for t in VALID_TEAMS]

        df = self._processed_df
        # Get unique players per team from the latest season
        latest_season = df["season"].iloc[-1] if "season" in df.columns else None
        season_df = df[df["season"] == latest_season] if latest_season else df
        team_counts = (
            season_df.groupby("team_abbr")["player_id"].nunique().to_dict()
        )

        # Get team names from rosters if available
        team_names = {}
        if self._rosters_df is not None and not self._rosters_df.empty:
            name_map = (
                self._rosters_df.groupby("team_abbr")["team_name"]
                .first()
                .to_dict()
            )
            team_names = name_map

        # Get team_ids from processed data
        team_ids = {}
        if "team_id" in df.columns:
            id_map = df.groupby("team_abbr")["team_id"].first().to_dict()
            team_ids = {k: int(v) for k, v in id_map.items()}

        return [
            {
                "team_abbr": t,
                "team_name": team_names.get(t),
                "team_id": team_ids.get(t),
                "player_count": team_counts.get(t, 0),
            }
            for t in VALID_TEAMS
        ]

    def get_player_season_averages(self, player_id: int) -> Optional[dict]:
        """Get a player's latest season averages."""
        if self._processed_df is None or self._processed_df.empty:
            return None
        player_df = self._processed_df[
            self._processed_df["player_id"] == player_id
        ]
        if player_df.empty:
            return None
        latest = player_df.sort_values("game_date").iloc[-1]
        return {
            "pts": _safe_float(latest.get("season_avg_pts")),
            "ast": _safe_float(latest.get("season_avg_ast")),
            "reb": _safe_float(latest.get("season_avg_reb")),
            "stl": _safe_float(latest.get("season_avg_stl")),
            "blk": _safe_float(latest.get("season_avg_blk")),
            "fg_pct": _safe_float(latest.get("season_avg_fg_pct")),
            "ft_pct": _safe_float(latest.get("season_avg_ft_pct")),
            "minutes": _safe_float(latest.get("season_avg_minutes")),
        }


def _safe_float(val) -> Optional[float]:
    """Convert to float, returning None for NaN/None."""
    if val is None:
        return None
    try:
        f = float(val)
        return None if pd.isna(f) else round(f, 1)
    except (ValueError, TypeError):
        return None


def _safe_val(val):
    """Return None for NaN/None, otherwise convert to string."""
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except (ValueError, TypeError):
        pass
    return str(val)


# Module-level singleton
data_store = DataStore()
