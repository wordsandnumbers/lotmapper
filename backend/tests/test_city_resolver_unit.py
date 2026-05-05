"""
Unit tests for city_resolver helper functions.

These tests make no network calls and run in milliseconds.
They document the exact contracts of the pure-logic helpers so that
regex or scoring changes don't silently break known-good cities.
"""
import pytest
from shapely.geometry import Point, mapping
from shapely.geometry.polygon import Polygon

from app.services.city_resolver import (
    _is_downtown_zone_code,
    _contains_downtown_keyword,
    _extract_name,
    _detect_zone_field,
    _is_near_city,
)


# ---------------------------------------------------------------------------
# _is_downtown_zone_code
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("code", [
    "CBD",                 # Central Business District
    "DT",                  # DT (bare)
    "DT-1",                # DT with hyphen+digit
    "DT1",                 # DT without hyphen
    "D",                   # San Antonio bare "D"
    "D1",
    "D-1",
    "D5",
    "MX-3",                # High-density mixed-use lower bound
    "MX-9",                # High-density mixed-use upper bound
    "C5",                  # NYC / other high-density commercial
    "C-5",
    "C6",
    "C-6",
    "C6-4",                # NYC sub-district (e.g. C6-4)
    "C6-3X",               # NYC sub-district with letter suffix
    "B-4",                 # Richmond downtown business (lower bound)
    "B4",
    "B-9",                 # Upper bound
    "CMX-3",               # Philadelphia commercial mixed-use
    "CMX-9",
    "CB-1",                # Lubbock central business sub-zones
    "CB-6",
    "UC",                  # Urban Core (bare)
    "UC-1",
    "CC",                  # Commercial Core (bare)
    "CC-2",
])
def test_is_downtown_zone_code_true(code):
    assert _is_downtown_zone_code(code), f"Expected {code!r} to be a downtown zone code"


@pytest.mark.parametrize("code", [
    "DR",          # Not a downtown district — "DR" could be Drive, Drainage, etc.
    "AG",          # Agricultural
    "AG/ETJ",      # San Antonio agricultural / ETJ
    "B-3",         # Below the B-4 threshold
    "B3",
    "C4",          # Below C5 threshold
    "C-4",
    "MX-2",        # Below MX-3 threshold
    "NC",          # Neighborhood Commercial
    "MU",          # Mixed-Use (generic — too low density)
    "R-4",         # Residential
    "O-1",         # Office
    "O-2",
    "SUP",         # Special Use Permit overlay
    "GR-D4",       # Compound code: "GR" zone with "D4" suffix — must NOT match on suffix
    "DT-X",        # DT variant with letter, not digit
])
def test_is_downtown_zone_code_false(code):
    assert not _is_downtown_zone_code(code), f"Expected {code!r} NOT to be a downtown zone code"


def test_is_downtown_zone_code_compound_code_not_matched_on_suffix():
    """A compound code like 'GR-D4' should not match just because it contains 'D4'.
    The function splits on whitespace/slashes, not hyphens — 'GR-D4' is one token."""
    assert not _is_downtown_zone_code("GR-D4")


def test_is_downtown_zone_code_multi_token_string():
    """A string containing a downtown code among other tokens should return True."""
    assert _is_downtown_zone_code("Zone CBD boundary")
    assert _is_downtown_zone_code("B-4 / B-5")


# ---------------------------------------------------------------------------
# _contains_downtown_keyword
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Downtown District",
    "downtown austin",
    "Central Business District",
    "City Center Plan",
    "Urban Core Overlay",
    "Commercial Core Zone",
    "Mixed Use District",    # "mixed use" is a keyword
    "Urban Village",
])
def test_contains_downtown_keyword_true(text):
    assert _contains_downtown_keyword(text), f"Expected downtown keyword in {text!r}"


@pytest.mark.parametrize("text", [
    "Residential Zone",
    "Agricultural District",
    "Parking Overlay",
    "School Zone",
    "Voting Precinct 03",
])
def test_contains_downtown_keyword_false(text):
    assert not _contains_downtown_keyword(text), f"Expected no downtown keyword in {text!r}"


# ---------------------------------------------------------------------------
# _extract_name
# ---------------------------------------------------------------------------

def test_extract_name_prefers_name_over_zone():
    props = {"name": "Downtown District", "zone": "C6"}
    assert _extract_name(props) == "Downtown District"


def test_extract_name_falls_back_to_zone_field():
    """When no name-type field is present, zone fields are used as the name."""
    props = {"zone": "CBD", "objectid": "42"}
    assert _extract_name(props) == "CBD"


def test_extract_name_case_insensitive_keys():
    """Field lookup should be case-insensitive."""
    assert _extract_name({"ZONE_NAME": "B-4"}) == "B-4"
    assert _extract_name({"Zone_Name": "CBD"}) == "CBD"
    assert _extract_name({"NAME": "Midtown"}) == "Midtown"


def test_extract_name_strips_whitespace():
    assert _extract_name({"name": "  Midtown  "}) == "Midtown"


def test_extract_name_skips_blank_values():
    assert _extract_name({"name": "", "zone": "D"}) == "D"
    assert _extract_name({"name": "   ", "zone": "D"}) == "D"


def test_extract_name_returns_none_when_empty():
    assert _extract_name({}) is None
    assert _extract_name({"objectid": 1, "shape_area": 1234.5}) is None


def test_extract_name_nbhd_name_field():
    """Denver-style nbhd_name field should be found."""
    assert _extract_name({"nbhd_name": "Five Points"}) == "Five Points"


def test_extract_name_district_name_field():
    assert _extract_name({"district_name": "Capitol Hill"}) == "Capitol Hill"


# ---------------------------------------------------------------------------
# _detect_zone_field
# ---------------------------------------------------------------------------

def test_detect_zone_field_finds_zone():
    features = [{"properties": {"OBJECTID": 1, "Zone": "D", "Shape_Area": 9999}}]
    assert _detect_zone_field(features) == "Zone"


def test_detect_zone_field_finds_zonedist():
    features = [{"properties": {"OBJECTID": 1, "ZONEDIST": "C6-3", "SHAPE_AREA": 100}}]
    assert _detect_zone_field(features) == "ZONEDIST"


def test_detect_zone_field_finds_zoning_code():
    features = [{"properties": {"zoning_code": "CBD"}}]
    assert _detect_zone_field(features) == "zoning_code"


def test_detect_zone_field_returns_none_for_non_zone_dataset():
    features = [{"properties": {"OBJECTID": 1, "NAME": "Precinct 5", "VOTES": 1234}}]
    assert _detect_zone_field(features) is None


def test_detect_zone_field_empty_input():
    assert _detect_zone_field([]) is None


def test_detect_zone_field_checks_multiple_features():
    """Should find zone field even if first feature lacks it."""
    features = [
        {"properties": {"OBJECTID": 1}},
        {"properties": {"OBJECTID": 2, "ZONE": "AG"}},
    ]
    assert _detect_zone_field(features) == "ZONE"


# ---------------------------------------------------------------------------
# _is_near_city
# ---------------------------------------------------------------------------

def _square(cx, cy, size=0.1):
    """Helper: make a square polygon centred at (cx, cy)."""
    half = size / 2
    coords = [
        (cx - half, cy - half), (cx + half, cy - half),
        (cx + half, cy + half), (cx - half, cy + half),
        (cx - half, cy - half),
    ]
    return mapping(Polygon(coords))


def test_is_near_city_close():
    centroid = Point(-98.49, 29.42)   # San Antonio
    geom = _square(-98.49, 29.42)     # Same spot
    assert _is_near_city(geom, centroid)


def test_is_near_city_within_threshold():
    centroid = Point(-98.49, 29.42)
    geom = _square(-98.49 + 0.25, 29.42 + 0.05)  # 0.26° away — within 0.3°
    assert _is_near_city(geom, centroid)


def test_is_near_city_too_far():
    centroid = Point(-98.49, 29.42)   # San Antonio
    geom = _square(-74.0, 40.7)       # New York
    assert not _is_near_city(geom, centroid)


def test_is_near_city_just_outside_threshold():
    centroid = Point(0.0, 0.0)
    geom = _square(0.35, 0.0)         # 0.35° away, default threshold is 0.3°
    assert not _is_near_city(geom, centroid)
