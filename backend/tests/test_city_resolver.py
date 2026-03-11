"""
Integration tests for city_resolver.get_candidates.

These make real network calls to ArcGIS/Nominatim and are meant to serve as
a baseline sanity check across a representative set of US cities.

Run with:
    cd backend && python -m pytest tests/test_city_resolver.py -v -s
"""
import pytest
from app.services.city_resolver import get_candidates

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
