"""滑動視窗上下文引擎 — 保留最近 N 條訊息，以 token 預算為限。

這是對原有 `_truncate_history` 行為的封裝，作為預設策略使用。
"""

from typing import List

from app.core.context_engine.base import ContextEngine
from app.core.token_utils import count_tokens


class SlidingWindowEngine(ContextEngine):
    """簡單的 token 預算截斷策略：從最新訊息往前保留，直到達到預算上限。"""

    def __init__(self, max_tokens: int = 4000, **kwargs):
        self.max_tokens = max_tokens
        self._history: List[dict] = []

    async def bootstrap(self, **kwargs) -> None:
        self.max_tokens = kwargs.get("max_tokens", self.max_tokens)
        history = kwargs.get("history")
        if history is not None:
            self._history = list(history)

    async def ingest(self, message: dict) -> None:
        self._history.append(message)

    async def assemble(self, query: str, max_tokens: int = 4000) -> List[dict]:
        budget = min(max_tokens, self.max_tokens)
        return self.compact_sync(self._history, budget)

    async def compact(self, messages: List[dict], max_tokens: int) -> List[dict]:
        return self.compact_sync(messages, max_tokens)

    @staticmethod
    def compact_sync(messages: List[dict], max_tokens: int) -> List[dict]:
        """同步版本的壓縮，與原有 `_truncate_history` 邏輯一致。"""
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
