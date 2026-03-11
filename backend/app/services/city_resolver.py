import asyncio
import logging
import re
from typing import Optional, Tuple, List
import httpx
from shapely.geometry import shape, Point, mapping
from shapely.ops import transform, unary_union
from app.services.osm import _to_3857, _to_4326

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_HEADERS = {"User-Agent": "ParkingLotApp/1.0 (parking-lot-inference)"}

DOWNTOWN_KEYWORDS = {"downtown", "cbd", "central business", "city center", "urban core"}
BOUNDARY_TITLE_KEYWORDS = {"district", "districts", "boundary", "boundaries", "plan", "zone", "zones", "area", "areas", "neighborhood", "neighbourhoods", "quarter"}
SKIP_SERVICE_KEYWORDS = {"school", "voting", "election", "precinct", "parcel", "address", "building"}

HUB_API_URL = "https://hub.arcgis.com/api/v3/datasets"


NAME_FIELDS = (
    "name", "NAME",
    "label", "LABEL",
    "neighborhood", "NEIGHBORHOOD", "nbhd", "NBHD",
    "nbhd_name", "NBHD_NAME",          # Denver, many others
    "nhood", "NHOOD",                   # common abbreviation
    "l_hood", "L_HOOD",                 # Seattle large neighborhood
    "s_hood", "S_HOOD",                 # Seattle small neighborhood
    "location", "LOCATION",
    "district", "DISTRICT", "district_name", "DISTRICT_NAME",
    "downtown_districts", "DOWNTOWN_DISTRICTS",
    "area_name", "AREA_NAME",
    "comm_name", "COMM_NAME",           # community name
    "placename", "PLACENAME",
)


def _contains_downtown_keyword(text: str) -> bool:
    t = text.lower()
    return any(kw in t for kw in DOWNTOWN_KEYWORDS)


def _extract_name(props: dict) -> Optional[str]:
    """Pull the best name value out of a feature's properties."""
    for field in NAME_FIELDS:
        val = props.get(field)
        if val and isinstance(val, str) and val.strip():
            return val.strip()
    return None


async def _try_arcgis(city: str, state: str) -> Optional[Tuple[dict, str]]:
    """Search ArcGIS Online for neighborhood boundary feature services.
    Returns (geometry, boundary_name) or None."""
    search_url = "https://www.arcgis.com/sharing/rest/search"
    params = {
        "q": f"{city} {state} neighborhood boundary",
        "type": "Feature Service",
        "num": 5,
        "f": "json",
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(search_url, params=params)
            r.raise_for_status()
            data = r.json()

        results = data.get("results", [])
        for item in results[:3]:
            url = item.get("url", "") or ""
            if not re.match(r"https://services\d*\.arcgis\.com/", url):
                continue
            # If the service title contains a downtown keyword AND a boundary-type
            # keyword, treat all features as matching (e.g. "Downtown_Austin_Plan_Districts").
            # This avoids false positives like "Downtown Austin Tree Canopy".
            service_title = item.get("title", "")
            title_lower = service_title.lower()
            service_is_downtown = (
                _contains_downtown_keyword(service_title)
                and any(kw in title_lower for kw in BOUNDARY_TITLE_KEYWORDS)
            )

            query_url = url.rstrip("/") + "/0/query"
            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    r = await client.get(
                        query_url,
                        params={"where": "1=1", "outFields": "*", "returnGeometry": "true", "f": "geojson"},
                    )
                    r.raise_for_status()
                    fc = r.json()
            except Exception as e:
                logger.debug(f"ArcGIS feature fetch failed: {e}")
                continue

            # Collect matching features and union them.
            # A feature matches if its property values contain a downtown keyword,
            # OR the service title itself is a downtown service (union all in that case).
            matching_geoms = []
            matching_names = []
            for feature in fc.get("features", []):
                props = feature.get("properties", {})
                name_val = " ".join(str(v) for v in props.values() if v)
                if service_is_downtown or _contains_downtown_keyword(name_val):
                    geom = feature.get("geometry")
                    if geom and geom.get("type") in ("Polygon", "MultiPolygon"):
                        try:
                            matching_geoms.append(shape(geom))
                            name = _extract_name(props)
                            if name:
                                matching_names.append(name)
                        except Exception:
                            continue

            if matching_geoms:
                merged = unary_union(matching_geoms)
                boundary_name = ", ".join(dict.fromkeys(matching_names)) or None
                logger.info(f"ArcGIS found {len(matching_geoms)} features in '{url}': {boundary_name}")
                return mapping(merged), boundary_name
    except Exception as e:
        logger.warning(f"ArcGIS search failed: {e}")
    return None


async def _fallback_city_buffer(city: str, state: str) -> dict:
    """Nominatim city search + 800m buffer around centroid."""
    params = {
        "q": f"{city}, {state}, United States",
        "format": "json",
        "limit": 1,
        "polygon_geojson": 1,
        "countrycodes": "us",
    }
    centroid = None
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(NOMINATIM_URL, params=params, headers=NOMINATIM_HEADERS)
            r.raise_for_status()
        results = r.json()
        if results:
            geom = results[0].get("geojson", {})
            if geom.get("type") in ("Polygon", "MultiPolygon"):
                centroid = shape(geom).centroid
    except Exception as e:
        logger.warning(f"Nominatim fallback failed: {e}")

    if centroid is None:
        centroid = Point(-98.5795, 39.8283)

    centroid_3857 = transform(_to_3857.transform, centroid)
    buffered_3857 = centroid_3857.buffer(800)
    buffered_4326 = transform(_to_4326.transform, buffered_3857)
    return {"type": "Polygon", "coordinates": [list(buffered_4326.exterior.coords)]}


async def _get_city_centroid(city: str, state: str) -> Optional[Point]:
    """Get city centroid from Nominatim (lon, lat)."""
    params = {
        "q": f"{city}, {state}, United States",
        "format": "json",
        "limit": 1,
        "polygon_geojson": 1,
        "countrycodes": "us",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(NOMINATIM_URL, params=params, headers=NOMINATIM_HEADERS)
            r.raise_for_status()
        results = r.json()
        if results:
            geom = results[0].get("geojson", {})
            if geom.get("type") in ("Polygon", "MultiPolygon"):
                return shape(geom).centroid
            # Fall back to lat/lon point
            lat = float(results[0].get("lat", 0))
            lon = float(results[0].get("lon", 0))
            if lat and lon:
                return Point(lon, lat)
    except Exception as e:
        logger.warning(f"Nominatim centroid lookup failed: {e}")
    return None


def _is_near_city(geom_dict: dict, centroid: Point, max_dist_deg: float = 0.3) -> bool:
    """Return True if the geometry's centroid is within max_dist_deg of the city centroid."""
    try:
        g = shape(geom_dict)
        return g.centroid.distance(centroid) <= max_dist_deg
    except Exception:
        return True  # Don't discard if we can't determine


async def _query_service_for_candidates(url: str, service_title: str = "") -> List[dict]:
    """Query one ArcGIS FeatureServer URL and return all named polygon features."""
    url = url.rstrip("/")
    # If URL already ends with a layer number, append /query directly
    # e.g. .../FeatureServer/9 -> .../FeatureServer/9/query
    # otherwise default to layer 0
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
        return []

    results = []
    for feature in fc.get("features", []):
        props = feature.get("properties", {})
        name = _extract_name(props)
        if not name:
            continue
        geom = feature.get("geometry")
        if not geom or geom.get("type") not in ("Polygon", "MultiPolygon"):
            continue
        try:
            area = shape(geom).area
        except Exception:
            continue
        # Skip near-zero area features (parcels, point-like polygons) — min ~0.1 km²
        if area < 1e-5:
            continue
        # Skip purely numeric names (e.g. voting precinct "03") and
        # bare compass directions (e.g. council quadrant names like "Northeast")
        SKIP_NAMES = {"north", "south", "east", "west", "northeast", "northwest", "southeast", "southwest", "central"}
        if name.strip().lstrip("0").isdigit() or name.strip() == "0":
            continue
        if name.strip().lower() in SKIP_NAMES:
            continue
        title_lower = service_title.lower()
        service_is_downtown = (
            _contains_downtown_keyword(service_title)
            and any(kw in title_lower for kw in BOUNDARY_TITLE_KEYWORDS)
        )
        score = 1 if (service_is_downtown or _contains_downtown_keyword(name)) else 0
        results.append({"name": name, "geometry": geom, "score": score, "_area": area})
    return results


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


async def _hub_search_and_fetch(query: str, num: int = 5) -> List[dict]:
    """Search Hub API and fetch polygon features from matching datasets."""
    items = await _hub_search(query, num=num)
    best: List[dict] = []
    for item in items[:3]:
        attrs = item.get("attributes", {})
        url = (attrs.get("url") or "").strip()
        if not re.match(r"https://services\d*\.arcgis\.com/", url):
            continue
        dataset_name = attrs.get("name", "") or ""
        name_lower = dataset_name.lower()
        if any(kw in name_lower for kw in SKIP_SERVICE_KEYWORDS):
            continue
        batch = await _query_service_for_candidates(url, service_title=dataset_name)
        if any(c["score"] >= 1 for c in batch):
            return batch  # High-confidence hit — stop immediately
        if batch and not best:
            best = batch
    return best


async def _arcgis_search_and_fetch(query: str, num: int = 5) -> List[dict]:
    """Search ArcGIS Online and fetch candidates, preferring score≥1 results."""
    results = await _arcgis_search(query, num=num)
    best: List[dict] = []
    for item in results[:3]:
        url = item.get("url", "") or ""
        if not re.match(r"https://services\d*\.arcgis\.com/", url):
            continue
        title_lower = (item.get("title") or "").lower()
        if any(kw in title_lower for kw in SKIP_SERVICE_KEYWORDS):
            continue
        batch = await _query_service_for_candidates(url, service_title=item.get("title", ""))
        if any(c["score"] >= 1 for c in batch):
            return batch  # High-confidence hit — stop immediately
        if batch and not best:
            best = batch  # Keep first non-empty as fallback
    return best


async def get_candidates(city: str, state: str) -> List[dict]:
    """
    Return all named polygon features from ArcGIS for the given city/state,
    ranked by relevance (downtown keywords first, then smaller area first).

    Strategy:
      1. Hub API: parallel queries to hub.arcgis.com (fast, city-open-data focused).
      2. If no score≥1 hit, fall back to ArcGIS Online search + org-ID discovery.
      3. Geographic filter: keep only features within ~0.75° of city centroid.
      4. Fallback: single 800m buffer entry.

    Each entry: {"name": str, "geometry": GeoJSON dict, "score": int}
    score=1 → contains downtown keyword, score=0 → other, score=-1 → fallback
    """
    candidates: List[dict] = []

    # --- Stage 1: Hub API — fast, purpose-built for city open data ---
    hub_queries = [
        f"downtown {city} district",
        f"downtown {city} boundary",
        f"{city} {state} neighborhood boundary",
        f"{city} {state} neighborhoods",
        f"{city} {state} village planning",  # Phoenix-style urban villages
    ]
    hub_batches = await asyncio.gather(*[_hub_search_and_fetch(q) for q in hub_queries])
    for batch in hub_batches:
        candidates.extend(batch)

    # --- Geographic filter ---
    centroid = await _get_city_centroid(city, state)
    if candidates and centroid:
        candidates = [c for c in candidates if _is_near_city(c["geometry"], centroid)]

    # --- Stage 2: ArcGIS Online search if no high-confidence Hub results ---
    if not any(c["score"] >= 1 for c in candidates):
        logger.info(f"Hub API found no high-confidence results for {city}, {state}; trying ArcGIS Online")
        arcgis_queries = [
            f"downtown {city}",
            f"{city} {state} downtown district",
            f"{city} {state} neighborhood boundary",
        ]
        arcgis_batches = await asyncio.gather(*[_arcgis_search_and_fetch(q) for q in arcgis_queries])
        for batch in arcgis_batches:
            candidates.extend(batch)

        if candidates and centroid:
            candidates = [c for c in candidates if _is_near_city(c["geometry"], centroid)]

    # --- Stage 3: org-ID discovery if still no high-confidence results ---
    if not any(c["score"] >= 1 for c in candidates):
        broad_results = await _arcgis_search(f"{city} {state}", num=20)
        # Count all arcgis.com org IDs — the geographic filter handles off-city results.
        # Don't require city name in item title; some city orgs publish with generic titles.
        org_counts: dict = {}
        for item in broad_results:
            url = item.get("url", "") or ""
            m = re.search(r"services\d*\.arcgis\.com/([A-Za-z0-9]+)/", url)
            if m:
                oid = m.group(1)
                org_counts[oid] = org_counts.get(oid, 0) + 1

        top_orgs = sorted(org_counts.items(), key=lambda x: -x[1])[:2]
        org_queries = []
        for orgid, _ in top_orgs:
            org_queries.append(f"orgid:{orgid} (downtown OR cbd)")
            org_queries.append(f"orgid:{orgid} (boundary OR district OR neighborhood)")

        if org_queries:
            org_batches = await asyncio.gather(*[_arcgis_search_and_fetch(q, num=10) for q in org_queries])
            for batch in org_batches:
                candidates.extend(batch)

            if candidates and centroid:
                candidates = [c for c in candidates if _is_near_city(c["geometry"], centroid)]

    if not candidates:
        geom = await _fallback_city_buffer(city, state)
        return [{"name": "Estimated downtown (800m radius)", "geometry": geom, "score": -1}]

    # Deduplicate by name, sort: score desc then area asc, return top 10
    seen: set = set()
    deduped = []
    for c in candidates:
        key = c["name"].lower()
        if key not in seen:
            seen.add(key)
            deduped.append(c)

    deduped.sort(key=lambda c: (-c["score"], c["_area"]))
    return [{"name": c["name"], "geometry": c["geometry"], "score": c["score"]} for c in deduped[:10]]


async def resolve_downtown(city: str, state: str) -> dict:
    """
    Resolve a downtown boundary polygon for the given city/state.
    Returns {"geometry": GeoJSON Polygon dict, "source": "arcgis"|"fallback", "boundary_name": str|None}
    """
    result = await _try_arcgis(city, state)
    if result:
        geom, boundary_name = result
        return {"geometry": geom, "source": "arcgis", "boundary_name": boundary_name}

    geom = await _fallback_city_buffer(city, state)
    return {"geometry": geom, "source": "fallback", "boundary_name": None}
