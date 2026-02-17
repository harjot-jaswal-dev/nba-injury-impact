"""FastAPI application entry point.

Configures CORS, lifespan events (model preloading, data loading,
scheduler startup), global exception handlers, and router wiring.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.config import settings
from backend.api.data_access import data_store
from backend.api.database import init_db
from backend.api.player_resolver import player_resolver
from backend.api.routes import admin, auth, chat, players, predictions
from backend.api.scheduler import create_scheduler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    # ── Startup ──
    logger.info("Initializing database...")
    init_db()

    logger.info("Loading data files into memory...")
    data_store.load_all()

    logger.info("Building player name index...")
    player_resolver.build_index()

    logger.info("Pre-loading ML models...")
    try:
        from backend.ml.predict import store as model_store

        model_store.get_baseline_models()
        model_store.get_ripple_models()
        logger.info("ML models loaded successfully (8 baseline + 8 ripple)")
    except FileNotFoundError as e:
        logger.warning(f"ML models not yet trained: {e}")

    # Graceful degradation warnings
    if not settings.ANTHROPIC_API_KEY:
        logger.warning(
            "ANTHROPIC_API_KEY not set — chat endpoint will return 503"
        )
    if not settings.GOOGLE_CLIENT_ID:
        logger.warning(
            "Google OAuth not configured — auth endpoints will return 503"
        )

    logger.info("Starting scheduler...")
    scheduler = create_scheduler()
    scheduler.start()
    logger.info(
        f"Scheduler started (daily refresh at {settings.REFRESH_SCHEDULE_HOUR}:00 "
        f"{settings.REFRESH_SCHEDULE_TIMEZONE})"
    )

    logger.info("NBA Injury Impact Analyzer API ready")

    yield  # App runs here

    # ── Shutdown ──
    scheduler.shutdown(wait=False)
    logger.info("Application shutdown complete")


app = FastAPI(
    title="NBA Injury Impact Analyzer API",
    description=(
        "Predict how player injuries affect NBA team and individual performance. "
        "Features baseline predictions, injury ripple effects, and an AI-powered "
        "analytics chat."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — use FRONTEND_URL as the allowed origin, not ["*"], because
# browsers reject allow_origins=["*"] when allow_credentials=True.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(predictions.router)
app.include_router(players.router)
app.include_router(chat.router)
app.include_router(auth.router)
app.include_router(admin.router)


# ── Global Exception Handlers ──────────────────────────────────


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """Bad input data → 400."""
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(FileNotFoundError)
async def file_not_found_handler(request: Request, exc: FileNotFoundError):
    """Missing data or models → 503."""
    return JSONResponse(
        status_code=503,
        content={"detail": f"Required data not available: {exc}"},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Catch-all: log the error, return clean JSON — never raw stack traces."""
    logger.error(f"Unhandled exception on {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500, content={"detail": "Internal server error"}
    )


# ── Health Check ────────────────────────────────────────────────


@app.get("/api/health", tags=["system"])
def health_check():
    """Quick health check for uptime monitoring."""
    return {"status": "ok", "version": "1.0.0"}
