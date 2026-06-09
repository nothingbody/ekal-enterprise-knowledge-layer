"""語義摘要上下文引擎 — 當歷史過長時使用 LLM 生成摘要。

策略：
1. 保留最近的 `recent_window` 條訊息不做修改
2. 當總訊息數超過 `summarize_threshold` 時，將較舊的訊息用 LLM 壓縮為一段摘要
3. 摘要作為 system 訊息前置在上下文中
4. 摘要會持久化到 ChatConversation.context_summary 欄位
"""

import logging
from typing import List, Optional

from app.core.context_engine.base import ContextEngine
from app.core.token_utils import count_tokens

logger = logging.getLogger(__name__)

SUMMARY_PROMPT = (
    "请将以下对话内容压缩为一段简洁的摘要，保留所有关键信息和结论：\n\n{old_messages}"
)


class SemanticSummaryEngine(ContextEngine):
    """語義摘要引擎：自動壓縮舊歷史，保留近期訊息原文。"""

    def __init__(
        self,
        max_tokens: int = 4000,
        recent_window: int = 10,
        summarize_threshold: int = 20,
        **kwargs,
    ):
        self.max_tokens = max_tokens
        self.recent_window = recent_window
        self.summarize_threshold = summarize_threshold

        self._history: List[dict] = []
        self._summary: Optional[str] = None

        self._llm_config = None
        self._db = None
        self._conversation_id: Optional[int] = None

    async def bootstrap(self, **kwargs) -> None:
        self.max_tokens = kwargs.get("max_tokens", self.max_tokens)
        self.recent_window = kwargs.get("recent_window", self.recent_window)
        self.summarize_threshold = kwargs.get("summarize_threshold", self.summarize_threshold)

        history = kwargs.get("history")
        if history is not None:
            self._history = list(history)

        self._summary = kwargs.get("context_summary")
        self._llm_config = kwargs.get("llm_config")
        self._db = kwargs.get("db")
        self._conversation_id = kwargs.get("conversation_id")

    async def ingest(self, message: dict) -> None:
        self._history.append(message)

    async def assemble(self, query: str, max_tokens: int = 4000) -> List[dict]:
        budget = min(max_tokens, self.max_tokens)

        if len(self._history) > self.summarize_threshold and self._llm_config:
            await self._generate_summary()

        result: List[dict] = []
        if self._summary:
            result.append({
                "role": "system",
                "content": f"以下是之前对话的摘要：\n{self._summary}",
            })

        recent = self._history[-self.recent_window:]

        total = sum(count_tokens(m.get("content", "")) for m in result)
        kept: List[dict] = []
        for msg in reversed(recent):
            msg_tokens = count_tokens(msg.get("content", ""))
            if total + msg_tokens > budget:
                break
            total += msg_tokens
            kept.append(msg)
        result.extend(reversed(kept))
        return result

    async def compact(self, messages: List[dict], max_tokens: int) -> List[dict]:
        total = 0
        kept: List[dict] = []
        for msg in reversed(messages):
            msg_tokens = count_tokens(msg.get("content", ""))
            if total + msg_tokens > max_tokens:
                break
            total += msg_tokens
            kept.append(msg)
        return list(reversed(kept))

    async def after_turn(self, assistant_response: str) -> None:
        if len(self._history) > self.summarize_threshold and self._llm_config:
            await self._generate_summary()

    async def _generate_summary(self) -> None:
        """使用 LLM 將較舊訊息壓縮為摘要。"""
        if not self._llm_config:
            return

        old_messages = self._history[: -self.recent_window]
        if not old_messages:
            return

        formatted = "\n".join(
            f"{m['role']}: {m.get('content', '')}" for m in old_messages
        )
        prompt = SUMMARY_PROMPT.format(old_messages=formatted)

        try:
            from app.core.llm_client import chat_completion

            messages = [{"role": "user", "content": prompt}]
            import asyncio
            response = await asyncio.wait_for(
                chat_completion(self._llm_config, messages, stream=False),
                timeout=30,
            )
            if isinstance(response, str):
                self._summary = response
            else:
                chunks = []
                async for chunk in response:
                    chunks.append(chunk)
                self._summary = "".join(chunks)

            await self._persist_summary()
            logger.info(
                "已為對話 %s 生成上下文摘要（%d 條舊訊息 → %d tokens）",
                self._conversation_id,
                len(old_messages),
                count_tokens(self._summary),
            )
        except Exception:
            logger.warning(
                "為對話 %s 生成摘要時失敗", self._conversation_id, exc_info=True
            )

    async def _persist_summary(self) -> None:
        """將摘要寫入資料庫 ChatConversation.context_summary。"""
        if not self._db or not self._conversation_id or not self._summary:
            return
        try:
            from sqlalchemy import update as sa_update
            from app.models.chat_history import ChatConversation

            await self._db.execute(
                sa_update(ChatConversation)
                .where(ChatConversation.id == self._conversation_id)
                .values(context_summary=self._summary)
            )
            await self._db.flush()
        except Exception:
            logger.warning(
                "持久化對話 %s 的摘要時失敗", self._conversation_id, exc_info=True
            )
