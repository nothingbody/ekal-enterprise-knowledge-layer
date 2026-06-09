"""Channel service — manage channels and process incoming webhook messages."""

import asyncio
import json
import logging
import secrets
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.channel import Channel
from app.models.knowledge_base import KnowledgeBase
from app.models.model_config import ModelConfig
from app.core.channels import get_adapter, OutgoingMessage
from app.core.encryption import encrypt_value, decrypt_value, is_encrypted
from app.config import settings
from app.schemas.chat import ChatRequest
from app.services.chat_service import stream_chat

logger = logging.getLogger(__name__)

# Config keys that contain secrets and should be encrypted at rest
_SENSITIVE_CONFIG_KEYS = {
    "token", "bot_webhook_key", "bot_secret", "encoding_aes_key",
    "app_secret", "access_token", "verification_token", "encrypt_key",
    "bot_webhook_url",  # may contain embedded token
    "bot_token", "secret_token",  # Telegram
}


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

async def list_channels(
    db: AsyncSession, user_id: int, page: int = 1, page_size: int = 50,
    workspace_id: Optional[int] = None,
) -> dict:
    if workspace_id:
        # Verify caller is a member of the workspace before listing its channels
        from app.services.access_service import ensure_workspace_member
        await ensure_workspace_member(db, workspace_id, user_id)
        filters = [Channel.workspace_id == workspace_id]
    else:
        filters = [Channel.user_id == user_id, Channel.workspace_id.is_(None)]
    total = (await db.execute(
        select(func.count(Channel.id)).where(*filters)
    )).scalar() or 0

    result = await db.execute(
        select(Channel).where(*filters)
        .order_by(Channel.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = []
    for ch in result.scalars().all():
        items.append(_channel_to_dict(ch))
    return {"items": items, "total": total, "page": page, "page_size": page_size}


async def get_channel(db: AsyncSession, user_id: int, channel_id: int) -> Optional[dict]:
    result = await db.execute(
        select(Channel).where(Channel.id == channel_id, Channel.user_id == user_id)
    )
    ch = result.scalar_one_or_none()
    if not ch:
        return None
    return _channel_to_dict(ch)


def _encrypt_config(config: dict) -> dict:
    """Encrypt sensitive fields in channel config before persisting."""
    if not config:
        return {}
    encrypted = dict(config)
    for key in _SENSITIVE_CONFIG_KEYS:
        val = encrypted.get(key)
        if val and isinstance(val, str) and not is_encrypted(val):
            encrypted[key] = encrypt_value(val, settings.SECRET_KEY)
    return encrypted


def _decrypt_config(config: dict) -> dict:
    """Decrypt sensitive fields in channel config for runtime use."""
    if not config or not isinstance(config, dict):
        return {}
    decrypted = dict(config)
    for key in _SENSITIVE_CONFIG_KEYS:
        val = decrypted.get(key)
        if val and isinstance(val, str) and is_encrypted(val):
            try:
                decrypted[key] = decrypt_value(val, settings.SECRET_KEY)
            except Exception as e:
                logger.warning("Failed to decrypt channel config key '%s': %s", key, e)
                decrypted[key] = ""
    return decrypted


def _mask_config(config: dict) -> dict:
    """Mask sensitive fields for API responses so secrets are not exposed."""
    if not config or not isinstance(config, dict):
        return {}
    masked = dict(config)
    for key in _SENSITIVE_CONFIG_KEYS:
        val = masked.get(key)
        if val and isinstance(val, str):
            # Show first 4 chars + masked remainder so user knows a value is set
            masked[key] = val[:4] + "****" if len(val) > 4 else "****"
    return masked


async def create_channel(
    db: AsyncSession,
    user_id: int,
    name: str,
    platform: str,
    kb_id: Optional[int],
    llm_model_id: Optional[int],
    chat_mode: str = "auto",
    config: Optional[dict] = None,
    workspace_id: Optional[int] = None,
) -> dict:
    webhook_token = secrets.token_urlsafe(32)
    ch = Channel(
        user_id=user_id,
        workspace_id=workspace_id,
        name=name,
        platform=platform,
        kb_id=kb_id,
        llm_model_id=llm_model_id,
        chat_mode=chat_mode,
        config=_encrypt_config(config or {}),
        webhook_token=webhook_token,
    )
    db.add(ch)
    await db.commit()
    await db.refresh(ch)
    return _channel_to_dict(ch)


async def update_channel(
    db: AsyncSession,
    user_id: int,
    channel_id: int,
    **kwargs,
) -> Optional[dict]:
    result = await db.execute(
        select(Channel).where(Channel.id == channel_id, Channel.user_id == user_id)
    )
    ch = result.scalar_one_or_none()
    if not ch:
        return None

    for key, value in kwargs.items():
        if hasattr(ch, key) and value is not None:
            if key == "config" and isinstance(value, dict):
                value = _encrypt_config(value)
            setattr(ch, key, value)

    await db.commit()
    await db.refresh(ch)
    return _channel_to_dict(ch)


async def delete_channel(db: AsyncSession, user_id: int, channel_id: int) -> bool:
    result = await db.execute(
        select(Channel).where(Channel.id == channel_id, Channel.user_id == user_id)
    )
    ch = result.scalar_one_or_none()
    if not ch:
        return False
    await db.delete(ch)
    await db.commit()
    return True


async def toggle_channel(db: AsyncSession, user_id: int, channel_id: int) -> Optional[dict]:
    result = await db.execute(
        select(Channel).where(Channel.id == channel_id, Channel.user_id == user_id)
    )
    ch = result.scalar_one_or_none()
    if not ch:
        return None
    ch.is_active = not ch.is_active
    await db.commit()
    await db.refresh(ch)
    return _channel_to_dict(ch)


async def send_test_message(db: AsyncSession, user_id: int, channel_id: int) -> tuple[bool, str]:
    """Send a test message to the channel. Returns (success, message)."""
    ch_dict = await get_channel(db, user_id, channel_id)
    if not ch_dict:
        return False, "渠道不存在"
    if not ch_dict.get("is_active"):
        return False, "渠道已停用，请先启用"
    decrypted = _decrypt_config(ch_dict.get("config") or {})
    adapter = get_adapter(ch_dict["platform"], decrypted)
    if not adapter:
        return False, f"不支持的平台: {ch_dict['platform']}"
    try:
        ok = await adapter.send_test_message()
        return ok, "发送成功" if ok else "发送失败，请检查配置"
    except Exception as e:
        logger.exception("Channel %d test send failed", channel_id)
        return False, str(e) or "发送失败"


# ---------------------------------------------------------------------------
# Webhook processing
# ---------------------------------------------------------------------------

async def process_webhook(
    db: AsyncSession,
    webhook_token: str,
    headers: dict,
    body: bytes,
    payload: dict,
) -> Optional[dict]:
    """Process an incoming webhook request for a channel.

    Returns a response dict to send back immediately.  The actual AI
    processing runs in a background task so we don't exceed webhook
    timeout limits (most IM platforms expect a response within 3-5 s).
    """
    # Find channel by webhook token
    result = await db.execute(
        select(Channel).where(Channel.webhook_token == webhook_token)
    )
    channel = result.scalar_one_or_none()
    if not channel:
        logger.warning("Webhook received for unknown token: %s...", webhook_token[:8])
        return {"error": "channel not found"}

    if not channel.is_active:
        logger.info("Webhook received for inactive channel %d", channel.id)
        return {"ok": True, "message": "channel inactive"}

    # Decrypt config for adapter use
    decrypted_config = _decrypt_config(channel.config if isinstance(channel.config, dict) else {})

    adapter = get_adapter(channel.platform, decrypted_config)
    if not adapter:
        logger.error("No adapter for platform: %s", channel.platform)
        return {"error": "unsupported platform"}

    # Slack / Discord 的 challenge 也是 POST webhook，必须先验签再返回 challenge
    must_verify_before_challenge = channel.platform in {"slack", "discord"}
    if must_verify_before_challenge:
        if not adapter.verify_request(headers, body):
            logger.warning("Webhook signature verification failed for channel %d", channel.id)
            return {"error": "signature verification failed"}

    # Handle challenge/verification
    challenge_resp = adapter.get_challenge_response(payload)
    if challenge_resp is not None:
        logger.info("Challenge response for channel %d", channel.id)
        return challenge_resp

    # Other platforms can verify after challenge handling (e.g. GET-based verification)
    if not must_verify_before_challenge and not adapter.verify_request(headers, body):
        logger.warning("Webhook signature verification failed for channel %d", channel.id)
        return {"error": "signature verification failed"}

    # Parse incoming message
    incoming = adapter.parse_message(payload)
    if not incoming:
        return {"ok": True}  # Not a processable message (e.g. event we don't handle)

    if incoming.is_unsupported_type:
        logger.info("Channel %d received unsupported message type from %s", channel.id, incoming.sender_id)
        try:
            await adapter.send_reply(
                OutgoingMessage(text="暂不支持图片/文件/语音等非文本消息，请发送文本内容。", markdown=False),
                incoming,
            )
        except Exception:
            pass
        return {"ok": True}

    logger.info(
        "Channel %d (%s) received message from %s: %s",
        channel.id, channel.platform, incoming.sender_id, incoming.text[:50],
    )

    # Validate that the channel has a knowledge base configured
    if not channel.kb_id:
        logger.warning("Channel %d has no kb_id configured, sending error", channel.id)
        try:
            await adapter.send_reply(
                OutgoingMessage(text="该渠道尚未绑定知识库，无法回复消息。请在管理后台配置渠道。", markdown=False),
                incoming,
            )
        except Exception:
            pass
        return {"ok": True}

    # Dispatch the heavy AI processing to a background task so we can
    # respond to the webhook immediately (avoids platform timeouts).
    # Capture the values needed by the background task.
    ch_id = channel.id
    ch_user_id = channel.user_id
    ch_kb_id = channel.kb_id
    ch_llm_model_id = channel.llm_model_id
    ch_chat_mode = channel.chat_mode or "auto"

    asyncio.create_task(
        _process_channel_message(
            ch_id, ch_user_id, ch_kb_id, ch_llm_model_id, ch_chat_mode,
            decrypted_config, channel.platform, incoming,
        )
    )

    return {"ok": True}


async def _process_channel_message(
    channel_id: int,
    user_id: int,
    kb_id: int,
    llm_model_id: Optional[int],
    chat_mode: str,
    decrypted_config: dict,
    platform: str,
    incoming,
) -> None:
    """Background task: call AI and send reply via the channel adapter.

    Enhancements (OpenClaw-inspired):
    - Per-session execution lock: only one AI run per (channel, sender) at a time.
    - Typing indicator: sent immediately before AI processing begins.
    - Channel session persistence: binds sender to a conversation so consecutive
      messages share context (dmScope: per-channel-peer equivalent).
    - Session idle-timeout: expired sessions start a fresh conversation.
    """
    from app.database import async_session
    from app.core.session_lock import acquire_session_lock
    from app.models.channel_session import ChannelSession
    from sqlalchemy import select
    from datetime import datetime, timezone, timedelta

    adapter = get_adapter(platform, decrypted_config)
    if not adapter:
        return

    # --- 1. Acquire per-session lock (OpenClaw queue: serialise per session-key) ---
    try:
        lock_ctx = acquire_session_lock(channel_id, incoming.sender_id, timeout=60)
        async with lock_ctx:
            await _run_channel_ai(  # extracted to keep lock scope explicit
                channel_id=channel_id,
                user_id=user_id,
                kb_id=kb_id,
                llm_model_id=llm_model_id,
                chat_mode=chat_mode,
                adapter=adapter,
                incoming=incoming,
            )
    except asyncio.TimeoutError:
        logger.warning(
            "Session lock timeout for channel %d sender %s — message dropped",
            channel_id, incoming.sender_id,
        )
    except Exception as exc:
        logger.error("Channel %d outer error: %s", channel_id, exc)


async def _run_channel_ai(
    channel_id: int,
    user_id: int,
    kb_id: int,
    llm_model_id: Optional[int],
    chat_mode: str,
    adapter,
    incoming,
) -> None:
    """Inner handler, called under the per-session lock."""
    from app.database import async_session
    from app.models.channel_session import ChannelSession
    from sqlalchemy import select
    from datetime import datetime, timezone, timedelta

    # --- 2. Typing indicator (OpenClaw typingMode: instant) ---
    try:
        await adapter.send_typing(incoming)
    except Exception:
        pass  # best-effort, never block on typing failure

    try:
        async with async_session() as db:
            # --- 3. Session persistence: look up or create ChannelSession ---
            result = await db.execute(
                select(ChannelSession).where(
                    ChannelSession.channel_id == channel_id,
                    ChannelSession.sender_id == incoming.sender_id,
                )
            )
            ch_session = result.scalar_one_or_none()

            conversation_id: Optional[int] = None

            if ch_session is not None:
                # Check idle timeout (OpenClaw session lifecycle: idle reset)
                if ch_session.last_active_at and not ch_session.is_expired:
                    cutoff = datetime.now(timezone.utc) - timedelta(
                        minutes=ch_session.idle_timeout_minutes
                    )
                    if ch_session.last_active_at < cutoff:
                        # Session has gone idle — start fresh
                        ch_session.is_expired = True
                        ch_session.conversation_id = None
                        await db.commit()
                        logger.info(
                            "Channel session %d:%s expired (idle); starting new conversation",
                            channel_id, incoming.sender_id,
                        )
                    elif not ch_session.is_expired:
                        conversation_id = ch_session.conversation_id

            # --- 4. Build ChatRequest with optional conversation_id ---
            chat_req = ChatRequest(
                kb_id=kb_id,
                llm_model_id=llm_model_id or 0,
                question=incoming.text,
                chat_mode=chat_mode,
                conversation_id=conversation_id,
            )

            full_response = ""
            new_conversation_id: Optional[int] = None

            async for chunk_str in stream_chat(db, user_id, chat_req):
                try:
                    chunk = json.loads(chunk_str.strip())
                    chunk_type = chunk.get("type")
                    if chunk_type == "content":
                        full_response += chunk["data"]
                    elif chunk_type == "done" and not new_conversation_id:
                        new_conversation_id = chunk.get("conversation_id")
                except (json.JSONDecodeError, KeyError):
                    continue

            if full_response:
                reply = OutgoingMessage(text=full_response, markdown=True)
                sent = await adapter.send_reply(reply, incoming)
                if not sent:
                    logger.warning("Failed to send reply for channel %d", channel_id)
            else:
                logger.warning("Empty response from AI for channel %d", channel_id)

            # --- 5. Backfill / update ChannelSession ---
            resolved_conv_id = new_conversation_id or conversation_id
            if resolved_conv_id:
                now = datetime.now(timezone.utc)
                if ch_session is None:
                    ch_session = ChannelSession(
                        channel_id=channel_id,
                        sender_id=incoming.sender_id,
                        conversation_id=resolved_conv_id,
                        last_active_at=now,
                        is_expired=False,
                    )
                    db.add(ch_session)
                else:
                    ch_session.conversation_id = resolved_conv_id
                    ch_session.last_active_at = now
                    ch_session.is_expired = False
                try:
                    await db.commit()
                except Exception as exc:
                    logger.warning("Could not persist ChannelSession: %s", exc)

    except Exception as exc:
        logger.error("Channel %d message processing error: %s", channel_id, exc)
        try:
            error_reply = OutgoingMessage(text="抱歉，处理消息时出错，请稍后再试。", markdown=False)
            await adapter.send_reply(error_reply, incoming)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _channel_to_dict(ch: Channel, unmask: bool = False) -> dict:
    # Return masked config by default; only decrypt for internal/runtime use
    raw_config = ch.config if isinstance(ch.config, dict) else {}
    decrypted = _decrypt_config(raw_config)
    display_config = decrypted if unmask else _mask_config(decrypted)
    return {
        "id": ch.id,
        "name": ch.name,
        "workspace_id": ch.workspace_id,
        "platform": ch.platform,
        "kb_id": ch.kb_id,
        "llm_model_id": ch.llm_model_id,
        "chat_mode": ch.chat_mode,
        "config": display_config,
        "is_active": ch.is_active,
        "webhook_token": ch.webhook_token,
        "created_at": ch.created_at.isoformat() if ch.created_at else None,
        "updated_at": ch.updated_at.isoformat() if ch.updated_at else None,
    }
