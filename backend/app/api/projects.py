from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from geoalchemy2.functions import ST_AsGeoJSON, ST_GeomFromGeoJSON
from shapely.geometry import box, mapping
import json

from app.database import get_db
from app.models.user import User
from app.models.project import Project
from app.models.polygon import Polygon
from app.schemas.project import (
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
    ProjectListResponse,
)
from app.api.deps import get_current_active_user

router = APIRouter()


def bounds_to_polygon_wkt(bounds) -> str:
    """Convert bounding box to WKT polygon string."""
    polygon = box(bounds.min_lng, bounds.min_lat, bounds.max_lng, bounds.max_lat)
    return f"SRID=4326;{polygon.wkt}"


def project_to_response(project: Project, db: Session) -> ProjectResponse:
    """Convert project model to response with GeoJSON bounds."""
    # Get bounds as GeoJSON
    bounds_geojson = db.execute(
        func.ST_AsGeoJSON(project.bounds)
    ).scalar()

    # Count polygons
    polygon_count = db.query(Polygon).filter(
        Polygon.project_id == project.id,
        Polygon.status != "deleted"
    ).count()

    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        bounds=json.loads(bounds_geojson) if bounds_geojson else {},
        status=project.status,
        created_by=project.created_by,
        approved_by=project.approved_by,
        created_at=project.created_at,
        updated_at=project.updated_at,
        polygon_count=polygon_count,
    )


@router.post("", response_model=ProjectResponse)
async def create_project(
    project_data: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a new project with a bounding box or polygon."""
    if project_data.bounds_polygon:
        from shapely.geometry import shape
        poly = shape(project_data.bounds_polygon)
        bounds_wkt = f"SRID=4326;{poly.wkt}"
    else:
        bounds_wkt = bounds_to_polygon_wkt(project_data.bounds)

    project = Project(
        name=project_data.name,
        description=project_data.description,
        bounds=bounds_wkt,
        created_by=current_user.id,
        status="pending",
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    return project_to_response(project, db)


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=100),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List all projects with optional status filter."""
    query = db.query(Project)

    if status:
        query = query.filter(Project.status == status)

    total = query.count()
    projects = query.order_by(Project.created_at.desc()).offset(offset).limit(limit).all()

    return ProjectListResponse(
        projects=[project_to_response(p, db) for p in projects],
        total=total,
    )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get a project by ID."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    return project_to_response(project, db)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    project_update: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update a project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    if project_update.name is not None:
        project.name = project_update.name
    if project_update.description is not None:
        project.description = project_update.description
    if project_update.status is not None:
        # Only admins can approve
        if project_update.status == "approved" and current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can approve projects",
            )
        project.status = project_update.status
        if project_update.status == "approved":
            project.approved_by = current_user.id

    db.commit()
    db.refresh(project)
    return project_to_response(project, db)


@router.delete("/{project_id}")
async def delete_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Delete a project. Admin only."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    db.delete(project)
    db.commit()
    return {"message": "Project deleted"}
