from fastapi import APIRouter, Depends

from app.models.user import User
from app.api.deps import get_current_active_user
from app.services.tiles import get_google_maps_tile_url

router = APIRouter()


@router.get("/tile-url")
async def get_tile_url(current_user: User = Depends(get_current_active_user)):
    """Return a Leaflet-compatible Google Maps satellite tile URL with a valid session token."""
    url = await get_google_maps_tile_url()
    return {"url": url}
