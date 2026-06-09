"""Background sync tasks — heartbeat and periodic usage reporting."""

from __future__ import annotations

import asyncio
import json as _json
import logging
import platform
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from app.cloud.client import (
    cloud_device_heartbeat,
    cloud_submit_usage,
    cloud_submit_operation_logs,
    is_cloud_enabled,
)

logger = logging.getLogger(__name__)

_DEVICE_ID_FILE = "device_id"
_TOKEN_FILE = ".cloud_tokens"
_device_id: str | None = None


def _get_data_dir() -> Path:
    from app.config import settings
    return Path(settings.UPLOAD_DIR).parent / "data"


def get_device_id(data_dir: str | None = None) -> str:
    """Return a persistent device identifier, creating one if needed."""
    global _device_id
    if _device_id:
        return _device_id

    if data_dir:
        id_file = Path(data_dir) / _DEVICE_ID_FILE
    else:
        id_file = _get_data_dir() / _DEVICE_ID_FILE

    id_file.parent.mkdir(parents=True, exist_ok=True)

    if id_file.exists():
        _device_id = id_file.read_text(encoding="utf-8").strip()
        if _device_id:
            return _device_id

    _device_id = uuid.uuid4().hex
    id_file.write_text(_device_id, encoding="utf-8")
    return _device_id


def get_os_info() -> str:
    return f"{platform.system()} {platform.machine()}"


def get_device_name() -> str:
    return "desktop"


# ─────────────────────────────────────────
# Cloud token storage (memory + file persistence)
# ─────────────────────────────────────────

_cloud_token: str | None = None
_cloud_refresh_token: str | None = None


def _token_file_path() -> Path:
    return _get_data_dir() / _TOKEN_FILE


def _persist_tokens() -> None:
    """Save tokens to disk so background tasks survive restarts.

    Uses atomic write (temp file + rename) to prevent corruption
    from concurrent writes or mid-write crashes.
    """
    try:
        import os, tempfile
        path = _token_file_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {"access": _cloud_token or "", "refresh": _cloud_refresh_token or ""}
        content = _json.dumps(data)
        # Atomic write: write to temp file then rename
        fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp_path, str(path))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    except Exception as exc:
        logger.debug("Failed to persist cloud tokens: %s", exc)


def _load_persisted_tokens() -> None:
    """Load tokens from disk if memory is empty."""
    global _cloud_token, _cloud_refresh_token
    if _cloud_token or _cloud_refresh_token:
        return
    try:
        path = _token_file_path()
        if path.exists():
            data = _json.loads(path.read_text(encoding="utf-8"))
            _cloud_token = data.get("access") or None
            _cloud_refresh_token = data.get("refresh") or None
    except Exception as exc:
        logger.debug("Failed to load persisted cloud tokens: %s", exc)


def set_cloud_tokens(access: str, refresh: str) -> None:
    global _cloud_token, _cloud_refresh_token
    _cloud_token = access
    _cloud_refresh_token = refresh
    _persist_tokens()


def get_cloud_token() -> str | None:
    _load_persisted_tokens()
    return _cloud_token


def clear_cloud_tokens() -> None:
    global _cloud_token, _cloud_refresh_token
    _cloud_token = None
    _cloud_refresh_token = None
    try:
        path = _token_file_path()
        if path.exists():
            path.unlink()
    except Exception as exc:
        logger.debug("Failed to clear token file: %s", exc)


def _is_token_expired(token: str) -> bool:
    """Check if a JWT token is expired or about to expire (within 60s)."""
    try:
        import jwt as pyjwt
        payload = pyjwt.decode(token, options={"verify_signature": False})
        exp = payload.get("exp", 0)
        import time
        return time.time() > (exp - 60)
    except Exception as exc:
        logger.debug("Token expiration check failed: %s", exc)
        return True


async def ensure_cloud_token() -> str | None:
    """Return the current cloud token, refreshing if needed."""
    global _cloud_token, _cloud_refresh_token
    _load_persisted_tokens()
    if _cloud_token and not _is_token_expired(_cloud_token):
        return _cloud_token
    _cloud_token = None
    if _cloud_refresh_token:
        try:
            from app.cloud.client import cloud_refresh_token
            result = await cloud_refresh_token(_cloud_refresh_token)
            _cloud_token = result.get("access_token")
            _cloud_refresh_token = result.get("refresh_token", _cloud_refresh_token)
            _persist_tokens()
            return _cloud_token
        except Exception as exc:
            logger.warning("Cloud token refresh failed: %s", exc)
            clear_cloud_tokens()
    return None


# ─────────────────────────────────────────
# Background loops
# ─────────────────────────────────────────

async def heartbeat_loop(interval_seconds: int = 300) -> None:
    """Send heartbeat to the central server every `interval_seconds`."""
    await detect_and_report_ip()
    while True:
        await asyncio.sleep(interval_seconds)
        if not is_cloud_enabled():
            continue
        token = await ensure_cloud_token()
        if not token:
            continue
        try:
            device_id = get_device_id()
            extra = await _collect_heartbeat_extras()
            await cloud_device_heartbeat(
                token=token,
                device_id=device_id,
                app_version=_get_app_version(),
                extra=extra,
            )
            logger.debug("Cloud heartbeat sent")
        except Exception as exc:
            logger.debug("Cloud heartbeat failed: %s", exc)


def _get_mac_address() -> str:
    """Get the primary MAC address of the device."""
    try:
        import uuid
        mac = uuid.getnode()
        return ':'.join(f'{(mac >> (8 * i)) & 0xff:02x}' for i in reversed(range(6)))
    except Exception:
        return ""


async def _collect_heartbeat_extras() -> dict:
    """Collect rich device info for the heartbeat payload."""
    import os
    extras: dict = {
        "os_info": get_os_info(),
        "hostname": platform.node(),
        "mac_address": _get_mac_address(),
    }
    try:
        from app.database import async_session
        from sqlalchemy import select, func
        from app.models.knowledge_base import KnowledgeBase
        from app.models.document import Document
        from app.models.user import User

        async with async_session() as db:
            extras["user_count"] = (await db.execute(select(func.count(User.id)))).scalar() or 0
            extras["kb_count"] = (await db.execute(select(func.count(KnowledgeBase.id)))).scalar() or 0
            extras["doc_count"] = (await db.execute(select(func.count(Document.id)))).scalar() or 0
    except Exception as exc:
        logger.debug("Failed to collect DB stats for heartbeat: %s", exc)
    try:
        data_dir = _get_data_dir()
        db_file = data_dir / "rag.db"
        if db_file.exists():
            extras["db_size_mb"] = round(db_file.stat().st_size / (1024 * 1024), 1)
    except Exception as exc:
        logger.debug("Failed to check db file size: %s", exc)
    try:
        last_usage_date = await _load_last_usage_sync_date()
        if last_usage_date:
            extras["last_usage_sync"] = last_usage_date.isoformat()
        last_log_id = await _load_last_synced_log_id()
        extras["last_synced_log_id"] = last_log_id
    except Exception as exc:
        logger.debug("Failed to load sync state: %s", exc)
    return extras


async def usage_report_loop(interval_seconds: int = 3600) -> None:
    """Aggregate and report usage to the central server periodically.

    On each cycle, sends today's usage AND any unsent historical days
    (up to 7 days back) to prevent data loss from transient failures.
    """
    from app.config import settings as _settings
    while True:
        await asyncio.sleep(interval_seconds)
        if not is_cloud_enabled():
            continue
        if not getattr(_settings, "CLOUD_USAGE_REPORT_ENABLED", True):
            continue
        token = await ensure_cloud_token()
        if not token:
            continue
        device_id = get_device_id()
        today = date.today()

        last_synced = await _load_last_usage_sync_date()
        backfill_start = max(today - timedelta(days=7), last_synced + timedelta(days=1)) if last_synced else today

        days_to_sync = []
        d = backfill_start
        while d <= today:
            days_to_sync.append(d)
            d += timedelta(days=1)

        latest_success = last_synced
        for report_day in days_to_sync:
            try:
                stats = await _collect_local_usage(report_day)
                await cloud_submit_usage(
                    token=token,
                    device_id=device_id,
                    report_date=report_day,
                    **stats,
                )
                latest_success = report_day
                if report_day != today:
                    logger.info("Cloud usage backfill for %s: %s", report_day, stats)
            except Exception as exc:
                logger.warning("Cloud usage report failed for %s: %s", report_day, exc)
                break

        if latest_success and latest_success != last_synced:
            await _save_last_usage_sync_date(latest_success)

        try:
            detailed = await _collect_detailed_usage()
            if detailed.get("by_model"):
                from app.cloud.client import cloud_submit_detailed_usage
                await cloud_submit_detailed_usage(token, device_id, detailed)
        except Exception as exc:
            logger.debug("Failed to submit detailed usage: %s", exc)


async def _load_last_usage_sync_date() -> date | None:
    try:
        path = _get_data_dir() / ".last_usage_sync_date"
        if path.exists():
            return date.fromisoformat(path.read_text(encoding="utf-8").strip())
    except Exception as exc:
        logger.debug("Failed to load last usage sync date: %s", exc)
    return None


async def _save_last_usage_sync_date(d: date) -> None:
    try:
        path = _get_data_dir() / ".last_usage_sync_date"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(d.isoformat(), encoding="utf-8")
    except Exception as exc:
        logger.debug("Failed to save last usage sync date: %s", exc)


async def _collect_local_usage(target_date: date | None = None) -> dict:
    """Gather aggregated usage statistics from local database for a given date."""
    try:
        from app.database import async_session
        from sqlalchemy import select, func
        from app.models.knowledge_base import KnowledgeBase
        from app.models.document import Document
        from app.models.chat_history import ChatConversation, ChatMessage

        target = target_date or date.today()

        async with async_session() as db:
            kb_count = (await db.execute(select(func.count(KnowledgeBase.id)))).scalar() or 0
            doc_count = (await db.execute(select(func.count(Document.id)))).scalar() or 0

            conv_count = 0
            msg_count = 0
            token_count = 0
            try:
                day_convs = (await db.execute(
                    select(ChatConversation)
                    .where(func.date(ChatConversation.created_at) == target)
                )).scalars().all()

                conv_count = len(day_convs)
                for c in day_convs:
                    token_count += (c.total_input_tokens or 0) + (c.total_output_tokens or 0)

                msg_count = (await db.execute(
                    select(func.count(ChatMessage.id))
                    .where(func.date(ChatMessage.created_at) == target)
                )).scalar() or 0
            except Exception as exc:
                logger.debug("Failed to count chat messages: %s", exc)

        return {
            "token_count": token_count,
            "conversation_count": conv_count,
            "message_count": msg_count,
            "kb_count": kb_count,
            "doc_count": doc_count,
        }
    except Exception as exc:
        logger.warning("Failed to collect local usage: %s", exc)
        return {
            "token_count": 0,
            "conversation_count": 0,
            "message_count": 0,
            "kb_count": 0,
            "doc_count": 0,
        }


async def _collect_detailed_usage() -> dict:
    """Collect detailed usage breakdown for cloud sync."""
    try:
        from app.database import async_session
        from sqlalchemy import select, func
        from app.models.chat_history import ChatConversation
        from app.models.model_config import ModelConfig

        async with async_session() as db:
            rows = (await db.execute(
                select(
                    ChatConversation.llm_model_id,
                    func.count(ChatConversation.id).label("conversations"),
                    func.coalesce(func.sum(ChatConversation.total_input_tokens), 0).label("input_tokens"),
                    func.coalesce(func.sum(ChatConversation.total_output_tokens), 0).label("output_tokens"),
                ).group_by(ChatConversation.llm_model_id)
            )).all()

            model_ids = [r.llm_model_id for r in rows if r.llm_model_id]
            model_names: dict[int, str] = {}
            if model_ids:
                for m in (await db.execute(
                    select(ModelConfig.id, ModelConfig.display_name).where(ModelConfig.id.in_(model_ids))
                )).all():
                    model_names[m.id] = m.display_name

            by_model = [
                {
                    "model_name": model_names.get(r.llm_model_id, "未知") if r.llm_model_id else "未配置",
                    "conversations": r.conversations,
                    "input_tokens": r.input_tokens,
                    "output_tokens": r.output_tokens,
                }
                for r in rows
            ]
            return {"by_model": by_model}
    except Exception as exc:
        logger.debug("Failed to collect detailed usage: %s", exc)
        return {"by_model": []}


async def user_data_sync_loop(interval_seconds: int = 3600) -> None:
    """Sync user memories, profiles, and agent configs to the central server periodically."""
    from app.config import settings as _settings
    while True:
        await asyncio.sleep(interval_seconds)
        if not is_cloud_enabled():
            continue
        if not getattr(_settings, "CLOUD_DATA_SYNC_ENABLED", False):
            continue
        token = await ensure_cloud_token()
        if not token:
            continue
        try:
            device_id = get_device_id()
            await _sync_user_data(token, device_id)
            logger.info("Cloud user data sync completed")
        except Exception as exc:
            logger.warning("Cloud user data sync failed: %s", exc)


async def _sync_user_data(token: str, device_id: str) -> None:
    """Collect and send user memories, profiles, and agent configs."""
    from app.cloud.client import cloud_sync_memories, cloud_sync_profile, cloud_sync_agents

    try:
        from app.database import async_session
        from sqlalchemy import select
        from app.models.user_memory import UserMemory
        from app.models.user_profile import UserProfile
        from app.models.agent_config import AgentConfig

        async with async_session() as db:
            # Memories
            memories_result = await db.execute(select(UserMemory))
            memories = [
                {
                    "user_id": m.user_id,
                    "content": m.content,
                    "category": m.category,
                    "source": m.source,
                    "importance": m.importance,
                    "memory_type": m.memory_type,
                    "created_at": str(m.created_at) if m.created_at else None,
                }
                for m in memories_result.scalars().all()
            ]
            if memories:
                await cloud_sync_memories(token, device_id, memories)

            # Profiles
            profiles_result = await db.execute(select(UserProfile))
            for p in profiles_result.scalars().all():
                profile = {
                    "user_id": p.user_id,
                    "profile_summary": p.profile_summary,
                    "topics_of_interest": p.topics_of_interest,
                    "communication_style": p.communication_style,
                    "expertise_areas": p.expertise_areas,
                }
                await cloud_sync_profile(token, device_id, profile)

            # Agent configs
            agents_result = await db.execute(select(AgentConfig))
            agents = [
                {
                    "user_id": a.user_id,
                    "name": a.name,
                    "description": a.description,
                    "system_prompt": a.system_prompt,
                    "kb_ids": a.kb_ids,
                    "is_active": a.is_active,
                    "created_at": str(a.created_at) if a.created_at else None,
                }
                for a in agents_result.scalars().all()
            ]
            if agents:
                await cloud_sync_agents(token, device_id, agents)

    except Exception as exc:
        logger.warning("Failed to collect user data for sync: %s", exc)


async def user_status_check_loop(interval_seconds: int = 300) -> None:
    """Periodically validate user session with the central server.

    Detects: banned users, role changes, session expiration.
    """
    while True:
        await asyncio.sleep(interval_seconds)
        if not is_cloud_enabled():
            continue
        token = await ensure_cloud_token()
        if not token:
            continue
        try:
            from app.cloud.client import cloud_get_me
            cloud_user = await cloud_get_me(token)
            if not cloud_user:
                continue

            is_active = cloud_user.get("is_active", True)
            if not is_active:
                logger.warning("用户已被服务器禁用，清除本地会话")
                clear_cloud_tokens()
                await _deactivate_local_user(cloud_user.get("username"))
                continue

            await _sync_user_role(cloud_user)
            logger.debug("User status check passed: %s", cloud_user.get("username"))
        except Exception as exc:
            logger.debug("User status check failed: %s", exc)


async def _deactivate_local_user(username: str | None) -> None:
    if not username:
        return
    try:
        from app.database import async_session
        from sqlalchemy import select
        from app.models.user import User
        async with async_session() as db:
            result = await db.execute(select(User).where(User.username == username))
            user = result.scalar_one_or_none()
            if user:
                user.is_active = False
                await db.commit()
                logger.info("Local user deactivated: %s", username)
    except Exception as exc:
        logger.warning("Failed to deactivate local user: %s", exc)


async def _sync_user_role(cloud_user: dict) -> None:
    username = cloud_user.get("username")
    cloud_role = cloud_user.get("role")
    if not username or not cloud_role:
        return
    try:
        from app.database import async_session
        from sqlalchemy import select
        from app.models.user import User
        async with async_session() as db:
            result = await db.execute(select(User).where(User.username == username))
            user = result.scalar_one_or_none()
            if user:
                current_role = user.role.value if hasattr(user.role, "value") else str(user.role)
                from app.models.user import UserRole
                expected_role = UserRole.ADMIN if cloud_role in ("admin", "super_admin", "org_admin") else UserRole.USER
                if current_role != expected_role.value:
                    user.role = expected_role
                    await db.commit()
                    logger.info("User role synced: %s → %s", username, cloud_role)
    except Exception as exc:
        logger.warning("Failed to sync user role: %s", exc)


async def notification_check_loop(interval_seconds: int = 600) -> None:
    """Pull notifications from the central server periodically."""
    while True:
        await asyncio.sleep(interval_seconds)
        if not is_cloud_enabled():
            continue
        token = await ensure_cloud_token()
        if not token:
            continue
        try:
            from app.cloud.client import cloud_get_notifications
            notifications = await cloud_get_notifications(token)
            if notifications:
                logger.info("Received %d notifications from server", len(notifications))
                await _store_notifications(notifications)
        except Exception as exc:
            logger.debug("Notification check failed: %s", exc)


async def _store_notifications(notifications: list) -> None:
    """Store server notifications locally for frontend display."""
    try:
        path = _get_data_dir() / ".notifications"
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = []
        if path.exists():
            try:
                existing = _json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.debug("Failed to parse notifications file: %s", exc)
                existing = []
        existing_ids = {n.get("id") for n in existing if isinstance(n, dict)}
        for n in notifications:
            if isinstance(n, dict) and n.get("id") not in existing_ids:
                existing.append(n)
        existing = existing[-100:]
        path.write_text(_json.dumps(existing, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed to store notifications: %s", exc)


async def model_sync_loop(interval_seconds: int = 3600) -> None:
    """Sync shared model configs from the central server periodically."""
    first_run = True
    while True:
        if first_run:
            await asyncio.sleep(15)
            first_run = False
        else:
            await asyncio.sleep(interval_seconds)
        if not is_cloud_enabled():
            continue
        token = await ensure_cloud_token()
        if not token:
            continue
        try:
            await do_model_sync(token)
        except Exception as exc:
            logger.debug("Model sync failed: %s", exc)
        try:
            await do_agent_mcp_sync(token)
        except Exception as exc:
            logger.debug("Agent/MCP sync failed: %s", exc)


async def do_model_sync(token: str | None = None) -> int:
    """Execute a single model sync cycle. Returns count of synced models.

    Can be called from the periodic loop or triggered on demand (e.g. after login).
    """
    if token is None:
        token = await ensure_cloud_token()
    if not token:
        return 0
    from app.cloud.client import cloud_get_shared_models
    shared_models = await cloud_get_shared_models(token)
    if shared_models:
        _cache_server_platform_models(shared_models)
        await _apply_shared_models(shared_models)
        logger.info("Synced %d shared models from server", len(shared_models))
    return len(shared_models) if shared_models else 0


async def do_agent_mcp_sync(token: str | None = None) -> int:
    """Sync shared Agent and MCP server configs from the central server."""
    if token is None:
        token = await ensure_cloud_token()
    if not token:
        return 0

    synced = 0

    try:
        from app.cloud.client import cloud_get_shared_agents
        from app.database import async_session
        from sqlalchemy import select
        from app.models.agent_config import AgentConfig

        shared_agents = await cloud_get_shared_agents(token)
        if shared_agents:
            async with async_session() as db:
                # Get user_id=1 (desktop default user)
                existing = (await db.execute(
                    select(AgentConfig).where(AgentConfig.user_id == 1)
                )).scalars().all()
                existing_names = {a.name for a in existing}

                for spec in shared_agents:
                    if spec.get("name") in existing_names:
                        continue
                    db.add(AgentConfig(
                        user_id=1,
                        name=spec["name"],
                        description=spec.get("description", ""),
                        kb_ids=spec.get("kb_ids", "[]"),
                        system_prompt=spec.get("system_prompt", ""),
                        is_active=spec.get("is_active", True),
                    ))
                    synced += 1
                if synced:
                    await db.commit()
                    logger.info("Synced %d shared agents from server", synced)
    except Exception as exc:
        logger.debug("Agent sync failed: %s", exc)

    try:
        from app.cloud.client import cloud_get_shared_mcp_servers
        from app.database import async_session
        from sqlalchemy import select
        from app.models.mcp_server import McpServerConfig

        shared_mcp = await cloud_get_shared_mcp_servers(token)
        if shared_mcp:
            async with async_session() as db:
                existing = (await db.execute(
                    select(McpServerConfig).where(McpServerConfig.user_id == 1)
                )).scalars().all()
                existing_names = {m.name for m in existing}

                mcp_synced = 0
                for spec in shared_mcp:
                    if spec.get("name") in existing_names:
                        continue
                    db.add(McpServerConfig(
                        user_id=1,
                        name=spec["name"],
                        transport_type=spec.get("transport_type", "http"),
                        command=spec.get("command"),
                        args=spec.get("args"),
                        env=spec.get("env"),
                        url=spec.get("url"),
                        headers=spec.get("headers"),
                        tool_filter=spec.get("tool_filter"),
                        is_active=spec.get("is_active", False),
                    ))
                    mcp_synced += 1
                if mcp_synced:
                    await db.commit()
                    synced += mcp_synced
                    logger.info("Synced %d shared MCP servers from server", mcp_synced)
    except Exception as exc:
        logger.debug("MCP sync failed: %s", exc)

    return synced


_SERVER_PLATFORM_CACHE = ".server_platform_models"


def _cache_server_platform_models(models: list) -> None:
    """Cache server shared models to a local file for platform_model_service."""
    try:
        path = _get_data_dir() / _SERVER_PLATFORM_CACHE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_json.dumps(models, ensure_ascii=False), encoding="utf-8")
        logger.debug("Cached %d server platform models", len(models))
    except Exception as exc:
        logger.warning("Failed to cache server platform models: %s", exc)


def get_cached_server_platform_models() -> list:
    """Read cached server platform models. Used by platform_model_service."""
    try:
        path = _get_data_dir() / _SERVER_PLATFORM_CACHE
        if path.exists():
            return _json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.debug("Failed to read server platform model cache: %s", exc)
    return []


async def _apply_shared_models(models: list) -> None:
    """Update API keys for existing platform models from server sync.

    New per-user model creation is handled by platform_model_service.ensure_platform_models
    (triggered on demand when users access the model list). This function only updates
    API keys and display names on models that already carry the __platform__ tag.
    """
    try:
        from app.database import async_session
        from sqlalchemy import select
        from app.models.model_config import ModelConfig
        from app.core.encryption import encrypt_value
        from app.config import settings

        _PLATFORM_TAG = "__platform__"

        async with async_session() as db:
            platform_models = (await db.execute(
                select(ModelConfig).where(
                    ModelConfig.params.contains(_PLATFORM_TAG),
                )
            )).scalars().all()

            if not platform_models:
                return

            server_lookup = {
                (m.get("model_name", ""), m.get("api_base", "")): m
                for m in models
            }

            updated = 0
            for existing in platform_models:
                key = (existing.model_name, existing.api_base)
                server_model = server_lookup.get(key)
                if not server_model:
                    continue
                api_key = server_model.get("api_key", "")
                if api_key:
                    existing.api_key_encrypted = encrypt_value(api_key, settings.SECRET_KEY)
                    updated += 1
                display = server_model.get("display_name")
                if display:
                    existing.display_name = display

            if updated:
                await db.commit()
                logger.info("Updated API keys for %d platform models", updated)
    except Exception as exc:
        logger.warning("Failed to apply shared models: %s", exc)


async def detect_and_report_ip() -> None:
    """Detect client's public IP and include it in heartbeat."""
    try:
        from app.cloud.client import detect_client_ip
        ip = await detect_client_ip()
        if ip:
            path = _get_data_dir() / ".client_ip"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(ip, encoding="utf-8")
            logger.info("Client public IP detected: %s", ip)
    except Exception as exc:
        logger.debug("Failed to cache client IP: %s", exc)


def get_cached_client_ip() -> str | None:
    try:
        path = _get_data_dir() / ".client_ip"
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    except Exception as exc:
        logger.debug("Failed to read cached client IP: %s", exc)
    return None


_op_log_last_synced_id: int = 0
_op_log_sync_lock = asyncio.Lock()


async def operation_log_sync_loop(interval_seconds: int = 60) -> None:
    """Sync local OperationLogs to the central server periodically (backup sync)."""
    global _op_log_last_synced_id
    from app.config import settings as _settings
    _op_log_last_synced_id = await _load_last_synced_log_id()
    while True:
        await asyncio.sleep(interval_seconds)
        await _do_operation_log_sync()


async def trigger_operation_log_sync() -> None:
    """Trigger an immediate operation log sync (called after key operations)."""
    asyncio.ensure_future(_do_operation_log_sync())


async def _do_operation_log_sync() -> None:
    """Perform actual operation log sync to server.

    Sends logs in batches of 200 until all pending logs are transmitted.
    """
    global _op_log_last_synced_id
    if not is_cloud_enabled():
        return
    from app.config import settings as _settings
    if not getattr(_settings, "CLOUD_USAGE_REPORT_ENABLED", True):
        return
    token = await ensure_cloud_token()
    if not token:
        return
    async with _op_log_sync_lock:
        try:
            device_id = get_device_id()
            total_synced = 0
            while True:
                logs, new_max_id = await _collect_operation_logs(_op_log_last_synced_id)
                if not logs:
                    break
                await cloud_submit_operation_logs(token, device_id, logs)
                _op_log_last_synced_id = new_max_id
                await _save_last_synced_log_id(new_max_id)
                total_synced += len(logs)
                if len(logs) < 200:
                    break
            if total_synced:
                logger.info("Synced %d operation logs to cloud (up to id=%d)", total_synced, _op_log_last_synced_id)
        except Exception as exc:
            logger.warning("Operation log sync failed: %s", exc)


async def _collect_operation_logs(since_id: int, batch_size: int = 200) -> tuple[list[dict], int]:
    """Collect unsynchronized OperationLogs since a given ID."""
    try:
        from app.database import async_session
        from sqlalchemy import select
        from app.models.operation_log import OperationLog

        async with async_session() as db:
            result = await db.execute(
                select(OperationLog)
                .where(OperationLog.id > since_id)
                .order_by(OperationLog.id.asc())
                .limit(batch_size)
            )
            rows = result.scalars().all()
            if not rows:
                return [], since_id

            logs = [
                {
                    "local_id": r.id,
                    "user_id": r.user_id,
                    "action": r.action,
                    "resource_type": r.resource_type,
                    "resource_id": r.resource_id,
                    "detail": r.detail,
                    "ip_address": r.ip_address,
                    "prompt_tokens": r.prompt_tokens or 0,
                    "completion_tokens": r.completion_tokens or 0,
                    "total_tokens": r.total_tokens or 0,
                    "latency_ms": r.latency_ms or 0,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]
            return logs, rows[-1].id
    except Exception as exc:
        logger.warning("Failed to collect operation logs: %s", exc)
        return [], since_id


async def _load_last_synced_log_id() -> int:
    try:
        path = _get_data_dir() / ".last_synced_log_id"
        if path.exists():
            return int(path.read_text(encoding="utf-8").strip())
    except Exception as exc:
        logger.debug("Failed to load last synced log id: %s", exc)
    return 0


async def _save_last_synced_log_id(log_id: int) -> None:
    try:
        path = _get_data_dir() / ".last_synced_log_id"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(log_id), encoding="utf-8")
    except Exception as exc:
        logger.debug("Failed to save last synced log id: %s", exc)


def _get_app_version() -> str:
    try:
        from app.config import settings
        from app._version import __version__
        return getattr(settings, "APP_VERSION", __version__)
    except Exception as exc:
        logger.debug("Failed to get app version from settings: %s", exc)
        from app._version import __version__
        return __version__
