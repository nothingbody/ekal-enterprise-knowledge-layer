"""Self-RAG: Adaptive retrieval decision module.

Determines whether a query actually needs knowledge base retrieval,
saving latency and compute for greetings, chitchat, and simple requests.

Two modes:
- Rule-based (default): regex/heuristic patterns, <1ms latency
- LLM-based (optional): for ambiguous cases, 500-1500ms latency
"""
import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rule-based patterns (zero LLM cost)
# ---------------------------------------------------------------------------

_GREETING_PATTERNS = [
    r"^(你好|您好|hi|hello|hey|嗨|早上好|晚上好|下午好|早安|晚安|morning|afternoon|evening)\s*[!！。.~]*$",
]

_CHITCHAT_PATTERNS = [
    r"^(谢谢|thanks|thank\s*you|感谢|多谢|辛苦了)\s*[!！。.~]*$",
    r"^(再见|bye|拜拜|回见|下次见)\s*[!！。.~]*$",
    r"^(你是谁|你叫什么|who\s+are\s+you|你是什么|介绍一下你自己)\s*[?？]*$",
    r"^(好的|ok|嗯|明白了|知道了|收到|了解)\s*[!！。.~]*$",
    r"^(帮我|请问|请帮我)\s*$",  # incomplete requests
]

_ARITHMETIC_PATTERNS = [
    r"^\s*\d+(\.\d+)?\s*[\+\-\*\/\%\^]\s*\d+(\.\d+)?\s*[=？?]?\s*$",
    r"^(计算|算一下|算算)\s*\d+",
]

_TIME_PATTERNS = [
    r"^(几点了|什么时间|现在几点|今天几号|今天星期几|what\s+time|今天的?日期)\s*[?？]*$",
]

_ALL_BYPASS_RULES: List[tuple] = [
    ("greeting", _GREETING_PATTERNS),
    ("chitchat", _CHITCHAT_PATTERNS),
    ("arithmetic", _ARITHMETIC_PATTERNS),
    ("time_query", _TIME_PATTERNS),
]

# Pre-compile all patterns
_COMPILED_RULES: List[tuple] = []
for bypass_type, patterns in _ALL_BYPASS_RULES:
    for p in patterns:
        _COMPILED_RULES.append((bypass_type, re.compile(p, re.IGNORECASE)))


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class RetrievalDecision:
    """Result of the adaptive retrieval check."""
    needs_retrieval: bool
    reason: str
    confidence: float  # 0.0 - 1.0
    bypass_type: Optional[str] = None  # "greeting" | "chitchat" | "arithmetic" | "time_query" | None


# ---------------------------------------------------------------------------
# LLM prompt for uncertain cases
# ---------------------------------------------------------------------------

_LLM_DECISION_PROMPT = """判断以下用户问题是否需要从知识库中检索文档来回答。

问题：{query}

判断标准：
- 需要检索：涉及专业知识、文档内容、具体事实、技术问题、业务问题
- 不需要检索：闲聊、问候、简单计算、询问时间、关于AI助手本身的问题、感谢/告别

只输出一个 JSON（不要输出其他内容）：
{{"needs_retrieval": true, "reason": "简要原因"}}"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def should_retrieve(
    query: str,
    llm_config=None,
    chat_history: Optional[List[dict]] = None,
    use_llm: bool = False,
) -> RetrievalDecision:
    """Decide whether KB retrieval is needed for this query.

    Args:
        query: The user's question.
        llm_config: ModelConfig for LLM-based decision (optional).
        chat_history: Recent chat history (unused by rules, available for LLM).
        use_llm: If True and rules are uncertain, fall back to LLM classification.

    Returns:
        RetrievalDecision with needs_retrieval flag and reasoning.
    """
    query_stripped = query.strip()

    # Empty or very short queries
    if len(query_stripped) <= 1:
        return RetrievalDecision(
            needs_retrieval=False,
            reason="查询过短",
            confidence=0.95,
            bypass_type="chitchat",
        )

    # Rule-based matching
    for bypass_type, pattern in _COMPILED_RULES:
        if pattern.search(query_stripped):
            logger.debug(
                "Adaptive retrieval: skip (rule=%s) query=%r", bypass_type, query_stripped[:50]
            )
            return RetrievalDecision(
                needs_retrieval=False,
                reason=f"规则匹配: {bypass_type}",
                confidence=0.9,
                bypass_type=bypass_type,
            )

    # If LLM mode is requested and a model is available, try LLM classification
    if use_llm and llm_config:
        try:
            return await _llm_decision(query_stripped, llm_config)
        except Exception as e:
            logger.warning("Adaptive retrieval LLM fallback failed: %s", e)
            # Fall through to default: needs retrieval

    # Default: needs retrieval
    return RetrievalDecision(
        needs_retrieval=True,
        reason="默认需要检索",
        confidence=0.7,
    )


async def _llm_decision(query: str, llm_config) -> RetrievalDecision:
    """Use LLM to decide whether retrieval is needed."""
    import json
    from app.core.llm_client import chat_completion

    prompt = _LLM_DECISION_PROMPT.replace("{query}", query)
    messages = [
        {"role": "system", "content": "你是检索决策专家。只输出 JSON，不要输出其他内容。"},
        {"role": "user", "content": prompt},
    ]

    result = await chat_completion(llm_config, messages, stream=False)
    result_text = result.strip()

    # Extract JSON from response (handle markdown code blocks)
    if "```" in result_text:
        result_text = result_text.split("```")[1]
        if result_text.startswith("json"):
            result_text = result_text[4:]
        result_text = result_text.strip()

    parsed = json.loads(result_text)
    needs = parsed.get("needs_retrieval", True)
    reason = parsed.get("reason", "LLM 判断")

    return RetrievalDecision(
        needs_retrieval=bool(needs),
        reason=f"LLM: {reason}",
        confidence=0.85,
        bypass_type=None if needs else "llm_classified",
    )
