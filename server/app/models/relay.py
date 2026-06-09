from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import Base


class RelayHostedWorkspace(Base):
    __tablename__ = "relay_hosted_workspaces"
    __table_args__ = (
        UniqueConstraint(
            "owner_user_id",
            "device_id",
            "local_workspace_id",
            name="uq_relay_hosted_workspace",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id = Column(String(100), nullable=False, index=True)
    local_workspace_id = Column(Integer, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    last_seen = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    owner = relationship("User")
    knowledge_bases = relationship(
        "RelayHostedKnowledgeBase",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    members = relationship(
        "RelayWorkspaceMember",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    invitations = relationship(
        "RelayInvitation",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )


class RelayHostedKnowledgeBase(Base):
    __tablename__ = "relay_hosted_knowledge_bases"
    __table_args__ = (
        UniqueConstraint("hosted_workspace_id", "local_kb_id", name="uq_relay_hosted_kb"),
    )

    id = Column(Integer, primary_key=True, index=True)
    hosted_workspace_id = Column(
        Integer,
        ForeignKey("relay_hosted_workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    local_kb_id = Column(Integer, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    doc_count = Column(Integer, default=0, nullable=False)
    chunk_count = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    workspace = relationship("RelayHostedWorkspace", back_populates="knowledge_bases")


class RelayWorkspaceMember(Base):
    __tablename__ = "relay_workspace_members"
    __table_args__ = (
        UniqueConstraint("hosted_workspace_id", "user_id", name="uq_relay_workspace_member"),
    )

    id = Column(Integer, primary_key=True, index=True)
    hosted_workspace_id = Column(
        Integer,
        ForeignKey("relay_hosted_workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), default="member", nullable=False)
    joined_at = Column(DateTime(timezone=True), server_default=func.now())

    workspace = relationship("RelayHostedWorkspace", back_populates="members")
    user = relationship("User")


class RelayInvitation(Base):
    __tablename__ = "relay_invitations"

    id = Column(Integer, primary_key=True, index=True)
    hosted_workspace_id = Column(
        Integer,
        ForeignKey("relay_hosted_workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    invite_token = Column(String(64), unique=True, nullable=False, index=True)
    role = Column(String(20), default="member", nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    max_uses = Column(Integer, nullable=True)
    use_count = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    workspace = relationship("RelayHostedWorkspace", back_populates="invitations")
