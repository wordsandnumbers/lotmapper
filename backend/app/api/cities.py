import json
import logging
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from shapely.geometry import shape
from shapely.validation import make_valid

from app.database import get_db
from app.models.user import User
from app.models.city_boundary import CityBoundary
from app.api.deps import get_current_active_user
from app.services.city_resolver import resolve_downtown, get_candidates

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/candidates")
async def get_city_candidates(
    city: str = Query(..., min_length=1),
    state: str = Query(..., min_length=2, max_length=2),
    current_user: User = Depends(get_current_active_user),
):
    """Return all candidate boundary polygons for a US city, ranked by relevance."""
    city_norm = city.strip().title()
    state_norm = state.strip().upper()
    candidates = await get_candidates(city_norm, state_norm)
    return {"candidates": candidates}


@router.get("/resolve")
async def resolve_city(
    city: str = Query(..., min_length=1),
    state: str = Query(..., min_length=2, max_length=2),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Resolve a downtown boundary polygon for a US city."""
    city_norm = city.strip().title()
    state_norm = state.strip().upper()

    # Check cache (case-insensitive)
    cached = (
        db.query(CityBoundary)
        .filter(
            func.lower(CityBoundary.city) == city_norm.lower(),
            func.lower(CityBoundary.state) == state_norm.lower(),
        )
        .first()
    )
    if cached:
        geojson_str = db.execute(func.ST_AsGeoJSON(cached.geometry)).scalar()
        return {
            "city": cached.city,
            "state": cached.state,
            "source": cached.source,
            "boundary_name": cached.boundary_name,
            "geometry": json.loads(geojson_str),
            "cached": True,
        }

    # Resolve fresh
    result = await resolve_downtown(city_norm, state_norm)
    geom_dict = result["geometry"]
    source = result["source"]
    boundary_name = result.get("boundary_name")

    # Validate and fix geometry
    shapely_geom = shape(geom_dict)
    if not shapely_geom.is_valid:
        shapely_geom = make_valid(shapely_geom)

    # Ensure it's a single Polygon (take largest if MultiPolygon)
    if shapely_geom.geom_type == "MultiPolygon":
        shapely_geom = max(shapely_geom.geoms, key=lambda g: g.area)

    wkt = f"SRID=4326;{shapely_geom.wkt}"

    # Store in cache
    record = CityBoundary(
        city=city_norm,
        state=state_norm,
        geometry=wkt,
        source=source,
        boundary_name=boundary_name,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    geojson_str = db.execute(func.ST_AsGeoJSON(record.geometry)).scalar()
    return {
        "city": city_norm,
        "state": state_norm,
        "source": source,
        "boundary_name": boundary_name,
        "geometry": json.loads(geojson_str),
        "cached": False,
    }
