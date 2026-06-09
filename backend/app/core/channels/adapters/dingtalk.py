"""DingTalk (钉钉) channel adapter."""

import hashlib
import hmac
import base64
import logging
import time
from typing import Optional

import httpx

from app.core.channels.base import BaseChannelAdapter, IncomingMessage, OutgoingMessage

logger = logging.getLogger(__name__)


class DingTalkAdapter(BaseChannelAdapter):
    """Adapter for DingTalk robot webhook.

    Config keys:
      - app_secret: 机器人密钥 (用于验证签名)
      - access_token: 机器人 access_token (用于发送消息)
    """

    platform = "dingtalk"

    def verify_request(self, headers: dict, body: bytes) -> bool:
        secret = self.config.get("app_secret", "")
        if not secret:
            return True

        timestamp = headers.get("timestamp", "")
        sign = headers.get("sign", "")
        if not timestamp or not sign:
            return False

        string_to_sign = f"{timestamp}\n{secret}"
        hmac_code = hmac.new(
            secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        computed_sign = base64.b64encode(hmac_code).decode("utf-8")
        return computed_sign == sign

    def parse_message(self, payload: dict) -> Optional[IncomingMessage]:
        msg_type = payload.get("msgtype", "")

        sender_id = payload.get("senderStaffId") or payload.get("senderId", "unknown")
        sender_name = payload.get("senderNick", "")
        conversation_id = payload.get("conversationId", "")

        if msg_type == "text":
            content = payload.get("text", {}).get("content", "").strip()
            if not content:
                return None

            return IncomingMessage(
                text=content,
                sender_id=str(sender_id),
                sender_name=sender_name,
                conversation_id=conversation_id,
                platform="dingtalk",
                raw=payload,
            )

        if msg_type and msg_type != "text":
            return IncomingMessage(
                text="",
                sender_id=str(sender_id),
                sender_name=sender_name,
                conversation_id=conversation_id,
                platform="dingtalk",
                raw=payload,
                is_unsupported_type=True,
            )

        return None

    async def send_reply(self, message: OutgoingMessage, incoming: IncomingMessage) -> bool:
        access_token = self.config.get("access_token", "")
        if not access_token:
            logger.error("DingTalk access_token not configured")
            return False

        url = f"https://oapi.dingtalk.com/robot/send?access_token={access_token}"

        # Add signature if secret is configured
        secret = self.config.get("app_secret", "")
        if secret:
            ts = str(int(time.time() * 1000))
            string_to_sign = f"{ts}\n{secret}"
            hmac_code = hmac.new(
                secret.encode("utf-8"),
                string_to_sign.encode("utf-8"),
                digestmod=hashlib.sha256,
            ).digest()
            sign = base64.b64encode(hmac_code).decode("utf-8")
            url += f"&timestamp={ts}&sign={sign}"

        if message.markdown:
            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "title": "AI 回复",
                    "text": message.text,
                },
            }
        else:
            payload = {
                "msgtype": "text",
                "text": {"content": message.text},
            }

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json=payload)
                data = resp.json()
                if data.get("errcode") != 0:
                    logger.warning("DingTalk send failed: %s", data)
                    return False
                return True
        except Exception as exc:
            logger.error("DingTalk send error: %s", exc)
            return False
