import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from geoalchemy2 import Geometry
from app.database import Base


class CityBoundary(Base):
    __tablename__ = "city_boundaries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    city = Column(String(255), nullable=False)
    state = Column(String(10), nullable=False)
    geometry = Column(Geometry("POLYGON", srid=4326), nullable=False)
    source = Column(String(50))  # arcgis, fallback
    boundary_name = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("city", "state"),)

    def __repr__(self):
        return f"<CityBoundary {self.city}, {self.state}>"
