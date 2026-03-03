import httpx
from fastapi import APIRouter
from fastapi.responses import Response

from app.config import get_settings
from app.services.tile_cache import get_cached_tile, cache_tile
from app.services.tiles import _get_current_session

router = APIRouter()


@router.get("/{z}/{x}/{y}")
async def get_tile(z: int, x: int, y: int):
    """Serve a map tile from cache, fetching from Google Maps and caching on miss."""
    cached = get_cached_tile(z, x, y)
    if cached:
        return Response(content=cached, media_type="image/jpeg")

    settings = get_settings()
    token = await _get_current_session()
    url = f"https://tile.googleapis.com/v1/2dtiles/{z}/{x}/{y}?session={token}&key={settings.google_maps_api_key}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url)
        response.raise_for_status()

    cache_tile(z, x, y, response.content)
    content_type = response.headers.get("content-type", "image/jpeg")
    return Response(content=response.content, media_type=content_type)
