"""
Benchmark 数据模型。
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum


class SampleCategory(str, Enum):
    """样本类别。"""
    FACTUAL_QA = "factual_qa"
    MULTI_HOP = "multi_hop"
    COMPARISON = "comparison"
    SUMMARIZATION = "summarization"
    NEGATIVE = "negative"
    AMBIGUOUS = "ambiguous"


class Difficulty(str, Enum):
    """难度分级。"""
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


@dataclass
class BenchmarkSample:
    """评测样本。"""
    id: str
    question: str
    ground_truth: str
    relevant_doc_ids: List[str]
    category: SampleCategory = SampleCategory.FACTUAL_QA
    difficulty: Difficulty = Difficulty.MEDIUM
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BenchmarkDataset:
    """评测数据集。"""
    name: str
    version: str
    samples: List[BenchmarkSample]
    created_at: datetime = field(default_factory=datetime.now)
    description: str = ""

    def __len__(self) -> int:
        return len(self.samples)

    def filter_by_category(self, category: SampleCategory) -> "BenchmarkDataset":
        """按类别筛选样本。"""
        filtered = [s for s in self.samples if s.category == category]
        return BenchmarkDataset(
            name=f"{self.name}_{category.value}",
            version=self.version,
            samples=filtered,
            created_at=self.created_at,
        )

    def filter_by_difficulty(self, difficulty: Difficulty) -> "BenchmarkDataset":
        """按难度筛选样本。"""
        filtered = [s for s in self.samples if s.difficulty == difficulty]
        return BenchmarkDataset(
            name=f"{self.name}_{difficulty.value}",
            version=self.version,
            samples=filtered,
            created_at=self.created_at,
        )


@dataclass
class RetrievalMetrics:
    """检索指标。"""
    hit: bool
    reciprocal_rank: float
    recall_at_k: float
    precision_at_k: float
    retrieved_ids: List[str]
    latency_ms: float


@dataclass
class AnswerMetrics:
    """回答指标。"""
    correctness: float
    citation_coverage: float
    hallucination_detected: bool
    completeness: float
    latency_ms: float
    confidence: float = 1.0


@dataclass
class BenchmarkResult:
    """单个样本的评测结果。"""
    sample_id: str
    question: str
    ground_truth: str
    generated_answer: str
    retrieval_metrics: RetrievalMetrics
    answer_metrics: AnswerMetrics
    error: Optional[str] = None


@dataclass
class MetricsSummary:
    """指标汇总。"""
    hit_rate: float
    mrr: float
    recall_at_k: float
    precision_at_k: float
    correctness: float
    citation_coverage: float
    hallucination_rate: float
    completeness: float
    retrieval_p95_ms: float
    e2e_p95_ms: float


@dataclass
class BenchmarkReport:
    """评测报告。"""
    benchmark_id: str
    timestamp: datetime
    dataset_name: str
    dataset_version: str
    config: Dict[str, Any]
    total_samples: int
    successful_samples: int
    failed_samples: int
    summary: MetricsSummary
    by_category: Dict[str, MetricsSummary]
    by_difficulty: Dict[str, MetricsSummary]
    results: List[BenchmarkResult]
    failed_details: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式。"""
        return {
            "benchmark_id": self.benchmark_id,
            "timestamp": self.timestamp.isoformat(),
            "dataset": {
                "name": self.dataset_name,
                "version": self.dataset_version,
            },
            "config": self.config,
            "summary": {
                "total_samples": self.total_samples,
                "successful_samples": self.successful_samples,
                "failed_samples": self.failed_samples,
                "retrieval": {
                    "hit_rate": self.summary.hit_rate,
                    "mrr": self.summary.mrr,
                    "recall_at_k": self.summary.recall_at_k,
                    "precision_at_k": self.summary.precision_at_k,
                },
                "answer": {
                    "correctness": self.summary.correctness,
                    "citation_coverage": self.summary.citation_coverage,
                    "hallucination_rate": self.summary.hallucination_rate,
                    "completeness": self.summary.completeness,
                },
                "performance": {
                    "retrieval_p95_ms": self.summary.retrieval_p95_ms,
                    "e2e_p95_ms": self.summary.e2e_p95_ms,
                },
            },
            "by_category": {
                k: self._metrics_to_dict(v) for k, v in self.by_category.items()
            },
            "by_difficulty": {
                k: self._metrics_to_dict(v) for k, v in self.by_difficulty.items()
            },
            "failed_details": self.failed_details,
        }

    def _metrics_to_dict(self, m: MetricsSummary) -> Dict[str, Any]:
        return {
            "hit_rate": m.hit_rate,
            "mrr": m.mrr,
            "correctness": m.correctness,
            "hallucination_rate": m.hallucination_rate,
        }
