"""Discord channel adapter — handles Discord Interactions webhook."""

import hashlib
import hmac
import logging
import time
from typing import Optional

import httpx

from app.core.channels.base import BaseChannelAdapter, IncomingMessage, OutgoingMessage

logger = logging.getLogger(__name__)


class DiscordAdapter(BaseChannelAdapter):
    platform = "discord"

    def verify_request(self, headers: dict, body: bytes) -> bool:
        public_key = self.config.get("public_key", "")
        signature = headers.get("x-signature-ed25519", "")
        timestamp = headers.get("x-signature-timestamp", "")
        if not public_key or not signature or not timestamp:
            return False
        try:
            from nacl.signing import VerifyKey
            verify_key = VerifyKey(bytes.fromhex(public_key))
            verify_key.verify(timestamp.encode() + body, bytes.fromhex(signature))
            return True
        except ImportError:
            logger.error("PyNaCl not installed, cannot verify Discord signature")
            return False
        except Exception:
            logger.warning("Discord signature verification failed")
            return False

    def parse_message(self, payload: dict) -> Optional[IncomingMessage]:
        msg_type = payload.get("type")
        if msg_type == 1:
            return None
        if msg_type == 2:
            data = payload.get("data", {})
            options = data.get("options", [])
            text = " ".join(opt.get("value", "") for opt in options if opt.get("value"))
            if not text:
                text = data.get("name", "")
            user = payload.get("member", {}).get("user", {}) or payload.get("user", {})
            return IncomingMessage(
                text=text,
                sender_id=user.get("id", ""),
                sender_name=user.get("username", ""),
                conversation_id=payload.get("channel_id", ""),
                platform="discord",
                raw=payload,
            )
        if "content" in payload:
            author = payload.get("author", {})
            if author.get("bot"):
                return None
            return IncomingMessage(
                text=payload.get("content", ""),
                sender_id=author.get("id", ""),
                sender_name=author.get("username", ""),
                conversation_id=payload.get("channel_id", ""),
                platform="discord",
                raw=payload,
            )
        return None

    async def send_test_message(self, text: str = "这是一条测试消息，说明渠道配置正确。") -> bool:
        raise ValueError("Discord 需先在频道中 @机器人 或发送消息激活，无法直接测试发送。配置无误时，在频道发消息即可收到回复。")

    async def send_reply(self, message: OutgoingMessage, incoming: IncomingMessage) -> bool:
        bot_token = self.config.get("bot_token", "")
        channel_id = incoming.conversation_id
        if not bot_token or not channel_id:
            logger.error("Discord: missing bot_token or channel_id")
            return False
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
        text = message.text
        chunks = [text[i:i+2000] for i in range(0, len(text), 2000)]
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                for chunk in chunks:
                    resp = await client.post(
                        url,
                        headers={"Authorization": f"Bot {bot_token}"},
                        json={"content": chunk},
                    )
                    if resp.status_code not in (200, 201):
                        logger.error("Discord send failed: %s %s", resp.status_code, resp.text[:200])
                        return False
            return True
        except Exception as exc:
            logger.error("Discord send error: %s", exc)
            return False

    def get_challenge_response(self, payload: dict) -> Optional[dict]:
        if payload.get("type") == 1:
            return {"type": 1}
        return None
