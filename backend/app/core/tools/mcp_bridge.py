"""Bridge between MCP tools and the local ToolRegistry.

Each tool discovered from an MCP server is wrapped in an ``McpToolWrapper``
that implements ``BaseTool``, so the Agent's ReAct loop can call it just like
any built-in tool.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.core.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

# Safe-name pattern: lowercase, digits, underscores only
_SAFE_NAME_RE = re.compile(r"[^a-z0-9_]")


def _safe_name(raw: str) -> str:
    """Turn an arbitrary string into a valid tool name."""
    return _SAFE_NAME_RE.sub("_", raw.lower()).strip("_")


class McpToolWrapper(BaseTool):
    """Wraps a single MCP tool so it can be used in the local ToolRegistry."""

    def __init__(
        self,
        tool_name: str,
        tool_description: str,
        input_schema: dict,
        server_config_id: int,
        server_name: str,
    ) -> None:
        safe_server = _safe_name(server_name)
        safe_tool = _safe_name(tool_name)
        self.name = f"mcp_{safe_server}_{safe_tool}"
        self.description = f"[MCP:{server_name}] {tool_description}"
        self.parameters = input_schema or {"type": "object", "properties": {}}

        # Internal references for call_tool dispatch
        self._server_config_id = server_config_id
        self._original_tool_name = tool_name

    async def execute(self, **kwargs) -> ToolResult:
        # Strip internal context keys injected by the agent loop
        call_args = {k: v for k, v in kwargs.items() if not k.startswith("_")}

        from app.core.mcp_client import get_mcp_manager
        manager = get_mcp_manager()

        try:
            text = await manager.call_tool(
                self._server_config_id,
                self._original_tool_name,
                call_args,
            )
            return ToolResult(success=True, data=text)
        except Exception as exc:
            logger.exception(
                "MCP tool %s (server %d) execution failed",
                self._original_tool_name, self._server_config_id,
            )
            return ToolResult(success=False, error=str(exc))


def sync_mcp_tools_to_registry(registry) -> int:
    """Register all tools from active MCP connections into *registry*.

    Returns the number of MCP tools registered.
    """
    from app.core.mcp_client import get_mcp_manager
    manager = get_mcp_manager()

    count = 0
    for tool_info in manager.get_all_tools():
        wrapper = McpToolWrapper(
            tool_name=tool_info.name,
            tool_description=tool_info.description,
            input_schema=tool_info.input_schema,
            server_config_id=tool_info.server_config_id,
            server_name=tool_info.server_name,
        )
        registry.register(wrapper)
        count += 1

    if count:
        logger.info("已将 %d 个 MCP 工具注册到 ToolRegistry", count)
    return count
