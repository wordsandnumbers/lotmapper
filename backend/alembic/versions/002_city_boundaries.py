"""Add city_boundaries table

Revision ID: 002
Revises: 001
Create Date: 2026-03-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import geoalchemy2
from sqlalchemy.dialects import postgresql

revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'city_boundaries',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('city', sa.String(255), nullable=False),
        sa.Column('state', sa.String(10), nullable=False),
        sa.Column('geometry', geoalchemy2.Geometry('POLYGON', srid=4326), nullable=False),
        sa.Column('source', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('city', 'state', name='uq_city_boundaries_city_state'),
    )


def downgrade() -> None:
    op.drop_table('city_boundaries')
