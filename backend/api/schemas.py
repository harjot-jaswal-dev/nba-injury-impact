"""Pydantic schemas for API request/response validation.

Defines the contract between the API and its consumers. All endpoints
use these models for automatic validation and Swagger documentation.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Player Schemas ──────────────────────────────────────────────


class PlayerSummary(BaseModel):
    """Compact player info for lists and search results."""

    player_id: int
    player_name: str
    team_abbr: str
    position: Optional[str] = None
    season_avg_pts: Optional[float] = None
    season_avg_ast: Optional[float] = None
    season_avg_reb: Optional[float] = None
    season_avg_minutes: Optional[float] = None


class PlayerDetail(BaseModel):
    """Full player profile with season averages and recent games."""

    player_id: int
    player_name: str
    team_abbr: str
    team_name: Optional[str] = None
    position: Optional[str] = None
    height: Optional[str] = None
    weight: Optional[str] = None
    age: Optional[float] = None
    experience: Optional[str] = None
    jersey_number: Optional[str] = None
    season_averages: dict = {}
    last_5_games: list[dict] = []


class TeamInfo(BaseModel):
    """Team summary for the /teams endpoint."""

    team_abbr: str
    team_name: Optional[str] = None
    team_id: Optional[int] = None
    player_count: int = 0


# ── Game Schemas ────────────────────────────────────────────────


class GameSummary(BaseModel):
    """Single game entry for the upcoming/recent games list."""

    game_id: int
    game_date: str
    home_team: str
    away_team: str
    status: str  # "completed" or "scheduled"
    season: Optional[str] = None


class UpcomingGamesResponse(BaseModel):
    """Response for GET /api/games/upcoming."""

    source: str  # "schedule" (real upcoming) or "recent_completed" (fallback)
    games: list[GameSummary]


# ── Prediction Schemas ──────────────────────────────────────────


class StatPredictions(BaseModel):
    """Predicted stat line — 8 core NBA stats."""

    pts: float
    ast: float
    reb: float
    stl: float
    blk: float
    fg_pct: float
    ft_pct: float
    minutes: float


class PlayerBaselinePrediction(BaseModel):
    """Baseline prediction for a single player (healthy team scenario)."""

    player_id: int
    player_name: str
    predictions: StatPredictions
    matchup_data: Optional[str] = None


class AbsentPlayer(BaseModel):
    """A player flagged as absent/injured."""

    player_id: int
    player_name: str


class InjuryContext(BaseModel):
    """The 17 injury-context features computed by the ML pipeline."""

    n_starters_out: int = 0
    starter_1_out: int = 0
    starter_2_out: int = 0
    starter_3_out: int = 0
    starter_4_out: int = 0
    starter_5_out: int = 0
    ball_handler_out: int = 0
    primary_scorer_out: int = 0
    primary_rebounder_out: int = 0
    primary_defender_out: int = 0
    sixth_man_out: int = 0
    n_rotation_players_out: int = 0
    total_pts_lost: float = 0.0
    total_ast_lost: float = 0.0
    total_reb_lost: float = 0.0
    total_minutes_lost: float = 0.0
    games_with_this_config: int = 0


class PlayerRipplePrediction(BaseModel):
    """Prediction for one player showing baseline vs injury-adjusted stats."""

    player_id: int
    player_name: str
    baseline: StatPredictions
    with_injuries: StatPredictions
    ripple_effect: StatPredictions  # with_injuries - baseline


class GamePredictionsResponse(BaseModel):
    """Response for GET /api/predictions/{game_id} — baseline predictions."""

    game_id: int
    game_date: str
    home_team: str
    away_team: str
    home_players: list[PlayerBaselinePrediction]
    away_players: list[PlayerBaselinePrediction]
    cached_at: Optional[datetime] = None


class RippleResponse(BaseModel):
    """Response for GET /api/predictions/{game_id}/ripple."""

    game_id: int
    team: str
    absent_players: list[AbsentPlayer]
    injury_context: InjuryContext
    player_predictions: list[PlayerRipplePrediction]
    absence_data_date: Optional[str] = None
    cached_at: Optional[datetime] = None


# ── Simulate Schemas ────────────────────────────────────────────


class SimulateRequest(BaseModel):
    """Request body for POST /api/simulate."""

    team: str = Field(..., description="Team abbreviation (e.g. 'LAL')")
    injured_player_ids: list[int] = Field(
        ..., description="Player IDs to simulate as injured"
    )
    opponent: str = Field(..., description="Opponent team abbreviation")
    home_or_away: str = Field("HOME", description="'HOME' or 'AWAY'")
    date: Optional[str] = Field(
        None, description="Date in YYYY-MM-DD format. Defaults to today."
    )


class SimulateResponse(BaseModel):
    """Response for POST /api/simulate."""

    team: str
    absent_players: list[AbsentPlayer]
    injury_context: InjuryContext
    player_predictions: list[PlayerRipplePrediction]


# ── Chat Schemas ────────────────────────────────────────────────


class PlayerReference(BaseModel):
    """A resolved player reference from chat message."""

    player_id: int
    player_name: str
    team_abbr: str


class ChatRequest(BaseModel):
    """Request body for POST /api/chat."""

    message: str = Field(..., min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    """Response for POST /api/chat."""

    response: str
    context_used: Optional[str] = None  # "prediction_data" | "general_stats" | "direct"
    players_referenced: list[PlayerReference] = []
    usage: Optional[dict] = None  # {used: int, limit: int, remaining: int}


# ── Auth Schemas ────────────────────────────────────────────────


class UserInfo(BaseModel):
    """Current authenticated user info."""

    id: int
    email: str
    name: Optional[str] = None
    picture: Optional[str] = None
    created_at: datetime


class AuthURL(BaseModel):
    """Google OAuth authorization URL."""

    auth_url: str


class ChatUsageInfo(BaseModel):
    """Daily chat usage stats."""

    used_today: int
    daily_limit: int
    remaining: int


class ChatExamplesResponse(BaseModel):
    """Response for GET /api/chat/examples."""

    examples: list[str]


# ── Error Schemas ───────────────────────────────────────────────


class ErrorResponse(BaseModel):
    """Standard error response."""

    detail: str
    status_code: int = 400


class RateLimitError(BaseModel):
    """429 rate limit exceeded response."""

    detail: str = "Daily chat limit exceeded"
    usage: ChatUsageInfo
