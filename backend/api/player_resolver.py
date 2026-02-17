"""Player name resolution for the chat endpoint.

Builds lookup indices from processed CSV data and provides fuzzy matching
to extract player references from natural language text. Surfaces ambiguous
matches rather than silently picking one — lets Claude disambiguate.
"""

import difflib
import re
from typing import Optional

from backend.api.data_access import data_store

# Common team name variants mapped to official abbreviations
TEAM_ALIASES = {
    "lakers": "LAL",
    "celtics": "BOS",
    "warriors": "GSW",
    "nets": "BKN",
    "knicks": "NYK",
    "heat": "MIA",
    "bucks": "MIL",
    "76ers": "PHI",
    "sixers": "PHI",
    "suns": "PHX",
    "nuggets": "DEN",
    "cavaliers": "CLE",
    "cavs": "CLE",
    "timberwolves": "MIN",
    "wolves": "MIN",
    "thunder": "OKC",
    "mavericks": "DAL",
    "mavs": "DAL",
    "clippers": "LAC",
    "kings": "SAC",
    "grizzlies": "MEM",
    "pelicans": "NOP",
    "hawks": "ATL",
    "bulls": "CHI",
    "raptors": "TOR",
    "pacers": "IND",
    "magic": "ORL",
    "hornets": "CHA",
    "pistons": "DET",
    "rockets": "HOU",
    "spurs": "SAS",
    "jazz": "UTA",
    "blazers": "POR",
    "trail blazers": "POR",
}


class PlayerResolver:
    """Resolves player names from natural language to player IDs."""

    def __init__(self):
        self._full_name_map: dict[str, tuple[int, str, str]] = {}  # norm_name -> (id, name, team)
        self._last_name_map: dict[str, list[tuple[int, str, str]]] = {}  # last -> [(id, name, team)]

    def build_index(self):
        """Build the name lookup indices from loaded data."""
        df = data_store._processed_df
        if df is None or df.empty:
            return

        # Get each player's most recent row for current team
        latest = df.sort_values("game_date").groupby("player_id").last().reset_index()

        full_map = {}
        last_map = {}

        for _, row in latest.iterrows():
            pid = int(row["player_id"])
            name = str(row["player_name"])
            team = str(row["team_abbr"])
            normalized = name.lower().strip()

            full_map[normalized] = (pid, name, team)

            # Index by last name
            parts = normalized.split()
            if parts:
                last = parts[-1]
                last_map.setdefault(last, []).append((pid, name, team))

        # Atomic swap
        self._full_name_map = full_map
        self._last_name_map = last_map

    def resolve_players(self, text: str) -> tuple[list[dict], bool]:
        """Extract player references from text.

        Returns (matches, ambiguous) where matches is a list of
        {player_id, player_name, team_abbr} dicts, and ambiguous is True
        if multiple candidates were found for an unclear reference.
        """
        text_lower = text.lower()
        found = []
        found_ids = set()
        ambiguous = False

        # Pass 1: exact full name matches
        for norm_name, (pid, name, team) in self._full_name_map.items():
            if norm_name in text_lower and pid not in found_ids:
                found.append(
                    {"player_id": pid, "player_name": name, "team_abbr": team}
                )
                found_ids.add(pid)

        if found:
            return (found, False)

        # Pass 2: last name matches
        words = set(re.findall(r"\b[a-z]+\b", text_lower))
        for word in words:
            if word in self._last_name_map:
                candidates = self._last_name_map[word]
                if len(candidates) == 1:
                    pid, name, team = candidates[0]
                    if pid not in found_ids:
                        found.append(
                            {"player_id": pid, "player_name": name, "team_abbr": team}
                        )
                        found_ids.add(pid)
                elif len(candidates) > 1:
                    # Multiple players share this last name — return all, flag ambiguous
                    ambiguous = True
                    for pid, name, team in candidates:
                        if pid not in found_ids:
                            found.append(
                                {"player_id": pid, "player_name": name, "team_abbr": team}
                            )
                            found_ids.add(pid)

        if found:
            return (found, ambiguous)

        # Pass 3: fuzzy matching as last resort — extract candidate
        # phrases (1-3 word N-grams) from the text and fuzzy-match each
        all_names = list(self._full_name_map.keys())
        words = text_lower.split()
        candidate_phrases = []
        for n in (2, 3, 1):  # Try 2-word, 3-word, then 1-word phrases
            for i in range(len(words) - n + 1):
                candidate_phrases.append(" ".join(words[i : i + n]))

        for phrase in candidate_phrases:
            matches = difflib.get_close_matches(
                phrase, all_names, n=2, cutoff=0.7
            )
            for match in matches:
                pid, name, team = self._full_name_map[match]
                if pid not in found_ids:
                    found.append(
                        {"player_id": pid, "player_name": name, "team_abbr": team}
                    )
                    found_ids.add(pid)

        if len(found) > 1:
            ambiguous = True

        return (found, ambiguous)

    def resolve_teams(self, text: str) -> list[str]:
        """Extract team abbreviations from text."""
        text_lower = text.lower()
        teams = []

        # Check 3-letter abbreviations
        from backend.api.data_access import VALID_TEAMS

        for abbr in VALID_TEAMS:
            if abbr.lower() in text_lower and abbr not in teams:
                teams.append(abbr)

        # Check common aliases
        for alias, abbr in TEAM_ALIASES.items():
            if alias in text_lower and abbr not in teams:
                teams.append(abbr)

        return teams


# Module-level singleton
player_resolver = PlayerResolver()
