"""PromptSkillTool — wraps a user-defined prompt template as an agent tool.

When the agent invokes this tool it:
1. Fills the prompt template with the provided variables.
2. Sends the rendered prompt to the LLM.
3. Returns the LLM response as the tool result.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.core.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

_VAR_PATTERN = re.compile(r"\{\{(\w+)\}\}")


class PromptSkillTool(BaseTool):
    """A tool backed by a user-defined prompt template."""

    def __init__(
        self,
        *,
        name: str,
        description: str,
        prompt_template: str,
        output_format: str = "text",
        variables: list[str] | None = None,
        model_config: Any = None,
    ):
        self.name = name
        self.description = description
        self.prompt_template = prompt_template
        self.output_format = output_format
        self.variables = variables or self._detect_variables(prompt_template)
        self._model_config = model_config
        self.parameters = self._build_parameters_schema()

    @staticmethod
    def _detect_variables(template: str) -> list[str]:
        """Auto-detect ``{{var}}`` placeholders in the template."""
        return list(dict.fromkeys(_VAR_PATTERN.findall(template)))

    def _build_parameters_schema(self) -> dict:
        props: dict[str, dict] = {
            "query": {
                "type": "string",
                "description": "用户的原始问题或输入文本",
            },
        }
        for var in self.variables:
            if var == "query":
                continue
            props[var] = {
                "type": "string",
                "description": f"模板变量: {var}",
            }
        required = list(props.keys())
        return {
            "type": "object",
            "properties": props,
            "required": required,
        }

    def _render_template(self, variables: dict[str, str]) -> str:
        """Replace ``{{var}}`` placeholders with values from *variables*.

        Raises ValueError if any required variable is missing.
        """
        missing = []
        def _replacer(m: re.Match) -> str:
            key = m.group(1)
            val = variables.get(key)
            if val is None:
                missing.append(key)
                return m.group(0)
            return str(val)
        rendered = _VAR_PATTERN.sub(_replacer, self.prompt_template)
        if missing:
            raise ValueError(f"Prompt 模板缺少必要变量: {', '.join(missing)}")
        return rendered

    async def execute(self, **kwargs) -> ToolResult:
        rendered = self._render_template(kwargs)

        model_cfg = self._model_config or kwargs.get("_model_config")
        if model_cfg is None:
            return ToolResult(
                success=False,
                error="未配置 LLM 模型，无法执行 Prompt 技能",
            )

        from app.core.llm_client import chat_completion

        messages = [
            {"role": "system", "content": rendered},
            {"role": "user", "content": kwargs.get("query", "")},
        ]

        try:
            response = await chat_completion(model_cfg, messages, stream=False)
            display = "json" if self.output_format == "json" else "text"
            return ToolResult(success=True, data=response, display_type=display)
        except Exception as exc:
            logger.exception("PromptSkillTool %s execution failed", self.name)
            return ToolResult(success=False, error=f"Prompt 技能执行失败: {exc}")
