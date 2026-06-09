"""Chat routing service: decides whether a question should use RAG, SQL, or both."""
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.llm_client import chat_completion
from app.models.database_source import DatabaseSource, DatabaseSourceStatus
from app.models.model_config import ModelConfig

logger = logging.getLogger(__name__)

ROUTE_CLASSIFY_PROMPT = """你是一个智能路由分类器。根据用户的问题，判断应该使用哪种方式回答。

可用的回答方式：
- rag：从知识库文档中检索相关信息来回答（适合：概念解释、文档内容查询、知识问答）
- sql：通过查询数据库表来获取结构化数据回答（适合：数据统计、数量查询、排序筛选、表格数据查询）
- hybrid：同时使用知识库检索和数据库查询来回答（适合：需要结合文档知识和数据表信息的复杂问题）

该知识库有以下数据源：
- 文档知识库：{has_docs}
- 数据库表：{db_tables}

请只输出一个词：rag、sql 或 hybrid。不要输出其他内容。

用户问题：{question}
"""


async def has_database_sources(db: AsyncSession, kb_id: int) -> bool:
    result = await db.execute(
        select(func.count(DatabaseSource.id)).where(
            DatabaseSource.kb_id == kb_id,
            DatabaseSource.status == DatabaseSourceStatus.COMPLETED,
        )
    )
    return (result.scalar() or 0) > 0


async def get_kb_database_sources(db: AsyncSession, kb_id: int) -> list[DatabaseSource]:
    result = await db.execute(
        select(DatabaseSource).where(
            DatabaseSource.kb_id == kb_id,
            DatabaseSource.status == DatabaseSourceStatus.COMPLETED,
        )
    )
    return list(result.scalars().all())


async def classify_intent(
    db: AsyncSession,
    llm_config: ModelConfig,
    question: str,
    kb_id: int,
    has_docs: bool = True,
) -> str:
    """Use LLM to classify the question intent as rag/sql/hybrid."""
    sources = await get_kb_database_sources(db, kb_id)
    if not sources:
        return "rag"

    from app.services.database_source_service import _parse_table_names
    table_names = []
    for src in sources:
        names = _parse_table_names(src.table_names)
        if names:
            table_names.extend(names)
        else:
            table_names.append(f"({src.name} 的所有表)")

    db_tables_str = ", ".join(table_names) if table_names else "无"

    prompt = ROUTE_CLASSIFY_PROMPT.format(
        has_docs="有" if has_docs else "无",
        db_tables=db_tables_str,
        question=question,
    )
    messages = [
        {"role": "system", "content": "你是一个路由分类器，只输出 rag、sql 或 hybrid 中的一个词。"},
        {"role": "user", "content": prompt},
    ]
    try:
        response = await chat_completion(llm_config, messages, stream=False)
        intent = response.strip().lower().strip("。.!！")
        if intent in ("rag", "sql", "hybrid"):
            logger.info("Chat route classified: %s for question: %s", intent, question[:80])
            return intent
        logger.warning("Unexpected route classification: %s, defaulting to rag", response[:50])
    except Exception as exc:
        logger.warning("Route classification failed: %s, defaulting to rag", exc)
    return "rag"


async def resolve_chat_mode(
    db: AsyncSession,
    kb_id: int,
    question: str,
    requested_mode: str,
    llm_config: Optional[ModelConfig] = None,
    user_id: Optional[int] = None,
) -> str:
    """Resolve the final chat mode based on user request and KB capabilities."""
    if requested_mode == "multi_agent":
        return "multi_agent"

    has_db = await has_database_sources(db, kb_id)
    logger.info(
        "resolve_chat_mode: kb_id=%s, requested=%s, has_db_sources=%s",
        kb_id, requested_mode, has_db,
    )

    if requested_mode == "sql":
        resolved = "sql" if has_db else "rag"
    elif requested_mode == "hybrid":
        resolved = "hybrid" if has_db else "rag"
    elif requested_mode == "rag":
        resolved = "rag"
    elif not has_db:
        resolved = "rag"
    elif llm_config:
        resolved = await classify_intent(db, llm_config, question, kb_id)
    else:
        resolved = "rag"

    if resolved != requested_mode and requested_mode != "auto":
        logger.warning(
            "Chat mode downgraded: requested=%s -> resolved=%s (kb_id=%s has_db=%s)",
            requested_mode, resolved, kb_id, has_db,
        )
    logger.info("resolve_chat_mode: final=%s", resolved)
    return resolved
