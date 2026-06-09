"""Corrective RAG: Retrieval quality evaluation module.

Evaluates whether retrieved documents actually answer the user's query.
If quality is insufficient, suggests corrective actions (re-query, web fallback, broaden).
"""
import json
import logging
from dataclasses import dataclass, field
from typing import List, Optional

from app.schemas.chat import RetrievalResult

logger = logging.getLogger(__name__)


@dataclass
class RetrievalEvaluation:
    """Result of retrieval quality evaluation."""
    verdict: str  # "sufficient" | "partial" | "insufficient"
    relevant_results: List[RetrievalResult]
    irrelevant_indices: List[int] = field(default_factory=list)
    confidence: float = 0.0
    corrective_action: Optional[str] = None  # "none" | "requery" | "web_fallback" | "broaden"
    refined_query: Optional[str] = None  # suggested re-query if action is "requery"


# ---------------------------------------------------------------------------
# LLM prompt
# ---------------------------------------------------------------------------

_EVALUATION_PROMPT = """你是检索质量评估专家。评估以下检索结果能否回答用户的问题。

用户问题：{query}

检索结果：
{formatted_results}

请对每条检索结果评分（0到1，1=完全相关，0=完全无关），并判断整体检索质量。

严格按以下 JSON 格式输出（不要输出其他内容）：
{{
  "scores": [0.8, 0.3],
  "verdict": "sufficient",
  "reason": "简要说明",
  "suggested_action": "none",
  "refined_query": null
}}

verdict 取值：
- "sufficient": 检索结果足以回答问题
- "partial": 部分相关，可以用相关部分回答
- "insufficient": 检索结果几乎无法回答问题

suggested_action 取值：
- "none": 不需要修正
- "requery": 建议用新的查询重新检索（须提供 refined_query）
- "web_fallback": 建议用网络搜索补充
- "broaden": 建议扩大检索范围（增大 top_k）"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def evaluate_retrieval(
    llm_config,
    query: str,
    results: List[RetrievalResult],
    threshold: float = 0.6,
) -> RetrievalEvaluation:
    """Evaluate retrieval results for relevance using LLM.

    Args:
        llm_config: ModelConfig for the evaluation LLM call.
        query: The user's original question.
        results: Retrieved documents to evaluate.
        threshold: Minimum per-document score to consider relevant.

    Returns:
        RetrievalEvaluation with verdict and corrective action.
    """
    if not results:
        return RetrievalEvaluation(
            verdict="insufficient",
            relevant_results=[],
            confidence=1.0,
            corrective_action="requery",
        )

    # Format results for prompt (limit content length)
    formatted = []
    for i, r in enumerate(results):
        content_preview = r.content[:300] + "..." if len(r.content) > 300 else r.content
        formatted.append(f"[{i+1}] 来源: {r.doc_name} (得分: {r.score:.3f})\n{content_preview}")
    formatted_text = "\n\n".join(formatted)

    prompt = _EVALUATION_PROMPT.replace("{query}", query).replace("{formatted_results}", formatted_text)

    try:
        from app.core.llm_client import chat_completion

        messages = [
            {"role": "system", "content": "你是检索质量评估专家。只输出 JSON，不要输出其他内容。"},
            {"role": "user", "content": prompt},
        ]

        result_text = await chat_completion(llm_config, messages, stream=False)
        result_text = result_text.strip()

        # Handle markdown code blocks
        if "```" in result_text:
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
            result_text = result_text.strip()

        parsed = json.loads(result_text)
        return _parse_evaluation(parsed, results, threshold)

    except Exception as e:
        logger.warning("Retrieval evaluation failed: %s, returning all results as-is", e)
        return RetrievalEvaluation(
            verdict="sufficient",
            relevant_results=results,
            confidence=0.3,
            corrective_action="none",
        )


def _parse_evaluation(
    parsed: dict,
    results: List[RetrievalResult],
    threshold: float,
) -> RetrievalEvaluation:
    """Parse LLM evaluation JSON into RetrievalEvaluation."""
    scores = parsed.get("scores", [])
    verdict = parsed.get("verdict", "sufficient")
    action = parsed.get("suggested_action", "none")
    refined = parsed.get("refined_query")

    # Validate verdict
    if verdict not in ("sufficient", "partial", "insufficient"):
        verdict = "sufficient"

    # Validate action
    if action not in ("none", "requery", "web_fallback", "broaden"):
        action = "none"

    # Filter relevant results by per-doc scores
    relevant = []
    irrelevant_indices = []
    for i, r in enumerate(results):
        score = scores[i] if i < len(scores) else 0.5
        if score >= threshold:
            relevant.append(r)
        else:
            irrelevant_indices.append(i)

    # If LLM says sufficient but all docs scored below threshold, override
    if not relevant and verdict == "sufficient":
        verdict = "partial"
        relevant = results  # keep all as fallback

    # Calculate confidence from average score
    avg_score = sum(scores) / len(scores) if scores else 0.5

    return RetrievalEvaluation(
        verdict=verdict,
        relevant_results=relevant,
        irrelevant_indices=irrelevant_indices,
        confidence=avg_score,
        corrective_action=action if verdict != "sufficient" else "none",
        refined_query=refined if action == "requery" else None,
    )
