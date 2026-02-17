"""Centralized application settings loaded from environment variables."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
RAW_DIR = BACKEND_DIR / "data" / "raw"
PROCESSED_DIR = BACKEND_DIR / "data" / "processed"


class Settings:
    """All configuration sourced from environment variables with sensible defaults."""

    # Database — SQLite for local dev, PostgreSQL for production
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./nba_injury_impact.db")

    # Session signing
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-change-in-production")

    # Google OAuth
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI: str = os.getenv(
        "GOOGLE_REDIRECT_URI",
        "http://localhost:8000/api/auth/google/callback",
    )

    # Frontend URL — used for CORS origin and OAuth redirect destination
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")

    # Claude / Chat
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    CHAT_MODEL: str = "claude-sonnet-4-20250514"
    CHAT_MAX_TOKENS: int = 1024
    CHAT_DAILY_LIMIT: int = int(os.getenv("CHAT_DAILY_LIMIT", "10"))

    # Scheduler
    REFRESH_SCHEDULE_HOUR: int = int(os.getenv("REFRESH_SCHEDULE_HOUR", "6"))
    REFRESH_SCHEDULE_TIMEZONE: str = "US/Eastern"

    # Admin
    ADMIN_KEY: str = os.getenv("ADMIN_KEY", "")

    # Data file paths
    SCHEDULE_CSV: Path = RAW_DIR / "schedule.csv"
    ABSENCES_CSV: Path = RAW_DIR / "player_absences.csv"
    ROSTERS_CSV: Path = RAW_DIR / "rosters.csv"
    GAME_LOGS_CSV: Path = RAW_DIR / "player_game_logs.csv"
    PROCESSED_CSV: Path = PROCESSED_DIR / "processed_player_data.csv"


settings = Settings()
