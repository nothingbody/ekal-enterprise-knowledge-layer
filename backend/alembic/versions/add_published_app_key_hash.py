"""add api_key_hash column to published_apps table

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f6g7
Create Date: 2026-03-07
"""
from alembic import op
import sqlalchemy as sa

revision = 'c3d4e5f6g7h8'
down_revision = 'b2c3d4e5f6g7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('published_apps', sa.Column('api_key_hash', sa.String(64), unique=True, nullable=True, index=True))


def downgrade() -> None:
    op.drop_column('published_apps', 'api_key_hash')
