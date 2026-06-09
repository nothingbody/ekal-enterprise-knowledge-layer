"""Enterprise WeChat (企业微信) channel adapter."""

import hashlib
import logging
from typing import Optional

import httpx

from app.core.channels.base import BaseChannelAdapter, IncomingMessage, OutgoingMessage

logger = logging.getLogger(__name__)


class WeComAdapter(BaseChannelAdapter):
    """Adapter for Enterprise WeChat bot webhook.

    Config keys:
      - corp_id: 企业ID
      - bot_secret: 机器人密钥 (用于验证回调)
      - bot_webhook_key: 机器人 webhook key (用于发送消息)
      - token: 回调配置 Token
      - encoding_aes_key: 回调配置 EncodingAESKey (optional, for encrypted mode)
    """

    platform = "wecom"

    def verify_request(self, headers: dict, body: bytes) -> bool:
        token = self.config.get("token", "")
        if not token:
            # Security: reject requests when token is not configured
            # to prevent unauthorized message injection
            return False
        # WeChat callback signature verification
        timestamp = headers.get("timestamp", "")
        nonce = headers.get("nonce", "")
        msg_signature = headers.get("msg_signature", "")
        check_str = "".join(sorted([token, timestamp, nonce]))
        computed = hashlib.sha1(check_str.encode()).hexdigest()
        return computed == msg_signature

    def parse_message(self, payload: dict) -> Optional[IncomingMessage]:
        msg_type = payload.get("MsgType") or payload.get("msgtype", "")

        sender_id = payload.get("FromUserName") or payload.get("from", {}).get("user_id", "unknown")

        # Handle text messages
        if msg_type == "text":
            content = ""
            if isinstance(payload.get("Text"), dict):
                content = payload["Text"].get("Content", "")
            elif isinstance(payload.get("text"), dict):
                content = payload["text"].get("content", "")
            elif isinstance(payload.get("Content"), str):
                content = payload["Content"]

            if not content.strip():
                return None

            return IncomingMessage(
                text=content.strip(),
                sender_id=str(sender_id),
                sender_name=payload.get("from", {}).get("name"),
                platform="wecom",
                raw=payload,
            )

        if msg_type and msg_type != "event":
            return IncomingMessage(
                text="",
                sender_id=str(sender_id),
                platform="wecom",
                raw=payload,
                is_unsupported_type=True,
            )

        return None

    async def send_reply(self, message: OutgoingMessage, incoming: IncomingMessage) -> bool:
        webhook_key = self.config.get("bot_webhook_key", "")
        if not webhook_key:
            logger.error("WeChat bot_webhook_key not configured")
            return False

        url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={webhook_key}"

        # Convert markdown to WeChat-compatible format
        if message.markdown:
            payload = {
                "msgtype": "markdown",
                "markdown": {"content": message.text},
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
                    logger.warning("WeChat send failed: %s", data)
                    return False
                return True
        except Exception as exc:
            logger.error("WeChat send error: %s", exc)
            return False

    def get_challenge_response(self, payload: dict) -> Optional[dict]:
        # WeChat URL verification echo
        echostr = payload.get("echostr")
        if echostr:
            return {"echostr": echostr}
        return None
