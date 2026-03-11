from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, model_validator


class BoundingBox(BaseModel):
    """Bounding box as [min_lng, min_lat, max_lng, max_lat]"""
    min_lng: float
    min_lat: float
    max_lng: float
    max_lat: float


class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    bounds: Optional[BoundingBox] = None        # manual draw → rectangle
    bounds_polygon: Optional[dict] = None       # city resolver → arbitrary polygon

    @model_validator(mode="after")
    def require_one_bounds(self):
        if not self.bounds and not self.bounds_polygon:
            raise ValueError("Either bounds or bounds_polygon is required")
        return self


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
