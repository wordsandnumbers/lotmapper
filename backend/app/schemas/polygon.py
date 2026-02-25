from datetime import datetime
from typing import Optional, List, Any, Dict
from uuid import UUID
from pydantic import BaseModel


class GeoJSONGeometry(BaseModel):
    type: str = "Polygon"
    coordinates: List[List[List[float]]]  # [[[lng, lat], ...]]


class GeoJSONFeature(BaseModel):
    type: str = "Feature"
    id: Optional[str] = None
    geometry: GeoJSONGeometry
    properties: Dict[str, Any] = {}


class GeoJSONFeatureCollection(BaseModel):
    type: str = "FeatureCollection"
    features: List[GeoJSONFeature]


class PolygonCreate(BaseModel):
    geometry: GeoJSONGeometry
    properties: Dict[str, Any] = {}


class PolygonUpdate(BaseModel):
    geometry: Optional[GeoJSONGeometry] = None
    properties: Optional[Dict[str, Any]] = None
    status: Optional[str] = None  # detected, edited, approved, deleted


class PolygonResponse(BaseModel):
    id: UUID
    project_id: UUID
    geometry: dict
    properties: Dict[str, Any]
    status: str
    created_at: datetime
    updated_at: datetime
    edited_by: Optional[UUID]

    class Config:
        from_attributes = True


class PolygonSplit(BaseModel):
    """Split a polygon with a line defined by two points."""
    line_start: List[float]  # [lng, lat]
    line_end: List[float]  # [lng, lat]
