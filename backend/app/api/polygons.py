from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from geoalchemy2.functions import ST_AsGeoJSON
from shapely.geometry import shape, LineString, mapping
from shapely.ops import split
import json

from app.database import get_db
from app.models.user import User
from app.models.project import Project
from app.models.polygon import Polygon, PolygonHistory
from app.schemas.polygon import (
    PolygonCreate,
    PolygonResponse,
    PolygonUpdate,
    PolygonSplit,
    GeoJSONFeature,
    GeoJSONFeatureCollection,
)
from app.api.deps import get_current_active_user

router = APIRouter()


def polygon_to_response(polygon: Polygon, db: Session) -> PolygonResponse:
    """Convert polygon model to response with GeoJSON geometry."""
    geom_geojson = db.execute(func.ST_AsGeoJSON(polygon.geometry)).scalar()

    return PolygonResponse(
        id=polygon.id,
        project_id=polygon.project_id,
        geometry=json.loads(geom_geojson) if geom_geojson else {},
        properties=polygon.properties or {},
        status=polygon.status,
        created_at=polygon.created_at,
        updated_at=polygon.updated_at,
        edited_by=polygon.edited_by,
    )


def geojson_to_wkt(geojson: dict) -> str:
    """Convert GeoJSON geometry to WKT with SRID."""
    geom = shape(geojson)
    return f"SRID=4326;{geom.wkt}"


def record_history(db: Session, polygon: Polygon, action: str, user_id: UUID, previous_geom=None):
    """Record polygon edit history."""
    history = PolygonHistory(
        polygon_id=polygon.id,
        action=action,
        previous_geometry=previous_geom,
        user_id=user_id,
    )
    db.add(history)


@router.get("/project/{project_id}", response_model=GeoJSONFeatureCollection)
async def get_project_polygons(
    project_id: UUID,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get all polygons for a project as GeoJSON FeatureCollection."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    query = db.query(Polygon).filter(Polygon.project_id == project_id)
    if not include_deleted:
        query = query.filter(Polygon.status != "deleted")

    polygons = query.all()

    features = []
    for polygon in polygons:
        geom_geojson = db.execute(func.ST_AsGeoJSON(polygon.geometry)).scalar()
        features.append(GeoJSONFeature(
            id=str(polygon.id),
            geometry=json.loads(geom_geojson),
            properties={
                **(polygon.properties or {}),
                "status": polygon.status,
                "polygon_id": str(polygon.id),
            },
        ))

    return GeoJSONFeatureCollection(features=features)


@router.post("/project/{project_id}", response_model=PolygonResponse)
async def create_polygon(
    project_id: UUID,
    polygon_data: PolygonCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a new polygon in a project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    geom_wkt = geojson_to_wkt(polygon_data.geometry.model_dump())

    polygon = Polygon(
        project_id=project_id,
        geometry=geom_wkt,
        properties=polygon_data.properties,
        status="edited",  # Manually added polygons are marked as edited
        edited_by=current_user.id,
    )
    db.add(polygon)
    db.commit()
    db.refresh(polygon)

    record_history(db, polygon, "create", current_user.id)
    db.commit()

    return polygon_to_response(polygon, db)


@router.get("/{polygon_id}", response_model=PolygonResponse)
async def get_polygon(
    polygon_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get a polygon by ID."""
    polygon = db.query(Polygon).filter(Polygon.id == polygon_id).first()
    if not polygon:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Polygon not found",
        )
    return polygon_to_response(polygon, db)


@router.patch("/{polygon_id}", response_model=PolygonResponse)
async def update_polygon(
    polygon_id: UUID,
    polygon_update: PolygonUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update a polygon (geometry, properties, or status)."""
    polygon = db.query(Polygon).filter(Polygon.id == polygon_id).first()
    if not polygon:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Polygon not found",
        )

    # Store previous geometry for history
    previous_geom = polygon.geometry

    if polygon_update.geometry is not None:
        polygon.geometry = geojson_to_wkt(polygon_update.geometry.model_dump())
        polygon.status = "edited"
        polygon.edited_by = current_user.id
        record_history(db, polygon, "edit", current_user.id, previous_geom)

    if polygon_update.properties is not None:
        polygon.properties = {**(polygon.properties or {}), **polygon_update.properties}

    if polygon_update.status is not None:
        polygon.status = polygon_update.status

    db.commit()
    db.refresh(polygon)
    return polygon_to_response(polygon, db)


@router.delete("/{polygon_id}")
async def delete_polygon(
    polygon_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Soft delete a polygon."""
    polygon = db.query(Polygon).filter(Polygon.id == polygon_id).first()
    if not polygon:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Polygon not found",
        )

    polygon.status = "deleted"
    polygon.edited_by = current_user.id
    record_history(db, polygon, "delete", current_user.id, polygon.geometry)
    db.commit()

    return {"message": "Polygon deleted"}


@router.post("/{polygon_id}/split", response_model=List[PolygonResponse])
async def split_polygon(
    polygon_id: UUID,
    split_data: PolygonSplit,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Split a polygon into two using a line."""
    polygon = db.query(Polygon).filter(Polygon.id == polygon_id).first()
    if not polygon:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Polygon not found",
        )

    # Get current geometry as shapely
    geom_geojson = db.execute(func.ST_AsGeoJSON(polygon.geometry)).scalar()
    poly_shape = shape(json.loads(geom_geojson))

    # Create split line (extended to ensure it crosses the polygon)
    line = LineString([split_data.line_start, split_data.line_end])
    # Extend line to ensure it crosses the polygon
    scale_factor = 10  # Scale to make sure line extends beyond polygon
    x1, y1 = split_data.line_start
    x2, y2 = split_data.line_end
    dx, dy = x2 - x1, y2 - y1
    extended_line = LineString([
        (x1 - dx * scale_factor, y1 - dy * scale_factor),
        (x2 + dx * scale_factor, y2 + dy * scale_factor),
    ])

    # Split the polygon
    try:
        result = split(poly_shape, extended_line)
        if len(result.geoms) < 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Split line does not divide the polygon",
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to split polygon: {str(e)}",
        )

    # Mark original as deleted
    polygon.status = "deleted"
    polygon.edited_by = current_user.id
    record_history(db, polygon, "split", current_user.id, polygon.geometry)

    # Create new polygons
    new_polygons = []
    for geom in result.geoms:
        if geom.geom_type == "Polygon":
            new_poly = Polygon(
                project_id=polygon.project_id,
                geometry=f"SRID=4326;{geom.wkt}",
                properties=polygon.properties.copy() if polygon.properties else {},
                status="edited",
                edited_by=current_user.id,
            )
            db.add(new_poly)
            db.flush()  # Get ID
            record_history(db, new_poly, "create", current_user.id)
            new_polygons.append(new_poly)

    db.commit()

    return [polygon_to_response(p, db) for p in new_polygons]
