"""
LLM-as-Judge 自动评分服务。

使用 LLM 评估 RAG 系统生成的回答质量。
"""
import json
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class JudgeAspect(str, Enum):
    """评估维度。"""
    CORRECTNESS = "correctness"       # 正确性
    RELEVANCE = "relevance"           # 相关性
    COMPLETENESS = "completeness"     # 完整性
    FAITHFULNESS = "faithfulness"     # 忠实度（是否基于上下文）
    COHERENCE = "coherence"           # 连贯性


@dataclass
class JudgeScore:
    """评分结果。"""
    aspect: JudgeAspect
    score: float  # 0-1
    reasoning: str
    confidence: float  # 0-1


@dataclass
class JudgeResult:
    """完整评估结果。"""
    overall_score: float
    scores: Dict[JudgeAspect, JudgeScore]
    hallucination_detected: bool
    hallucination_details: Optional[str]
    raw_response: str


# 评分 Prompt 模板
JUDGE_PROMPT_TEMPLATE = """你是一个专业的 RAG 系统回答质量评估专家。请根据以下信息评估 AI 生成的回答质量。

## 用户问题
{question}

## 参考上下文（检索到的文档）
{context}

## 标准答案
{ground_truth}

## AI 生成的回答
{answer}

## 评估要求
请从以下维度评估回答质量，每个维度给出 0-10 分，并简要说明理由：

1. **正确性 (Correctness)**: 回答是否准确、与标准答案一致
2. **相关性 (Relevance)**: 回答是否切题、与问题相关
3. **完整性 (Completeness)**: 回答是否涵盖了问题的所有要点
4. **忠实度 (Faithfulness)**: 回答是否基于提供的上下文，未添加无根据的信息
5. **连贯性 (Coherence)**: 回答是否逻辑清晰、表达流畅

另外，请判断是否存在幻觉（即回答中包含上下文中不存在的虚假信息）。

## 输出格式
请严格按以下 JSON 格式输出评估结果：
```json
{{
  "correctness": {{"score": 8, "reasoning": "..."}},
  "relevance": {{"score": 9, "reasoning": "..."}},
  "completeness": {{"score": 7, "reasoning": "..."}},
  "faithfulness": {{"score": 8, "reasoning": "..."}},
  "coherence": {{"score": 9, "reasoning": "..."}},
  "hallucination": {{"detected": false, "details": null}},
  "overall_score": 8.2
}}
```
"""

# 简化版 Prompt（用于快速评估）
FAST_JUDGE_PROMPT = """评估以下 RAG 回答的质量（0-10分）。

问题: {question}
标准答案: {ground_truth}
AI 回答: {answer}

输出 JSON: {{"score": 分数, "has_error": 是否有错误, "reason": "简要理由"}}
"""


class LLMJudge:
    """LLM-as-Judge 评分器。"""

    def __init__(
        self,
        llm_client,
        model_id: Optional[str] = None,
        fast_mode: bool = False,
    ):
        """
        初始化评分器。
        
        :param llm_client: LLM 客户端实例
        :param model_id: 用于评估的模型 ID
        :param fast_mode: 是否使用快速模式（简化评估）
        """
        self.llm_client = llm_client
        self.model_id = model_id
        self.fast_mode = fast_mode

    async def evaluate(
        self,
        question: str,
        answer: str,
        ground_truth: str,
        context: str = "",
    ) -> JudgeResult:
        """
        评估回答质量。
        
        :param question: 用户问题
        :param answer: AI 生成的回答
        :param ground_truth: 标准答案
        :param context: 检索到的上下文
        :return: 评估结果
        """
        if self.fast_mode:
            return await self._fast_evaluate(question, answer, ground_truth)
        
        return await self._full_evaluate(question, answer, ground_truth, context)

    async def _full_evaluate(
        self,
        question: str,
        answer: str,
        ground_truth: str,
        context: str,
    ) -> JudgeResult:
        """完整评估。"""
        prompt = JUDGE_PROMPT_TEMPLATE.format(
            question=question,
            context=context or "（无上下文）",
            ground_truth=ground_truth,
            answer=answer,
        )
        
        try:
            response = await self._call_llm(prompt)
            return self._parse_full_response(response)
        except Exception as e:
            logger.error(f"LLM Judge 评估失败: {e}")
            return self._fallback_result(str(e))

    async def _fast_evaluate(
        self,
        question: str,
        answer: str,
        ground_truth: str,
    ) -> JudgeResult:
        """快速评估。"""
        prompt = FAST_JUDGE_PROMPT.format(
            question=question,
            ground_truth=ground_truth,
            answer=answer,
        )
        
        try:
            response = await self._call_llm(prompt)
            return self._parse_fast_response(response)
        except Exception as e:
            logger.error(f"LLM Judge 快速评估失败: {e}")
            return self._fallback_result(str(e))

    async def _call_llm(self, prompt: str) -> str:
        """调用 LLM。"""
        if self.llm_client is None:
            raise ValueError("LLM client not configured")
        
        # 调用 LLM 客户端
        response = await self.llm_client.generate(
            prompt=prompt,
            model_id=self.model_id,
            max_tokens=1000,
            temperature=0.1,  # 低温度以获得更一致的评估
        )
        return response

    def _parse_full_response(self, response: str) -> JudgeResult:
        """解析完整评估响应。"""
        # 尝试提取 JSON
        json_str = self._extract_json(response)
        if not json_str:
            return self._fallback_result("无法解析 JSON 响应")
        
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            return self._fallback_result(f"JSON 解析错误: {e}")
        
        scores = {}
        for aspect in JudgeAspect:
            aspect_data = data.get(aspect.value, {})
            raw_score = aspect_data.get("score", 5)
            scores[aspect] = JudgeScore(
                aspect=aspect,
                score=raw_score / 10.0,  # 归一化到 0-1
                reasoning=aspect_data.get("reasoning", ""),
                confidence=0.8,
            )
        
        hallucination = data.get("hallucination", {})
        
        return JudgeResult(
            overall_score=data.get("overall_score", 5.0) / 10.0,
            scores=scores,
            hallucination_detected=hallucination.get("detected", False),
            hallucination_details=hallucination.get("details"),
            raw_response=response,
        )

    def _parse_fast_response(self, response: str) -> JudgeResult:
        """解析快速评估响应。"""
        json_str = self._extract_json(response)
        if not json_str:
            return self._fallback_result("无法解析 JSON 响应")
        
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            return self._fallback_result(f"JSON 解析错误: {e}")
        
        score = data.get("score", 5) / 10.0
        
        # 快速模式只返回总体分数
        scores = {
            aspect: JudgeScore(
                aspect=aspect,
                score=score,
                reasoning=data.get("reason", ""),
                confidence=0.6,  # 快速模式置信度较低
            )
            for aspect in JudgeAspect
        }
        
        return JudgeResult(
            overall_score=score,
            scores=scores,
            hallucination_detected=data.get("has_error", False),
            hallucination_details=None,
            raw_response=response,
        )

    def _extract_json(self, text: str) -> Optional[str]:
        """从文本中提取 JSON。"""
        # 尝试找到 ```json ... ``` 块
        import re
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', text)
        if json_match:
            return json_match.group(1).strip()
        
        # 尝试找到 { ... } 块
        brace_match = re.search(r'\{[\s\S]*\}', text)
        if brace_match:
            return brace_match.group(0)
        
        return None

    def _fallback_result(self, error: str) -> JudgeResult:
        """创建回退结果。"""
        scores = {
            aspect: JudgeScore(
                aspect=aspect,
                score=0.5,
                reasoning=f"评估失败: {error}",
                confidence=0.0,
            )
            for aspect in JudgeAspect
        }
        
        return JudgeResult(
            overall_score=0.5,
            scores=scores,
            hallucination_detected=False,
            hallucination_details=None,
            raw_response=error,
        )


class SimpleLLMJudge:
    """
    简化版 LLM Judge，不依赖外部 LLM。
    
    使用规则和关键词匹配进行评估，适合离线测试。
    """

    def evaluate(
        self,
        question: str,
        answer: str,
        ground_truth: str,
        context: str = "",
    ) -> JudgeResult:
        """评估回答质量。"""
        # 基于规则的简单评估
        correctness = self._eval_correctness(answer, ground_truth)
        relevance = self._eval_relevance(answer, question)
        completeness = self._eval_completeness(answer, ground_truth)
        faithfulness = self._eval_faithfulness(answer, context)
        coherence = self._eval_coherence(answer)
        
        scores = {
            JudgeAspect.CORRECTNESS: JudgeScore(
                aspect=JudgeAspect.CORRECTNESS,
                score=correctness,
                reasoning="基于关键词重叠计算",
                confidence=0.5,
            ),
            JudgeAspect.RELEVANCE: JudgeScore(
                aspect=JudgeAspect.RELEVANCE,
                score=relevance,
                reasoning="基于问题关键词出现率",
                confidence=0.5,
            ),
            JudgeAspect.COMPLETENESS: JudgeScore(
                aspect=JudgeAspect.COMPLETENESS,
                score=completeness,
                reasoning="基于长度比例估计",
                confidence=0.4,
            ),
            JudgeAspect.FAITHFULNESS: JudgeScore(
                aspect=JudgeAspect.FAITHFULNESS,
                score=faithfulness,
                reasoning="基于上下文词汇覆盖",
                confidence=0.4,
            ),
            JudgeAspect.COHERENCE: JudgeScore(
                aspect=JudgeAspect.COHERENCE,
                score=coherence,
                reasoning="基于句子结构检查",
                confidence=0.4,
            ),
        }
        
        overall = sum(s.score for s in scores.values()) / len(scores)
        
        return JudgeResult(
            overall_score=overall,
            scores=scores,
            hallucination_detected=faithfulness < 0.3,
            hallucination_details="低忠实度可能表示幻觉" if faithfulness < 0.3 else None,
            raw_response="SimpleLLMJudge 规则评估",
        )

    def _eval_correctness(self, answer: str, ground_truth: str) -> float:
        """评估正确性。"""
        if not answer or not ground_truth:
            return 0.0
        
        answer_words = set(answer.lower().split())
        truth_words = set(ground_truth.lower().split())
        
        if not truth_words:
            return 0.0
        
        overlap = len(answer_words & truth_words)
        return min(overlap / len(truth_words), 1.0)

    def _eval_relevance(self, answer: str, question: str) -> float:
        """评估相关性。"""
        if not answer or not question:
            return 0.0
        
        # 提取问题关键词（去除停用词）
        stop_words = {"的", "是", "什么", "如何", "为什么", "哪些", "怎么", "吗", "呢"}
        question_words = set(question.lower().split()) - stop_words
        answer_words = set(answer.lower().split())
        
        if not question_words:
            return 0.5
        
        overlap = len(question_words & answer_words)
        return min(overlap / len(question_words), 1.0)

    def _eval_completeness(self, answer: str, ground_truth: str) -> float:
        """评估完整性。"""
        if not ground_truth:
            return 0.5
        
        ratio = len(answer) / max(len(ground_truth), 1)
        # 回答过短或过长都扣分
        if ratio < 0.5:
            return ratio
        elif ratio > 2.0:
            return max(0.5, 1.0 - (ratio - 2.0) * 0.25)
        else:
            return min(ratio, 1.0)

    def _eval_faithfulness(self, answer: str, context: str) -> float:
        """评估忠实度。"""
        if not context:
            return 0.5  # 无上下文时给中等分
        
        context_words = set(context.lower().split())
        answer_words = set(answer.lower().split())
        
        if not answer_words:
            return 0.0
        
        # 检查回答中有多少词来自上下文
        from_context = len(answer_words & context_words)
        return min(from_context / len(answer_words), 1.0)

    def _eval_coherence(self, answer: str) -> float:
        """评估连贯性。"""
        if not answer:
            return 0.0
        
        # 简单检查：有句号、长度合理
        has_punctuation = any(p in answer for p in ["。", ".", "！", "？"])
        reasonable_length = 10 < len(answer) < 5000
        
        score = 0.5
        if has_punctuation:
            score += 0.25
        if reasonable_length:
            score += 0.25
        
        return score
