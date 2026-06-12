"""Add city and state columns to projects table

Revision ID: 008
Revises: 007
Create Date: 2026-05-28
"""
from typing import Union
import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("city", sa.String(100), nullable=True))
    op.add_column("projects", sa.Column("state", sa.String(2), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "state")
    op.drop_column("projects", "city")
