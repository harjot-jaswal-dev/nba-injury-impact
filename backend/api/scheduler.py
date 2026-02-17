"""Daily data refresh scheduler using APScheduler.

Runs once daily (configurable, default 6 AM EST):
1. Refreshes schedule data via collect_schedules.py
2. Refreshes absence data via collect_injury_data.py
3. Reloads the in-memory DataStore
4. Pre-computes and caches predictions for upcoming games
"""

import json
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.api.config import settings

logger = logging.getLogger("scheduler")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def run_refresh_job() -> dict:
    """Execute the full daily refresh pipeline.

    Returns a dict describing the outcome of each step.
    """
    results = {}

    # Step 1: Refresh schedule
    results["schedule"] = _run_script("backend.scripts.collect_schedules", timeout=300)

    # Step 2: Refresh injury/absence data
    results["injuries"] = _run_script("backend.scripts.collect_injury_data", timeout=600)

    # Step 3: Reload in-memory data store (thread-safe atomic swap)
    try:
        from backend.api.data_access import data_store

        data_store.load_all()
        results["data_reload"] = "success"
    except Exception as e:
        results["data_reload"] = f"error: {e}"
        logger.error(f"Data reload failed: {e}")

    # Step 4: Pre-compute and cache predictions for upcoming games
    results["cache"] = _precompute_predictions()

    logger.info(f"Refresh completed: {results}")
    return results


def _run_script(module_name: str, timeout: int = 300) -> str:
    """Run a data collection script as a subprocess."""
    try:
        logger.info(f"Running {module_name}...")
        proc = subprocess.run(
            [sys.executable, "-m", module_name],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if proc.returncode == 0:
            return "success"
        else:
            msg = proc.stderr[:300] if proc.stderr else "unknown error"
            logger.warning(f"{module_name} failed: {msg}")
            return f"failed: {msg}"
    except subprocess.TimeoutExpired:
        logger.error(f"{module_name} timed out after {timeout}s")
        return f"timeout after {timeout}s"
    except Exception as e:
        logger.error(f"{module_name} error: {e}")
        return f"error: {e}"


def _precompute_predictions() -> str:
    """Pre-compute baseline predictions for all upcoming games and cache them."""
    try:
        from backend.api.data_access import data_store
        from backend.api.database import CachedPrediction, SessionLocal
        from backend.ml.predict import get_ripple_effect, predict_baseline

        source, games = data_store.get_upcoming_games(limit=30)
        if not games:
            return "no games to cache"

        db = SessionLocal()
        cached_count = 0
        try:
            for game in games:
                game_id = game["game_id"]
                game_date = game.get("game_date")
                home_team = game.get("home_team", "")
                away_team = game.get("away_team", "")

                key_players = data_store.get_key_players_for_game(game_id)
                home_preds = []
                away_preds = []

                # Baseline predictions for home team
                for player in key_players.get("home_players", []):
                    try:
                        pred = predict_baseline(
                            player_id=player["player_id"],
                            opponent_team=away_team,
                            home_or_away="HOME",
                            date=game_date,
                        )
                        home_preds.append({
                            "player_id": pred["player_id"],
                            "player_name": pred["player_name"],
                            "predictions": pred["predictions"],
                            "matchup_data": pred.get("matchup_data"),
                        })
                    except (ValueError, FileNotFoundError):
                        continue

                # Baseline predictions for away team
                for player in key_players.get("away_players", []):
                    try:
                        pred = predict_baseline(
                            player_id=player["player_id"],
                            opponent_team=home_team,
                            home_or_away="AWAY",
                            date=game_date,
                        )
                        away_preds.append({
                            "player_id": pred["player_id"],
                            "player_name": pred["player_name"],
                            "predictions": pred["predictions"],
                            "matchup_data": pred.get("matchup_data"),
                        })
                    except (ValueError, FileNotFoundError):
                        continue

                result = {
                    "game_id": game_id,
                    "game_date": game_date,
                    "home_team": home_team,
                    "away_team": away_team,
                    "home_players": home_preds,
                    "away_players": away_preds,
                    "cached_at": datetime.utcnow().isoformat(),
                }

                entry = CachedPrediction(
                    game_id=game_id,
                    prediction_type="baseline",
                    data=json.dumps(result),
                )
                db.add(entry)
                cached_count += 1

                # Also pre-compute ripple with auto-detected absences
                for team_abbr, opponent, side in [
                    (home_team, away_team, "HOME"),
                    (away_team, home_team, "AWAY"),
                ]:
                    absent_ids = data_store.get_recent_absences(team_abbr, game_date)
                    if absent_ids:
                        try:
                            ripple = get_ripple_effect(
                                team=team_abbr,
                                absent_player_ids=absent_ids,
                                opponent_team=opponent,
                                home_or_away=side,
                                date=game_date,
                            )
                            absence_date = data_store.get_absence_data_date(team_abbr)
                            ripple_data = {
                                "game_id": game_id,
                                "team": ripple["team"],
                                "absent_players": ripple["absent_players"],
                                "injury_context": ripple["injury_context"],
                                "player_predictions": [
                                    {
                                        "player_id": p["player_id"],
                                        "player_name": p["player_name"],
                                        "baseline": p["baseline"],
                                        "with_injuries": p["with_injuries"],
                                        "ripple_effect": p["ripple_effect"],
                                    }
                                    for p in ripple["player_predictions"]
                                ],
                                "absence_data_date": absence_date,
                                "cached_at": datetime.utcnow().isoformat(),
                            }
                            sorted_absent = ",".join(str(x) for x in sorted(absent_ids))
                            entry = CachedPrediction(
                                game_id=game_id,
                                prediction_type="ripple",
                                team=team_abbr,
                                absent_player_ids=sorted_absent,
                                data=json.dumps(ripple_data),
                            )
                            db.add(entry)
                        except (ValueError, FileNotFoundError) as e:
                            logger.debug(f"Skipping ripple cache for {team_abbr}: {e}")

            db.commit()
        finally:
            db.close()

        return f"cached {cached_count} games"

    except Exception as e:
        logger.error(f"Pre-compute caching failed: {e}")
        return f"error: {e}"


def create_scheduler() -> BackgroundScheduler:
    """Create and configure the background scheduler."""
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        run_refresh_job,
        trigger=CronTrigger(
            hour=settings.REFRESH_SCHEDULE_HOUR,
            minute=0,
            timezone=settings.REFRESH_SCHEDULE_TIMEZONE,
        ),
        id="daily_refresh",
        name="Daily data refresh (schedule + injuries + cache)",
        replace_existing=True,
    )
    return scheduler
