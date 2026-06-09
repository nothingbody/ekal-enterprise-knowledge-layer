"""Query complexity classification for dynamic pipeline control.

Classifies queries into complexity levels to determine which retrieval
pipeline stages to activate, saving latency for simple queries and
increasing thoroughness for complex ones.
"""
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

logger = logging.getLogger(__name__)


class QueryComplexity(str, Enum):
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"
    VERY_COMPLEX = "very_complex"


@dataclass
class PipelineDecision:
    """Pipeline parameters determined by query complexity."""
    complexity: QueryComplexity
    enable_rewrite: bool
    enable_multi_query: bool
    enable_rerank: bool
    context_window: int
    fetch_k_multiplier: float

    def to_dict(self) -> dict:
        return {
            "complexity": self.complexity.value,
            "enable_rewrite": self.enable_rewrite,
            "enable_multi_query": self.enable_multi_query,
            "enable_rerank": self.enable_rerank,
            "context_window": self.context_window,
            "fetch_k_multiplier": self.fetch_k_multiplier,
        }


# ---------------------------------------------------------------------------
# Complexity → Pipeline mapping
# ---------------------------------------------------------------------------

_PIPELINE_MAP = {
    QueryComplexity.SIMPLE: PipelineDecision(
        complexity=QueryComplexity.SIMPLE,
        enable_rewrite=False,
        enable_multi_query=False,
        enable_rerank=False,
        context_window=0,
        fetch_k_multiplier=1.0,
    ),
    QueryComplexity.MODERATE: PipelineDecision(
        complexity=QueryComplexity.MODERATE,
        enable_rewrite=True,
        enable_multi_query=False,
        enable_rerank=True,
        context_window=1,
        fetch_k_multiplier=1.0,
    ),
    QueryComplexity.COMPLEX: PipelineDecision(
        complexity=QueryComplexity.COMPLEX,
        enable_rewrite=True,
        enable_multi_query=True,
        enable_rerank=True,
        context_window=2,
        fetch_k_multiplier=2.0,
    ),
    QueryComplexity.VERY_COMPLEX: PipelineDecision(
        complexity=QueryComplexity.VERY_COMPLEX,
        enable_rewrite=True,
        enable_multi_query=True,
        enable_rerank=True,
        context_window=3,
        fetch_k_multiplier=3.0,
    ),
}


# ---------------------------------------------------------------------------
# Rule-based complexity patterns
# ---------------------------------------------------------------------------

# Indicators of complex queries
_MULTI_TOPIC_PATTERNS = re.compile(
    r"(和|以及|同时|还有|并且|另外|此外|以及|and|also|additionally)", re.IGNORECASE
)
_COMPARISON_PATTERNS = re.compile(
    r"(对比|比较|区别|不同|差异|优劣|vs\.?|versus|相比|异同)", re.IGNORECASE
)
_MULTI_HOP_PATTERNS = re.compile(
    r"(为什么.*导致|如何.*影响|.*的原因.*是什么|.*之间.*关系|因为.*所以|如果.*那么)", re.IGNORECASE
)
_COMPREHENSIVE_PATTERNS = re.compile(
    r"(总结|概述|综述|全面|详细|系统地|完整地|分析|梳理|列举所有|summarize|overview|comprehensive)",
    re.IGNORECASE,
)
_QUESTION_WORDS = re.compile(
    r"(什么|怎么|如何|为什么|哪些|哪个|多少|是否|能否|what|how|why|which|when|where)", re.IGNORECASE
)


def _count_sub_questions(query: str) -> int:
    """Estimate number of sub-questions in a query."""
    # Count question marks
    qmarks = query.count("？") + query.count("?")
    # Count semicolons/numbered items that suggest multiple parts
    parts = len(re.findall(r"[;；]\s*|[1-9][.、)]", query))
    return max(qmarks, parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def classify_complexity(
    query: str,
    chat_history: Optional[List[dict]] = None,
    llm_config=None,
    method: str = "rule",
) -> PipelineDecision:
    """Classify query complexity and return pipeline parameters.

    Args:
        query: The user's question.
        chat_history: Recent chat turns (for context-aware classification).
        llm_config: ModelConfig if LLM-based classification is requested.
        method: "rule" (default, 0ms) or "llm" (500-1500ms).

    Returns:
        PipelineDecision with tuned pipeline parameters.
    """
    if method == "llm" and llm_config:
        try:
            return await _llm_classify(query, llm_config)
        except Exception as e:
            logger.warning("LLM complexity classification failed: %s, falling back to rules", e)

    return _rule_classify(query)


def _rule_classify(query: str) -> PipelineDecision:
    """Rule-based complexity classification (<1ms)."""
    q = query.strip()
    length = len(q)
    sub_questions = _count_sub_questions(q)

    # SIMPLE: very short, no question words, single keyword
    if length <= 10 and not _QUESTION_WORDS.search(q) and sub_questions == 0:
        complexity = QueryComplexity.SIMPLE
    # VERY_COMPLEX: multi-hop reasoning, comprehensive analysis, or multiple sub-questions
    elif (
        _MULTI_HOP_PATTERNS.search(q)
        or (_COMPREHENSIVE_PATTERNS.search(q) and length > 30)
        or sub_questions >= 3
    ):
        complexity = QueryComplexity.VERY_COMPLEX
    # COMPLEX: multi-topic, comparison, or long query
    elif (
        _MULTI_TOPIC_PATTERNS.search(q)
        or _COMPARISON_PATTERNS.search(q)
        or length > 50
        or sub_questions >= 2
    ):
        complexity = QueryComplexity.COMPLEX
    # MODERATE: standard question
    else:
        complexity = QueryComplexity.MODERATE

    decision = _PIPELINE_MAP[complexity]
    logger.debug("Query complexity: %s (len=%d, sub_q=%d) → %s", q[:40], length, sub_questions, complexity.value)
    return decision


_LLM_CLASSIFY_PROMPT = """分析以下查询的复杂度，用于决定检索策略。

查询：{query}

复杂度级别：
- simple: 简单关键词查找，单一事实
- moderate: 标准问句，单一主题
- complex: 多主题/比较/长查询
- very_complex: 多跳推理、综合分析、条件逻辑

只输出一个 JSON：{{"complexity": "simple|moderate|complex|very_complex"}}"""


async def _llm_classify(query: str, llm_config) -> PipelineDecision:
    """LLM-based complexity classification."""
    import json
    from app.core.llm_client import chat_completion

    prompt = _LLM_CLASSIFY_PROMPT.replace("{query}", query)
    messages = [
        {"role": "system", "content": "你是查询分析专家。只输出 JSON。"},
        {"role": "user", "content": prompt},
    ]

    result = await chat_completion(llm_config, messages, stream=False)
    result_text = result.strip()
    if "```" in result_text:
        result_text = result_text.split("```")[1]
        if result_text.startswith("json"):
            result_text = result_text[4:]
        result_text = result_text.strip()

    parsed = json.loads(result_text)
    level = parsed.get("complexity", "moderate")

    try:
        complexity = QueryComplexity(level)
    except ValueError:
        complexity = QueryComplexity.MODERATE

    return _PIPELINE_MAP[complexity]
