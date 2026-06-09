"""FAIR-RAG: Answer quality evaluation and iterative refinement module.

Evaluates generated answer quality and suggests refined queries
for iterative retrieval when the answer is insufficient.
"""
import json
import logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AnswerEvaluation:
    """Result of answer quality evaluation."""
    is_sufficient: bool
    score: float  # 0.0 - 1.0
    deficiencies: List[str] = field(default_factory=list)
    refined_query: Optional[str] = None
    should_iterate: bool = False


# ---------------------------------------------------------------------------
# LLM prompt
# ---------------------------------------------------------------------------

_EVALUATION_PROMPT = """你是回答质量评估专家。评估以下回答是否充分回答了用户的问题。

用户问题：{query}

参考资料摘要（前500字）：
{context_summary}

生成的回答：
{answer}

当前是第 {iteration} 轮评估（最多 {max_iterations} 轮）。

评估维度：
1. 完整性：是否回答了问题的所有方面
2. 准确性：回答是否与参考资料一致，未凭空编造
3. 具体性：是否提供了具体信息而非笼统回答

严格按以下 JSON 格式输出（不要输出其他内容）：
{{
  "score": 0.8,
  "is_sufficient": true,
  "deficiencies": [],
  "refined_query": null
}}

如果不充分，deficiencies 列出缺失的方面，refined_query 提供一个补充检索查询来获取缺失信息。"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def evaluate_answer(
    llm_config,
    query: str,
    answer: str,
    context: str,
    iteration: int = 0,
    max_iterations: int = 2,
) -> AnswerEvaluation:
    """Evaluate generated answer quality and decide whether to iterate.

    Args:
        llm_config: ModelConfig for the evaluation LLM.
        query: Original user question.
        answer: Generated answer text.
        context: Retrieved context that was used for generation.
        iteration: Current iteration number (0-based).
        max_iterations: Maximum allowed iterations.

    Returns:
        AnswerEvaluation with quality score and refinement suggestion.
    """
    # Don't evaluate very short answers (likely errors)
    if not answer or len(answer.strip()) < 10:
        return AnswerEvaluation(
            is_sufficient=False,
            score=0.1,
            deficiencies=["回答过短或为空"],
            refined_query=query,
            should_iterate=(iteration < max_iterations),
        )

    # Don't evaluate error messages
    if answer.strip().startswith("⚠️"):
        return AnswerEvaluation(is_sufficient=True, score=0.0, should_iterate=False)

    # Last iteration: no more loops allowed
    if iteration >= max_iterations:
        return AnswerEvaluation(is_sufficient=True, score=0.5, should_iterate=False)

    context_summary = context[:500] + "..." if len(context) > 500 else context

    prompt = (
        _EVALUATION_PROMPT
        .replace("{query}", query)
        .replace("{context_summary}", context_summary)
        .replace("{answer}", answer[:1000])
        .replace("{iteration}", str(iteration + 1))
        .replace("{max_iterations}", str(max_iterations))
    )

    try:
        from app.core.llm_client import chat_completion

        messages = [
            {"role": "system", "content": "你是回答质量评估专家。只输出 JSON，不要输出其他内容。"},
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
        return _parse_answer_eval(parsed, iteration, max_iterations)

    except Exception as e:
        logger.warning("Answer evaluation failed: %s, skipping refinement", e)
        return AnswerEvaluation(is_sufficient=True, score=0.5, should_iterate=False)


def _parse_answer_eval(
    parsed: dict,
    iteration: int,
    max_iterations: int,
) -> AnswerEvaluation:
    """Parse LLM evaluation response into AnswerEvaluation."""
    score = float(parsed.get("score", 0.7))
    score = max(0.0, min(1.0, score))
    is_sufficient = bool(parsed.get("is_sufficient", True))
    deficiencies = parsed.get("deficiencies", [])
    refined_query = parsed.get("refined_query")

    if not isinstance(deficiencies, list):
        deficiencies = []

    # Determine whether to iterate
    should_iterate = (
        not is_sufficient
        and score < 0.7
        and refined_query
        and iteration < max_iterations
    )

    return AnswerEvaluation(
        is_sufficient=is_sufficient,
        score=score,
        deficiencies=deficiencies,
        refined_query=refined_query,
        should_iterate=should_iterate,
    )
