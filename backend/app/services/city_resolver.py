import asyncio
import logging
import re
from collections import defaultdict
from typing import Optional, Tuple, List, Any, Callable
import httpx
from shapely.geometry import shape, Point, mapping
from shapely.ops import transform, unary_union
from app.services.osm import _to_3857, _to_4326

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_HEADERS = {"User-Agent": "ParkingLotApp/1.0 (parking-lot-inference)"}

DOWNTOWN_KEYWORDS = {
    "downtown", "cbd", "central business", "city center", "urban core",
    "commercial core", "mixed use", "urban village",
}
BOUNDARY_TITLE_KEYWORDS = {
    "district", "districts", "boundary", "boundaries", "plan",
    "zone", "zones", "zoning", "area", "areas",
    "neighborhood", "neighbourhoods", "quarter",
}
SKIP_SERVICE_KEYWORDS = {"school", "voting", "election", "precinct", "parcel", "address", "building", "permit", "buffer", "parking"}

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
    "subdist", "SUBDIST", "sub_dist", "SUB_DIST",
    "downtown_districts", "DOWNTOWN_DISTRICTS",
    "area_name", "AREA_NAME",
    "comm_name", "COMM_NAME",           # community name
    "placename", "PLACENAME",
    "spa_name", "SPA_NAME",              # Cleveland Strategic Planning Area
    "common_name", "CommonName",         # Lubbock Design Districts
    "detail_name", "DetailName",         # Lubbock Design Districts sub-code
)

# Fields used in zoning datasets to identify zone type/code
ZONE_FIELDS = (
    "zone_desc", "ZONE_DESC",
    "zone_name", "ZONE_NAME",
    "zone_type", "ZONE_TYPE",
    "zoning_type", "ZONING_TYPE",
    "zoning_code", "ZONING_CODE",
    "zone_class", "ZONE_CLASS",
    "zone_code", "ZONE_CODE",
    "zonecode", "ZONECODE",
    "zonedist", "ZONEDIST",
    "zoningdist", "ZoningDist",          # Lubbock UDC zoning description
    "zoningactual", "ZoningActual",      # Lubbock UDC zone code
    "zoneabbr", "ZONEABBR",
    "zone", "ZONE",
    "zoning", "ZONING",
    "land_use", "LAND_USE",
    "landuse", "LANDUSE",
    "lu_type", "LU_TYPE",
)


# Zone code patterns that indicate downtown/high-density commercial zones.
# Applied as a fullmatch against individual whitespace/slash-delimited tokens so that
# composite codes like "GR-D4" are not matched on their "D4" suffix.
_DOWNTOWN_ZONE_TOKEN_RE = re.compile(
    r"^("
    r"CBD"                          # Central Business District (very common)
    r"|DT-?\d*"                     # DT, DT-1, DT1
    r"|D-?\d+"                      # D1, D-1, D5 (standalone downtown districts)
    r"|MX-?[3-9]"                   # MX-3 through MX-9 (high-density mixed use)
    r"|C-?[5-9]"                    # C-5, C5, C6 (commercial core)
    r"|B-?[4-9]"                    # B-4, B4 (high-density business)
    r"|CMX-?[3-9]"                  # CMX-3 (Philadelphia commercial mixed-use)
    r"|CB-?\d+"                     # CB-1…CB-6 (Lubbock/other Central Business sub-zones)
    r"|UC-?\d*"                     # Urban Core
    r"|CC-?\d*"                     # Commercial Core
    r")$",
    re.IGNORECASE,
)

_UUID_RE = re.compile(
    r"^[{(]?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}[)}]?$",
    re.IGNORECASE,
)


def _contains_downtown_keyword(text: str) -> bool:
    t = text.lower()
    return any(kw in t for kw in DOWNTOWN_KEYWORDS)


def _is_downtown_zone_code(text: str) -> bool:
    """Return True if text contains a standalone downtown zone code token.
    Splits on whitespace and forward-slashes only (not hyphens) so that
    compound codes like 'GR-D4' are not matched via their '-D4' suffix."""
    for token in re.split(r"[\s/,;()\[\]]+", text):
        if token and _DOWNTOWN_ZONE_TOKEN_RE.match(token.strip()):
            return True
    return False


# Pre-computed lowercase versions for case-insensitive matching
_NAME_FIELDS_LOWER = tuple(dict.fromkeys(f.lower() for f in (*NAME_FIELDS, *ZONE_FIELDS)))


def _extract_name(props: dict) -> Optional[str]:
    """Pull the best name value out of a feature's properties (case-insensitive).
    Falls back to zone fields for zoning datasets."""
    lower_props = {k.lower(): v for k, v in props.items()}
    for field in _NAME_FIELDS_LOWER:
        val = lower_props.get(field)
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


def _safe_area(geom_dict: dict) -> float:
    try:
        return shape(geom_dict).area
    except Exception:
        return 0.0


async def _get_service_layer_urls(base_url: str) -> List[str]:
    """Fetch FeatureServer metadata and return URLs for all polygon Feature Layers.
    Falls back to /0 if metadata is unavailable."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(base_url, params={"f": "json"})
            r.raise_for_status()
            meta = r.json()
        layers = [
            l for l in meta.get("layers", [])
            if l.get("id") is not None
            and l.get("type") == "Feature Layer"
            and l.get("geometryType", "esriGeometryPolygon") == "esriGeometryPolygon"
        ]
        if layers:
            return [f"{base_url}/{l['id']}" for l in layers[:5]]
    except Exception as e:
        logger.debug(f"Service metadata fetch failed for {base_url}: {e}")
    return [f"{base_url}/0"]


async def _query_service_for_candidates(url: str, service_title: str = "") -> List[dict]:
    """Query one ArcGIS FeatureServer URL and return all named polygon features."""
    url = url.rstrip("/")

    # If URL already ends with a layer number use it directly; otherwise discover
    # the actual layer IDs from service metadata (many services don't use layer 0).
    if re.search(r"/\d+$", url):
        layer_urls = [url]
    else:
        layer_urls = await _get_service_layer_urls(url)

    all_features: List[dict] = []
    for layer_url in layer_urls:
        query_url = layer_url + "/query"
        page_size = 1000
        offset = 0
        while True:
            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    r = await client.get(
                        query_url,
                        params={
                            "where": "1=1",
                            "outFields": "*",
                            "returnGeometry": "true",
                            "resultRecordCount": page_size,
                            "resultOffset": offset,
                            "f": "geojson",
                        },
                    )
                    r.raise_for_status()
                    fc = r.json()
                page_features = fc.get("features", [])
                all_features.extend(page_features)
                # Only paginate if we got a full page AND total is small enough to be worth it
                if len(page_features) == page_size and len(all_features) < 5000:
                    offset += page_size
                else:
                    break
            except Exception as e:
                logger.debug(f"ArcGIS feature fetch failed for {layer_url} offset={offset}: {e}")
                break

    if not all_features:
        return []

    SKIP_NAMES = {"north", "south", "east", "west", "northeast", "northwest", "southeast", "southwest", "central"}
    title_lower = service_title.lower()
    service_is_downtown = (
        _contains_downtown_keyword(service_title)
        and any(kw in title_lower for kw in BOUNDARY_TITLE_KEYWORDS)
    )

    # Only fall back to the service title as name for small-feature services.
    # Count only features with valid polygon geometry above the minimum area
    # threshold — tiny parcel layers in the same FeatureServer inflate the count
    # and would otherwise suppress the fallback for purpose-built boundary layers
    # (e.g. a BID polygon in layer 1 alongside parcel records in layer 2).
    valid_area_count = sum(
        1 for f in all_features
        if (f.get("geometry") or {}).get("type") in ("Polygon", "MultiPolygon")
        and _safe_area(f["geometry"]) >= 1e-5
    )
    allow_title_fallback = valid_area_count <= 5

    raw = []
    for feature in all_features:
        props = feature.get("properties", {})
        name = _extract_name(props)
        if not name and allow_title_fallback and service_title:
            name = service_title.replace("_", " ")
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
        # Skip purely numeric names (e.g. voting precinct "03") and bare compass directions
        if name.strip().lstrip("0").isdigit() or name.strip() == "0":
            continue
        if name.strip().lower() in SKIP_NAMES:
            continue
        # Score on ALL property values + normalized service title.
        # Including the title catches services like "Honolulu_DT_Proposed_BID_WFL1"
        # whose features have no text properties but whose title signals downtown.
        all_props_text = " ".join(
            str(v) for v in props.values()
            if v and isinstance(v, str) and not _UUID_RE.match(v.strip())
        )
        normalized_title = service_title.replace("_", " ")
        all_text = f"{all_props_text} {normalized_title}".strip()
        score = 1 if (
            service_is_downtown
            or _contains_downtown_keyword(all_text)
            or _is_downtown_zone_code(all_text)
        ) else 0
        raw.append({"name": name, "geometry": geom, "score": score, "_area": area})

    if not raw:
        return []

    # Union features that share the same name — handles zoning datasets where dozens of
    # individual parcels all carry the same zone code (e.g. "CBD").
    groups: dict = defaultdict(list)
    for r in raw:
        groups[r["name"].lower()].append(r)

    results = []
    for group in groups.values():
        if len(group) == 1:
            results.append(group[0])
        else:
            try:
                merged = unary_union([shape(r["geometry"]) for r in group])
                best = max(group, key=lambda r: r["score"])
                results.append({
                    "name": best["name"],
                    "geometry": mapping(merged),
                    "score": best["score"],
                    "_area": merged.area,
                })
            except Exception:
                results.append(group[0])  # fallback: keep first

    return results


async def _get_city_portal_org_id(city: str) -> Optional[str]:
    """Try common ArcGIS portal URL patterns to directly discover a city's org ID.
    Returns org ID string if found, else None."""
    city_slug = city.lower().replace(" ", "")
    candidates = [
        f"https://cityof{city_slug}.maps.arcgis.com",
        f"https://{city_slug}.maps.arcgis.com",
        f"https://{city_slug}gis.maps.arcgis.com",
    ]
    for base in candidates:
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                r = await client.get(f"{base}/sharing/rest/portals/self", params={"f": "json"})
                if r.status_code == 200:
                    data = r.json()
                    org_id = data.get("id")
                    if org_id:
                        logger.debug(f"Found city portal org {org_id} via {base}")
                        return org_id
        except Exception:
            pass
    return None


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


def _is_arcgis_service_url(url: str) -> bool:
    """Return True if the URL looks like a queryable ArcGIS FeatureServer or MapServer endpoint."""
    if not url or not url.startswith("https://"):
        return False
    # Hosted ArcGIS Online services
    if re.match(r"https://services\d*\.arcgis\.com/", url):
        return True
    # Self-hosted city/county ArcGIS servers (e.g. www.clevelandgis.org/arcgis/...)
    if re.search(r"/arcgis/rest/services/.+/(Feature|Map)Server", url):
        return True
    return False


async def _hub_search_and_fetch(query: str, num: int = 5) -> List[dict]:
    """Search Hub API and fetch polygon features from matching datasets."""
    items = await _hub_search(query, num=num)
    best: List[dict] = []
    for item in items[:5]:
        attrs = item.get("attributes", {})
        url = (attrs.get("url") or "").strip()
        if not _is_arcgis_service_url(url):
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
    for item in results[:5]:
        url = item.get("url", "") or ""
        if not _is_arcgis_service_url(url):
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
    Return all named polygon features from ArcGIS for the given city/state,
    ranked by relevance (downtown keywords first, then smaller area first).

    Strategy:
      1. Hub API: parallel queries to hub.arcgis.com (fast, city-open-data focused).
      2. If no score≥1 hit, fall back to ArcGIS Online search + org-ID discovery.
      3. Geographic filter: keep only features within ~0.75° of city centroid.
      4. Fallback: single 800m buffer entry.

    Each entry: {"name": str, "geometry": GeoJSON dict, "score": int, "source": str}
    score=1 → contains downtown keyword, score=0 → other, score=-1 → fallback
    """
    candidates: List[dict] = []

    # --- Stage 1: Hub API ---
    await _emit(progress_cb, f"Searching ArcGIS Hub for {city}, {state}...")
    hub_queries = [
        f"downtown {city} district",
        f"downtown {city} boundary",
        f"{city} {state} neighborhood boundary",
        f"{city} {state} neighborhoods",
        f"{city} {state} village planning",  # Phoenix-style urban villages
        f"{city} {state} zoning districts",
        f"{city} {state} zoning",
    ]
    hub_batches = await asyncio.gather(*[_hub_search_and_fetch(q) for q in hub_queries])
    for batch in hub_batches:
        _tag_source(batch, "arcgis_hub")
        candidates.extend(batch)

    # --- Geographic filter ---
    centroid = await _get_city_centroid(city, state)
    if candidates and centroid:
        candidates = [c for c in candidates if _is_near_city(c["geometry"], centroid)]

    high_conf = [c for c in candidates if c["score"] >= 1]
    if high_conf:
        await _emit(progress_cb, f"Found {len(high_conf)} downtown boundary match{'es' if len(high_conf) != 1 else ''}")
    elif candidates:
        await _emit(progress_cb, f"Found {len(candidates)} nearby area{'s' if len(candidates) != 1 else ''}, no exact downtown match")

    # --- Stage 2: ArcGIS Online search if no high-confidence results ---
    if not any(c["score"] >= 1 for c in candidates):
        await _emit(progress_cb, "Trying ArcGIS Online search...")
        arcgis_queries = [
            f"downtown {city}",
            f"{city} {state} downtown district",
            f"{city} {state} neighborhood boundary",
            f"{city} {state} zoning districts",
        ]
        arcgis_batches = await asyncio.gather(*[_arcgis_search_and_fetch(q) for q in arcgis_queries])
        for batch in arcgis_batches:
            _tag_source(batch, "arcgis_online")
            candidates.extend(batch)

        if candidates and centroid:
            candidates = [c for c in candidates if _is_near_city(c["geometry"], centroid)]

    # --- Stage 3: org-ID discovery if still no high-confidence results ---
    if not any(c["score"] >= 1 for c in candidates):
        await _emit(progress_cb, "Discovering city organization datasets...")
        # Run broad searches and direct portal lookup in parallel.
        # The portal lookup tries common ArcGIS portal URL patterns (e.g.
        # cityoflubbock.maps.arcgis.com) to get the official city org ID directly —
        # this bypasses the search-result noise from academic/research orgs that
        # happen to publish datasets mentioning the city name.
        broad_arcgis, broad_hub, portal_org_id = await asyncio.gather(
            _arcgis_search(f"{city} {state}", num=20),
            _hub_search(f"{city} {state}", num=15),
            _get_city_portal_org_id(city),
        )
        # Count arcgis.com org IDs, weighting items whose title contains the city name
        # more heavily. This prevents generic academic/research orgs that happen to
        # publish datasets mentioning the city name from outranking the actual city org.
        city_lower = city.lower()
        org_counts: dict = {}
        for item in broad_arcgis:
            url = item.get("url", "") or ""
            m = re.search(r"services\d*\.arcgis\.com/([A-Za-z0-9]+)/", url)
            if m:
                oid = m.group(1)
                title = (item.get("title") or "").lower()
                weight = 3 if city_lower in title else 1
                org_counts[oid] = org_counts.get(oid, 0) + weight
        for item in broad_hub:
            url = (item.get("attributes", {}).get("url") or "").strip()
            m = re.search(r"services\d*\.arcgis\.com/([A-Za-z0-9]+)/", url)
            if m:
                oid = m.group(1)
                title = (item.get("attributes", {}).get("name") or "").lower()
                weight = 3 if city_lower in title else 1
                org_counts[oid] = org_counts.get(oid, 0) + weight

        # If we found the city's official portal, boost its org to the front.
        if portal_org_id:
            org_counts[portal_org_id] = org_counts.get(portal_org_id, 0) + 100

        top_orgs = sorted(org_counts.items(), key=lambda x: -x[1])[:2]
        org_queries = []
        for orgid, _ in top_orgs:
            org_queries.append(f"orgid:{orgid} (downtown OR cbd)")
            org_queries.append(f"orgid:{orgid} (boundary OR district OR neighborhood)")
            org_queries.append(f"orgid:{orgid} (zoning OR zones)")

        if org_queries:
            org_batches = await asyncio.gather(*[_arcgis_search_and_fetch(q, num=10) for q in org_queries])
            for batch in org_batches:
                _tag_source(batch, "arcgis_online")
                candidates.extend(batch)

            if candidates and centroid:
                candidates = [c for c in candidates if _is_near_city(c["geometry"], centroid)]

    if not candidates:
        await _emit(progress_cb, "No boundaries found, using approximate downtown area")
        geom = await _fallback_city_buffer(city, state)
        return [{"name": "Estimated downtown (800m radius)", "geometry": geom, "score": -1, "source": "fallback"}]

    # Deduplicate by name, sort: score desc then area asc, return top 10
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
        for c in deduped[:10]
    ]


async def resolve_downtown(city: str, state: str) -> dict:
    """
    Resolve a downtown boundary polygon for the given city/state.
    Returns {"geometry": GeoJSON Polygon dict, "source": str, "boundary_name": str|None}
    """
    candidates = await get_candidates(city, state)
    top = candidates[0] if candidates else None
    if top and top["score"] >= 0:
        return {
            "geometry": top["geometry"],
            "source": top.get("source", "arcgis_hub"),
            "boundary_name": top["name"],
        }

    geom = await _fallback_city_buffer(city, state)
    return {"geometry": geom, "source": "fallback", "boundary_name": None}
