"""Add inference_jobs table

Revision ID: 005
Revises: 004
Create Date: 2026-03-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'inference_jobs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String, nullable=False, server_default='queued'),
        sa.Column('progress', sa.Integer, nullable=False, server_default='0'),
        sa.Column('step', sa.String, nullable=True),
        sa.Column('message', sa.String, nullable=True),
        sa.Column('error', sa.Text, nullable=True),
        sa.Column('queued_at', sa.DateTime, nullable=True),
        sa.Column('started_at', sa.DateTime, nullable=True),
        sa.Column('completed_at', sa.DateTime, nullable=True),
    )
    op.create_index('ix_inference_jobs_project_id', 'inference_jobs', ['project_id'])


def downgrade() -> None:
    op.drop_index('ix_inference_jobs_project_id', table_name='inference_jobs')
    op.drop_table('inference_jobs')
