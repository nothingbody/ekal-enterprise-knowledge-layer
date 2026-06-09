"""Agentic RAG Orchestrator.

Central coordination layer that conditionally activates pipeline stages
(adaptive retrieval, complexity classification, retrieval evaluation, corrective actions)
based on the AgenticRAGConfig.

Wraps around the existing retrieve() function — when all features are disabled,
the orchestrator is not invoked at all (see chat_service.py integration).
"""
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.core.agentic_rag.trajectory import Trajectory

from app.models.model_config import ModelConfig
from app.schemas.chat import RetrievalResult
from app.core.agentic_rag.config import AgenticRAGConfig

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorResult:
    """Result of the agentic RAG orchestration."""
    retrieval_results: List[RetrievalResult]
    metadata: dict = field(default_factory=dict)
    skipped_retrieval: bool = False
    bypass_reason: Optional[str] = None
    iterations_used: int = 1
    corrective_actions: List[str] = field(default_factory=list)
    trajectory: Optional["Trajectory"] = None


class AgenticRAGOrchestrator:
    """Orchestrates the agentic RAG pipeline stages."""

    def __init__(self, config: AgenticRAGConfig):
        self.config = config

    async def execute(
        self,
        db: AsyncSession,
        query: str,
        kb_id: int,
        user_id: Optional[int],
        model_config: ModelConfig,
        chat_history: Optional[List[dict]] = None,
        top_k: int = 5,
        score_threshold: Optional[float] = None,
        enable_rewrite: bool = True,
        event_callback: Optional[Callable] = None,
        metadata_out: Optional[dict] = None,
        user_context_embedding: Optional[List[float]] = None,
        blend_weight: float = 0.1,
    ) -> OrchestratorResult:
        """Execute the full agentic RAG pipeline.

        Args:
            db: Database session.
            query: User's question.
            kb_id: Knowledge base ID.
            user_id: Current user ID.
            model_config: LLM model configuration.
            chat_history: Recent chat history.
            top_k: Number of results to return.
            score_threshold: Minimum score filter.
            enable_rewrite: Whether query rewriting is allowed.
            event_callback: Optional callback for streaming status events.
            metadata_out: Optional dict to populate with RAG metadata.
            user_context_embedding: User interest vector for memory-enhanced retrieval.
            blend_weight: Weight for blending user interest into query embedding.

        Returns:
            OrchestratorResult with retrieval results and pipeline trace.
        """
        trace = {}
        corrective_actions = []
        t_start = time.monotonic()

        # Trajectory recorder (zero overhead when disabled)
        recorder = None
        if self.config.enable_trajectory_recording:
            from app.core.agentic_rag.trajectory import TrajectoryRecorder
            recorder = TrajectoryRecorder(
                query=query, kb_id=kb_id, user_id=user_id,
                config_snapshot=self.config.model_dump(),
            )
            recorder.add_step(
                stage="init", action="start", parameters={"top_k": top_k},
                duration_ms=0,
                state_snapshot={"query": query[:200], "doc_count": 0},
            )

        def _emit(stage: str, data: dict):
            """Send an agentic_status event if callback is provided."""
            if event_callback:
                event_callback({"stage": stage, **data})

        # ---------------------------------------------------------------
        # Step 0 (optional): Trajectory policy hints
        # ---------------------------------------------------------------
        if self.config.enable_trajectory_recording:
            try:
                from app.core.agentic_rag.trajectory_policy import TrajectoryPolicy
                policy = TrajectoryPolicy()
                _hint = await policy.suggest_pipeline_override(db, query, kb_id)
                if _hint:
                    trace["policy_hint"] = _hint
                    _emit("policy_hint", {"hints": _hint})
                    if recorder:
                        recorder.add_step(
                            stage="policy_hint", action="policy_hint",
                            parameters=_hint, duration_ms=0,
                        )
                    logger.debug("Trajectory policy hint for kb_id=%s: %s", kb_id, _hint)
            except Exception as _pol_exc:
                logger.debug("Trajectory policy hint failed: %s", _pol_exc)

        # ---------------------------------------------------------------
        # Step 1: Adaptive Retrieval (Self-RAG)
        # ---------------------------------------------------------------
        if self.config.enable_adaptive_retrieval:
            from app.core.agentic_rag.adaptive_retrieval import should_retrieve

            t0 = time.monotonic()
            decision = await should_retrieve(
                query,
                llm_config=model_config,
                chat_history=chat_history,
                use_llm=(self.config.complexity_method == "llm"),
            )
            dt = (time.monotonic() - t0) * 1000
            trace["adaptive_retrieval"] = {
                "needs_retrieval": decision.needs_retrieval,
                "reason": decision.reason,
                "bypass_type": decision.bypass_type,
                "ms": round(dt, 1),
            }
            _emit("adaptive_check", {
                "result": "needs_retrieval" if decision.needs_retrieval else "skip",
                "reason": decision.reason,
                "ms": round(dt, 1),
            })

            if recorder:
                recorder.add_step(
                    stage="adaptive_check",
                    action="skip_retrieval" if not decision.needs_retrieval else "proceed",
                    parameters={"reason": decision.reason, "bypass_type": decision.bypass_type},
                    duration_ms=dt,
                    reward=decision.confidence if not decision.needs_retrieval else None,
                    reward_source="bypass_confidence" if not decision.needs_retrieval else None,
                    state_snapshot={"query": query[:200], "doc_count": 0},
                )

            if not decision.needs_retrieval:
                logger.info(
                    "Agentic RAG: skipped retrieval (reason=%s, bypass=%s)",
                    decision.reason, decision.bypass_type,
                )
                return OrchestratorResult(
                    retrieval_results=[],
                    metadata=trace,
                    skipped_retrieval=True,
                    bypass_reason=decision.reason,
                    trajectory=recorder.finalize("skipped") if recorder else None,
                )

        # ---------------------------------------------------------------
        # Step 2: Query Complexity Classification
        # ---------------------------------------------------------------
        pipeline_kwargs = {}  # extra kwargs for retrieve()
        if self.config.enable_dynamic_pipeline:
            from app.core.agentic_rag.query_complexity import classify_complexity

            t0 = time.monotonic()
            pipeline = await classify_complexity(
                query,
                chat_history=chat_history,
                llm_config=model_config,
                method=self.config.complexity_method,
            )
            dt = (time.monotonic() - t0) * 1000
            trace["complexity"] = {**pipeline.to_dict(), "ms": round(dt, 1)}
            _emit("complexity", {
                "result": pipeline.complexity.value,
                "pipeline": pipeline.to_dict(),
                "ms": round(dt, 1),
            })

            pipeline_kwargs = {
                "force_multi_query": pipeline.enable_multi_query,
                "force_rerank": pipeline.enable_rerank,
                "override_context_window": pipeline.context_window,
                "fetch_k_multiplier": pipeline.fetch_k_multiplier,
            }
            # If pipeline says skip rewrite, override
            if not pipeline.enable_rewrite:
                enable_rewrite = False

            if recorder:
                recorder.add_step(
                    stage="complexity",
                    action="classify_complexity",
                    parameters=pipeline.to_dict(),
                    duration_ms=dt,
                    state_snapshot={"query": query[:200], "doc_count": 0},
                )

        # ---------------------------------------------------------------
        # Step 2.5: Query Planning for very_complex queries
        # ---------------------------------------------------------------
        if (
            self.config.enable_query_planning
            and trace.get("complexity", {}).get("complexity") == "very_complex"
        ):
            from app.core.agentic_rag.query_planner import create_plan
            from app.core.agentic_rag.plan_executor import execute_plan

            t0 = time.monotonic()
            plan = await create_plan(query, model_config, chat_history)
            dt_plan = (time.monotonic() - t0) * 1000

            if plan and plan.is_valid():
                trace["planning"] = {
                    "step_count": len(plan.steps),
                    "reasoning": plan.reasoning[:200],
                    "planning_ms": round(dt_plan, 1),
                }
                _emit("planning", {
                    "step_count": len(plan.steps),
                    "reasoning": plan.reasoning[:200],
                    "ms": round(dt_plan, 1),
                })
                if recorder:
                    recorder.add_step(
                        stage="planning", action="create_plan",
                        parameters={"step_count": len(plan.steps)},
                        duration_ms=dt_plan,
                        state_snapshot={"reasoning": plan.reasoning[:200]},
                    )

                plan_result = await execute_plan(
                    plan, db, kb_id, user_id, model_config,
                    chat_history=chat_history, top_k=top_k,
                    user_context_embedding=user_context_embedding,
                    blend_weight=blend_weight,
                    event_callback=event_callback,
                    recorder=recorder,
                )
                trace["plan_execution"] = {
                    "step_count": plan_result.step_count,
                    "total_ms": plan_result.total_ms,
                    "result_count": len(plan_result.retrieval_results),
                }

                total_ms = (time.monotonic() - t_start) * 1000
                trace["total_ms"] = round(total_ms, 1)

                return OrchestratorResult(
                    retrieval_results=plan_result.retrieval_results,
                    metadata=trace,
                    trajectory=recorder.finalize("success") if recorder else None,
                )
            else:
                logger.info("Query plan invalid or creation failed, falling back to standard retrieval")

        # ---------------------------------------------------------------
        # Step 3: Execute retrieval (existing pipeline)
        # ---------------------------------------------------------------
        from app.services.retrieval_service import retrieve

        t0 = time.monotonic()
        results = await retrieve(
            db, kb_id, query,
            top_k=top_k,
            enable_rewrite=enable_rewrite,
            score_threshold=score_threshold,
            user_id=user_id,
            chat_history=chat_history,
            metadata_out=metadata_out,
            blend_embedding=user_context_embedding,
            blend_weight=blend_weight,
            **pipeline_kwargs,
        )
        dt = (time.monotonic() - t0) * 1000
        trace["retrieval"] = {
            "count": len(results),
            "top_score": round(results[0].score, 4) if results else None,
            "ms": round(dt, 1),
        }

        if recorder:
            _top = round(results[0].score, 4) if results else None
            recorder.add_step(
                stage="retrieval",
                action="retrieve",
                parameters={"count": len(results), "top_k": top_k, **pipeline_kwargs},
                duration_ms=dt,
                reward=_top,
                reward_source="retrieval_score",
                state_snapshot={"query": query[:200], "doc_count": len(results), "top_score": _top},
            )

        # ---------------------------------------------------------------
        # Step 4: Retrieval Quality Evaluation (Corrective RAG)
        # ---------------------------------------------------------------
        if self.config.enable_retrieval_evaluation and results:
            from app.core.agentic_rag.retrieval_evaluator import evaluate_retrieval

            t0 = time.monotonic()
            evaluation = await evaluate_retrieval(
                model_config, query, results,
                threshold=self.config.relevance_threshold,
            )
            dt = (time.monotonic() - t0) * 1000
            trace["evaluation"] = {
                "verdict": evaluation.verdict,
                "relevant_count": len(evaluation.relevant_results),
                "action": evaluation.corrective_action,
                "confidence": round(evaluation.confidence, 3),
                "ms": round(dt, 1),
            }
            _emit("evaluation", {
                "verdict": evaluation.verdict,
                "action": evaluation.corrective_action,
                "relevant_count": len(evaluation.relevant_results),
                "ms": round(dt, 1),
            })

            if evaluation.verdict == "sufficient":
                # All good, use results as-is
                if recorder:
                    recorder.add_step(
                        stage="evaluation", action="accept",
                        parameters={"verdict": "sufficient"},
                        duration_ms=dt,
                        reward=evaluation.confidence,
                        reward_source="eval_confidence",
                        state_snapshot={"doc_count": len(results)},
                    )
            elif evaluation.verdict == "partial":
                # Keep only relevant results
                results = evaluation.relevant_results
                corrective_actions.append("filter_irrelevant")
                if recorder:
                    recorder.add_step(
                        stage="evaluation", action="filter_irrelevant",
                        parameters={"verdict": "partial", "kept": len(results)},
                        duration_ms=dt,
                        reward=evaluation.confidence,
                        reward_source="eval_confidence",
                        state_snapshot={"doc_count": len(results)},
                    )
            elif evaluation.verdict == "insufficient":
                if recorder:
                    recorder.add_step(
                        stage="evaluation",
                        action=evaluation.corrective_action or "unknown",
                        parameters={"verdict": "insufficient", "action": evaluation.corrective_action},
                        duration_ms=dt,
                        reward=evaluation.confidence,
                        reward_source="eval_confidence",
                        state_snapshot={"doc_count": len(results)},
                    )
                results = await self._handle_corrective_action(
                    db, evaluation, query, kb_id, user_id, top_k,
                    chat_history, model_config, results, corrective_actions,
                    metadata_out, pipeline_kwargs,
                )
                if recorder:
                    recorder.add_step(
                        stage="corrective", action=corrective_actions[-1] if corrective_actions else "fallback",
                        parameters={"result_count": len(results)},
                        duration_ms=0,
                        state_snapshot={"doc_count": len(results), "top_score": round(results[0].score, 4) if results else None},
                    )

        total_ms = (time.monotonic() - t_start) * 1000
        trace["total_ms"] = round(total_ms, 1)

        # Determine outcome based on results
        _outcome = "skipped"
        if results:
            _top = results[0].score if results else 0
            _outcome = "success" if _top >= 0.5 else "partial"
        elif not results and not corrective_actions:
            _outcome = "failure"

        return OrchestratorResult(
            retrieval_results=results,
            metadata=trace,
            corrective_actions=corrective_actions,
            trajectory=recorder.finalize(_outcome) if recorder else None,
        )

    async def _handle_corrective_action(
        self,
        db: AsyncSession,
        evaluation,
        query: str,
        kb_id: int,
        user_id: Optional[int],
        top_k: int,
        chat_history: Optional[List[dict]],
        model_config: ModelConfig,
        original_results: List[RetrievalResult],
        corrective_actions: List[str],
        metadata_out: Optional[dict],
        pipeline_kwargs: dict,
    ) -> List[RetrievalResult]:
        """Execute corrective action based on evaluation."""
        action = evaluation.corrective_action

        if action == "requery" and evaluation.refined_query:
            corrective_actions.append("requery")
            logger.info("CRAG: re-querying with refined query: %r", evaluation.refined_query[:60])
            from app.services.retrieval_service import retrieve
            new_results = await retrieve(
                db, kb_id, evaluation.refined_query,
                top_k=top_k,
                enable_rewrite=False,  # already refined
                user_id=user_id,
                chat_history=chat_history,
                metadata_out=metadata_out,
                **pipeline_kwargs,
            )
            if new_results:
                return new_results
            return original_results  # fallback to original if re-query also fails

        elif action == "web_fallback":
            corrective_actions.append("web_fallback")
            logger.info("CRAG: falling back to web search for: %r", query[:60])
            try:
                web_results = await self._web_search_fallback(query, model_config, top_k)
                if web_results:
                    # Merge web results with any relevant KB results
                    return evaluation.relevant_results + web_results
            except Exception as e:
                logger.warning("CRAG web fallback failed: %s", e)
            return evaluation.relevant_results if evaluation.relevant_results else original_results

        elif action == "broaden":
            corrective_actions.append("broaden")
            logger.info("CRAG: broadening search with increased top_k")
            from app.services.retrieval_service import retrieve
            broader = await retrieve(
                db, kb_id, query,
                top_k=top_k * 2,
                enable_rewrite=True,
                user_id=user_id,
                chat_history=chat_history,
                metadata_out=metadata_out,
                fetch_k_multiplier=2.0,
            )
            return broader if broader else original_results

        # No recognized action, return relevant results or original
        return evaluation.relevant_results if evaluation.relevant_results else original_results

    async def _web_search_fallback(
        self, query: str, model_config: ModelConfig, top_k: int
    ) -> List[RetrievalResult]:
        """Use the built-in web search tool as a fallback retrieval source."""
        from app.core.tools import get_default_registry

        registry = get_default_registry()
        try:
            result = await registry.execute(
                "web_search",
                query=query,
                _model_config=model_config,
            )
            if not result.success or not result.data:
                return []

            # Convert web search results to RetrievalResult format
            web_items = result.data if isinstance(result.data, list) else [result.data]
            retrieval_results = []
            for i, item in enumerate(web_items[:top_k]):
                content = item.get("text", item.get("snippet", str(item))) if isinstance(item, dict) else str(item)
                title = item.get("title", "网络搜索结果") if isinstance(item, dict) else "网络搜索结果"
                retrieval_results.append(RetrievalResult(
                    content=content,
                    score=0.5,  # neutral score for web results
                    doc_name=f"[网络] {title}",
                    chunk_index=i,
                    source_type="web",
                ))
            return retrieval_results
        except Exception as e:
            logger.warning("Web search fallback failed: %s", e)
            return []
