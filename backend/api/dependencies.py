"""FastAPI dependency functions for injection.

Provides database sessions, user authentication, and rate limiting
as reusable Depends() callables for route handlers.
"""

import secrets
from datetime import date, datetime

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session as DBSession

from backend.api.config import settings
from backend.api.database import ChatUsage, Session, SessionLocal, User


def get_db():
    """Yield a database session, ensuring cleanup after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user_optional(
    request: Request, db: DBSession = Depends(get_db)
) -> User | None:
    """Extract current user from session cookie. Returns None if unauthenticated."""
    session_token = request.cookies.get("session_token")
    if not session_token:
        return None
    session = (
        db.query(Session)
        .filter(
            Session.session_token == session_token,
            Session.expires_at > datetime.utcnow(),
        )
        .first()
    )
    if not session:
        return None
    return db.query(User).filter(User.id == session.user_id).first()


def get_current_user(
    request: Request, db: DBSession = Depends(get_db)
) -> User:
    """Require authenticated user. Raises 401 if not logged in."""
    user = get_current_user_optional(request, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Please log in first.",
        )
    return user


def check_chat_rate_limit(
    user: User = Depends(get_current_user), db: DBSession = Depends(get_db)
) -> ChatUsage:
    """Check and enforce daily chat rate limit.

    Returns the ChatUsage record for the current day. Raises 429 if
    the user has exceeded their daily limit.
    """
    today = date.today()
    usage = (
        db.query(ChatUsage)
        .filter(
            ChatUsage.user_id == user.id,
            ChatUsage.usage_date == today,
        )
        .first()
    )

    if usage is None:
        usage = ChatUsage(user_id=user.id, usage_date=today, question_count=0)
        db.add(usage)
        db.commit()
        db.refresh(usage)

    if usage.question_count >= settings.CHAT_DAILY_LIMIT:
        remaining = 0
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Daily chat limit exceeded",
            headers={
                "X-RateLimit-Limit": str(settings.CHAT_DAILY_LIMIT),
                "X-RateLimit-Remaining": str(remaining),
            },
        )

    return usage


def create_session_token() -> str:
    """Generate a cryptographically secure session token."""
    return secrets.token_urlsafe(32)
