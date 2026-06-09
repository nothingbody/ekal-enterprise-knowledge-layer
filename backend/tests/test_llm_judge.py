"""
LLM-as-Judge 单元测试。
"""
import pytest
from app.benchmark.llm_judge import (
    SimpleLLMJudge,
    JudgeAspect,
    JudgeResult,
)


class TestSimpleLLMJudge:
    """SimpleLLMJudge 测试。"""

    def setup_method(self):
        """初始化测试。"""
        self.judge = SimpleLLMJudge()

    def test_evaluate_returns_judge_result(self):
        """evaluate 返回 JudgeResult 类型。"""
        result = self.judge.evaluate(
            question="什么是 RAG？",
            answer="RAG 是检索增强生成技术。",
            ground_truth="RAG 是 Retrieval-Augmented Generation，检索增强生成。",
        )
        assert isinstance(result, JudgeResult)

    def test_evaluate_has_all_aspects(self):
        """结果包含所有评估维度。"""
        result = self.judge.evaluate(
            question="什么是 RAG？",
            answer="RAG 是检索增强生成技术。",
            ground_truth="RAG 是检索增强生成。",
        )
        for aspect in JudgeAspect:
            assert aspect in result.scores

    def test_scores_in_valid_range(self):
        """所有分数在 0-1 范围内。"""
        result = self.judge.evaluate(
            question="测试问题",
            answer="测试回答",
            ground_truth="标准答案",
        )
        assert 0.0 <= result.overall_score <= 1.0
        for score in result.scores.values():
            assert 0.0 <= score.score <= 1.0

    def test_high_correctness_for_matching_answer(self):
        """答案与标准答案匹配时正确性分数较高。"""
        result = self.judge.evaluate(
            question="什么是机器学习？",
            answer="机器学习是人工智能的一个分支，让计算机从数据中学习。",
            ground_truth="机器学习是人工智能的一个分支，让计算机从数据中学习。",
        )
        assert result.scores[JudgeAspect.CORRECTNESS].score > 0.8

    def test_low_correctness_for_wrong_answer(self):
        """答案错误时正确性分数较低。"""
        result = self.judge.evaluate(
            question="什么是机器学习？",
            answer="机器学习是一种烹饪技术。",
            ground_truth="机器学习是人工智能的一个分支。",
        )
        assert result.scores[JudgeAspect.CORRECTNESS].score < 0.5

    def test_empty_answer_gives_low_score(self):
        """空答案得分为 0。"""
        result = self.judge.evaluate(
            question="测试",
            answer="",
            ground_truth="标准答案",
        )
        assert result.scores[JudgeAspect.CORRECTNESS].score == 0.0

    def test_faithfulness_with_context(self):
        """有上下文时评估忠实度。"""
        context = "RAG 系统包含检索和生成两个核心组件。"
        result = self.judge.evaluate(
            question="RAG 有哪些组件？",
            answer="RAG 系统包含检索和生成组件。",
            ground_truth="RAG 有检索和生成两个组件。",
            context=context,
        )
        # 回答基于上下文，忠实度应该不低
        assert result.scores[JudgeAspect.FAITHFULNESS].score >= 0.5

    def test_low_faithfulness_detects_hallucination(self):
        """低忠实度时检测到幻觉。"""
        context = "今天天气很好。"
        result = self.judge.evaluate(
            question="今天天气怎么样？",
            answer="明天会下大雨，气温骤降至零下。",
            ground_truth="今天天气很好。",
            context=context,
        )
        # 回答与上下文不符，可能检测到幻觉
        assert result.scores[JudgeAspect.FAITHFULNESS].score < 0.5

    def test_coherence_for_well_formed_answer(self):
        """结构良好的回答连贯性分数较高。"""
        result = self.judge.evaluate(
            question="什么是 Python？",
            answer="Python 是一种高级编程语言，广泛用于数据科学和 Web 开发。它语法简洁，易于学习。",
            ground_truth="Python 是一种编程语言。",
        )
        assert result.scores[JudgeAspect.COHERENCE].score >= 0.75

    def test_completeness_for_detailed_answer(self):
        """详细回答的完整性分数较高。"""
        result = self.judge.evaluate(
            question="什么是 Python？",
            answer="Python 是一种高级编程语言，广泛用于数据科学和 Web 开发。",
            ground_truth="Python 是一种高级编程语言。",
        )
        assert result.scores[JudgeAspect.COMPLETENESS].score > 0.5


class TestJudgeAspect:
    """JudgeAspect 枚举测试。"""

    def test_all_aspects_defined(self):
        """所有评估维度已定义。"""
        expected = ["correctness", "relevance", "completeness", "faithfulness", "coherence"]
        actual = [a.value for a in JudgeAspect]
        assert set(expected) == set(actual)
