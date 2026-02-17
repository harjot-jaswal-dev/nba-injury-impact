"""Database engine, session management, and ORM models.

Uses SQLAlchemy with SQLite for local development and PostgreSQL for
production. The DATABASE_URL environment variable controls which backend.
Tables are created automatically on first startup via init_db().
"""

from datetime import date as date_type, datetime

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker

from backend.api.config import settings

# SQLite needs check_same_thread=False for FastAPI's threaded request handling
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ── ORM Models ──────────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=True)
    picture = Column(String(500), nullable=True)
    google_id = Column(String(255), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Session(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_token = Column(String(255), unique=True, nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)


class ChatUsage(Base):
    __tablename__ = "chat_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    usage_date = Column(Date, nullable=False, default=date_type.today)
    question_count = Column(Integer, default=0)


class ChatMessage(Base):
    """Stores recent chat messages for lightweight conversation history.

    Each user keeps at most 6 rows (3 exchanges). Pruned after each chat call.
    """

    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    role = Column(String(20), nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class CachedPrediction(Base):
    __tablename__ = "cached_predictions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(Integer, nullable=False, index=True)
    prediction_type = Column(String(50), nullable=False)  # "baseline" or "ripple"
    team = Column(String(3), nullable=True)
    absent_player_ids = Column(String(255), nullable=True)  # sorted comma-separated IDs
    data = Column(Text, nullable=False)  # JSON string of prediction results
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    """Create all tables if they don't exist."""
    Base.metadata.create_all(bind=engine)
