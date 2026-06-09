import enum

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text,
    Boolean, Enum as SAEnum,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import Base


class ModelType(str, enum.Enum):
    LLM = "llm"
    EMBEDDING = "embedding"
    RERANKER = "reranker"


class ModelProvider(str, enum.Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    OLLAMA = "ollama"
    CUSTOM = "custom"


class ModelConfig(Base):
    __tablename__ = "model_configs"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    model_type = Column(SAEnum(ModelType), nullable=False, index=True)
    provider = Column(SAEnum(ModelProvider), nullable=False)
    api_base = Column(String(500), nullable=False)
    api_key_encrypted = Column(String(1000), nullable=True)
    model_name = Column(String(200), nullable=False)
    display_name = Column(String(200), nullable=False)
    params = Column(Text, nullable=True)
    is_default = Column(Boolean, default=False)
    is_shared = Column(Boolean, default=False)
    max_tokens_per_day = Column(Integer, nullable=True)
    tokens_used_today = Column(Integer, default=0)
    tokens_reset_date = Column(String(10), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    organization = relationship("Organization")
    creator = relationship("User")
