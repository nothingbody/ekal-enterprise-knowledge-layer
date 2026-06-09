"""Utility helpers for chat: error classification, truncation, context building."""
import asyncio
import json
import logging
from typing import List, Optional

from app.core.token_utils import count_tokens as _count_tokens
from app.config import settings
from app.schemas.chat import ChatRequest, RetrievalResult
from app.services.chat_constants import PUBLIC_APP_TITLE_PREFIX, MAX_CONTEXT_TOKENS

_log = logging.getLogger(__name__)

_tiktoken_enc = None


def classify_llm_error(exc: Exception) -> str:
    """Return a user-friendly error message based on exception type."""
    exc_str = str(exc).lower()

    if isinstance(exc, asyncio.TimeoutError):
        return "模型响应超时。请检查网络连接和 API 地址是否正确，或尝试切换到响应更快的模型。"

    if "401" in exc_str or "unauthorized" in exc_str or "invalid api key" in exc_str:
        return "API 密钥无效或已过期。请前往「模型管理」页面检查并更新 API Key。"

    if "403" in exc_str or "forbidden" in exc_str or "permission" in exc_str:
        return "API 权限不足。请检查 API Key 是否有权访问该模型，或是否已开通相关服务。"

    if "404" in exc_str or "model_not_found" in exc_str or "does not exist" in exc_str:
        return "所选模型不存在。请前往「模型管理」页面确认模型名称是否正确。"

    if "429" in exc_str or "rate_limit" in exc_str or "quota" in exc_str:
        return "请求过于频繁或额度已用尽。请稍后重试，或检查 API 账户余额。"

    if "500" in exc_str or "502" in exc_str or "503" in exc_str:
        return "模型服务暂时不可用。请稍后重试，或切换到其他可用模型。"

    if "connect" in exc_str or "connection" in exc_str or "dns" in exc_str or "resolve" in exc_str:
        return "无法连接到模型服务。请检查 API 地址是否正确，以及网络连接是否正常。"

    if "ssl" in exc_str or "certificate" in exc_str:
        return "模型服务 SSL 证书验证失败。请检查 API 地址是否正确。"

    return "模型调用失败，请检查模型配置或稍后重试。如持续失败，请查看系统日志获取详细信息。"


def truncate_context(context: str, max_tokens: int = MAX_CONTEXT_TOKENS) -> str:
    """Truncate retrieval context to fit within token budget using token-level cut."""
    tokens = _count_tokens(context)
    if tokens <= max_tokens:
        return context
    global _tiktoken_enc
    try:
        if _tiktoken_enc is None:
            import tiktoken
            _tiktoken_enc = tiktoken.get_encoding("cl100k_base")
        encoded = _tiktoken_enc.encode(context)
        return _tiktoken_enc.decode(encoded[:max_tokens]) + "\n\n[...上下文已截断...]"
    except Exception:
        ratio = max_tokens / tokens
        cut = int(len(context) * ratio * 0.9)
        return context[:cut] + "\n\n[...上下文已截断...]"


def truncate_history(history: list, max_tokens: int = settings.MAX_HISTORY_TOKENS) -> list:
    """Keep recent history messages within token budget, dropping oldest first."""
    from app.core.context_engine.sliding_window import SlidingWindowEngine
    return SlidingWindowEngine.compact_sync(history, max_tokens)


def build_public_app_title(chat_req: ChatRequest) -> str:
    return f"{PUBLIC_APP_TITLE_PREFIX}{chat_req.published_app_id}:{chat_req.visitor_id}] {chat_req.question[:50]}"


def is_public_app_title(title) -> bool:
    return bool(title and title.startswith(PUBLIC_APP_TITLE_PREFIX))


def is_public_chat_request(chat_req: ChatRequest) -> bool:
    return bool(chat_req.published_app_id and chat_req.visitor_id)


async def build_context(retrieval_results: List[RetrievalResult]) -> str:
    if not retrieval_results:
        return "（未找到相关参考资料）"

    parts = []
    for i, r in enumerate(retrieval_results, 1):
        parts.append(f"[{i}] 来源: {r.doc_name} | 片段 {r.chunk_index}\n{r.content}\n")
    return "\n".join(parts)


def resolve_agentic_config(
    chat_req: ChatRequest,
    kb=None,
) -> Optional["AgenticRAGConfig"]:
    """Resolve agentic RAG config with precedence: request > KB > global settings.

    Returns None when all features are disabled (the common case).
    """
    from app.core.agentic_rag.config import AgenticRAGConfig

    # Start from global settings
    base = {
        "enable_adaptive_retrieval": settings.AGENTIC_RAG_ADAPTIVE_RETRIEVAL,
        "enable_retrieval_evaluation": settings.AGENTIC_RAG_RETRIEVAL_EVALUATION,
        "enable_dynamic_pipeline": settings.AGENTIC_RAG_DYNAMIC_PIPELINE,
        "enable_iterative_refinement": settings.AGENTIC_RAG_ITERATIVE_REFINEMENT,
        "max_refinement_iterations": settings.AGENTIC_RAG_MAX_ITERATIONS,
        "relevance_threshold": settings.AGENTIC_RAG_RELEVANCE_THRESHOLD,
        "enable_query_planning": settings.AGENTIC_RAG_QUERY_PLANNING,
        "enable_trajectory_recording": settings.AGENTIC_RAG_TRAJECTORY_RECORDING,
    }

    # Layer 2: per-KB overrides
    if kb and getattr(kb, "agentic_rag_config", None):
        try:
            kb_overrides = json.loads(kb.agentic_rag_config)
            if isinstance(kb_overrides, dict):
                base.update(kb_overrides)
        except (json.JSONDecodeError, TypeError):
            _log.warning("Invalid agentic_rag_config JSON on kb_id=%s", getattr(kb, "id", "?"))

    # Layer 3: per-request overrides
    if chat_req.agentic_rag and isinstance(chat_req.agentic_rag, dict):
        base.update(chat_req.agentic_rag)

    try:
        config = AgenticRAGConfig(**base)
    except Exception:
        return None

    if config.has_any_enabled() or config.enable_trajectory_recording:
        return config
    return None


def build_sql_context(sql_result: dict) -> str:
    if not sql_result:
        return "（未执行数据库查询）"
    parts = [f"执行的 SQL：{sql_result.get('sql', '')}"]
    results = sql_result.get("results", {})
    rows = results.get("rows", [])
    if rows:
        parts.append(f"返回 {results.get('row_count', len(rows))} 行数据：")
        for row in rows[:30]:
            parts.append(json.dumps(row, ensure_ascii=False, default=str))
        if results.get("truncated"):
            parts.append("...（结果已截断）")
    else:
        parts.append("查询结果为空")
    if sql_result.get("answer"):
        parts.append(f"\n数据分析摘要：{sql_result['answer']}")
    return "\n".join(parts)
