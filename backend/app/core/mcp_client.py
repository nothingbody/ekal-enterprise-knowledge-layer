"""MCP Client Manager — manages connections to external MCP servers.

The RAG platform acts as an MCP Host.  For each configured MCP server we
create one MCP Client (1:1 relationship) that can list & call tools.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thin abstraction so the rest of the app doesn't need to depend on the
# `mcp` package at import time (it might not be installed).
# ---------------------------------------------------------------------------

_MCP_SDK_AVAILABLE: bool | None = None


def _check_mcp_sdk() -> bool:
    global _MCP_SDK_AVAILABLE
    if _MCP_SDK_AVAILABLE is None:
        try:
            import mcp  # noqa: F401
            _MCP_SDK_AVAILABLE = True
        except ImportError:
            _MCP_SDK_AVAILABLE = False
    return _MCP_SDK_AVAILABLE


@dataclass
class McpToolInfo:
    """Lightweight descriptor for a tool exposed by an MCP server."""
    name: str
    description: str
    input_schema: dict
    server_config_id: int
    server_name: str


@dataclass
class _ActiveConnection:
    """Tracks the runtime artefacts of a live MCP connection."""
    config_id: int
    session: Any  # mcp.ClientSession
    # Context managers we need to keep alive
    _cm_transport: Any = None
    _cm_session: Any = None
    tools: list[McpToolInfo] = field(default_factory=list)


class McpClientManager:
    """Singleton manager for all MCP server connections."""

    def __init__(self) -> None:
        self._connections: dict[int, _ActiveConnection] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self, config) -> list[McpToolInfo]:
        """Establish a connection to an MCP server described by *config*.

        *config* is an ``McpServerConfig`` ORM instance (or any object with
        the same attributes).  Returns the list of tools discovered.
        """
        if not _check_mcp_sdk():
            raise RuntimeError(
                "MCP Python SDK 未安装。请运行: pip install 'mcp>=1.9.0'"
            )

        config_id = config.id
        if config_id in self._connections:
            return self._connections[config_id].tools

        from mcp import ClientSession

        transport_type = config.transport_type
        try:
            if transport_type == "stdio":
                cm_transport, session, cm_session = await self._connect_stdio(config)
            elif transport_type in ("http", "sse"):
                cm_transport, session, cm_session = await self._connect_http(config)
            else:
                raise ValueError(f"不支持的传输类型: {transport_type}")
        except Exception:
            logger.exception("连接 MCP 服务器 [%s] 失败", config.name)
            raise

        conn = _ActiveConnection(
            config_id=config_id,
            session=session,
            _cm_transport=cm_transport,
            _cm_session=cm_session,
        )

        # Discover tools
        try:
            tools_result = await session.list_tools()
            tool_filter = _parse_tool_filter(config.tool_filter)
            for t in tools_result.tools:
                if not _tool_passes_filter(t.name, tool_filter):
                    continue
                conn.tools.append(McpToolInfo(
                    name=t.name,
                    description=t.description or "",
                    input_schema=t.inputSchema if hasattr(t, "inputSchema") else {},
                    server_config_id=config_id,
                    server_name=config.name,
                ))
        except Exception:
            logger.exception("获取 MCP 工具列表失败 [%s]", config.name)

        async with self._lock:
            self._connections[config_id] = conn

        logger.info(
            "已连接 MCP 服务器 [%s] (transport=%s), 发现 %d 个工具",
            config.name, transport_type, len(conn.tools),
        )
        return conn.tools

    async def disconnect(self, config_id: int) -> None:
        async with self._lock:
            conn = self._connections.pop(config_id, None)
        if conn is None:
            return
        try:
            if conn._cm_session:
                await conn._cm_session.__aexit__(None, None, None)
            if conn._cm_transport:
                await conn._cm_transport.__aexit__(None, None, None)
        except Exception:
            logger.debug("关闭 MCP 连接 %d 时出错", config_id, exc_info=True)

    async def disconnect_all(self) -> None:
        ids = list(self._connections.keys())
        for cid in ids:
            await self.disconnect(cid)

    # ------------------------------------------------------------------
    # Tool operations
    # ------------------------------------------------------------------

    async def list_tools(self, config_id: int) -> list[McpToolInfo]:
        conn = self._connections.get(config_id)
        if not conn:
            return []
        return conn.tools

    async def call_tool(
        self, config_id: int, tool_name: str, arguments: dict[str, Any]
    ) -> str:
        """Call a tool on the connected MCP server and return text result."""
        conn = self._connections.get(config_id)
        if not conn:
            raise RuntimeError(f"MCP 服务器 {config_id} 未连接")
        try:
            result = await asyncio.wait_for(
                conn.session.call_tool(tool_name, arguments=arguments),
                timeout=60,
            )
        except asyncio.TimeoutError:
            raise RuntimeError(f"MCP 工具 {tool_name} 调用超时 (60s)")
        # Flatten content blocks into text
        parts: list[str] = []
        for block in result.content:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
        return "\n".join(parts) if parts else "(无返回内容)"

    def get_all_tools(self) -> list[McpToolInfo]:
        """Return tools from all active connections."""
        tools: list[McpToolInfo] = []
        for conn in self._connections.values():
            tools.extend(conn.tools)
        return tools

    def is_connected(self, config_id: int) -> bool:
        return config_id in self._connections

    # ------------------------------------------------------------------
    # Transport helpers
    # ------------------------------------------------------------------

    # Allowed commands for stdio MCP servers (prevent arbitrary command execution)
    _ALLOWED_COMMANDS = frozenset({
        "node", "npx", "python", "python3", "uvx", "uv",
        "deno", "bun", "docker",
    })

    async def _connect_stdio(self, config):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        # Validate command against whitelist to prevent arbitrary execution
        import os
        cmd_basename = os.path.basename(config.command).lower().split(".")[0]
        if cmd_basename not in self._ALLOWED_COMMANDS:
            raise ValueError(
                f"MCP 命令 '{config.command}' 不在允许列表中。"
                f"允许的命令: {', '.join(sorted(self._ALLOWED_COMMANDS))}"
            )

        args = json.loads(config.args) if config.args else []
        env_dict = json.loads(config.env) if config.env else None

        params = StdioServerParameters(
            command=config.command,
            args=args,
            env=env_dict,
        )

        cm_transport = stdio_client(params)
        read, write = await cm_transport.__aenter__()
        cm_session = ClientSession(read, write)
        session = await cm_session.__aenter__()
        await session.initialize()
        return cm_transport, session, cm_session

    async def _connect_http(self, config):
        from mcp import ClientSession

        # Validate URL to prevent SSRF to internal services
        if config.url:
            from app.core.url_safety import validate_url_safe
            try:
                validate_url_safe(config.url)
            except ValueError as e:
                raise ValueError(f"MCP 服务器 URL 不安全: {e}")

        transport_type = config.transport_type
        headers_dict = json.loads(config.headers) if config.headers else {}

        if transport_type == "sse":
            from mcp.client.sse import sse_client
            cm_transport = sse_client(url=config.url, headers=headers_dict)
        else:
            try:
                from mcp.client.streamable_http import streamable_http_client
                cm_transport = streamable_http_client(url=config.url, headers=headers_dict)
            except (ImportError, AttributeError):
                # Fallback to SSE if streamable_http not available (e.g. PyInstaller)
                from mcp.client.sse import sse_client
                # Convert URL for SSE: some servers use /sse suffix
                sse_url = config.url
                if not sse_url.endswith("/sse"):
                    sse_url = sse_url.rstrip("/") + "/sse"
                cm_transport = sse_client(url=sse_url, headers=headers_dict)

        read, write = await cm_transport.__aenter__()
        cm_session = ClientSession(read, write)
        session = await cm_session.__aenter__()
        await session.initialize()
        return cm_transport, session, cm_session

    # ------------------------------------------------------------------
    # Test helper
    # ------------------------------------------------------------------

    async def test_connection(self, config) -> dict:
        """Quick connect → list_tools → disconnect for validation."""
        tools = await self.connect(config)
        tool_names = [t.name for t in tools]
        await self.disconnect(config.id)
        return {"ok": True, "tools": tool_names}


# ---------------------------------------------------------------------------
# Tool filter helpers
# ---------------------------------------------------------------------------

def _parse_tool_filter(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def _tool_passes_filter(name: str, filt: dict | None) -> bool:
    if filt is None:
        return True
    include = filt.get("include")
    if include is not None:
        return name in include
    exclude = filt.get("exclude")
    if exclude is not None:
        return name not in exclude
    return True


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_manager: McpClientManager | None = None


def get_mcp_manager() -> McpClientManager:
    global _manager
    if _manager is None:
        _manager = McpClientManager()
    return _manager
