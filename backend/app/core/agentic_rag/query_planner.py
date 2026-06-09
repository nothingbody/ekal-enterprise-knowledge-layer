"""Query decomposition planner for complex multi-step questions.

For very_complex queries, the planner uses LLM to decompose the question
into a DAG of sub-tasks (retrieve, analyze, synthesize) with explicit
dependencies, enabling structured multi-step retrieval and reasoning.

Only activated when:
- enable_query_planning is True in AgenticRAGConfig
- Query complexity is classified as very_complex
"""
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_PLAN_STEPS = 8


class StepAction(str, Enum):
    RETRIEVE = "retrieve"       # KB search with a targeted sub-query
    SYNTHESIZE = "synthesize"   # Combine results from dependency steps
    ANALYZE = "analyze"         # LLM reasoning over collected data


@dataclass
class PlanStep:
    """One step in the query execution plan."""
    step_id: int
    action: StepAction
    query: str                          # Sub-query or instruction
    depends_on: List[int] = field(default_factory=list)
    result: Optional[Any] = None        # Populated during execution
    status: str = "pending"             # pending | running | completed | failed
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "action": self.action.value,
            "query": self.query,
            "depends_on": self.depends_on,
            "status": self.status,
            "duration_ms": round(self.duration_ms, 1),
        }


@dataclass
class QueryPlan:
    """Structured plan for executing a complex query."""
    original_query: str
    steps: List[PlanStep]
    reasoning: str = ""

    def execution_order(self) -> List[List[int]]:
        """Return topological layers for dependency-ordered execution.

        Each layer contains step IDs that can execute after all previous
        layers are complete. Steps within a layer have no mutual dependencies.
        """
        completed = set()
        layers = []
        remaining = {s.step_id for s in self.steps}

        while remaining:
            layer = []
            for s in self.steps:
                if s.step_id in remaining and all(d in completed for d in s.depends_on):
                    layer.append(s.step_id)
            if not layer:
                # Cycle or unresolvable dependency — break to avoid infinite loop
                logger.warning("Plan has unresolvable dependencies: remaining=%s", remaining)
                layer = list(remaining)  # force-execute remaining
            for sid in layer:
                remaining.discard(sid)
                completed.add(sid)
            layers.append(layer)

        return layers

    def is_valid(self) -> bool:
        """Validate plan structure: no cycles, all deps exist, bounded size."""
        if not self.steps or len(self.steps) > MAX_PLAN_STEPS:
            return False
        ids = {s.step_id for s in self.steps}
        for s in self.steps:
            for d in s.depends_on:
                if d not in ids or d >= s.step_id:
                    return False  # dependency must reference earlier step
        # Check for synthesize at the end
        last = self.steps[-1]
        if last.action != StepAction.SYNTHESIZE and len(self.steps) > 2:
            return False  # multi-step plans should end with synthesis
        return True

    def get_step(self, step_id: int) -> Optional[PlanStep]:
        for s in self.steps:
            if s.step_id == step_id:
                return s
        return None

    def to_dict(self) -> dict:
        return {
            "original_query": self.original_query,
            "reasoning": self.reasoning,
            "steps": [s.to_dict() for s in self.steps],
        }


# ---------------------------------------------------------------------------
# LLM-based planner
# ---------------------------------------------------------------------------

_PLAN_PROMPT = """你是一个查询分析和任务规划专家。将以下复杂问题分解为可执行的子任务计划。

用户问题：{query}

可用操作：
- retrieve: 从知识库检索特定信息（提供具体的搜索子问题）
- analyze: 对已收集的数据进行分析推理（在 depends_on 中指定依赖步骤）
- synthesize: 综合多个步骤的结果生成最终答案（必须作为最后一步）

规则：
1. 每个 retrieve 步骤应该针对一个具体的、独立的子问题
2. synthesize 必须是最后一步，且依赖之前的所有关键步骤
3. depends_on 中的 ID 必须引用前面已定义的步骤（ID 更小的步骤）
4. 步骤数量控制在 3-{max_steps} 个
5. 不要生成多余的步骤，够用即可

严格按以下 JSON 格式输出（不要输出其他内容）：
{{
  "reasoning": "分解思路说明",
  "steps": [
    {{"step_id": 1, "action": "retrieve", "query": "子问题1", "depends_on": []}},
    {{"step_id": 2, "action": "retrieve", "query": "子问题2", "depends_on": []}},
    {{"step_id": 3, "action": "synthesize", "query": "综合以上结果回答原始问题", "depends_on": [1, 2]}}
  ]
}}"""


async def create_plan(
    query: str,
    llm_config,
    chat_history: Optional[List[dict]] = None,
) -> Optional[QueryPlan]:
    """Use LLM to decompose a complex query into a structured plan.

    Returns QueryPlan if successful, None on failure (graceful degradation
    to standard retrieval).
    """
    from app.core.llm_client import chat_completion

    prompt = _PLAN_PROMPT.replace("{query}", query).replace("{max_steps}", str(MAX_PLAN_STEPS))
    messages = [
        {"role": "system", "content": "你是查询规划专家。只输出 JSON，不要输出其他内容。"},
        {"role": "user", "content": prompt},
    ]

    try:
        result = await chat_completion(llm_config, messages, stream=False)
        result_text = result.strip()

        # Handle markdown code blocks
        if "```" in result_text:
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
            result_text = result_text.strip()

        parsed = json.loads(result_text)
        return _parse_plan(query, parsed)

    except Exception as exc:
        logger.warning("Query plan creation failed, falling back to standard retrieval: %s", exc)
        return None


def _parse_plan(query: str, parsed: dict) -> Optional[QueryPlan]:
    """Parse LLM response into a validated QueryPlan."""
    reasoning = parsed.get("reasoning", "")
    raw_steps = parsed.get("steps", [])

    if not raw_steps or len(raw_steps) > MAX_PLAN_STEPS:
        return None

    steps = []
    for s in raw_steps:
        try:
            action = StepAction(s.get("action", "retrieve"))
        except ValueError:
            action = StepAction.RETRIEVE
        steps.append(PlanStep(
            step_id=int(s.get("step_id", len(steps) + 1)),
            action=action,
            query=s.get("query", query),
            depends_on=s.get("depends_on", []),
        ))

    plan = QueryPlan(original_query=query, steps=steps, reasoning=reasoning)
    if not plan.is_valid():
        logger.warning("Generated plan failed validation, discarding")
        return None
    return plan
