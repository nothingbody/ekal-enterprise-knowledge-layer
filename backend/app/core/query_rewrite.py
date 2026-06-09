"""
Query rewrite and multi-query generation for improving retrieval accuracy.
Uses the user's configured LLM to rewrite queries before searching.
"""
import logging
from typing import List, Optional

from app.models.model_config import ModelConfig
from app.core.llm_client import chat_completion

logger = logging.getLogger(__name__)


CONDENSE_PROMPT = """根据以下对话历史和用户的后续问题，将后续问题改写为一个独立的、包含完整上下文的搜索查询。

规则：
1. 如果后续问题包含指代（"它"、"这个"、"那个"、"上面"等），用对话历史中的具体实体替换
2. 如果后续问题本身已经是独立完整的，直接返回原问题
3. 只返回改写后的查询，不要解释

对话历史：
{history}

后续问题：{question}
独立查询："""


REWRITE_PROMPT = """你是一个搜索查询优化专家。请将用户的提问改写为更适合在知识库中搜索的形式。

要求：
1. 去除口语化表达，提取核心关键词
2. 如果问题含糊，补充可能的限定词
3. 只返回改写后的查询，不要解释

用户提问: {query}
改写后的查询:"""

MULTI_QUERY_PROMPT = """你是一个搜索查询扩展专家。请将用户的提问从不同角度改写为 3 个搜索查询，以提升检索召回率。

要求：
1. 每个查询从不同角度表述同一个意图
2. 每行一个查询，不要编号
3. 只返回查询内容，不要解释

用户提问: {query}
改写后的查询:"""


async def rewrite_query(
    model_config: ModelConfig,
    query: str,
) -> str:
    """Rewrite a user query to improve retrieval accuracy."""
    try:
        messages = [
            {"role": "system", "content": "你是搜索查询优化专家。"},
            {"role": "user", "content": REWRITE_PROMPT.replace("{query}", query)},
        ]
        result = await chat_completion(model_config, messages, stream=False)
        rewritten = result.strip().strip('"').strip("'")
        if not rewritten:
            return query
        # Guard against LLM returning excessively long rewrites
        max_len = max(len(query) * 3, 500)
        if len(rewritten) > max_len:
            rewritten = rewritten[:max_len]
        return rewritten
    except Exception:
        return query


async def condense_question(
    model_config: ModelConfig,
    question: str,
    chat_history: List[dict],
) -> str:
    """Condense a follow-up question with chat history into a standalone query.

    This resolves pronouns and references like "它", "这个", "那个" by
    incorporating context from the conversation history.
    """
    if not chat_history:
        return question

    # Only use last few turns to keep prompt short
    recent = chat_history[-6:]
    history_text = "\n".join(
        f"{'用户' if m['role'] == 'user' else '助手'}: {m['content'][:200]}"
        for m in recent
    )

    prompt = CONDENSE_PROMPT.replace("{history}", history_text).replace("{question}", question)
    try:
        messages = [
            {"role": "system", "content": "你是查询改写专家。将用户的后续问题改写为独立查询。"},
            {"role": "user", "content": prompt},
        ]
        result = await chat_completion(model_config, messages, stream=False)
        condensed = result.strip().strip('"').strip("'")
        if condensed:
            logger.info("Query condensed: '%s' → '%s'", question[:60], condensed[:60])
            return condensed
    except Exception as exc:
        logger.warning("Query condensation failed: %s", exc)
    return question


async def generate_multi_queries(
    model_config: ModelConfig,
    query: str,
) -> List[str]:
    """Generate multiple query variations for multi-query retrieval."""
    try:
        messages = [
            {"role": "system", "content": "你是搜索查询扩展专家。"},
            {"role": "user", "content": MULTI_QUERY_PROMPT.replace("{query}", query)},
        ]
        result = await chat_completion(model_config, messages, stream=False)
        queries = [q.strip() for q in result.strip().split("\n") if q.strip()]
        queries = [query] + queries[:3]
        return queries
    except Exception:
        return [query]


COMBINED_REWRITE_PROMPT = """你是搜索查询优化专家。请完成以下两个任务：

任务1：如果提供了对话历史，将用户问题改写为独立查询（解决代词指代）。如果没有历史或问题已经独立，保留原问题。
任务2：从不同角度将查询扩展为 2 个变体查询，提升检索召回率。

对话历史：
{history}

用户问题：{question}

请严格按以下格式输出（每行一个查询，第一行是改写后的主查询，后面是变体）：
主查询
变体1
变体2"""


async def condense_and_expand(
    model_config: ModelConfig,
    question: str,
    chat_history: Optional[List[dict]] = None,
) -> List[str]:
    """Condense follow-up question AND generate multi-queries in a single LLM call.
    
    Skips the LLM call for very short queries with no history — the overhead
    of query rewriting outweighs the benefit for simple keyword searches.
    """
    if not chat_history and len(question.strip()) <= 8:
        return [question]

    history_text = "（无历史）"
    if chat_history:
        recent = chat_history[-6:]
        history_text = "\n".join(
            f"{'用户' if m['role'] == 'user' else '助手'}: {m['content'][:200]}"
            for m in recent
        )

    prompt = COMBINED_REWRITE_PROMPT.replace("{history}", history_text).replace("{question}", question)
    try:
        messages = [
            {"role": "system", "content": "你是搜索查询优化专家。严格按要求格式输出。"},
            {"role": "user", "content": prompt},
        ]
        result = await chat_completion(model_config, messages, stream=False)
        lines = [q.strip() for q in result.strip().split("\n") if q.strip()]
        if lines:
            main_query = lines[0]
            variants = lines[1:3]
            queries = [main_query] + variants
            logger.info("Combined rewrite: '%s' → %d queries", question[:40], len(queries))
            return queries
    except Exception as exc:
        logger.warning("Combined rewrite failed: %s", exc)
    return [question]
