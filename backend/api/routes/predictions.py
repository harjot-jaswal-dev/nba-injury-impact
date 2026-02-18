"""Prediction and game endpoints.

Provides baseline predictions, injury-adjusted ripple predictions, and
injury simulation. Uses a cache-first strategy backed by the database
to avoid recomputing predictions on every request.

All route handlers are sync `def` (not `async def`) so FastAPI
automatically runs them in a threadpool, preventing the synchronous
ML prediction calls from blocking the event loop.
"""

import json
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.data_access import VALID_TEAMS, data_store
from backend.api.database import CachedPrediction
from backend.api.dependencies import get_db
from backend.api.schemas import (
    AbsentPlayer,
    GamePredictionsResponse,
    GameSummary,
    InjuryContext,
    PlayerBaselinePrediction,
    PlayerRipplePrediction,
    RippleResponse,
    SimulateRequest,
    SimulateResponse,
    StatPredictions,
    UpcomingGamesResponse,
)

# Import ML prediction functions (read-only dependency)
from backend.ml.predict import get_ripple_effect, predict_baseline

logger = logging.getLogger("predictions")
router = APIRouter(prefix="/api", tags=["predictions"])

# Cache TTL: predictions older than this are considered stale
CACHE_TTL_HOURS = 24


# ── Helper: Cache Layer ─────────────────────────────────────────


def _get_cached(db, game_id: int, pred_type: str, team: str = None,
                absent_ids: str = None) -> Optional[dict]:
    """Check for a fresh cached prediction. Returns parsed JSON or None."""
    query = db.query(CachedPrediction).filter(
        CachedPrediction.game_id == game_id,
        CachedPrediction.prediction_type == pred_type,
    )
    if team:
        query = query.filter(CachedPrediction.team == team)
    if absent_ids is not None:
        query = query.filter(CachedPrediction.absent_player_ids == absent_ids)

    cached = query.order_by(CachedPrediction.created_at.desc()).first()
    if cached is None:
        return None

    # Check freshness
    age = datetime.utcnow() - cached.created_at
    if age > timedelta(hours=CACHE_TTL_HOURS):
        return None

    try:
        result = json.loads(cached.data)
        result["cached_at"] = cached.created_at.isoformat()
        return result
    except (json.JSONDecodeError, TypeError):
        return None


def _store_cache(db, game_id: int, pred_type: str, data: dict,
                 team: str = None, absent_ids: str = None):
    """Store a prediction result in the cache."""
    entry = CachedPrediction(
        game_id=game_id,
        prediction_type=pred_type,
        team=team,
        absent_player_ids=absent_ids,
        data=json.dumps(data),
    )
    db.add(entry)
    db.commit()


# ── Endpoints ───────────────────────────────────────────────────


@router.get("/games/upcoming", response_model=UpcomingGamesResponse)
def get_upcoming_games(limit: int = Query(15, ge=1, le=50)):
    """List upcoming games, or most recent completed if no schedule data."""
    source, games = data_store.get_upcoming_games(limit)
    return UpcomingGamesResponse(
        source=source,
        games=[GameSummary(**g) for g in games],
    )


@router.get("/predictions/{game_id}", response_model=GamePredictionsResponse)
def get_game_predictions(game_id: int, db=Depends(get_db)):
    """Baseline predictions for all key players (15+ min avg) in a game.

    Uses cache-first strategy: returns cached predictions if fresh (<24h),
    otherwise computes live and stores in cache.
    """
    game_info = data_store.get_game_info(game_id)
    if not game_info:
        raise HTTPException(404, f"Game {game_id} not found")

    # Check cache
    cached = _get_cached(db, game_id, "baseline")
    if cached:
        return GamePredictionsResponse(**cached)

    # Cache miss — compute live
    home_team = game_info["home_team"]
    away_team = game_info["away_team"]
    key_players = data_store.get_key_players_for_game(
        game_id, home_team=home_team, away_team=away_team,
    )
    home_preds = []
    away_preds = []

    # Home team players: home_or_away="HOME", opponent=away_team
    for player in key_players.get("home_players", []):
        try:
            pred = predict_baseline(
                player_id=player["player_id"],
                opponent_team=away_team,
                home_or_away="HOME",
                date=game_info.get("game_date"),
            )
            home_preds.append(
                {
                    "player_id": pred["player_id"],
                    "player_name": pred["player_name"],
                    "predictions": pred["predictions"],
                    "matchup_data": pred.get("matchup_data"),
                }
            )
        except (ValueError, FileNotFoundError) as e:
            logger.debug(f"Skipping player {player['player_id']}: {e}")
            continue

    # Away team players: home_or_away="AWAY", opponent=home_team
    for player in key_players.get("away_players", []):
        try:
            pred = predict_baseline(
                player_id=player["player_id"],
                opponent_team=home_team,
                home_or_away="AWAY",
                date=game_info.get("game_date"),
            )
            away_preds.append(
                {
                    "player_id": pred["player_id"],
                    "player_name": pred["player_name"],
                    "predictions": pred["predictions"],
                    "matchup_data": pred.get("matchup_data"),
                }
            )
        except (ValueError, FileNotFoundError) as e:
            logger.debug(f"Skipping player {player['player_id']}: {e}")
            continue

    now = datetime.utcnow()
    result = {
        "game_id": game_id,
        "game_date": game_info["game_date"],
        "home_team": home_team,
        "away_team": away_team,
        "home_players": home_preds,
        "away_players": away_preds,
        "cached_at": now.isoformat(),
    }

    # Store in cache
    _store_cache(db, game_id, "baseline", result)

    return GamePredictionsResponse(**result)


@router.get("/predictions/{game_id}/ripple", response_model=RippleResponse)
def get_game_ripple(
    game_id: int,
    team: Optional[str] = Query(
        None, description="Team to analyze (defaults to home team)"
    ),
    absent_player_ids: Optional[str] = Query(
        None, description="Comma-separated player IDs to treat as absent"
    ),
    db=Depends(get_db),
):
    """Predictions with injury context, showing baseline vs adjusted deltas.

    Auto-detects absent players from absence data if not specified.
    Includes absence_data_date for freshness indicator.
    """
    game_info = data_store.get_game_info(game_id)
    if not game_info:
        raise HTTPException(404, f"Game {game_id} not found")

    # Determine which team to analyze
    analysis_team = team or game_info.get("home_team")
    if not analysis_team:
        raise HTTPException(400, "Could not determine team to analyze")

    opponent = (
        game_info["away_team"]
        if analysis_team == game_info["home_team"]
        else game_info["home_team"]
    )
    home_or_away = (
        "HOME" if analysis_team == game_info["home_team"] else "AWAY"
    )

    # Determine absent players
    if absent_player_ids:
        absent_ids = [int(x.strip()) for x in absent_player_ids.split(",")]
    else:
        absent_ids = data_store.get_recent_absences(
            analysis_team, game_info.get("game_date")
        )

    # Cache key includes sorted absent IDs
    sorted_absent = ",".join(str(x) for x in sorted(absent_ids))

    # Check cache
    cached = _get_cached(db, game_id, "ripple", team=analysis_team,
                         absent_ids=sorted_absent)
    if cached:
        return RippleResponse(**cached)

    # Compute live
    try:
        result = get_ripple_effect(
            team=analysis_team,
            absent_player_ids=absent_ids,
            opponent_team=opponent,
            home_or_away=home_or_away,
            date=game_info.get("game_date"),
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except FileNotFoundError as e:
        raise HTTPException(503, str(e))

    absence_date = data_store.get_absence_data_date(analysis_team)
    now = datetime.utcnow()

    response_data = {
        "game_id": game_id,
        "team": result["team"],
        "absent_players": result["absent_players"],
        "injury_context": result["injury_context"],
        "player_predictions": [
            {
                "player_id": p["player_id"],
                "player_name": p["player_name"],
                "baseline": p["baseline"],
                "with_injuries": p["with_injuries"],
                "ripple_effect": p["ripple_effect"],
            }
            for p in result["player_predictions"]
        ],
        "absence_data_date": absence_date,
        "cached_at": now.isoformat(),
    }

    # Store in cache
    _store_cache(db, game_id, "ripple", response_data,
                 team=analysis_team, absent_ids=sorted_absent)

    return RippleResponse(**response_data)


@router.post("/simulate", response_model=SimulateResponse)
def simulate_injuries(req: SimulateRequest):
    """Simulate the ripple effect of specified injuries.

    Always computes live (custom scenarios can't be pre-cached).
    Uses get_ripple_effect() which accepts explicit team + multiple absent
    players, matching the endpoint semantics exactly. simulate_injury()
    only handles a single player and auto-detects team, so it's less flexible.
    """
    if req.team.upper() not in VALID_TEAMS:
        raise HTTPException(400, f"Invalid team abbreviation: {req.team}")
    if not req.injured_player_ids:
        raise HTTPException(400, "At least one injured player ID is required")

    # Default date to today if not provided
    sim_date = req.date or date.today().isoformat()

    try:
        result = get_ripple_effect(
            team=req.team.upper(),
            absent_player_ids=req.injured_player_ids,
            opponent_team=req.opponent.upper(),
            home_or_away=req.home_or_away.upper(),
            date=sim_date,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except FileNotFoundError as e:
        raise HTTPException(503, str(e))

    return SimulateResponse(
        team=result["team"],
        absent_players=[AbsentPlayer(**p) for p in result["absent_players"]],
        injury_context=InjuryContext(**result["injury_context"]),
        player_predictions=[
            PlayerRipplePrediction(
                player_id=p["player_id"],
                player_name=p["player_name"],
                baseline=StatPredictions(**p["baseline"]),
                with_injuries=StatPredictions(**p["with_injuries"]),
                ripple_effect=StatPredictions(**p["ripple_effect"]),
            )
            for p in result["player_predictions"]
        ],
    )
