from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import Base


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    embedding_model = Column(String(200), nullable=True)
    doc_count = Column(Integer, default=0)
    chunk_count = Column(Integer, default=0)
    chunk_strategy = Column(String(50), default="fixed")
    chunk_size = Column(Integer, default=500)
    chunk_overlap = Column(Integer, default=50)
    search_mode = Column(String(50), default="hybrid")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)

    owner = relationship("User")
    workspace = relationship("Workspace")
    documents = relationship("Document", back_populates="knowledge_base", cascade="all, delete-orphan")
    conversations = relationship("ChatConversation", back_populates="knowledge_base", cascade="all, delete-orphan")
