"""
检索与回答质量指标计算。
"""
from typing import List, Set
import numpy as np


def calculate_hit_rate(results: List[bool]) -> float:
    """
    计算命中率。
    
    :param results: 每个查询是否命中的列表
    :return: 命中率 (0-1)
    """
    if not results:
        return 0.0
    return sum(results) / len(results)


def calculate_mrr(ranks: List[int]) -> float:
    """
    计算 Mean Reciprocal Rank。
    
    :param ranks: 首个相关结果的排名列表（从 1 开始，0 表示未命中）
    :return: MRR (0-1)
    """
    if not ranks:
        return 0.0
    reciprocals = [1.0 / r if r > 0 else 0.0 for r in ranks]
    return sum(reciprocals) / len(reciprocals)


def calculate_recall_at_k(
    retrieved_ids: List[str],
    relevant_ids: Set[str],
    k: int = 5,
) -> float:
    """
    计算 Recall@K。
    
    :param retrieved_ids: 检索到的文档 ID 列表
    :param relevant_ids: 相关文档 ID 集合
    :param k: Top-K
    :return: Recall@K (0-1)
    """
    if not relevant_ids:
        return 1.0  # 无相关文档时视为完全召回
    top_k = set(retrieved_ids[:k])
    hits = len(top_k & relevant_ids)
    return hits / len(relevant_ids)


def calculate_precision_at_k(
    retrieved_ids: List[str],
    relevant_ids: Set[str],
    k: int = 5,
) -> float:
    """
    计算 Precision@K。
    
    :param retrieved_ids: 检索到的文档 ID 列表
    :param relevant_ids: 相关文档 ID 集合
    :param k: Top-K
    :return: Precision@K (0-1)
    """
    top_k = retrieved_ids[:k]
    if not top_k:
        return 0.0
    hits = len(set(top_k) & relevant_ids)
    return hits / len(top_k)


def calculate_first_relevant_rank(
    retrieved_ids: List[str],
    relevant_ids: Set[str],
) -> int:
    """
    计算首个相关结果的排名。
    
    :param retrieved_ids: 检索到的文档 ID 列表
    :param relevant_ids: 相关文档 ID 集合
    :return: 排名（从 1 开始），0 表示未命中
    """
    for i, doc_id in enumerate(retrieved_ids):
        if doc_id in relevant_ids:
            return i + 1
    return 0


def calculate_percentile(values: List[float], percentile: float) -> float:
    """
    计算百分位数。
    
    :param values: 数值列表
    :param percentile: 百分位（0-100）
    :return: 百分位数值
    """
    if not values:
        return 0.0
    return float(np.percentile(values, percentile))


# ---------------------------------------------------------------------------
# Trajectory quality metrics
# ---------------------------------------------------------------------------


def calculate_decision_efficiency(trajectories: List[dict]) -> float:
    """Ratio of successful trajectories to their total step count.

    Higher is better — means fewer steps needed to reach success.

    :param trajectories: list of trajectory dicts with "outcome" and "step_count"
    :return: efficiency score (0-1)
    """
    successes = [t for t in trajectories if t.get("outcome") == "success"]
    if not successes:
        return 0.0
    total_steps = sum(t.get("step_count", 1) for t in successes)
    return round(len(successes) / total_steps, 4) if total_steps > 0 else 0.0


def calculate_corrective_action_rate(trajectories: List[dict]) -> float:
    """Fraction of trajectories that needed corrective actions.

    Lower is better — means the pipeline gets it right more often on the first try.

    :param trajectories: list of trajectory dicts with "steps_json" (parsed list)
    :return: rate (0-1)
    """
    if not trajectories:
        return 0.0
    corrective_actions = {"requery", "web_fallback", "broaden", "filter_irrelevant"}
    count = 0
    for t in trajectories:
        steps = t.get("steps", [])
        if any(s.get("action") in corrective_actions for s in steps):
            count += 1
    return round(count / len(trajectories), 4)


def calculate_skip_accuracy(trajectories: List[dict]) -> float:
    """When retrieval was skipped, how often was the outcome still positive.

    :param trajectories: list of trajectory dicts
    :return: accuracy (0-1), or -1 if no skips occurred
    """
    skipped = [t for t in trajectories if t.get("outcome") == "skipped"]
    if not skipped:
        return -1.0  # not applicable
    positive = sum(1 for t in skipped
                   if t.get("user_feedback") == "like"
                   or (t.get("reward_score") is not None and t["reward_score"] > 0.5))
    return round(positive / len(skipped), 4)


def calculate_optimal_path_rate(trajectories: List[dict]) -> float:
    """Fraction of successful trajectories that used the minimum steps.

    The minimum step count is defined as the shortest successful trajectory
    seen in the dataset.

    :param trajectories: list of trajectory dicts
    :return: rate (0-1)
    """
    successes = [t for t in trajectories if t.get("outcome") == "success"]
    if not successes:
        return 0.0
    min_steps = min(t.get("step_count", 99) for t in successes)
    optimal = sum(1 for t in successes if t.get("step_count", 99) == min_steps)
    return round(optimal / len(successes), 4)


def calculate_feedback_agreement(trajectories: List[dict]) -> float:
    """Correlation between automated reward_score and user feedback.

    Returns fraction of trajectories where the automated reward and
    user feedback agree (both positive or both negative).

    :param trajectories: list of trajectory dicts
    :return: agreement rate (0-1), or -1 if insufficient data
    """
    pairs = []
    for t in trajectories:
        reward = t.get("reward_score")
        feedback = t.get("user_feedback")
        if reward is not None and feedback:
            auto_positive = reward > 0.5
            user_positive = feedback == "like"
            pairs.append(auto_positive == user_positive)
    if len(pairs) < 3:
        return -1.0  # insufficient data
    return round(sum(pairs) / len(pairs), 4)


def aggregate_metrics(
    hit_results: List[bool],
    ranks: List[int],
    recalls: List[float],
    precisions: List[float],
    correctness_scores: List[float],
    citation_coverages: List[float],
    hallucination_flags: List[bool],
    completeness_scores: List[float],
    retrieval_latencies: List[float],
    e2e_latencies: List[float],
) -> dict:
    """
    聚合所有指标。
    
    :return: 指标汇总字典
    """
    return {
        "hit_rate": calculate_hit_rate(hit_results),
        "mrr": calculate_mrr(ranks),
        "recall_at_k": sum(recalls) / len(recalls) if recalls else 0.0,
        "precision_at_k": sum(precisions) / len(precisions) if precisions else 0.0,
        "correctness": sum(correctness_scores) / len(correctness_scores) if correctness_scores else 0.0,
        "citation_coverage": sum(citation_coverages) / len(citation_coverages) if citation_coverages else 0.0,
        "hallucination_rate": sum(hallucination_flags) / len(hallucination_flags) if hallucination_flags else 0.0,
        "completeness": sum(completeness_scores) / len(completeness_scores) if completeness_scores else 0.0,
        "retrieval_p95_ms": calculate_percentile(retrieval_latencies, 95),
        "e2e_p95_ms": calculate_percentile(e2e_latencies, 95),
    }
