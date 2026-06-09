"""Tool registry — manages available tools and resolves tool calls."""

from __future__ import annotations

import logging
from typing import Optional

from app.core.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Central registry for all available agent tools."""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        if not tool.name:
            raise ValueError("Tool must have a non-empty name")
        if tool.name in self._tools:
            logger.warning("Overwriting existing tool: %s", tool.name)
        self._tools[tool.name] = tool
        logger.info("Registered tool: %s", tool.name)

    def get(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def list_tools(self) -> list[BaseTool]:
        return list(self._tools.values())

    def get_openai_tools_schema(self) -> list[dict]:
        """Return list of OpenAI-compatible tool definitions for all registered tools."""
        return [tool.get_openai_tool_schema() for tool in self._tools.values()]

    def clone(self) -> "ToolRegistry":
        """Return a shallow copy with the same tool set (for per-request customisation)."""
        new = ToolRegistry()
        new._tools = dict(self._tools)
        return new

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    async def execute(self, tool_name: str, **kwargs) -> ToolResult:
        """Look up and execute a tool by name."""
        tool = self._tools.get(tool_name)
        if not tool:
            return ToolResult(success=False, error=f"未知工具: {tool_name}")
        if getattr(tool, "sandboxed", False):
            from app.config import settings
            if not getattr(settings, "SANDBOX_ENABLED", False):
                return ToolResult(
                    success=False,
                    error="该工具需要沙箱环境，但当前未启用沙箱。请在配置中设置 SANDBOX_ENABLED=true。",
                )
        try:
            return await tool.execute(**kwargs)
        except Exception as exc:
            logger.exception("Tool %s execution failed", tool_name)
            return ToolResult(success=False, error=str(exc))


# ---------------------------------------------------------------------------
# Singleton default registry
# ---------------------------------------------------------------------------
_default_registry: Optional[ToolRegistry] = None


def get_default_registry() -> ToolRegistry:
    global _default_registry
    if _default_registry is None:
        _default_registry = ToolRegistry()
        _register_builtin_tools(_default_registry)
    return _default_registry


def _register_builtin_tools(registry: ToolRegistry) -> None:
    """Register all built-in tools."""
    from app.core.tools.builtin.knowledge_search import KnowledgeSearchTool
    from app.core.tools.builtin.sql_query import SQLQueryTool
    from app.core.tools.builtin.calculator import CalculatorTool
    from app.core.tools.builtin.current_time import CurrentTimeTool
    from app.core.tools.builtin.web_search import WebSearchTool
    from app.core.tools.builtin.agent_query import AgentQueryTool
    from app.core.tools.builtin.browser_tool import BrowserTool
    from app.core.tools.builtin.code_executor import CodeExecutorTool
    from app.core.tools.builtin.file_analyzer import FileAnalyzerTool

    registry.register(KnowledgeSearchTool())
    registry.register(SQLQueryTool())
    registry.register(CalculatorTool())
    registry.register(CurrentTimeTool())
    registry.register(WebSearchTool())
    registry.register(AgentQueryTool())
    registry.register(BrowserTool())
    registry.register(CodeExecutorTool())
    registry.register(FileAnalyzerTool())
