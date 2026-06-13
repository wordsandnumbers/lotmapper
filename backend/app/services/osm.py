import asyncio
import logging
from typing import List
import httpx
from shapely.geometry import Polygon, MultiPolygon, LineString
from shapely.ops import unary_union, transform
from pyproj import Transformer

logger = logging.getLogger(__name__)

_to_3857 = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
_to_4326 = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)

ROAD_EXCLUDE = {'service', 'footway', 'path', 'construction', 'steps', 'track', 'cycleway'}

# Official Overpass API instances per https://dev.overpass-api.de/overpass-doc/en/preface/commons.html
# gall/lambert are the two physical servers behind overpass-api.de
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://gall.openstreetmap.de/api/interpreter",
    "https://lambert.openstreetmap.de/api/interpreter",
]
OVERPASS_HEADERS = {"User-Agent": "ParkingLotApp/1.0 (parking-lot-inference)"}

# Declare these in every query so the server knows our resource budget up front.
# timeout=25 (seconds), maxsize=512 MiB (the server default, stated explicitly as good practice).
OVERPASS_SETTINGS = "[out:json][timeout:25][maxsize:536870912]"


async def _overpass_post(query: str, max_retries: int = 3) -> dict:
    """POST to Overpass with 429/504-aware retry and endpoint rotation.

    Behaviour per the API commons:
    - 429 rate-limited: wait 15 s (the server's own queue window) then try next endpoint
    - 504 resource limit: try next endpoint immediately (other server may have capacity)
    - ConnectError / timeout: try next endpoint immediately
    - All endpoints exhausted: back off 15 s × attempt and retry up to max_retries
    """
    last_exc: Exception = RuntimeError("All Overpass endpoints failed")

    for attempt in range(max_retries):
        if attempt > 0:
            backoff = 15 * attempt  # 15 s, then 30 s
            logger.info(f"Overpass retry {attempt}/{max_retries - 1} in {backoff}s")
            await asyncio.sleep(backoff)

        async with httpx.AsyncClient(timeout=35.0) as client:
            for url in OVERPASS_ENDPOINTS:
                try:
                    r = await client.post(url, data={"data": query}, headers=OVERPASS_HEADERS)

                    if r.status_code == 429:
                        # Server will queue requests for up to 15 s before denying; mirror that wait.
                        logger.warning(f"Overpass 429 (rate limited) from {url}, waiting 15 s")
                        await asyncio.sleep(15)
                        last_exc = httpx.HTTPStatusError(
                            "429 Too Many Requests", request=r.request, response=r
                        )
                        continue  # try next endpoint after the wait

                    if r.status_code == 504:
                        # This server hit a resource ceiling; another may have capacity.
                        logger.warning(f"Overpass 504 (resource limit) from {url}, trying next")
                        last_exc = httpx.HTTPStatusError(
                            "504 Gateway Timeout", request=r.request, response=r
                        )
                        continue

                    r.raise_for_status()
                    return r.json()

                except (httpx.ConnectError, httpx.TimeoutException) as e:
                    logger.debug(f"Overpass {url} unreachable: {e}")
                    last_exc = e
                    continue

                except httpx.HTTPStatusError:
                    raise  # unexpected status code — surface immediately, don't retry

                except Exception as e:
                    logger.debug(f"Overpass {url} error: {e}")
                    last_exc = e
                    continue

    raise last_exc


async def fetch_osm_roads(min_lat, min_lng, max_lat, max_lng) -> List[Polygon]:
    """Query Overpass for highways, buffer by lane width, return polygons in EPSG:4326."""
    query = f"""
    {OVERPASS_SETTINGS};
    (way["highway"]({min_lat},{min_lng},{max_lat},{max_lng});
    relation["highway"]({min_lat},{min_lng},{max_lat},{max_lng}););
    out body;>;out skel qt;
    """
    try:
        osm = await _overpass_post(query)
    except Exception as e:
        logger.warning(f"OSM road fetch failed: {e}")
        return []

    node_dict = {n["id"]: (n["lon"], n["lat"]) for n in osm.get("elements", []) if n["type"] == "node"}
    buffered = []
    for el in osm.get("elements", []):
        if el["type"] != "way":
            continue
        tags = el.get("tags", {})
        highway = tags.get("highway", "")
        if highway in ROAD_EXCLUDE or not highway:
            continue
        coords = [node_dict[nid] for nid in el["nodes"] if nid in node_dict]
        if len(coords) < 2:
            continue
        try:
            line = LineString(coords)  # in EPSG:4326 (lon, lat)
            line_3857 = transform(_to_3857.transform, line)
            lanes = int(tags.get("lanes", 1) or 1)
            width = lanes * 1 if highway == "cycleway" else lanes * 3
            poly_3857 = line_3857.buffer(width, cap_style="flat")
            poly_4326 = transform(_to_4326.transform, poly_3857)
            buffered.append(poly_4326)
        except Exception:
            continue
    return buffered


async def fetch_osm_buildings(min_lat, min_lng, max_lat, max_lng) -> List[Polygon]:
    """Query Overpass for building footprints, return polygons in EPSG:4326."""
    query = f"""
    {OVERPASS_SETTINGS};
    (way["building"]({min_lat},{min_lng},{max_lat},{max_lng}););
    out body;>;out skel qt;
    """
    try:
        osm = await _overpass_post(query)
    except Exception as e:
        logger.warning(f"OSM building fetch failed: {e}")
        return []

    node_dict = {n["id"]: (n["lon"], n["lat"]) for n in osm.get("elements", []) if n["type"] == "node"}
    polygons = []
    for el in osm.get("elements", []):
        if el["type"] != "way":
            continue
        coords = [node_dict[nid] for nid in el["nodes"] if nid in node_dict]
        if len(coords) < 3:
            continue
        try:
            poly = Polygon(coords)
            if poly.is_valid and not poly.is_empty:
                polygons.append(poly)
        except Exception:
            continue
    return polygons


PARKING_EXCLUDE = {"multi-storey", "underground", "rooftop", "lane"}

async def fetch_osm_parking(min_lat, min_lng, max_lat, max_lng) -> List[Polygon]:
    """Fetch surface amenity=parking polygons from Overpass. Returns EPSG:4326.

    Fetches all amenity=parking and filters non-surface types client-side to avoid
    Overpass 406 errors from != filter syntax.
    """
    query = f"""
    {OVERPASS_SETTINGS};
    (way["amenity"="parking"]({min_lat},{min_lng},{max_lat},{max_lng});
    relation["amenity"="parking"]({min_lat},{min_lng},{max_lat},{max_lng}););
    out body;>;out skel qt;
    """
    try:
        osm = await _overpass_post(query)
    except Exception as e:
        logger.warning(f"OSM parking fetch failed: {e}")
        return []

    node_dict = {n["id"]: (n["lon"], n["lat"]) for n in osm.get("elements", []) if n["type"] == "node"}
    way_coords: dict = {}
    polygons = []

    for el in osm.get("elements", []):
        if el["type"] != "way":
            continue
        tags = el.get("tags", {})
        if tags.get("parking", "surface") in PARKING_EXCLUDE:
            continue
        coords = [node_dict[nid] for nid in el.get("nodes", []) if nid in node_dict]
        way_coords[el["id"]] = coords
        if len(coords) >= 3:
            try:
                poly = Polygon(coords)
                if poly.is_valid and not poly.is_empty:
                    polygons.append(poly)
            except Exception:
                continue

    skipped_relations = 0
    for el in osm.get("elements", []):
        if el["type"] != "relation":
            continue
        if el.get("tags", {}).get("parking", "surface") in PARKING_EXCLUDE:
            continue
        for member in el.get("members", []):
            if member.get("role") == "outer" and member.get("type") == "way":
                coords = way_coords.get(member["ref"], [])
                if len(coords) >= 3:
                    try:
                        poly = Polygon(coords)
                        if poly.is_valid and not poly.is_empty:
                            polygons.append(poly)
                    except Exception:
                        pass
                    break  # first outer ring only
                else:
                    skipped_relations += 1
                    break

    if skipped_relations:
        logger.debug(f"  Skipped {skipped_relations} OSM parking relations with incomplete outer rings")

    return polygons


def subtract_features(parking_polys: List[Polygon], overlay_polys: List[Polygon], label: str) -> List[Polygon]:
    """Subtract overlay polygons from parking lot polygons."""
    if not overlay_polys:
        return parking_polys
    try:
        overlay_union = unary_union(overlay_polys)
        result = []
        for poly in parking_polys:
            try:
                cleaned = poly.difference(overlay_union)
                if not cleaned.is_empty:
                    if isinstance(cleaned, MultiPolygon):
                        result.extend(cleaned.geoms)
                    else:
                        result.append(cleaned)
            except Exception:
                result.append(poly)
        logger.info(f"  After {label} removal: {len(result)} polygons (was {len(parking_polys)})")
        return result
    except Exception as e:
        logger.warning(f"Failed to subtract {label}: {e}")
        return parking_polys


def simplify_polygons(polygons: List[Polygon], tolerance_meters: float = 1.5) -> List[Polygon]:
    """
    Simplify polygon edges using Douglas-Peucker (equivalent to mapshaper -simplify 20%).
    Reprojects to EPSG:3857 (meters) for the tolerance, then back to EPSG:4326.
    """
    result = []
    for poly in polygons:
        try:
            poly_3857 = transform(_to_3857.transform, poly)
            simplified_3857 = poly_3857.simplify(tolerance_meters, preserve_topology=True)
            simplified_4326 = transform(_to_4326.transform, simplified_3857)
            if not simplified_4326.is_empty:
                result.append(simplified_4326)
        except Exception:
            result.append(poly)
    return result
