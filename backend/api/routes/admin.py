"""Admin endpoints for manual data refresh.

Protected by X-Admin-Key header. Includes a concurrency guard
to prevent overlapping refresh runs.
"""

import logging

from fastapi import APIRouter, HTTPException, Header

from backend.api.config import settings

logger = logging.getLogger("admin")
router = APIRouter(prefix="/api/admin", tags=["admin"])

# Concurrency guard — Python GIL makes boolean check-and-set safe
_refresh_in_progress = False


@router.post("/refresh")
def trigger_refresh(x_admin_key: str = Header(None)):
    """Manually trigger the data refresh pipeline.

    Requires X-Admin-Key header matching ADMIN_KEY env var.
    Returns 409 if a refresh is already in progress.
    """
    global _refresh_in_progress

    # Auth check
    if not settings.ADMIN_KEY:
        raise HTTPException(403, "ADMIN_KEY not configured on server")
    if x_admin_key != settings.ADMIN_KEY:
        raise HTTPException(403, "Invalid admin key")

    # Concurrency guard
    if _refresh_in_progress:
        raise HTTPException(409, "Refresh already in progress")

    _refresh_in_progress = True
    try:
        from backend.api.scheduler import run_refresh_job

        result = run_refresh_job()
        return {"detail": "Refresh completed", "result": result}
    except Exception as e:
        logger.error(f"Refresh failed: {e}")
        raise HTTPException(500, f"Refresh failed: {e}")
    finally:
        _refresh_in_progress = False
