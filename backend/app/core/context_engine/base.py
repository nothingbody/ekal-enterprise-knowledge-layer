"""ContextEngine 抽象基類 — 定義可插拔上下文管理的統一介面。"""

from abc import ABC, abstractmethod
from typing import List, Optional


class ContextEngine(ABC):
    """可插拔的上下文管理引擎。

    每個引擎實現不同的策略來管理對話歷史，包括截斷、摘要、全量等。
    """

    @abstractmethod
    async def bootstrap(self, **kwargs) -> None:
        """初始化引擎（連線至儲存、載入狀態等）。"""

    @abstractmethod
    async def ingest(self, message: dict) -> None:
        """處理一條新訊息（user / assistant / tool）。"""

    @abstractmethod
    async def assemble(self, query: str, max_tokens: int = 4000) -> List[dict]:
        """組裝要傳送給模型的上下文訊息列表。"""

    @abstractmethod
    async def compact(self, messages: List[dict], max_tokens: int) -> List[dict]:
        """當上下文接近 token 上限時進行壓縮。"""

    @abstractmethod
    async def after_turn(self, assistant_response: str) -> None:
        """每輪對話後的後處理（更新摘要、統計等）。"""
