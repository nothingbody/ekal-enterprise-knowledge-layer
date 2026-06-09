"""Plan execution engine for query decomposition.

Executes a QueryPlan by running steps in dependency order:
- retrieve steps → call retrieval_service.retrieve()
- analyze steps → LLM reasoning over dependent step results
- synthesize steps → LLM combines all results into final answer

The executor emits streaming events for each step and records trajectory
steps when trajectory recording is enabled.
"""
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agentic_rag.query_planner import QueryPlan, PlanStep, StepAction
from app.schemas.chat import RetrievalResult

logger = logging.getLogger(__name__)


@dataclass
class PlanExecutionResult:
    """Result of executing a complete query plan."""
    final_answer: str
    retrieval_results: List[RetrievalResult]
    plan: QueryPlan
    step_count: int
    total_ms: float


_SYNTHESIZE_PROMPT = """基于以下分步检索和分析的结果，请综合回答用户的原始问题。

用户原始问题：{original_query}

各步骤结果：
{step_results}

请给出完整、准确、有条理的最终回答。确保覆盖所有子问题的要点。如果某些子问题未找到相关信息，请如实说明。"""


_ANALYZE_PROMPT = """基于以下信息进行分析推理。

分析指令：{instruction}

参考信息：
{context}

请给出有逻辑、有依据的分析结果。"""


async def execute_plan(
    plan: QueryPlan,
    db: AsyncSession,
    kb_id: int,
    user_id: Optional[int],
    model_config,
    chat_history: Optional[List[dict]] = None,
    top_k: int = 5,
    user_context_embedding: Optional[List[float]] = None,
    blend_weight: float = 0.1,
    event_callback: Optional[Callable] = None,
    recorder=None,
) -> PlanExecutionResult:
    """Execute a query plan step by step in dependency order.

    Args:
        plan: The QueryPlan to execute.
        db: Database session.
        kb_id: Knowledge base ID for retrieval steps.
        user_id: Current user ID.
        model_config: LLM model configuration for analyze/synthesize.
        chat_history: Recent conversation history.
        top_k: Number of results per retrieval step.
        user_context_embedding: User interest vector for personalized retrieval.
        blend_weight: Blend weight for memory-enhanced retrieval.
        event_callback: Streaming event callback.
        recorder: TrajectoryRecorder instance (or None).

    Returns:
        PlanExecutionResult with final answer and merged retrieval results.
    """
    from app.services.retrieval_service import retrieve
    from app.core.llm_client import chat_completion

    t_start = time.monotonic()
    all_retrieval_results: List[RetrievalResult] = []

    def _emit(data: dict):
        if event_callback:
            event_callback({"stage": "plan_execute", **data})

    execution_layers = plan.execution_order()
    logger.info("Executing plan: %d steps in %d layers", len(plan.steps), len(execution_layers))

    for layer_idx, layer in enumerate(execution_layers):
        for step_id in layer:
            step = plan.get_step(step_id)
            if not step:
                continue

            step.status = "running"
            _emit({"step_id": step.step_id, "action": step.action.value,
                   "query": step.query[:100], "status": "running"})

            t0 = time.monotonic()

            try:
                if step.action == StepAction.RETRIEVE:
                    results = await retrieve(
                        db, kb_id, step.query,
                        top_k=top_k,
                        enable_rewrite=True,
                        user_id=user_id,
                        chat_history=chat_history,
                        blend_embedding=user_context_embedding,
                        blend_weight=blend_weight,
                    )
                    step.result = _format_retrieval_for_plan(results)
                    all_retrieval_results.extend(results)

                elif step.action == StepAction.ANALYZE:
                    dep_context = _collect_dependency_results(plan, step)
                    prompt = _ANALYZE_PROMPT.replace("{instruction}", step.query)
                    prompt = prompt.replace("{context}", dep_context)
                    messages = [
                        {"role": "system", "content": "你是数据分析专家。"},
                        {"role": "user", "content": prompt},
                    ]
                    step.result = await chat_completion(model_config, messages, stream=False)

                elif step.action == StepAction.SYNTHESIZE:
                    step_results = _collect_all_step_results(plan, step)
                    prompt = _SYNTHESIZE_PROMPT.replace("{original_query}", plan.original_query)
                    prompt = prompt.replace("{step_results}", step_results)
                    messages = [
                        {"role": "system", "content": "你是知识综合专家。请基于提供的分步结果给出完整回答。"},
                        {"role": "user", "content": prompt},
                    ]
                    step.result = await chat_completion(model_config, messages, stream=False)

                step.status = "completed"

            except Exception as exc:
                logger.warning("Plan step %d failed: %s", step.step_id, exc)
                step.status = "failed"
                step.result = f"(步骤执行失败: {type(exc).__name__})"

            step.duration_ms = (time.monotonic() - t0) * 1000

            _emit({"step_id": step.step_id, "action": step.action.value,
                   "status": step.status, "ms": round(step.duration_ms, 1)})

            if recorder:
                recorder.add_step(
                    stage="plan_execute",
                    action=f"{step.action.value}:{step.step_id}",
                    parameters={"query": step.query[:200], "depends_on": step.depends_on},
                    duration_ms=step.duration_ms,
                    state_snapshot={"result_len": len(str(step.result or "")[:500])},
                )

    total_ms = (time.monotonic() - t_start) * 1000

    # Final answer is the result of the last step (should be synthesize)
    final_answer = ""
    for step in reversed(plan.steps):
        if step.result and step.status == "completed":
            final_answer = str(step.result)
            break

    # Deduplicate retrieval results
    seen = set()
    unique_results = []
    for r in all_retrieval_results:
        key = (r.doc_name, r.chunk_index)
        if key not in seen:
            seen.add(key)
            unique_results.append(r)

    return PlanExecutionResult(
        final_answer=final_answer,
        retrieval_results=unique_results,
        plan=plan,
        step_count=len(plan.steps),
        total_ms=round(total_ms, 1),
    )


def _format_retrieval_for_plan(results: List[RetrievalResult]) -> str:
    """Format retrieval results into readable text for use in subsequent steps."""
    if not results:
        return "(未找到相关信息)"
    parts = []
    for i, r in enumerate(results[:5]):
        parts.append(f"[{i+1}] {r.doc_name} (相关度: {r.score:.2f})\n{r.content[:500]}")
    return "\n\n".join(parts)


def _collect_dependency_results(plan: QueryPlan, step: PlanStep) -> str:
    """Collect results from all dependency steps."""
    parts = []
    for dep_id in step.depends_on:
        dep = plan.get_step(dep_id)
        if dep and dep.result:
            parts.append(f"--- 步骤 {dep.step_id} ({dep.action.value}: {dep.query[:50]}) ---\n{dep.result}")
    return "\n\n".join(parts) if parts else "(无依赖结果)"


def _collect_all_step_results(plan: QueryPlan, synth_step: PlanStep) -> str:
    """Collect results from all steps that the synthesis step depends on."""
    parts = []
    for dep_id in synth_step.depends_on:
        dep = plan.get_step(dep_id)
        if dep and dep.result:
            label = {"retrieve": "检索", "analyze": "分析", "synthesize": "综合"}.get(dep.action.value, dep.action.value)
            parts.append(f"### 步骤 {dep.step_id} ({label}): {dep.query[:80]}\n{dep.result}")
    return "\n\n".join(parts) if parts else "(无可用结果)"
