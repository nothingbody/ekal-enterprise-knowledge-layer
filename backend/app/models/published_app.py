import secrets
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class PublishedApp(Base):
    __tablename__ = "published_apps"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kb_id = Column(Integer, ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    share_token = Column(String(64), unique=True, nullable=False, default=lambda: secrets.token_urlsafe(32))
    api_key = Column(String(64), unique=True, nullable=True)  # legacy plaintext
    api_key_hash = Column(String(64), unique=True, nullable=True, index=True)
    llm_model_id = Column(Integer, ForeignKey("model_configs.id", ondelete="SET NULL"), nullable=True)
    is_active = Column(Boolean, default=True)
    welcome_message = Column(Text, nullable=True)
    suggested_questions = Column(Text, nullable=True)
    prompt_template = Column(Text, nullable=True)
    default_chat_mode = Column(String(32), nullable=False, server_default="auto")
    daily_limit = Column(Integer, nullable=False, server_default="100")
    # Branding customization for public share page
    brand_color = Column(String(20), nullable=True)
    logo_url = Column(String(500), nullable=True)
    custom_css = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User")
    knowledge_base = relationship("KnowledgeBase")
