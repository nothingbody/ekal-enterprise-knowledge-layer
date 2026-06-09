"""add login ip tracking and operation log ip

Revision ID: a1b2c3d4e5f6
Revises: 53be9adf87bb
Create Date: 2025-01-01 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '53be9adf87bb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('last_login_ip', sa.String(45), nullable=True))
    op.add_column('users', sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('operation_logs', sa.Column('ip_address', sa.String(45), nullable=True))


def downgrade() -> None:
    op.drop_column('operation_logs', 'ip_address')
    op.drop_column('users', 'last_login_at')
    op.drop_column('users', 'last_login_ip')
