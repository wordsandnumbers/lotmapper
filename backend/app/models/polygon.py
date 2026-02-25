import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry
from app.database import Base


class Polygon(Base):
    __tablename__ = "polygons"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    geometry = Column(Geometry("POLYGON", srid=4326), nullable=False)
    properties = Column(JSONB, default=dict)
    status = Column(
        String(50), default="detected"
    )  # detected, edited, approved, deleted
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    edited_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Relationships
    project = relationship("Project", back_populates="polygons")
    editor = relationship("User", back_populates="edited_polygons")
    history = relationship(
        "PolygonHistory", back_populates="polygon", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Polygon {self.id}>"


class PolygonHistory(Base):
    __tablename__ = "polygon_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    polygon_id = Column(
        UUID(as_uuid=True),
        ForeignKey("polygons.id", ondelete="CASCADE"),
        nullable=False,
    )
    action = Column(String(50), nullable=False)  # create, edit, delete, split
    previous_geometry = Column(Geometry("POLYGON", srid=4326), nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    polygon = relationship("Polygon", back_populates="history")
    user = relationship("User", back_populates="polygon_edits")

    def __repr__(self):
        return f"<PolygonHistory {self.action} on {self.polygon_id}>"
