"""add relay tables

Revision ID: 005_relay_tables
Revises: 004_user_nickname
Create Date: 2026-05-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "005_relay_tables"
down_revision: Union[str, None] = "004_user_nickname"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "relay_hosted_workspaces",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", sa.String(100), nullable=False),
        sa.Column("local_workspace_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("owner_user_id", "device_id", "local_workspace_id", name="uq_relay_hosted_workspace"),
    )
    op.create_index("ix_relay_hosted_workspaces_owner_user_id", "relay_hosted_workspaces", ["owner_user_id"])
    op.create_index("ix_relay_hosted_workspaces_device_id", "relay_hosted_workspaces", ["device_id"])
    op.create_index("ix_relay_hosted_workspaces_local_workspace_id", "relay_hosted_workspaces", ["local_workspace_id"])

    op.create_table(
        "relay_hosted_knowledge_bases",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("hosted_workspace_id", sa.Integer(), sa.ForeignKey("relay_hosted_workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("local_kb_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("doc_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("hosted_workspace_id", "local_kb_id", name="uq_relay_hosted_kb"),
    )
    op.create_index("ix_relay_hosted_knowledge_bases_hosted_workspace_id", "relay_hosted_knowledge_bases", ["hosted_workspace_id"])
    op.create_index("ix_relay_hosted_knowledge_bases_local_kb_id", "relay_hosted_knowledge_bases", ["local_kb_id"])

    op.create_table(
        "relay_workspace_members",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("hosted_workspace_id", sa.Integer(), sa.ForeignKey("relay_hosted_workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="member"),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("hosted_workspace_id", "user_id", name="uq_relay_workspace_member"),
    )
    op.create_index("ix_relay_workspace_members_hosted_workspace_id", "relay_workspace_members", ["hosted_workspace_id"])
    op.create_index("ix_relay_workspace_members_user_id", "relay_workspace_members", ["user_id"])

    op.create_table(
        "relay_invitations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("hosted_workspace_id", sa.Integer(), sa.ForeignKey("relay_hosted_workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invite_token", sa.String(64), nullable=False, unique=True),
        sa.Column("role", sa.String(20), nullable=False, server_default="member"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_uses", sa.Integer(), nullable=True),
        sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_relay_invitations_hosted_workspace_id", "relay_invitations", ["hosted_workspace_id"])
    op.create_index("ix_relay_invitations_invite_token", "relay_invitations", ["invite_token"])


def downgrade() -> None:
    op.drop_table("relay_invitations")
    op.drop_table("relay_workspace_members")
    op.drop_table("relay_hosted_knowledge_bases")
    op.drop_table("relay_hosted_workspaces")
