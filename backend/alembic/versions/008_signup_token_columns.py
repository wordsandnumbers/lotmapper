"""Add signup_token columns to users for short DB-backed signup links

Revision ID: 008
Revises: 007
Create Date: 2026-05-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("signup_token", sa.String(64), nullable=True))
    op.add_column(
        "users", sa.Column("signup_token_expires_at", sa.DateTime(), nullable=True)
    )
    op.create_index(
        "ix_users_signup_token", "users", ["signup_token"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_users_signup_token", table_name="users")
    op.drop_column("users", "signup_token_expires_at")
    op.drop_column("users", "signup_token")
