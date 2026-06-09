from sqlalchemy import Boolean, Column, Float, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    embedding_model_id = Column(Integer, ForeignKey("model_configs.id", ondelete="SET NULL"), nullable=True)
    doc_count = Column(Integer, default=0)
    chunk_count = Column(Integer, default=0)
    chunk_strategy = Column(String(50), default="fixed")
    chunk_size = Column(Integer, default=500)
    chunk_overlap = Column(Integer, default=50)
    search_mode = Column(String(50), default="hybrid")
    vector_weight = Column(Float, default=0.7, server_default="0.7")
    context_window = Column(Integer, default=1)
    welcome_message = Column(Text, nullable=True)
    suggested_questions = Column(Text, nullable=True)
    prompt_template = Column(Text, nullable=True)
    prompt_template_id = Column(Integer, ForeignKey("prompt_templates.id", ondelete="SET NULL"), nullable=True)
    agentic_rag_config = Column(Text, nullable=True)  # JSON blob of AgenticRAGConfig
    knowledge_compilation_config = Column(Text, nullable=True)  # JSON blob of KnowledgeCompilationConfig
    reindexing = Column(Boolean, default=False, server_default="false")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)

    user = relationship("User", back_populates="knowledge_bases")
    workspace_link = relationship("WorkspaceKnowledgeBase", back_populates="knowledge_base", cascade="all, delete-orphan", uselist=False)
    database_sources = relationship("DatabaseSource", back_populates="knowledge_base", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="knowledge_base", cascade="all, delete-orphan")
    chunks = relationship("DocumentChunk", back_populates="knowledge_base", cascade="all, delete-orphan")
    conversations = relationship("ChatConversation", back_populates="knowledge_base", cascade="all, delete-orphan")
    compiled_articles = relationship("CompiledArticle", back_populates="knowledge_base", cascade="all, delete-orphan")
    health_reports = relationship("HealthReport", back_populates="knowledge_base", cascade="all, delete-orphan")
