import enum

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text,
    BigInteger, Boolean, Enum as SAEnum,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import Base


class DocumentStatus(str, enum.Enum):
    UPLOADING = "uploading"
    PARSING = "parsing"
    EMBEDDING = "embedding"
    COMPLETED = "completed"
    FAILED = "failed"


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    kb_id = Column(Integer, ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    uploader_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    filename = Column(String(500), nullable=False)
    storage_key = Column(String(1000), nullable=False)
    file_size = Column(BigInteger, nullable=True)
    file_type = Column(String(50), nullable=False)
    chunk_count = Column(Integer, default=0)
    status = Column(SAEnum(DocumentStatus), default=DocumentStatus.UPLOADING)
    error_message = Column(Text, nullable=True)
    content_hash = Column(String(64), nullable=True, index=True)
    is_archived = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)

    knowledge_base = relationship("KnowledgeBase", back_populates="documents")
    uploader = relationship("User")
