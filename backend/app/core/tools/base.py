"""Base class and data structures for agent tools."""

from __future__ import annotations

import abc
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """Result returned by a tool execution."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    display_type: str = "text"  # text | table | chart | json

    def to_message_content(self) -> str:
        """Convert result to a string for feeding back to the LLM."""
        if not self.success:
            return f"工具执行失败: {self.error}"
        if isinstance(self.data, str):
            return self.data
        if isinstance(self.data, dict):
            # Prefer a "text" key if present (more concise for LLM context)
            if "text" in self.data:
                return self.data["text"]
            import json
            return json.dumps(self.data, ensure_ascii=False, indent=2)
        return str(self.data)

    def to_frontend_payload(self) -> dict:
        """Convert result to a dict for streaming to the frontend."""
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "display_type": self.display_type,
        }


class BaseTool(abc.ABC):
    """Abstract base class for all agent tools.

    Subclasses must define:
      - name: unique tool identifier
      - description: what the tool does (used by the LLM to decide when to call it)
      - parameters: JSON Schema dict describing the function parameters
      - execute(**kwargs) -> ToolResult
    """

    name: str = ""
    description: str = ""
    parameters: dict = {}
    sandboxed: bool = False

    def get_openai_tool_schema(self) -> dict:
        """Return the OpenAI-compatible tool definition."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    @abc.abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with the given arguments."""
        ...
