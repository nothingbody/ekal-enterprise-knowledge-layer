"""Telegram Bot channel adapter."""

import logging
from typing import Optional

import httpx

from app.core.channels.base import BaseChannelAdapter, IncomingMessage, OutgoingMessage

logger = logging.getLogger(__name__)


class TelegramAdapter(BaseChannelAdapter):
    """Adapter for Telegram Bot API.

    Config keys:
      - bot_token: Telegram Bot API token (from @BotFather)
      - secret_token: Optional webhook secret for request verification
    """

    platform = "telegram"

    _API_BASE = "https://api.telegram.org"

    def _bot_url(self, method: str) -> str:
        token = self.config.get("bot_token", "")
        return f"{self._API_BASE}/bot{token}/{method}"

    def verify_request(self, headers: dict, body: bytes) -> bool:
        secret = self.config.get("secret_token", "")
        if not secret:
            return True
        header_secret = headers.get("x-telegram-bot-api-secret-token", "")
        return header_secret == secret

    def parse_message(self, payload: dict) -> Optional[IncomingMessage]:
        message = payload.get("message") or payload.get("edited_message")
        if not message:
            return None

        from_user = message.get("from", {})
        sender_id = str(from_user.get("id", "unknown"))
        sender_name = from_user.get("first_name", "")
        if from_user.get("last_name"):
            sender_name += " " + from_user["last_name"]

        chat_id = str(message.get("chat", {}).get("id", ""))

        text = message.get("text", "").strip()
        if not text:
            has_media = any(k in message for k in ("photo", "document", "video", "audio", "voice", "sticker", "animation"))
            if has_media:
                return IncomingMessage(
                    text="",
                    sender_id=sender_id,
                    sender_name=sender_name or None,
                    conversation_id=chat_id,
                    platform="telegram",
                    raw=payload,
                    is_unsupported_type=True,
                )
            return None

        return IncomingMessage(
            text=text,
            sender_id=sender_id,
            sender_name=sender_name or None,
            conversation_id=chat_id,
            platform="telegram",
            raw=payload,
        )

    async def send_reply(self, message: OutgoingMessage, incoming: IncomingMessage) -> bool:
        chat_id = incoming.raw.get("message", incoming.raw.get("edited_message", {})).get("chat", {}).get("id")
        if not chat_id:
            logger.error("Telegram: cannot determine chat_id for reply")
            return False

        payload = {
            "chat_id": chat_id,
            "text": message.text,
        }
        if message.markdown:
            payload["parse_mode"] = "Markdown"

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(self._bot_url("sendMessage"), json=payload)
                data = resp.json()
                if not data.get("ok"):
                    # Retry without parse_mode if Markdown fails
                    if message.markdown:
                        payload.pop("parse_mode", None)
                        resp = await client.post(self._bot_url("sendMessage"), json=payload)
                        data = resp.json()
                    if not data.get("ok"):
                        logger.warning("Telegram send failed: %s", data)
                        return False
                return True
        except Exception as exc:
            logger.error("Telegram send error: %s", exc)
            return False

    async def send_test_message(self, text: str = "这是一条测试消息，说明渠道配置正确。") -> bool:
        """Telegram requires a chat_id; without a prior user message we cannot send.
        Raise a clear error instead of failing silently.
        """
        raise ValueError("Telegram 需先向机器人发送任意消息激活对话，无法直接测试发送。配置无误时，向机器人发消息即可收到回复。")

    async def send_typing(self, incoming: IncomingMessage) -> None:
        chat_id = incoming.raw.get("message", incoming.raw.get("edited_message", {})).get("chat", {}).get("id")
        if not chat_id:
            return
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(self._bot_url("sendChatAction"), json={
                    "chat_id": chat_id,
                    "action": "typing",
                })
        except Exception:
            pass  # Best effort
