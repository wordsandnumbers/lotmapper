from sqlalchemy import Column, Integer, UniqueConstraint
from app.database import Base


class TileUsage(Base):
    __tablename__ = "tile_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    count = Column(Integer, nullable=False, default=0)

    __table_args__ = (UniqueConstraint("year", "month", name="uq_tile_usage_year_month"),)
