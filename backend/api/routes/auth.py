"""Google OAuth authentication endpoints.

Handles the OAuth2 flow: redirect to Google, handle callback, create
session, and manage logout. Uses httpx for token exchange.

GRACEFUL DEGRADATION: If GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET are
not set, all auth endpoints return 503 — but the rest of the API works.
"""

import logging
from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from backend.api.config import settings
from backend.api.database import Session, User
from backend.api.dependencies import create_session_token, get_current_user, get_db
from backend.api.schemas import AuthURL, UserInfo

logger = logging.getLogger("auth")
router = APIRouter(prefix="/api/auth", tags=["auth"])

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


def _check_oauth_configured():
    """Raise 503 if Google OAuth credentials are missing."""
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            503, "Google OAuth not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET."
        )


@router.get("/google", response_model=AuthURL)
def google_login():
    """Generate Google OAuth authorization URL."""
    _check_oauth_configured()

    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
    }
    auth_url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
    return AuthURL(auth_url=auth_url)


@router.get("/google/callback")
def google_callback(code: str, db=Depends(get_db)):
    """Handle Google OAuth callback.

    Exchanges authorization code for tokens, fetches user info,
    creates/updates the user record, creates a session, and redirects
    to the frontend with a session cookie.
    """
    _check_oauth_configured()

    # Exchange authorization code for access token
    token_data = {
        "code": code,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }
    try:
        token_resp = httpx.post(GOOGLE_TOKEN_URL, data=token_data, timeout=10.0)
    except httpx.TimeoutException:
        raise HTTPException(504, "Google authentication timed out")
    except httpx.HTTPError as e:
        logger.error(f"Token exchange failed: {e}")
        raise HTTPException(502, "Failed to communicate with Google")

    if token_resp.status_code != 200:
        logger.error(f"Token exchange returned {token_resp.status_code}")
        raise HTTPException(400, "Failed to exchange authorization code")

    tokens = token_resp.json()
    access_token = tokens.get("access_token")
    if not access_token:
        raise HTTPException(400, "No access token received from Google")

    # Fetch user info
    try:
        userinfo_resp = httpx.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10.0,
        )
    except httpx.HTTPError as e:
        logger.error(f"User info fetch failed: {e}")
        raise HTTPException(502, "Failed to get user info from Google")

    if userinfo_resp.status_code != 200:
        raise HTTPException(400, "Failed to get user info from Google")

    userinfo = userinfo_resp.json()

    # Upsert user
    user = db.query(User).filter(User.google_id == userinfo["id"]).first()
    if not user:
        user = User(
            email=userinfo.get("email", ""),
            name=userinfo.get("name"),
            picture=userinfo.get("picture"),
            google_id=userinfo["id"],
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        # Update profile info on login
        user.name = userinfo.get("name", user.name)
        user.picture = userinfo.get("picture", user.picture)
        db.commit()

    # Create session
    token = create_session_token()
    session = Session(
        session_token=token,
        user_id=user.id,
        expires_at=datetime.utcnow() + timedelta(days=30),
    )
    db.add(session)
    db.commit()

    # Redirect to frontend with session cookie.
    # Cross-origin (Vercel→Railway) requires SameSite=None + Secure=True.
    # Local dev over HTTP can't use SameSite=None, so fall back to Lax.
    is_https = settings.BACKEND_URL.startswith("https")
    redirect = RedirectResponse(url=settings.FRONTEND_URL, status_code=302)
    redirect.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        samesite="none" if is_https else "lax",
        secure=is_https,
        max_age=30 * 24 * 3600,  # 30 days
        path="/",
    )
    return redirect


@router.get("/me", response_model=UserInfo)
def get_me(user: User = Depends(get_current_user)):
    """Get current authenticated user info."""
    return UserInfo(
        id=user.id,
        email=user.email,
        name=user.name,
        picture=user.picture,
        created_at=user.created_at,
    )


@router.post("/logout")
def logout(request: Request, response: Response, db=Depends(get_db)):
    """Log out: delete session from DB and clear cookie."""
    token = request.cookies.get("session_token")
    if token:
        db.query(Session).filter(Session.session_token == token).delete()
        db.commit()
    is_https = settings.BACKEND_URL.startswith("https")
    response.delete_cookie(
        "session_token",
        path="/",
        samesite="none" if is_https else "lax",
        secure=is_https,
        httponly=True,
    )
    return {"detail": "Logged out"}
