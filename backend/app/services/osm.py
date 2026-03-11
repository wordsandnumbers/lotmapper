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

async def fetch_osm_roads(min_lat, min_lng, max_lat, max_lng) -> List[Polygon]:
    """Query Overpass for highways, buffer by lane width, return polygons in EPSG:4326."""
    query = f"""
    [out:json][timeout:25];
    (way["highway"]({min_lat},{min_lng},{max_lat},{max_lng});
    relation["highway"]({min_lat},{min_lng},{max_lat},{max_lng}););
    out body;>;out skel qt;
    """
    try:
        async with httpx.AsyncClient(timeout=35.0) as client:
            r = await client.get("https://overpass-api.de/api/interpreter", params={"data": query})
            r.raise_for_status()
        osm = r.json()
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
    [out:json][timeout:25];
    (way["building"]({min_lat},{min_lng},{max_lat},{max_lng}););
    out body;>;out skel qt;
    """
    try:
        async with httpx.AsyncClient(timeout=35.0) as client:
            r = await client.get("https://overpass-api.de/api/interpreter", params={"data": query})
            r.raise_for_status()
        osm = r.json()
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
