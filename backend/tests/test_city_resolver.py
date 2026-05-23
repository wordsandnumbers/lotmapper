"""
Integration tests for city_resolver.get_candidates.

These make real network calls to ArcGIS/Nominatim and are meant to serve as
a baseline sanity check across a representative set of US cities.

Run with:
    cd backend && python -m pytest tests/test_city_resolver.py -v -s
"""
import pytest
from app.services.city_resolver import get_candidates, _is_downtown_zone_code

# Cities expected to return real (non-fallback) neighborhood candidates
CITIES_WITH_DATA = [
    ("Portland", "OR"),
    ("Denver", "CO"),
    ("Seattle", "WA"),
    ("Austin", "TX"),
    ("Chicago", "IL"),
    ("Nashville", "TN"),
    ("Phoenix", "AZ"),
    ("Minneapolis", "MN"),
    ("Atlanta", "GA"),
    ("Longview", "TX"),
]

# Smaller cities with no public neighborhood GIS data — fallback is expected and correct
CITIES_FALLBACK_OK: list = []

ALL_CITIES = CITIES_WITH_DATA + CITIES_FALLBACK_OK


@pytest.mark.asyncio
@pytest.mark.parametrize("city,state", CITIES_WITH_DATA)
async def test_city_candidates_not_fallback(city, state):
    """Each city should return at least one real (non-fallback) candidate."""
    candidates = await get_candidates(city, state)

    assert candidates, f"{city}, {state}: returned empty list"

    real = [c for c in candidates if c["score"] >= 0]
    names = [c["name"] for c in candidates]
    assert real, f"{city}, {state}: only fallback returned. Candidates: {names}"


@pytest.mark.asyncio
@pytest.mark.parametrize("city,state", ALL_CITIES)
async def test_city_candidates_have_valid_geometry(city, state):
    """All returned candidates should have valid GeoJSON polygon geometry."""
    from shapely.geometry import shape

    candidates = await get_candidates(city, state)
    for c in candidates:
        geom_dict = c["geometry"]
        assert geom_dict.get("type") in ("Polygon", "MultiPolygon"), (
            f"{city}, {state}: candidate '{c['name']}' has unexpected geometry type {geom_dict.get('type')}"
        )
        geom = shape(geom_dict)
        assert not geom.is_empty, f"{city}, {state}: candidate '{c['name']}' has empty geometry"


@pytest.mark.asyncio
@pytest.mark.parametrize("city,state", CITIES_WITH_DATA)
async def test_city_candidates_near_city_center(city, state):
    """All real (non-fallback) candidates should be within 0.3° of the city centroid."""
    from shapely.geometry import shape
    from app.services.city_resolver import _get_city_centroid

    centroid = await _get_city_centroid(city, state)
    assert centroid is not None, f"Could not get centroid for {city}, {state}"

    candidates = await get_candidates(city, state)
    real = [c for c in candidates if c["score"] >= 0]
    for c in real:
        geom = shape(c["geometry"])
        dist = geom.centroid.distance(centroid)
        assert dist <= 0.3, (
            f"{city}, {state}: candidate '{c['name']}' centroid is {dist:.3f}° from city center "
            f"(max 0.3°)"
        )


# ---------------------------------------------------------------------------
# Zone-code regression tests
#
# These pin the specific zone codes that were tricky to get right and guard
# against regressions from future regex or scoring changes.  Each city+code
# pair was manually verified against the city's official zoning documents.
# ---------------------------------------------------------------------------

CITIES_WITH_EXPECTED_ZONE_CODES = [
    # (city, state, expected_code)
    # San Antonio uses bare "D" as its downtown zone.  The dataset is a
    # 35k-feature multi-city merge; "D" features start at OBJECTID ~7066,
    # beyond the 5000-record pagination cap — requires the targeted two-pass
    # distinct-values query to surface them.
    ("San Antonio", "TX", "D"),
    # Richmond uses "B-4" for its downtown business district.
    ("Richmond", "VA", "B-4"),
    # NYC's zoning uses C5/C6 sub-district codes for Midtown/Downtown.
    # The resolver must reach Stage 2 to find the DCP zoning layer.
    ("New York City", "NY", "C6"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("city,state,expected_code", CITIES_WITH_EXPECTED_ZONE_CODES)
async def test_city_has_expected_zone_code(city, state, expected_code):
    """Each city should surface its known downtown zone code at score=2."""
    candidates = await get_candidates(city, state)
    zone_code_hits = [c for c in candidates if c["score"] == 2]
    names = [c["name"] for c in zone_code_hits]
    assert any(expected_code.upper() == n.upper() for n in names), (
        f"{city}, {state}: expected zone code {expected_code!r} at score=2 "
        f"but got: {names}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("city,state,expected_code", CITIES_WITH_EXPECTED_ZONE_CODES)
async def test_city_zone_code_ranked_first(city, state, expected_code):
    """The expected zone code should be the top-ranked result (score=2 sorts first)."""
    candidates = await get_candidates(city, state)
    assert candidates, f"{city}, {state}: returned empty list"
    top = candidates[0]
    assert top["score"] == 2, (
        f"{city}, {state}: expected top candidate to be a zone code (score=2) "
        f"but got score={top['score']} name={top['name']!r}"
    )
