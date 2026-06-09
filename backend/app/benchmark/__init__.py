"""
RAG Benchmark 评测模块。
"""
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
from .evaluator import RAGEvaluator, load_dataset, save_report
from .llm_judge import (
    LLMJudge,
    SimpleLLMJudge,
    JudgeAspect,
    JudgeScore,
    JudgeResult,
)
from .metrics import (
    calculate_hit_rate,
    calculate_mrr,
    calculate_recall_at_k,
    calculate_precision_at_k,
)

__all__ = [
    "BenchmarkDataset",
    "BenchmarkSample",
    "BenchmarkResult",
    "BenchmarkReport",
    "RAGEvaluator",
    "LLMJudge",
    "SimpleLLMJudge",
    "JudgeAspect",
    "JudgeScore",
    "JudgeResult",
    "calculate_hit_rate",
    "calculate_mrr",
    "calculate_recall_at_k",
    "calculate_precision_at_k",
]
