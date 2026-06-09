"""Knowledge base document search tool."""

from __future__ import annotations

from app.core.tools.base import BaseTool, ToolResult


class KnowledgeSearchTool(BaseTool):
    name = "knowledge_search"
    description = (
        "从知识库文档中检索与查询相关的信息片段。"
        "适用于需要查找文档内容、概念解释、知识问答等场景。"
        "返回最相关的文档片段及其来源。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "要搜索的问题或关键词",
            },
            "top_k": {
                "type": "integer",
                "description": "返回的最相关片段数量，默认5",
                "default": 5,
            },
        },
        "required": ["query"],
    }

    async def execute(self, **kwargs) -> ToolResult:
        query = kwargs.get("query", "")
        top_k = kwargs.get("top_k", 5)
        # These are injected at call time by the agent loop
        db = kwargs.get("_db")
        kb_id = kwargs.get("_kb_id")
        user_id = kwargs.get("_user_id")
        chat_history = kwargs.get("_chat_history")

        if not db or not kb_id:
            return ToolResult(success=False, error="缺少知识库上下文")

        # Verify user has access to the KB before searching
        if user_id:
            from app.services.access_service import list_accessible_kb_ids
            accessible = await list_accessible_kb_ids(db, user_id, "read")
            if kb_id not in accessible:
                return ToolResult(success=False, error="无权访问该知识库")

        from app.services.retrieval_service import retrieve

        try:
            results = await retrieve(
                db, kb_id, query,
                top_k=top_k,
                user_id=user_id,
                chat_history=chat_history,
            )
            if not results:
                return ToolResult(
                    success=True,
                    data="未找到相关文档内容。",
                    display_type="text",
                )

            # Build readable text for LLM + structured data for frontend
            text_parts = []
            refs = []
            for i, r in enumerate(results, 1):
                text_parts.append(
                    f"[{i}] (来源: {r.doc_name}, 相关度: {r.score:.2f})\n{r.content}"
                )
                refs.append({
                    "index": i,
                    "doc_name": r.doc_name,
                    "score": round(r.score, 4),
                    "content": r.content[:200],
                })

            return ToolResult(
                success=True,
                data={
                    "text": "\n\n".join(text_parts),
                    "references": refs,
                    "count": len(results),
                },
                display_type="references",
            )
        except Exception as exc:
            return ToolResult(success=False, error=f"知识检索失败: {str(exc)}")
