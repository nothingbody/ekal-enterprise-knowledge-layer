"""Channel model — stores multi-channel integration configurations."""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, JSON
from sqlalchemy.sql import func

from app.database import Base


class Channel(Base):
    __tablename__ = "channels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True, index=True)
    name = Column(String(100), nullable=False)
    platform = Column(String(32), nullable=False)  # wecom | dingtalk | feishu
    kb_id = Column(Integer, ForeignKey("knowledge_bases.id", ondelete="SET NULL"), nullable=True)
    llm_model_id = Column(Integer, ForeignKey("model_configs.id", ondelete="SET NULL"), nullable=True)
    chat_mode = Column(String(16), default="auto")  # auto | rag | sql | hybrid | agent | multi_agent
    config = Column(JSON, nullable=False, default=dict)  # platform-specific config (tokens, secrets, etc.)
    is_active = Column(Boolean, default=True)
    webhook_token = Column(String(64), nullable=True, unique=True)  # internal token for incoming webhook URL
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
