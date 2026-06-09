"""Agent query tool — allows one agent to query another agent's knowledge bases."""

from __future__ import annotations

import json
from app.core.tools.base import BaseTool, ToolResult


class AgentQueryTool(BaseTool):
    name = "agent_query"
    description = (
        "查询其他专业 Agent 获取特定领域的知识。"
        "当当前知识库无法回答用户问题，但其他 Agent 可能有相关知识时使用。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "agent_id": {
                "type": "integer",
                "description": "要查询的目标 Agent ID",
            },
            "query": {
                "type": "string",
                "description": "要向目标 Agent 提出的问题",
            },
        },
        "required": ["agent_id", "query"],
    }

    async def execute(self, **kwargs) -> ToolResult:
        agent_id = kwargs.get("agent_id")
        query = kwargs.get("query", "")
        db = kwargs.get("_db")
        user_id = kwargs.get("_user_id")

        if not db or not user_id:
            return ToolResult(success=False, error="缺少上下文信息")

        from sqlalchemy import select
        from app.models.agent_config import AgentConfig
        from app.services.multi_agent_service import execute_single_agent

        try:
            result = await db.execute(
                select(AgentConfig).where(
                    AgentConfig.id == agent_id,
                    AgentConfig.user_id == user_id,
                    AgentConfig.is_active == True,
                )
            )
            agent = result.scalar_one_or_none()
            if not agent:
                return ToolResult(success=False, error=f"Agent {agent_id} 不存在或未启用")

            agent_result = await execute_single_agent(db, agent, query, user_id)
            return ToolResult(
                success=True,
                data={
                    "text": f"[{agent_result['agent_name']}] {agent_result['answer']}",
                    "agent_name": agent_result["agent_name"],
                    "references": agent_result.get("references", []),
                },
                display_type="text",
            )
        except Exception as exc:
            return ToolResult(success=False, error=f"Agent 查询失败: {str(exc)}")
