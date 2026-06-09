"""add key_hash and key_preview columns to api_keys table

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-07
"""
from alembic import op
import sqlalchemy as sa

revision = 'b2c3d4e5f6g7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('api_keys', sa.Column('key_hash', sa.String(64), unique=True, nullable=True, index=True))
    op.add_column('api_keys', sa.Column('key_preview', sa.String(20), nullable=True))
    op.alter_column('api_keys', 'key', existing_type=sa.String(64), nullable=True)


def downgrade() -> None:
    op.alter_column('api_keys', 'key', existing_type=sa.String(64), nullable=False)
    op.drop_column('api_keys', 'key_preview')
    op.drop_column('api_keys', 'key_hash')
