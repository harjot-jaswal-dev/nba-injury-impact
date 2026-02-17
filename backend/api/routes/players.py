"""Player and team lookup endpoints.

Provides search, detail, and listing endpoints used by the frontend
for dropdowns, player cards, and the injury simulator player selector.
Data comes from the in-memory DataStore (processed CSV + rosters).
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.api.data_access import data_store
from backend.api.schemas import PlayerDetail, PlayerSummary, TeamInfo

router = APIRouter(prefix="/api", tags=["players"])


@router.get("/players", response_model=list[PlayerSummary])
def search_players(
    team: Optional[str] = Query(None, description="Filter by team abbreviation"),
    search: Optional[str] = Query(None, description="Search by player name"),
):
    """Search players by team and/or name substring."""
    results = data_store.search_players(team=team, search=search)
    return [PlayerSummary(**p) for p in results]


@router.get("/players/{player_id}", response_model=PlayerDetail)
def get_player(player_id: int):
    """Get detailed player info including season averages and last 5 games."""
    player = data_store.get_player_detail(player_id)
    if not player:
        raise HTTPException(404, f"Player {player_id} not found")
    return PlayerDetail(**player)


@router.get("/teams", response_model=list[TeamInfo])
def get_teams():
    """Get all 30 NBA teams with abbreviation, name, and roster count."""
    teams = data_store.get_all_teams()
    return [TeamInfo(**t) for t in teams]
