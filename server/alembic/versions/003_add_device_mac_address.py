"""add mac_address to devices table

Revision ID: 003_device_mac
Revises: 002_user_quota_fields
Create Date: 2026-03-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003_device_mac"
down_revision: Union[str, None] = "002_user_quota_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("devices") as batch_op:
        batch_op.add_column(sa.Column("mac_address", sa.String(50), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("devices") as batch_op:
        batch_op.drop_column("mac_address")
