"""ContextEngine 註冊表 — 根據名稱取得對應的引擎實例。"""

from typing import Dict, Type

from app.core.context_engine.base import ContextEngine
from app.core.context_engine.sliding_window import SlidingWindowEngine
from app.core.context_engine.semantic_summary import SemanticSummaryEngine
from app.core.context_engine.full_context import FullContextEngine

ENGINES: Dict[str, Type[ContextEngine]] = {
    "sliding_window": SlidingWindowEngine,
    "semantic_summary": SemanticSummaryEngine,
    "full_context": FullContextEngine,
}


def get_engine(name: str = "sliding_window", **kwargs) -> ContextEngine:
    """根據名稱建立並回傳對應的 ContextEngine 實例。

    Args:
        name: 引擎名稱，必須是 ENGINES 中的 key。
        **kwargs: 傳遞給引擎建構函式的參數。

    Raises:
        ValueError: 如果引擎名稱不在註冊表中。
    """
    engine_cls = ENGINES.get(name)
    if engine_cls is None:
        available = ", ".join(sorted(ENGINES.keys()))
        raise ValueError(
            f"未知的上下文引擎 '{name}'，可用引擎：{available}"
        )
    return engine_cls(**kwargs)
