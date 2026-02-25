from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel


class BoundingBox(BaseModel):
    """Bounding box as [min_lng, min_lat, max_lng, max_lat]"""
    min_lng: float
    min_lat: float
    max_lng: float
    max_lat: float


class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    bounds: BoundingBox  # Will be converted to polygon


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None  # pending, processing, review, approved


class ProjectResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    bounds: dict  # GeoJSON polygon
    status: str
    created_by: Optional[UUID]
    approved_by: Optional[UUID]
    created_at: datetime
    updated_at: datetime
    polygon_count: Optional[int] = None

    class Config:
        from_attributes = True


class ProjectListResponse(BaseModel):
    projects: List[ProjectResponse]
    total: int
