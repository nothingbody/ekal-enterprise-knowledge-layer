"""Feishu / Lark (飞书) channel adapter."""

import hashlib
import hmac
import logging
from typing import Optional

import httpx

from app.core.channels.base import BaseChannelAdapter, IncomingMessage, OutgoingMessage

logger = logging.getLogger(__name__)


class FeishuAdapter(BaseChannelAdapter):
    """Adapter for Feishu bot webhook.

    Config keys:
      - app_id: 应用 App ID
      - app_secret: 应用 App Secret
      - verification_token: 事件订阅 Verification Token
      - encrypt_key: 事件订阅 Encrypt Key (optional)
      - bot_webhook_url: 自定义机器人 webhook URL (用于发送消息)
    """

    platform = "feishu"

    def verify_request(self, headers: dict, body: bytes) -> bool:
        token = self.config.get("verification_token", "")
        if not token:
            return True

        # Feishu signs with X-Lark-Signature header
        signature = headers.get("x-lark-signature", "")
        timestamp = headers.get("x-lark-request-timestamp", "")
        nonce = headers.get("x-lark-request-nonce", "")

        if signature and timestamp and nonce:
            content = timestamp + nonce + token + body.decode("utf-8", errors="ignore")
            computed = hashlib.sha256(content.encode("utf-8")).hexdigest()
            return computed == signature

        return True  # If no signature headers present, allow (might be challenge)

    def parse_message(self, payload: dict) -> Optional[IncomingMessage]:
        # Feishu event format
        event = payload.get("event", {})
        header = payload.get("header", {})

        # v2.0 event format
        event_type = header.get("event_type", "")
        if event_type == "im.message.receive_v1":
            message = event.get("message", {})
            msg_type = message.get("message_type", "")

            sender = event.get("sender", {}).get("sender_id", {})
            sender_id = sender.get("open_id") or sender.get("user_id", "unknown")
            chat_id = message.get("chat_id", "")

            if msg_type == "text":
                import json
                try:
                    content_obj = json.loads(message.get("content", "{}"))
                    text = content_obj.get("text", "").strip()
                except (json.JSONDecodeError, TypeError):
                    text = ""

                if not text:
                    return None

                return IncomingMessage(
                    text=text,
                    sender_id=str(sender_id),
                    conversation_id=chat_id,
                    platform="feishu",
                    raw=payload,
                )

            return IncomingMessage(
                text="",
                sender_id=str(sender_id),
                conversation_id=chat_id,
                platform="feishu",
                raw=payload,
                is_unsupported_type=True,
            )

        # v1.0 event format fallback
        if payload.get("type") == "event_callback":
            event_v1 = payload.get("event", {})
            if event_v1.get("type") == "message":
                text = event_v1.get("text_without_at_bot", "") or event_v1.get("text", "")
                text = text.strip()
                if not text:
                    return None
                return IncomingMessage(
                    text=text,
                    sender_id=event_v1.get("open_id", "unknown"),
                    conversation_id=event_v1.get("open_chat_id", ""),
                    platform="feishu",
                    raw=payload,
                )

        return None

    async def send_reply(self, message: OutgoingMessage, incoming: IncomingMessage) -> bool:
        webhook_url = self.config.get("bot_webhook_url", "")
        if not webhook_url:
            logger.error("Feishu bot_webhook_url not configured")
            return False

        # Sign webhook if secret is configured
        secret = self.config.get("app_secret", "")

        import json
        if message.markdown:
            payload = {
                "msg_type": "interactive",
                "card": {
                    "elements": [
                        {
                            "tag": "markdown",
                            "content": message.text,
                        }
                    ],
                },
            }
        else:
            payload = {
                "msg_type": "text",
                "content": {"text": message.text},
            }

        if secret:
            import time
            timestamp = str(int(time.time()))
            string_to_sign = f"{timestamp}\n{secret}"
            hmac_code = hmac.new(
                string_to_sign.encode("utf-8"), b"",
                digestmod=hashlib.sha256,
            ).digest()
            import base64
            sign = base64.b64encode(hmac_code).decode("utf-8")
            payload["timestamp"] = timestamp
            payload["sign"] = sign

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(webhook_url, json=payload)
                data = resp.json()
                if data.get("code") not in (0, None) and data.get("StatusCode") != 0:
                    logger.warning("Feishu send failed: %s", data)
                    return False
                return True
        except Exception as exc:
            logger.error("Feishu send error: %s", exc)
            return False

    def get_challenge_response(self, payload: dict) -> Optional[dict]:
        # Feishu URL verification challenge
        challenge = payload.get("challenge")
        if challenge:
            return {"challenge": challenge}
        return None
