"""add deleted_at columns to knowledge_bases and documents for soft delete

Revision ID: d4e5f6g7h8i9
Revises: c3d4e5f6g7h8
Create Date: 2026-03-07
"""
from alembic import op
import sqlalchemy as sa

revision = 'd4e5f6g7h8i9'
down_revision = 'c3d4e5f6g7h8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('knowledge_bases', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, index=True))
    op.add_column('documents', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, index=True))


def downgrade() -> None:
    op.drop_column('documents', 'deleted_at')
    op.drop_column('knowledge_bases', 'deleted_at')
