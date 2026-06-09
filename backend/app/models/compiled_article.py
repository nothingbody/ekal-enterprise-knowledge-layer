from sqlalchemy import Column, Index, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.database import Base


class CompiledArticleStatus(str, enum.Enum):
    DRAFTING = "drafting"
    COMPILED = "compiled"
    OUTDATED = "outdated"
    ARCHIVED = "archived"


class CompiledArticle(Base):
    __tablename__ = "compiled_articles"

    id = Column(Integer, primary_key=True, index=True)
    kb_id = Column(Integer, ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)
    tags = Column(Text, nullable=True)  # JSON array of strings
    source_doc_ids = Column(Text, nullable=True)  # JSON array of document IDs
    source_chunk_ids = Column(Text, nullable=True)  # JSON array of chunk IDs
    version = Column(Integer, default=1, nullable=False)
    status = Column(String(20), default=CompiledArticleStatus.COMPILED.value, nullable=False, index=True)
    token_count = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)

    __table_args__ = (
        Index("ix_compiled_articles_kb_status", "kb_id", "status"),
    )

    knowledge_base = relationship("KnowledgeBase", back_populates="compiled_articles")
    outgoing_refs = relationship(
        "ArticleCrossRef",
        foreign_keys="ArticleCrossRef.from_article_id",
        back_populates="from_article",
        cascade="all, delete-orphan",
    )
    incoming_refs = relationship(
        "ArticleCrossRef",
        foreign_keys="ArticleCrossRef.to_article_id",
        back_populates="to_article",
        cascade="all, delete-orphan",
    )


class ArticleCrossRef(Base):
    __tablename__ = "article_cross_refs"

    id = Column(Integer, primary_key=True, index=True)
    from_article_id = Column(Integer, ForeignKey("compiled_articles.id", ondelete="CASCADE"), nullable=False, index=True)
    to_article_id = Column(Integer, ForeignKey("compiled_articles.id", ondelete="CASCADE"), nullable=False, index=True)
    relationship_type = Column(String(50), nullable=False, default="related")  # related, contradicts, supersedes, extends
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    from_article = relationship("CompiledArticle", foreign_keys=[from_article_id], back_populates="outgoing_refs")
    to_article = relationship("CompiledArticle", foreign_keys=[to_article_id], back_populates="incoming_refs")
