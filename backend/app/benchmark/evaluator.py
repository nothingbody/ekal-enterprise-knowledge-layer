"""
RAG Benchmark 评估器。
"""
import json
import time
import uuid
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any, Set
from pathlib import Path

from .models import (
    BenchmarkDataset,
    BenchmarkSample,
    BenchmarkResult,
    BenchmarkReport,
    RetrievalMetrics,
    AnswerMetrics,
    MetricsSummary,
    SampleCategory,
    Difficulty,
)
from .metrics import (
    calculate_hit_rate,
    calculate_mrr,
    calculate_recall_at_k,
    calculate_precision_at_k,
    calculate_first_relevant_rank,
    calculate_percentile,
)

logger = logging.getLogger(__name__)


class RAGEvaluator:
    """RAG 评测执行器。"""

    def __init__(
        self,
        retrieval_service,
        chat_service,
        llm_judge_model: Optional[str] = None,
    ):
        """
        初始化评估器。
        
        :param retrieval_service: 检索服务实例
        :param chat_service: 对话服务实例
        :param llm_judge_model: 用于 LLM-as-Judge 的模型 ID
        """
        self.retrieval_service = retrieval_service
        self.chat_service = chat_service
        self.llm_judge_model = llm_judge_model

    async def evaluate_sample(
        self,
        sample: BenchmarkSample,
        knowledge_base_id: int,
        model_config_id: int,
        top_k: int = 5,
    ) -> BenchmarkResult:
        """
        评测单个样本。
        
        :param sample: 评测样本
        :param knowledge_base_id: 知识库 ID
        :param model_config_id: 模型配置 ID
        :param top_k: 检索 Top-K
        :return: 评测结果
        """
        error = None
        generated_answer = ""
        
        try:
            # 执行检索
            retrieval_start = time.time()
            retrieval_result = await self.retrieval_service.search(
                query=sample.question,
                knowledge_base_id=knowledge_base_id,
                top_k=top_k,
            )
            retrieval_latency = (time.time() - retrieval_start) * 1000
            
            # 提取检索到的文档 ID
            retrieved_ids = [
                chunk.document_id for chunk in retrieval_result.chunks
            ] if hasattr(retrieval_result, 'chunks') else []
            
            # 计算检索指标
            relevant_set = set(sample.relevant_doc_ids)
            hit = bool(set(retrieved_ids) & relevant_set)
            rank = calculate_first_relevant_rank(retrieved_ids, relevant_set)
            recall = calculate_recall_at_k(retrieved_ids, relevant_set, top_k)
            precision = calculate_precision_at_k(retrieved_ids, relevant_set, top_k)
            
            retrieval_metrics = RetrievalMetrics(
                hit=hit,
                reciprocal_rank=1.0 / rank if rank > 0 else 0.0,
                recall_at_k=recall,
                precision_at_k=precision,
                retrieved_ids=retrieved_ids,
                latency_ms=retrieval_latency,
            )
            
            # 生成回答
            answer_start = time.time()
            context = self._format_context(retrieval_result)
            generated_answer = await self._generate_answer(
                question=sample.question,
                context=context,
                model_config_id=model_config_id,
            )
            answer_latency = (time.time() - answer_start) * 1000
            
            # 评估回答质量
            answer_metrics = await self._evaluate_answer(
                question=sample.question,
                answer=generated_answer,
                ground_truth=sample.ground_truth,
                context=context,
                latency_ms=answer_latency,
            )
            
        except Exception as e:
            logger.error(f"评测样本 {sample.id} 失败: {e}")
            error = str(e)
            retrieval_metrics = RetrievalMetrics(
                hit=False,
                reciprocal_rank=0.0,
                recall_at_k=0.0,
                precision_at_k=0.0,
                retrieved_ids=[],
                latency_ms=0.0,
            )
            answer_metrics = AnswerMetrics(
                correctness=0.0,
                citation_coverage=0.0,
                hallucination_detected=False,
                completeness=0.0,
                latency_ms=0.0,
                confidence=0.0,
            )
        
        return BenchmarkResult(
            sample_id=sample.id,
            question=sample.question,
            ground_truth=sample.ground_truth,
            generated_answer=generated_answer,
            retrieval_metrics=retrieval_metrics,
            answer_metrics=answer_metrics,
            error=error,
        )

    async def run_benchmark(
        self,
        dataset: BenchmarkDataset,
        knowledge_base_id: int,
        model_config_id: int,
        top_k: int = 5,
    ) -> BenchmarkReport:
        """
        执行完整评测。
        
        :param dataset: 评测数据集
        :param knowledge_base_id: 知识库 ID
        :param model_config_id: 模型配置 ID
        :param top_k: 检索 Top-K
        :return: 评测报告
        """
        logger.info(f"开始评测: {dataset.name} ({len(dataset)} 样本)")
        
        results: List[BenchmarkResult] = []
        for i, sample in enumerate(dataset.samples):
            logger.info(f"评测样本 {i+1}/{len(dataset)}: {sample.id}")
            result = await self.evaluate_sample(
                sample=sample,
                knowledge_base_id=knowledge_base_id,
                model_config_id=model_config_id,
                top_k=top_k,
            )
            results.append(result)
        
        # 生成报告
        report = self._generate_report(
            dataset=dataset,
            results=results,
            config={
                "knowledge_base_id": knowledge_base_id,
                "model_config_id": model_config_id,
                "top_k": top_k,
            },
        )
        
        logger.info(f"评测完成: 成功 {report.successful_samples}/{report.total_samples}")
        return report

    def _format_context(self, retrieval_result) -> str:
        """格式化检索结果为上下文。"""
        if not hasattr(retrieval_result, 'chunks') or not retrieval_result.chunks:
            return ""
        
        context_parts = []
        for i, chunk in enumerate(retrieval_result.chunks):
            content = chunk.content if hasattr(chunk, 'content') else str(chunk)
            context_parts.append(f"[文档 {i+1}]\n{content}")
        
        return "\n\n".join(context_parts)

    async def _generate_answer(
        self,
        question: str,
        context: str,
        model_config_id: int,
    ) -> str:
        """生成回答。"""
        # 简化实现，实际应调用 chat_service
        prompt = f"""基于以下参考文档回答问题。

## 参考文档
{context}

## 问题
{question}

## 回答
"""
        # 这里应该调用实际的 chat_service
        # response = await self.chat_service.generate(...)
        # return response.content
        return f"[待实现] 基于上下文生成的回答"

    async def _evaluate_answer(
        self,
        question: str,
        answer: str,
        ground_truth: str,
        context: str,
        latency_ms: float,
    ) -> AnswerMetrics:
        """评估回答质量。"""
        # 简单实现，实际应使用 LLM-as-Judge
        # 这里使用简单的字符串匹配作为基线
        
        # 正确率：简单检查关键词重叠
        correctness = self._simple_correctness(answer, ground_truth)
        
        # 引用覆盖：检查是否引用了上下文
        citation_coverage = 1.0 if context and any(
            phrase in answer for phrase in context.split()[:10]
        ) else 0.0
        
        # 幻觉检测：简单检查（实际应使用 LLM）
        hallucination_detected = False
        
        # 完整性：简单估计
        completeness = min(len(answer) / max(len(ground_truth), 1), 1.0)
        
        return AnswerMetrics(
            correctness=correctness,
            citation_coverage=citation_coverage,
            hallucination_detected=hallucination_detected,
            completeness=completeness,
            latency_ms=latency_ms,
            confidence=0.5,  # 简单评估置信度较低
        )

    def _simple_correctness(self, answer: str, ground_truth: str) -> float:
        """简单的正确率计算。"""
        if not answer or not ground_truth:
            return 0.0
        
        # 提取关键词
        answer_words = set(answer.lower().split())
        truth_words = set(ground_truth.lower().split())
        
        if not truth_words:
            return 0.0
        
        overlap = len(answer_words & truth_words)
        return min(overlap / len(truth_words), 1.0)

    def _generate_report(
        self,
        dataset: BenchmarkDataset,
        results: List[BenchmarkResult],
        config: Dict[str, Any],
    ) -> BenchmarkReport:
        """生成评测报告。"""
        successful = [r for r in results if r.error is None]
        failed = [r for r in results if r.error is not None]
        
        # 计算汇总指标
        summary = self._calculate_summary(successful)
        
        # 按类别分组
        by_category = {}
        for cat in SampleCategory:
            cat_samples = [
                s for s in dataset.samples if s.category == cat
            ]
            cat_ids = {s.id for s in cat_samples}
            cat_results = [r for r in successful if r.sample_id in cat_ids]
            if cat_results:
                by_category[cat.value] = self._calculate_summary(cat_results)
        
        # 按难度分组
        by_difficulty = {}
        for diff in Difficulty:
            diff_samples = [
                s for s in dataset.samples if s.difficulty == diff
            ]
            diff_ids = {s.id for s in diff_samples}
            diff_results = [r for r in successful if r.sample_id in diff_ids]
            if diff_results:
                by_difficulty[diff.value] = self._calculate_summary(diff_results)
        
        return BenchmarkReport(
            benchmark_id=f"bench_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}",
            timestamp=datetime.now(),
            dataset_name=dataset.name,
            dataset_version=dataset.version,
            config=config,
            total_samples=len(results),
            successful_samples=len(successful),
            failed_samples=len(failed),
            summary=summary,
            by_category=by_category,
            by_difficulty=by_difficulty,
            results=results,
            failed_details=[
                {"sample_id": r.sample_id, "error": r.error}
                for r in failed
            ],
        )

    def _calculate_summary(self, results: List[BenchmarkResult]) -> MetricsSummary:
        """计算指标汇总。"""
        if not results:
            return MetricsSummary(
                hit_rate=0.0,
                mrr=0.0,
                recall_at_k=0.0,
                precision_at_k=0.0,
                correctness=0.0,
                citation_coverage=0.0,
                hallucination_rate=0.0,
                completeness=0.0,
                retrieval_p95_ms=0.0,
                e2e_p95_ms=0.0,
            )
        
        hits = [r.retrieval_metrics.hit for r in results]
        ranks = [
            int(1 / r.retrieval_metrics.reciprocal_rank) 
            if r.retrieval_metrics.reciprocal_rank > 0 else 0
            for r in results
        ]
        recalls = [r.retrieval_metrics.recall_at_k for r in results]
        precisions = [r.retrieval_metrics.precision_at_k for r in results]
        correctness_scores = [r.answer_metrics.correctness for r in results]
        citation_coverages = [r.answer_metrics.citation_coverage for r in results]
        hallucinations = [r.answer_metrics.hallucination_detected for r in results]
        completeness_scores = [r.answer_metrics.completeness for r in results]
        retrieval_latencies = [r.retrieval_metrics.latency_ms for r in results]
        e2e_latencies = [
            r.retrieval_metrics.latency_ms + r.answer_metrics.latency_ms
            for r in results
        ]
        
        return MetricsSummary(
            hit_rate=calculate_hit_rate(hits),
            mrr=calculate_mrr(ranks),
            recall_at_k=sum(recalls) / len(recalls),
            precision_at_k=sum(precisions) / len(precisions),
            correctness=sum(correctness_scores) / len(correctness_scores),
            citation_coverage=sum(citation_coverages) / len(citation_coverages),
            hallucination_rate=sum(hallucinations) / len(hallucinations),
            completeness=sum(completeness_scores) / len(completeness_scores),
            retrieval_p95_ms=calculate_percentile(retrieval_latencies, 95),
            e2e_p95_ms=calculate_percentile(e2e_latencies, 95),
        )


def load_dataset(path: str) -> BenchmarkDataset:
    """从 JSON 文件加载数据集。"""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    samples = [
        BenchmarkSample(
            id=s["id"],
            question=s["question"],
            ground_truth=s["ground_truth"],
            relevant_doc_ids=s.get("relevant_doc_ids", []),
            category=SampleCategory(s.get("category", "factual_qa")),
            difficulty=Difficulty(s.get("difficulty", "medium")),
            tags=s.get("tags", []),
            metadata=s.get("metadata", {}),
        )
        for s in data.get("samples", [])
    ]
    
    return BenchmarkDataset(
        name=data.get("dataset_name", "unknown"),
        version=data.get("version", "1.0.0"),
        samples=samples,
        description=data.get("description", ""),
    )


def save_report(report: BenchmarkReport, path: str) -> None:
    """保存评测报告到 JSON 文件。"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
