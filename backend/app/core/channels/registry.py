"""Channel adapter registry — maps platform names to adapter classes."""

from typing import Optional
from app.core.channels.base import BaseChannelAdapter


_ADAPTERS: dict[str, type[BaseChannelAdapter]] = {}


def register_adapter(platform: str, adapter_cls: type[BaseChannelAdapter]):
    _ADAPTERS[platform] = adapter_cls


def get_adapter(platform: str, config: dict) -> Optional[BaseChannelAdapter]:
    cls = _ADAPTERS.get(platform)
    if not cls:
        return None
    return cls(config)


def list_platforms() -> list[str]:
    return list(_ADAPTERS.keys())


# Auto-register built-in adapters
def _register_builtins():
    from app.core.channels.adapters.wecom import WeComAdapter
    from app.core.channels.adapters.dingtalk import DingTalkAdapter
    from app.core.channels.adapters.feishu import FeishuAdapter
    from app.core.channels.adapters.telegram import TelegramAdapter
    from app.core.channels.adapters.discord import DiscordAdapter
    from app.core.channels.adapters.slack import SlackAdapter

    register_adapter("wecom", WeComAdapter)
    register_adapter("dingtalk", DingTalkAdapter)
    register_adapter("feishu", FeishuAdapter)
    register_adapter("telegram", TelegramAdapter)
    register_adapter("discord", DiscordAdapter)
    register_adapter("slack", SlackAdapter)


_register_builtins()
