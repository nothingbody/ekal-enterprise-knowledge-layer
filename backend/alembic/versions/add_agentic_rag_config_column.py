"""add agentic_rag_config column to knowledge_bases

Revision ID: e5f6g7h8i9j0
Revises: d4e5f6g7h8i9
Create Date: 2026-04-05
"""
from alembic import op
import sqlalchemy as sa

revision = 'e5f6g7h8i9j0'
down_revision = 'd4e5f6g7h8i9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('knowledge_bases', sa.Column('agentic_rag_config', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('knowledge_bases', 'agentic_rag_config')
