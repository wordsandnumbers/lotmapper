"""Allow multipolygon project bounds

Revision ID: 004
Revises: 003
Create Date: 2026-03-05

"""
from typing import Sequence, Union

from alembic import op
import geoalchemy2

revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE projects "
        "ALTER COLUMN bounds TYPE geometry(Geometry, 4326) "
        "USING bounds::geometry(Geometry, 4326)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE projects "
        "ALTER COLUMN bounds TYPE geometry(Polygon, 4326) "
        "USING ST_GeometryN(bounds, 1)::geometry(Polygon, 4326)"
    )
