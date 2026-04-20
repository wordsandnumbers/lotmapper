import asyncio
import logging
import re
from typing import Optional, Tuple, List, Any, Callable
import httpx
from shapely.geometry import shape, Point, mapping
from shapely.ops import transform, unary_union
from app.services.osm import _to_3857, _to_4326

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_HEADERS = {"User-Agent": "ParkingLotApp/1.0 (parking-lot-inference)"}

# Keywords for downtown/CBD/mixed-use zoning districts
DOWNTOWN_ZONE_KEYWORDS = {
    "downtown", "cbd", "central business", "mixed use", "urban core",
    "city center", "central core",
}
# Common zone code prefixes for downtown zones across US cities
DOWNTOWN_ZONE_CODES = {"MX", "CBD", "D1", "D2", "D3", "DT", "UC", "CC"}

SKIP_SERVICE_KEYWORDS = {"school", "voting", "election", "precinct", "parcel", "address", "building", "buffer", "radius"}

# For boundary-layer searches (filter_by_zone_keywords=False), the service title must contain
# at least one of these to avoid false positives from POI buffers or unrelated datasets.
BOUNDARY_TITLE_KEYWORDS = {
    "downtown", "district", "boundary", "central business", "cbd", "urban core",
    "city center", "plan district", "core", "central",
}

HUB_API_URL = "https://hub.arcgis.com/api/v3/datasets"

# Zoning-specific field names (checked first)
ZONE_NAME_FIELDS = (
    "zone", "ZONE",
    "zone_name", "ZONE_NAME",
    "zoning_code", "ZONE_CODE", "ZONING_CODE",
    "district_type", "DISTRICT_TYPE",
    "zone_type", "ZONE_TYPE",
    "zone_class", "ZONE_CLASS",
    "zone_desc", "ZONE_DESC",
    "land_use", "LAND_USE",
    "land_use_code", "LAND_USE_CODE",
    "zonedist", "ZONEDIST",
    "zone_id", "ZONE_ID",
)

# General name fields (fallback)
NAME_FIELDS = (
    "name", "NAME",
    "label", "LABEL",
    "neighborhood", "NEIGHBORHOOD", "nbhd", "NBHD",
    "nbhd_name", "NBHD_NAME",
    "nhood", "NHOOD",
    "l_hood", "L_HOOD",
    "s_hood", "S_HOOD",
    "location", "LOCATION",
    "district", "DISTRICT", "district_name", "DISTRICT_NAME",
    "downtown_districts", "DOWNTOWN_DISTRICTS",
    "area_name", "AREA_NAME",
    "comm_name", "COMM_NAME",
    "placename", "PLACENAME",
)


def _contains_downtown_zone_keyword(text: str) -> bool:
    """Return True if text contains a downtown/CBD zoning keyword or code."""
    t = text.lower()
    if any(kw in t for kw in DOWNTOWN_ZONE_KEYWORDS):
        return True
    t_upper = text.upper()
    for code in DOWNTOWN_ZONE_CODES:
        if re.search(r'\b' + re.escape(code) + r'\b', t_upper):
            return True
    return False


def _extract_downtown_name(props: dict) -> Optional[str]:
    """
    Return the zone name/code if it matches a downtown keyword, else None.
    Checks known zoning fields first, then general name fields, then all string props.
    """
    all_fields = ZONE_NAME_FIELDS + NAME_FIELDS
    for field in all_fields:
        val = props.get(field)
        if val and isinstance(val, str) and val.strip():
            name = val.strip()
            if _contains_downtown_zone_keyword(name):
                return name
    # Fallback: check any string property
    for val in props.values():
        if val and isinstance(val, str) and val.strip() and len(val.strip()) <= 100:
            if _contains_downtown_zone_keyword(val):
                return val.strip()
    return None


def _clean_service_title(title: str, downtown_zones: bool = False) -> str:
    """Produce a human-readable candidate name from a service/dataset title."""
    # Replace _ and - with spaces
    s = re.sub(r'[_\-]', ' ', title)
    # Split camelCase on lowercase→uppercase transitions
    s = re.sub(r'([a-z])([A-Z])', r'\1 \2', s)
    # Normalize whitespace
    s = ' '.join(s.split())
    # Strip trailing standalone 4-digit year
    s = re.sub(r'\s+\b\d{4}\b$', '', s)
    # Title-case
    s = s.title()
    if downtown_zones:
        s += " (downtown zones)"
    return s


async def _get_city_nominatim(city: str, state: str) -> dict:
    """
    Fetch city info from Nominatim.
    Returns {"centroid": Point|None, "polygon": GeoJSON dict|None}
    """
    params = {
        "q": f"{city}, {state}, United States",
        "format": "json",
        "limit": 1,
        "polygon_geojson": 1,
        "countrycodes": "us",
    }
    centroid = None
    polygon = None
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(NOMINATIM_URL, params=params, headers=NOMINATIM_HEADERS)
            r.raise_for_status()
        results = r.json()
        if results:
            geom = results[0].get("geojson", {})
            if geom.get("type") in ("Polygon", "MultiPolygon"):
                centroid = shape(geom).centroid
                polygon = geom
            if centroid is None:
                lat = float(results[0].get("lat", 0))
                lon = float(results[0].get("lon", 0))
                if lat and lon:
                    centroid = Point(lon, lat)
    except Exception as e:
        logger.warning(f"Nominatim lookup failed: {e}")
    return {"centroid": centroid, "polygon": polygon}


async def _get_city_centroid(city: str, state: str) -> Optional[Point]:
    """Get city centroid from Nominatim."""
    result = await _get_city_nominatim(city, state)
    return result["centroid"]


async def _fallback_city_buffer(city: str, state: str) -> dict:
    """Nominatim city search + 800m buffer around centroid."""
    result = await _get_city_nominatim(city, state)
    centroid = result["centroid"]
    if centroid is None:
        centroid = Point(-98.5795, 39.8283)
    centroid_3857 = transform(_to_3857.transform, centroid)
    buffered_3857 = centroid_3857.buffer(800)
    buffered_4326 = transform(_to_4326.transform, buffered_3857)
    return {"type": "Polygon", "coordinates": [list(buffered_4326.exterior.coords)]}


def _is_near_city(geom_dict: dict, centroid: Point, max_dist_deg: float = 0.3) -> bool:
    """Return True if the geometry's centroid is within max_dist_deg of the city centroid."""
    try:
        g = shape(geom_dict)
        return g.centroid.distance(centroid) <= max_dist_deg
    except Exception:
        return True  # Don't discard if we can't determine


async def _query_service_for_downtown(
    url: str,
    service_title: str = "",
    filter_by_zone_keywords: bool = True,
    score: int = 1,
) -> Optional[dict]:
    """
    Query one ArcGIS FeatureServer URL and return a single merged downtown candidate.

    If filter_by_zone_keywords=True (zoning layers): only include features matching
    downtown keywords/codes. If False (explicit boundary layers): include all polygon features.
    Returns ONE candidate (union of all matching geometries) or None.
    """
    url = url.rstrip("/")
    if re.search(r"/\d+$", url):
        query_url = url + "/query"
    else:
        query_url = url + "/0/query"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(
                query_url,
                params={"where": "1=1", "outFields": "*", "returnGeometry": "true", "f": "geojson"},
            )
            r.raise_for_status()
            fc = r.json()
    except Exception as e:
        logger.debug(f"ArcGIS feature fetch failed for {url}: {e}")
        return None

    geoms = []
    for feature in fc.get("features", []):
        geom = feature.get("geometry")
        if not geom or geom.get("type") not in ("Polygon", "MultiPolygon"):
            continue
        if filter_by_zone_keywords:
            props = feature.get("properties", {})
            if not _extract_downtown_name(props):
                continue
        try:
            g = shape(geom)
            if not g.is_empty:
                geoms.append(g)
        except Exception:
            continue

    if not geoms:
        return None

    union = unary_union(geoms)
    if not union.is_valid:
        union = union.buffer(0)

    if union.geom_type == "GeometryCollection":
        return None

    name = _clean_service_title(service_title, downtown_zones=filter_by_zone_keywords)
    return {
        "name": name,
        "geometry": mapping(union),
        "score": score,
        "_area": union.area,
    }


async def _arcgis_search(query: str, num: int = 5) -> list:
    """Run an ArcGIS Online content search and return results list."""
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(
                "https://www.arcgis.com/sharing/rest/search",
                params={"q": query, "type": "Feature Service", "num": num, "f": "json"},
            )
            r.raise_for_status()
            return r.json().get("results", [])
    except Exception as e:
        logger.warning(f"ArcGIS search failed ({query!r}): {e}")
        return []


async def _hub_search(query: str, num: int = 5) -> list:
    """Search ArcGIS Hub API for datasets matching the query."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                HUB_API_URL,
                params={"q": query, "filter[type]": "Feature Layer", "page[size]": num},
            )
            r.raise_for_status()
            return r.json().get("data", [])
    except Exception as e:
        logger.warning(f"Hub API search failed ({query!r}): {e}")
        return []


async def _hub_search_and_fetch_downtown(
    query: str,
    filter_by_zone_keywords: bool = True,
    score: int = 1,
    num: int = 5,
) -> Optional[dict]:
    """Search Hub API and return one merged downtown candidate (first-hit wins)."""
    items = await _hub_search(query, num=num)
    for item in items[:3]:
        attrs = item.get("attributes", {})
        url = (attrs.get("url") or "").strip()
        if not re.match(r"https://services\d*\.arcgis\.com/", url):
            continue
        dataset_name = attrs.get("name", "") or ""
        name_lower = dataset_name.lower()
        if any(kw in name_lower for kw in SKIP_SERVICE_KEYWORDS):
            continue
        # For explicit boundary searches, require a boundary-related keyword in the title
        # to avoid false positives (e.g. YMCA buffers, POI layers)
        if not filter_by_zone_keywords and not any(kw in name_lower for kw in BOUNDARY_TITLE_KEYWORDS):
            continue
        candidate = await _query_service_for_downtown(
            url, service_title=dataset_name,
            filter_by_zone_keywords=filter_by_zone_keywords, score=score,
        )
        if candidate:
            return candidate
    return None


async def _arcgis_search_and_fetch_downtown(
    query: str,
    filter_by_zone_keywords: bool = True,
    score: int = 1,
    num: int = 5,
) -> Optional[dict]:
    """Search ArcGIS Online and return one merged downtown candidate (first-hit wins)."""
    results = await _arcgis_search(query, num=num)
    for item in results[:3]:
        url = item.get("url", "") or ""
        if not re.match(r"https://services\d*\.arcgis\.com/", url):
            continue
        title = item.get("title", "") or ""
        title_lower = title.lower()
        if any(kw in title_lower for kw in SKIP_SERVICE_KEYWORDS):
            continue
        # For explicit boundary searches, require a boundary-related keyword in the title
        if not filter_by_zone_keywords and not any(kw in title_lower for kw in BOUNDARY_TITLE_KEYWORDS):
            continue
        candidate = await _query_service_for_downtown(
            url, service_title=title,
            filter_by_zone_keywords=filter_by_zone_keywords, score=score,
        )
        if candidate:
            return candidate
    return None



def _tag_source(batch: List[dict], source: str) -> List[dict]:
    for c in batch:
        c.setdefault("source", source)
    return batch


async def _emit(cb: Optional[Any], message: str) -> None:
    if cb:
        await cb({"status": "searching", "message": message})


async def get_candidates(
    city: str,
    state: str,
    progress_cb: Optional[Callable] = None,
) -> List[dict]:
    """
    Return downtown/CBD polygon candidates for the given city/state,
    each representing a merged union of relevant features from one source layer.

    Strategy:
      Stage 1: Hub API, explicit boundary layers (score=2) — short-circuit if found
      Stage 2: Hub API, zoning union (score=1) — only if Stage 1 empty
      Stage 3: ArcGIS Online fallback (both tiers) — only if Stages 1+2 empty
      Stage 4: Nominatim city boundary or 800m buffer (score=-1)

    Each entry: {"name": str, "geometry": GeoJSON dict, "score": int, "source": str}
    score=2 → explicit downtown/boundary layer
    score=1 → downtown zones merged from zoning layer
    score=-1 → fallback city boundary
    """
    # Fetch Nominatim centroid first so geographic filtering is available immediately
    nominatim_result = await _get_city_nominatim(city, state)
    centroid = nominatim_result["centroid"]

    def _geo_filter(cands: List[dict], min_area: float) -> List[dict]:
        filtered = []
        for c in cands:
            if centroid and not _is_near_city(c["geometry"], centroid):
                continue
            if c["_area"] < min_area:
                continue
            filtered.append(c)
        return filtered

    candidates: List[dict] = []

    # --- Stage 1: Hub API, explicit boundary layers (score=2) ---
    await _emit(progress_cb, f"Searching ArcGIS Hub for {city}, {state}...")
    stage1_queries = [
        f"{city} downtown",
        f"{city} downtown plan",
        f"{city} central business district",
        f"{city} downtown boundary",
    ]
    stage1_results = await asyncio.gather(*[
        _hub_search_and_fetch_downtown(q, filter_by_zone_keywords=False, score=2)
        for q in stage1_queries
    ])
    for r in stage1_results:
        if r:
            r.setdefault("source", "arcgis_hub")
            candidates.append(r)
    candidates = _geo_filter(candidates, min_area=5e-5)

    # Short-circuit: score=2 found from Hub → skip Stages 2-3
    if not any(c["score"] == 2 for c in candidates):
        candidates = []

        # --- Stage 2: Hub API, zoning union (score=1) ---
        await _emit(progress_cb, f"Searching zoning layers for {city}, {state}...")
        stage2_queries = [
            f"{city} {state} zoning",
            f"{city} {state} land use",
            f"{city} zoning districts",
        ]
        stage2_results = await asyncio.gather(*[
            _hub_search_and_fetch_downtown(q, filter_by_zone_keywords=True, score=1)
            for q in stage2_queries
        ])
        for r in stage2_results:
            if r:
                r.setdefault("source", "arcgis_hub")
                candidates.append(r)
        candidates = _geo_filter(candidates, min_area=1e-5)

        # --- Stage 3: ArcGIS Online fallback (only if Stages 1+2 empty) ---
        if not candidates:
            logger.info(f"Hub API found nothing for {city}, {state}; trying ArcGIS Online")
            await _emit(progress_cb, "Trying ArcGIS Online search...")

            # Stage 3 Tier 1: explicit boundary layers
            arcgis_t1_queries = [
                f"{city} downtown",
                f"{city} downtown plan",
                f"{city} central business district",
                f"{city} downtown boundary",
            ]
            arcgis_t1_results = await asyncio.gather(*[
                _arcgis_search_and_fetch_downtown(q, filter_by_zone_keywords=False, score=2)
                for q in arcgis_t1_queries
            ])
            for r in arcgis_t1_results:
                if r:
                    r.setdefault("source", "arcgis_online")
                    candidates.append(r)
            candidates = _geo_filter(candidates, min_area=5e-5)

            # Stage 3 Tier 2: zoning (only if Tier 1 found nothing)
            if not any(c["score"] == 2 for c in candidates):
                candidates = []
                arcgis_t2_queries = [
                    f"{city} {state} zoning",
                    f"{city} {state} land use districts",
                    f"{city} zoning districts",
                ]
                arcgis_t2_results = await asyncio.gather(*[
                    _arcgis_search_and_fetch_downtown(q, filter_by_zone_keywords=True, score=1)
                    for q in arcgis_t2_queries
                ])
                for r in arcgis_t2_results:
                    if r:
                        r.setdefault("source", "arcgis_online")
                        candidates.append(r)
                candidates = _geo_filter(candidates, min_area=1e-5)

    # --- Stage 4: Nominatim fallback ---
    if not candidates:
        await _emit(progress_cb, "No boundaries found, using approximate downtown area")
        city_polygon = nominatim_result["polygon"]
        if city_polygon:
            name = f"{city}, {state} (city boundary — no zoning data found)"
            return [{"name": name, "geometry": city_polygon, "score": -1, "source": "fallback"}]
        geom = await _fallback_city_buffer(city, state)
        return [{"name": "Estimated downtown (800m radius)", "geometry": geom, "score": -1, "source": "fallback"}]

    # Deduplicate by name, sort score desc then area asc, return top 5
    seen: set = set()
    deduped = []
    for c in candidates:
        key = c["name"].lower()
        if key not in seen:
            seen.add(key)
            deduped.append(c)

    deduped.sort(key=lambda c: (-c["score"], c["_area"]))
    return [
        {"name": c["name"], "geometry": c["geometry"], "score": c["score"], "source": c.get("source", "arcgis_hub")}
        for c in deduped[:5]
    ]


async def geocode_city(city: str, state: str) -> Optional[dict]:
    """
    Return geocoded center and administrative polygon for a US city.
    Returns {"center": {"lat": float, "lon": float}, "polygon": GeoJSON dict|None} or None.
    """
    result = await _get_city_nominatim(city, state)
    centroid = result["centroid"]
    if centroid is None:
        return None
    return {
        "center": {"lat": centroid.y, "lon": centroid.x},
        "polygon": result["polygon"],
    }


async def resolve_downtown(city: str, state: str) -> dict:
    """
    Resolve a downtown boundary polygon for the given city/state.
    Returns {"geometry": GeoJSON Polygon dict, "source": "arcgis"|"fallback", "boundary_name": str|None}
    """
    candidates_list = await get_candidates(city, state)
    if candidates_list and candidates_list[0]["score"] >= 1:
        # Prefer score=2 (explicit boundary) over score=1 (zoning union)
        tier1 = [c for c in candidates_list if c["score"] == 2]
        use = tier1 if tier1 else [c for c in candidates_list if c["score"] == 1]
        geoms = [shape(c["geometry"]) for c in use]
        merged = unary_union(geoms) if len(geoms) > 1 else geoms[0]
        names = [c["name"] for c in use]
        boundary_name = ", ".join(dict.fromkeys(names)) or None
        return {"geometry": mapping(merged), "source": "arcgis", "boundary_name": boundary_name}

    geom = await _fallback_city_buffer(city, state)
    return {"geometry": geom, "source": "fallback", "boundary_name": None}
