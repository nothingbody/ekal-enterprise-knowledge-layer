"""SQLAlchemy model for knowledge graph entity-relationship triples."""
from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base


class EntityTriple(Base):
    """Stores an entity-relationship triple extracted from a document chunk.

    Each triple represents a (subject, predicate, object) relationship
    found in a specific chunk of a document within a knowledge base.
    """
    __tablename__ = "entity_triples"

    id = Column(Integer, primary_key=True, index=True)
    kb_id = Column(Integer, ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    doc_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    subject = Column(String(200), nullable=False)
    predicate = Column(String(100), nullable=False)
    object = Column(String(200), nullable=False)
    subject_type = Column(String(20), default="ENTITY", nullable=False)
    object_type = Column(String(20), default="ENTITY", nullable=False)
    confidence = Column(Float, default=0.8)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_triple_kb_subject", "kb_id", "subject"),
        Index("ix_triple_kb_object", "kb_id", "object"),
        Index("ix_triple_doc", "doc_id"),
    )
