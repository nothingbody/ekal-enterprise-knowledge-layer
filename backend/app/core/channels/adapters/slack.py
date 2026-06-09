"""Slack channel adapter — handles Slack Events API webhook."""

import hashlib
import hmac
import logging
import time
from typing import Optional

import httpx

from app.core.channels.base import BaseChannelAdapter, IncomingMessage, OutgoingMessage

logger = logging.getLogger(__name__)


class SlackAdapter(BaseChannelAdapter):
    platform = "slack"

    def verify_request(self, headers: dict, body: bytes) -> bool:
        signing_secret = self.config.get("signing_secret", "")
        timestamp = headers.get("x-slack-request-timestamp", "")
        slack_signature = headers.get("x-slack-signature", "")
        if not signing_secret or not timestamp or not slack_signature:
            return False
        if abs(time.time() - int(timestamp)) > 300:
            logger.warning("Slack request timestamp too old")
            return False
        sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
        computed = "v0=" + hmac.HMAC(
            signing_secret.encode(), sig_basestring.encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(computed, slack_signature)

    def parse_message(self, payload: dict) -> Optional[IncomingMessage]:
        if payload.get("type") == "url_verification":
            return None
        event = payload.get("event", {})
        if event.get("type") != "message":
            return None
        if event.get("subtype"):
            return None
        if event.get("bot_id"):
            return None
        return IncomingMessage(
            text=event.get("text", ""),
            sender_id=event.get("user", ""),
            sender_name=event.get("user", ""),
            conversation_id=event.get("channel", ""),
            platform="slack",
            raw=payload,
        )

    async def send_test_message(self, text: str = "这是一条测试消息，说明渠道配置正确。") -> bool:
        raise ValueError("Slack 需先在频道中 @机器人 或发送消息激活，无法直接测试发送。配置无误时，在频道发消息即可收到回复。")

    async def send_reply(self, message: OutgoingMessage, incoming: IncomingMessage) -> bool:
        bot_token = self.config.get("bot_token", "")
        channel = incoming.conversation_id
        if not bot_token or not channel:
            logger.error("Slack: missing bot_token or channel")
            return False
        url = "https://slack.com/api/chat.postMessage"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {bot_token}"},
                    json={"channel": channel, "text": message.text, "mrkdwn": message.markdown},
                )
                data = resp.json()
                if not data.get("ok"):
                    logger.error("Slack send failed: %s", data.get("error"))
                    return False
            return True
        except Exception as exc:
            logger.error("Slack send error: %s", exc)
            return False

    def get_challenge_response(self, payload: dict) -> Optional[dict]:
        if payload.get("type") == "url_verification":
            return {"challenge": payload.get("challenge", "")}
        return None
