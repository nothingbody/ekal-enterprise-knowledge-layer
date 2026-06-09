"""Skill model — represents a tool/capability package in the skill marketplace."""

from __future__ import annotations

import enum

from sqlalchemy import Column, Integer, Float, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func

from app.database import Base


class SkillType(str, enum.Enum):
    BUILTIN = "builtin"   # Built-in tool (knowledge_search, calculator, etc.)
    MCP = "mcp"           # Backed by an MCP Server connection
    CUSTOM = "custom"     # User-defined (future)
    PROMPT = "prompt"     # User-defined prompt template skill


class Skill(Base):
    """A skill (tool package) that can be installed by users."""

    __tablename__ = "skills"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)  # unique identifier
    description = Column(Text, default="")
    icon_url = Column(String(512), nullable=True)
    category = Column(String(50), default="general")

    skill_type = Column(String(16), nullable=False, default=SkillType.BUILTIN.value)

    # For builtin: the tool class name(s); for mcp: mcp_server_config_id
    config = Column(Text, nullable=True)  # JSON

    is_public = Column(Boolean, default=False, nullable=False)
    author_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    install_count = Column(Integer, default=0, nullable=False)
    total_use_count = Column(Integer, default=0, nullable=False)
    avg_rating = Column(Float, nullable=True)
    rating_count = Column(Integer, default=0, nullable=False)
    version = Column(String(32), default="1.0.0")

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
