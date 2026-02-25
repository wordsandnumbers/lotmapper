import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="reviewer")  # admin, reviewer
    is_active = Column(Boolean, default=False)  # requires admin approval
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    created_projects = relationship(
        "Project", back_populates="creator", foreign_keys="Project.created_by"
    )
    approved_projects = relationship(
        "Project", back_populates="approver", foreign_keys="Project.approved_by"
    )
    edited_polygons = relationship("Polygon", back_populates="editor")
    polygon_edits = relationship("PolygonHistory", back_populates="user")

    def __repr__(self):
        return f"<User {self.email}>"
