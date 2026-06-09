"""add database_sources table

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-03-07
"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'database_sources',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('kb_id', sa.Integer(), sa.ForeignKey('knowledge_bases.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('db_type', sa.Enum('postgresql', 'mysql', 'sqlite', name='databasetype'), nullable=False),
        sa.Column('host', sa.String(255), nullable=True),
        sa.Column('port', sa.Integer(), nullable=True),
        sa.Column('database_name', sa.String(255), nullable=True),
        sa.Column('schema_name', sa.String(255), nullable=True),
        sa.Column('username', sa.String(255), nullable=True),
        sa.Column('password_encrypted', sa.Text(), nullable=True),
        sa.Column('sqlite_path', sa.String(1000), nullable=True),
        sa.Column('table_names', sa.Text(), nullable=True),
        sa.Column('row_limit', sa.Integer(), default=200),
        sa.Column('status', sa.Enum('pending', 'syncing', 'completed', 'failed', name='databasesourcestatus'), default='pending'),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('database_sources')
    op.execute("DROP TYPE IF EXISTS databasetype")
    op.execute("DROP TYPE IF EXISTS databasesourcestatus")
