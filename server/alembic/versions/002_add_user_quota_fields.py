"""add user quota fields (plan, trial_total, trial_used, token_credit, token_used)

Revision ID: 002_user_quota_fields
Revises: 001_system_config
Create Date: 2026-03-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002_user_quota_fields"
down_revision: Union[str, None] = "001_system_config"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("plan", sa.String(30), nullable=False, server_default="trial"))
        batch_op.add_column(sa.Column("trial_total", sa.Integer(), nullable=False, server_default="50"))
        batch_op.add_column(sa.Column("trial_used", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("token_credit", sa.BigInteger(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("token_used", sa.BigInteger(), nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("token_used")
        batch_op.drop_column("token_credit")
        batch_op.drop_column("trial_used")
        batch_op.drop_column("trial_total")
        batch_op.drop_column("plan")
