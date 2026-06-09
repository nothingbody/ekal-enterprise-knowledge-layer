from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Text, Enum as SAEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.database import Base


class ModelType(str, enum.Enum):
    LLM = "llm"
    EMBEDDING = "embedding"
    RERANKER = "reranker"


class ModelProvider(str, enum.Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    CUSTOM = "custom"


class ModelConfig(Base):
    __tablename__ = "model_configs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    model_type = Column(SAEnum(ModelType), nullable=False)
    provider = Column(SAEnum(ModelProvider), nullable=False)
    api_base = Column(String(500), nullable=False)
    api_key_encrypted = Column(String(500), nullable=True)
    model_name = Column(String(200), nullable=False)
    display_name = Column(String(200), nullable=False)
    params = Column(Text, nullable=True)
    is_default = Column(Boolean, default=False)
    # Fallback model IDs for failover (JSON array of model_config ids, ordered by priority)
    fallback_model_ids = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="model_configs")
