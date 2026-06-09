"""全量上下文引擎 — 不做截斷，適用於大上下文視窗模型。

仍保留安全上限 `max_tokens` 以避免超出模型容量。
"""

from typing import List

from app.core.context_engine.base import ContextEngine
from app.core.token_utils import count_tokens


class FullContextEngine(ContextEngine):
    """將全部歷史訊息傳送給模型，僅在超過安全上限時才截斷。"""

    DEFAULT_SAFETY_CAP = 120_000

    def __init__(self, max_tokens: int = DEFAULT_SAFETY_CAP, **kwargs):
        self.max_tokens = max_tokens
        self._history: List[dict] = []

    async def bootstrap(self, **kwargs) -> None:
        self.max_tokens = kwargs.get("max_tokens", self.max_tokens)
        history = kwargs.get("history")
        if history is not None:
            self._history = list(history)

    async def ingest(self, message: dict) -> None:
        self._history.append(message)

    async def assemble(self, query: str, max_tokens: int = 120_000) -> List[dict]:
        budget = min(max_tokens, self.max_tokens)
        total = sum(count_tokens(m.get("content", "")) for m in self._history)
        if total <= budget:
            return list(self._history)
        return await self.compact(self._history, budget)

    async def compact(self, messages: List[dict], max_tokens: int) -> List[dict]:
        """超出安全上限時從最舊的訊息開始丟棄。"""
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
        pass
