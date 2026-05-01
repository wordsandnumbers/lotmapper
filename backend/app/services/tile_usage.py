from datetime import datetime

from sqlalchemy.orm import Session

from app.models.tile_usage import TileUsage


def get_monthly_count(db: Session, year: int, month: int) -> int:
    row = db.query(TileUsage).filter_by(year=year, month=month).first()
    return row.count if row else 0


def get_current_monthly_count(db: Session) -> int:
    now = datetime.utcnow()
    return get_monthly_count(db, now.year, now.month)


def increment_monthly_count(db: Session, count: int) -> int:
    now = datetime.utcnow()
    row = db.query(TileUsage).filter_by(year=now.year, month=now.month).first()
    if row:
        row.count += count
    else:
        row = TileUsage(year=now.year, month=now.month, count=count)
        db.add(row)
    db.commit()
    db.refresh(row)
    return row.count
