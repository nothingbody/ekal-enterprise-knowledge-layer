from sqlalchemy import Boolean, Column, Index, Integer, String, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class ChatConversation(Base):
    __tablename__ = "chat_conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kb_id = Column(Integer, ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(500), nullable=True)
    llm_model_id = Column(Integer, ForeignKey("model_configs.id", ondelete="SET NULL"), nullable=True)
    # Token usage tracking (inspired by OpenClaw usage-tracking)
    total_input_tokens = Column(Integer, default=0, nullable=False)
    total_output_tokens = Column(Integer, default=0, nullable=False)
    context_summary = Column(Text, nullable=True)
    is_pinned = Column(Boolean, default=False, server_default="false")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_conv_user_created", "user_id", "created_at"),
    )

    user = relationship("User", back_populates="conversations")
    knowledge_base = relationship("KnowledgeBase", back_populates="conversations")
    messages = relationship("ChatMessage", back_populates="conversation", cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("chat_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    references = Column(Text, nullable=True)
    token_count = Column(Integer, default=0)
    feedback = Column(String(20), nullable=True)
    feedback_reason = Column(String(100), nullable=True)
    latency_ms = Column(Float, nullable=True)
    # msg_type: 'chat' (normal) | 'compaction' (summary replacing old messages)
    msg_type = Column(String(20), default="chat", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    conversation = relationship("ChatConversation", back_populates="messages")
