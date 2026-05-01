from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.config import get_settings
from app.database import get_db
from app.models.user import User
from app.services.tile_usage import get_monthly_count

router = APIRouter()


@router.get("/tiles")
async def get_tile_usage(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Return current month's Google Maps tile API usage vs. the configured monthly limit."""
    now = datetime.utcnow()
    settings = get_settings()
    used = get_monthly_count(db, now.year, now.month)
    limit = settings.google_maps_monthly_tile_limit
    return {
        "year": now.year,
        "month": now.month,
        "used": used,
        "limit": limit,
        "remaining": max(0, limit - used),
        "percent_used": round(used / limit * 100, 1) if limit > 0 else 0,
    }
