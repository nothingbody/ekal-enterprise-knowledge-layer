"""MCP Server configuration model."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Enum, ForeignKey
from sqlalchemy.sql import func

from app.database import Base


class McpTransportType(str, enum.Enum):
    STDIO = "stdio"
    HTTP = "http"
    SSE = "sse"


class McpServerConfig(Base):
    """Stores connection configuration for an external MCP server."""

    __tablename__ = "mcp_server_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True)

    name = Column(String(100), nullable=False)
    transport_type = Column(String(16), nullable=False, default=McpTransportType.HTTP.value)

    # stdio transport fields
    command = Column(String(256), nullable=True)   # e.g. "npx", "python", "uvx"
    args = Column(Text, nullable=True)             # JSON array of arguments
    env = Column(Text, nullable=True)              # JSON dict of env vars

    # HTTP / SSE transport fields
    url = Column(String(512), nullable=True)       # e.g. "https://mcp.example.com/sse"
    headers = Column(Text, nullable=True)          # JSON dict of custom headers

    # Tool filtering
    tool_filter = Column(Text, nullable=True)      # JSON: {"include": [...]} or {"exclude": [...]}

    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
