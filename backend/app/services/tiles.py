"""
Service for fetching satellite tiles from ESRI World Imagery.
"""
import math
import asyncio
from typing import Tuple, List
import httpx
import numpy as np
from PIL import Image
from io import BytesIO


# ESRI World Imagery tile server
ESRI_TILE_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"


def lat_lng_to_tile(lat: float, lng: float, zoom: int) -> Tuple[int, int]:
    """Convert lat/lng to tile x/y coordinates at given zoom level."""
    lat_rad = math.radians(lat)
    n = 2.0 ** zoom
    x = int((lng + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


def tile_to_lat_lng(x: int, y: int, zoom: int) -> Tuple[float, float]:
    """Convert tile x/y to lat/lng (northwest corner of tile)."""
    n = 2.0 ** zoom
    lng = x / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat = math.degrees(lat_rad)
    return lat, lng


def get_tile_bounds(x: int, y: int, zoom: int) -> Tuple[float, float, float, float]:
    """Get bounding box of a tile as (min_lat, min_lng, max_lat, max_lng)."""
    nw_lat, nw_lng = tile_to_lat_lng(x, y, zoom)
    se_lat, se_lng = tile_to_lat_lng(x + 1, y + 1, zoom)
    return se_lat, nw_lng, nw_lat, se_lng  # min_lat, min_lng, max_lat, max_lng


async def fetch_tile(client: httpx.AsyncClient, x: int, y: int, zoom: int) -> Image.Image:
    """Fetch a single tile from ESRI."""
    url = ESRI_TILE_URL.format(z=zoom, x=x, y=y)
    response = await client.get(url)
    response.raise_for_status()
    return Image.open(BytesIO(response.content))


async def fetch_tiles_for_bounds(
    min_lat: float,
    min_lng: float,
    max_lat: float,
    max_lng: float,
    zoom: int = 18,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Fetch all tiles covering a bounding box and stitch them together.

    Returns:
        Tuple of (image_array, lons_array, lats_array)
        - image_array: RGB image as numpy array
        - lons_array: 2D array of longitude values for each pixel
        - lats_array: 2D array of latitude values for each pixel
    """
    # Get tile range
    min_x, max_y = lat_lng_to_tile(min_lat, min_lng, zoom)
    max_x, min_y = lat_lng_to_tile(max_lat, max_lng, zoom)

    # Ensure we have the correct order
    if min_x > max_x:
        min_x, max_x = max_x, min_x
    if min_y > max_y:
        min_y, max_y = max_y, min_y

    num_tiles_x = max_x - min_x + 1
    num_tiles_y = max_y - min_y + 1

    tile_size = 256  # Standard tile size
    total_width = num_tiles_x * tile_size
    total_height = num_tiles_y * tile_size

    # Fetch all tiles concurrently
    async with httpx.AsyncClient(timeout=30.0) as client:
        tasks = []
        for y in range(min_y, max_y + 1):
            for x in range(min_x, max_x + 1):
                tasks.append(fetch_tile(client, x, y, zoom))

        tiles = await asyncio.gather(*tasks)

    # Stitch tiles into single image
    stitched = Image.new('RGB', (total_width, total_height))
    idx = 0
    for row, y in enumerate(range(min_y, max_y + 1)):
        for col, x in enumerate(range(min_x, max_x + 1)):
            stitched.paste(tiles[idx], (col * tile_size, row * tile_size))
            idx += 1

    # Create coordinate arrays (lon/lat for each pixel)
    lons = np.zeros((total_height, total_width))
    lats = np.zeros((total_height, total_width))

    for row, tile_y in enumerate(range(min_y, max_y + 1)):
        for col, tile_x in enumerate(range(min_x, max_x + 1)):
            # Get bounds of this tile
            tile_min_lat, tile_min_lng, tile_max_lat, tile_max_lng = get_tile_bounds(
                tile_x, tile_y, zoom
            )

            # Calculate pixel positions
            start_x = col * tile_size
            start_y = row * tile_size

            # Create linear interpolation for this tile
            for py in range(tile_size):
                for px in range(tile_size):
                    # Interpolate coordinates
                    lng = tile_min_lng + (tile_max_lng - tile_min_lng) * (px / tile_size)
                    lat = tile_max_lat - (tile_max_lat - tile_min_lat) * (py / tile_size)

                    lons[start_y + py, start_x + px] = lng
                    lats[start_y + py, start_x + px] = lat

    return np.array(stitched), lons, lats


def calculate_optimal_zoom(min_lat: float, min_lng: float, max_lat: float, max_lng: float) -> int:
    """
    TODO: remove zoom, we should always use the highest zoom level (19) for best parking lot detection results.
    Calculate optimal zoom level based on area size.
    Higher zoom = more detail but more tiles to fetch.

    Note: Parking lot detection model requires zoom 18+ for accurate results.
    We enforce minimum zoom of 18 even for larger areas.
    """
    # Approximate area size in degrees
    lat_span = abs(max_lat - min_lat)
    lng_span = abs(max_lng - min_lng)
    max_span = max(lat_span, lng_span)

    # For very small areas, use zoom 19
    if max_span < 0.005:
        return 19
    else:
        # For all other areas, use zoom 18 (minimum for parking lot detection)
        return 18
