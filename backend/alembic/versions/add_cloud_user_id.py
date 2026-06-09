"""add cloud_user_id to users

Revision ID: add_cloud_user_id
Revises: e5f6g7h8i9j0
Create Date: 2026-05-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "add_cloud_user_id"
down_revision: Union[str, None] = "e5f6g7h8i9j0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("cloud_user_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_users_cloud_user_id", ["cloud_user_id"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_index("ix_users_cloud_user_id")
        batch_op.drop_column("cloud_user_id")
