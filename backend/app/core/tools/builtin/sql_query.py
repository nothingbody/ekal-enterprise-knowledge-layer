"""SQL query tool — executes text-to-SQL against connected database sources."""

from __future__ import annotations

from app.core.tools.base import BaseTool, ToolResult


class SQLQueryTool(BaseTool):
    name = "sql_query"
    description = (
        "根据自然语言问题自动生成SQL并查询知识库关联的数据库，返回结构化数据结果。"
        "适用于数据统计、数量查询、排序筛选、表格数据查询等场景。"
        "只有当知识库连接了数据库数据源时才可使用。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "用自然语言描述你想查询的数据，例如：'上个月销售额最高的前10个产品'",
            },
        },
        "required": ["question"],
    }

    async def execute(self, **kwargs) -> ToolResult:
        question = kwargs.get("question", "")
        db = kwargs.get("_db")
        kb_id = kwargs.get("_kb_id")
        model_config = kwargs.get("_model_config")

        if not db or not kb_id:
            return ToolResult(success=False, error="缺少知识库上下文")

        from app.services.chat_router_service import get_kb_database_sources
        from app.services.text_to_sql_service import text_to_sql_query

        try:
            sources = await get_kb_database_sources(db, kb_id)
            if not sources:
                return ToolResult(
                    success=False,
                    error="该知识库未连接数据库数据源，无法执行SQL查询",
                )

            result = await text_to_sql_query(
                db, sources[0], model_config, question, summarize=False,
            )

            sql = result.get("sql", "")
            results_data = result.get("results", {})
            columns = results_data.get("columns", [])
            rows = results_data.get("rows", [])
            row_count = results_data.get("row_count", 0)

            # Build text summary for LLM
            text_parts = [f"执行的SQL: {sql}", f"返回 {row_count} 行数据。"]
            if columns and rows:
                # Show first few rows as text
                header = " | ".join(columns)
                text_parts.append(header)
                text_parts.append("-" * len(header))
                for row in rows[:20]:
                    text_parts.append(" | ".join(str(v) for v in row))
                if row_count > 20:
                    text_parts.append(f"... 还有 {row_count - 20} 行未显示")

            return ToolResult(
                success=True,
                data={
                    "text": "\n".join(text_parts),
                    "sql": sql,
                    "columns": columns,
                    "rows": rows[:50],
                    "row_count": row_count,
                },
                display_type="table",
            )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error("SQL query tool failed: %s", exc)
            # Sanitize error message: don't expose internal DB details
            err_type = type(exc).__name__
            return ToolResult(success=False, error=f"数据库查询失败 ({err_type})")
