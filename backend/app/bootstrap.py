import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.database import engine, Base
import app.models


logger = logging.getLogger("rag_platform")


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        import json as _json
        entry = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if hasattr(record, "request_id"):
            entry["request_id"] = record.request_id
        if record.exc_info and record.exc_info[1]:
            entry["exception"] = self.formatException(record.exc_info)
        return _json.dumps(entry, ensure_ascii=False)


def setup_logging():
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    use_json = not settings.DEBUG and not settings.DESKTOP_MODE

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    handler = logging.StreamHandler()
    if use_json:
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
    root.addHandler(handler)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    if not settings.DEBUG:
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


async def _migrate_legacy_plaintext_keys(db) -> None:
    import hashlib
    from sqlalchemy import select
    from app.models.api_key import ApiKey
    from app.models.published_app import PublishedApp

    result = await db.execute(
        select(ApiKey).where(ApiKey.key.isnot(None), ApiKey.key != "")
    )
    legacy_keys = result.scalars().all()
    for k in legacy_keys:
        if k.key and not k.key_hash:
            k.key_hash = hashlib.sha256(k.key.encode()).hexdigest()
            k.key_preview = k.key[:8] + "..." + k.key[-4:] if len(k.key) > 12 else "***"
        k.key = None
    if legacy_keys:
        await db.commit()
        logger.info("已迁移 %d 个 ApiKey 明文密钥为哈希值", len(legacy_keys))

    result2 = await db.execute(
        select(PublishedApp).where(PublishedApp.api_key.isnot(None), PublishedApp.api_key != "")
    )
    legacy_apps = result2.scalars().all()
    for app_obj in legacy_apps:
        if app_obj.api_key and not app_obj.api_key_hash:
            app_obj.api_key_hash = hashlib.sha256(app_obj.api_key.encode()).hexdigest()
        app_obj.api_key = None
    if legacy_apps:
        await db.commit()
        logger.info("已迁移 %d 个 PublishedApp 明文密钥为哈希值", len(legacy_apps))


async def initialize_database() -> None:
    attempts = max(1, settings.DB_STARTUP_MAX_RETRIES)
    for attempt in range(1, attempts + 1):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                if not settings.DATABASE_URL.startswith("sqlite"):
                    from sqlalchemy import inspect as sa_inspect, text
                    has_cloud_user_id = await conn.run_sync(
                        lambda sync_conn: "cloud_user_id" in [
                            c["name"] for c in sa_inspect(sync_conn).get_columns("users")
                        ]
                    )
                    if not has_cloud_user_id:
                        await conn.execute(text("ALTER TABLE users ADD COLUMN cloud_user_id INTEGER"))
                        await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_cloud_user_id ON users (cloud_user_id)"))
            return
        except Exception:
            if attempt >= attempts:
                raise
            logger.warning(
                "数据库初始化失败（%s/%s），将在 %.1f 秒后重试",
                attempt,
                attempts,
                settings.DB_STARTUP_RETRY_SECONDS,
            )
            await asyncio.sleep(settings.DB_STARTUP_RETRY_SECONDS)


def validate_production_config(is_production: bool) -> None:
    if "change" in settings.SECRET_KEY:
        if is_production:
            raise RuntimeError(
                "SECRET_KEY 包含默认值，生产环境禁止使用！"
                "请运行 python -c \"import secrets; print(secrets.token_urlsafe(64))\" 生成密钥并写入 .env 文件。"
            )
        logger.warning("⚠ SECRET_KEY 未修改，请在生产环境中设置强随机密钥！")
    if is_production and settings.DATABASE_URL.startswith("sqlite"):
        raise RuntimeError(
            "生产环境禁止使用 SQLite！SQLite 不支持并发写入，会导致数据库锁表。"
            "请在 .env 中配置 PostgreSQL: DATABASE_URL=postgresql+asyncpg://user:pass@host/dbname"
        )


async def bootstrap_admin() -> None:
    try:
        from app.database import async_session as _user_session
        from app.services.auth_service import ensure_desktop_default_admin
        async with _user_session() as db:
            bootstrap_admin_user = await ensure_desktop_default_admin(db)
            if bootstrap_admin_user is not None:
                logger.info("已初始化默认管理员账号: %s", bootstrap_admin_user.username)
    except Exception as exc:
        logger.warning("默认管理员初始化失败: %s", exc)


async def migrate_keys() -> None:
    try:
        from app.database import async_session as _key_session
        async with _key_session() as db:
            await _migrate_legacy_plaintext_keys(db)
    except Exception as exc:
        logger.warning("明文 API Key 迁移失败: %s", exc)


async def recover_stale_sources() -> None:
    try:
        from app.database import async_session
        from app.services.database_source_service import recover_stale_syncing_sources
        async with async_session() as db:
            await recover_stale_syncing_sources(db)
    except Exception as exc:
        logger.warning("同步卡死恢复失败: %s", exc)


async def recover_stuck_documents() -> None:
    try:
        from sqlalchemy import select, update as sa_update
        from app.database import async_session as _doc_session
        from app.models.document import Document, DocumentStatus
        from app.tasks.document_tasks import process_document_task
        from app.core.task_runner import dispatch as dispatch_task
        async with _doc_session() as db:
            stuck = (await db.execute(
                select(Document).where(
                    Document.status.in_([
                        DocumentStatus.UPLOADING,
                        DocumentStatus.PARSING,
                        DocumentStatus.EMBEDDING,
                    ])
                )
            )).scalars().all()
            if stuck:
                logger.info("发现 %d 个卡住的文档，重新提交处理任务", len(stuck))
                for doc in stuck:
                    await db.execute(
                        sa_update(Document).where(Document.id == doc.id)
                        .values(status=DocumentStatus.UPLOADING, error_message=None, chunk_count=0)
                    )
                await db.commit()
                for doc in stuck:
                    dispatch_task(process_document_task, doc.id, doc.kb_id)
    except Exception as exc:
        logger.warning("文档卡死恢复失败: %s", exc)


def probe_redis(is_production: bool) -> None:
    if settings.DESKTOP_MODE:
        return
    try:
        import redis as redis_lib
        r = redis_lib.from_url(settings.REDIS_URL, socket_connect_timeout=0.5)
        r.ping()
        r.close()
        redis_ok = True
    except Exception:
        redis_ok = False
    if not redis_ok and is_production:
        logger.error(
            "⚠ Redis 不可用！生产环境下多 Worker 模式的 Token 黑名单将无法跨进程同步，"
            "已吊销的 Token 可能在其他 Worker 上仍然有效。请确保 Redis 可用: %s",
            settings.REDIS_URL,
        )


async def seed_models() -> None:
    try:
        from app.database import async_session as _model_session
        from app.services.model_seed import seed_default_models
        async with _model_session() as db:
            await seed_default_models(db)
    except Exception as exc:
        logger.warning("预置模型配置失败: %s", exc)


async def seed_default_kb() -> None:
    try:
        from app.database import async_session as _kb_session
        from app.services.model_seed import seed_default_knowledge_base
        async with _kb_session() as db:
            await seed_default_knowledge_base(db)
    except Exception as exc:
        logger.warning("预置知识库创建失败: %s", exc)


async def seed_prompt_templates() -> None:
    try:
        from app.database import async_session as _pt_session
        from app.services.prompt_template_service import seed_builtin_templates
        async with _pt_session() as db:
            await seed_builtin_templates(db)
    except Exception as exc:
        logger.warning("内置模板初始化失败: %s", exc)


async def seed_skills() -> None:
    try:
        from app.database import async_session as _skill_session
        from app.services.skill_service import seed_builtin_skills
        async with _skill_session() as db:
            await seed_builtin_skills(db)
    except Exception as exc:
        logger.warning("内置技能 seed 失败: %s", exc)


async def init_mcp_connections() -> None:
    try:
        from sqlalchemy import select
        from app.core.mcp_client import get_mcp_manager
        from app.database import async_session as _mcp_session
        from app.models.mcp_server import McpServerConfig
        manager = get_mcp_manager()
        async with _mcp_session() as db:
            result = await db.execute(
                select(McpServerConfig).where(McpServerConfig.is_active == True)
            )
            for cfg in result.scalars().all():
                try:
                    await manager.connect(cfg)
                except Exception as exc:
                    logger.warning("MCP 服务器 [%s] 启动连接失败: %s", cfg.name, exc)
    except Exception as exc:
        logger.warning("MCP 初始化失败: %s", exc)


def setup_metrics(app: FastAPI) -> None:
    try:
        from app.core.metrics import setup_instrumentator
        setup_instrumentator(app)
    except Exception as exc:
        logger.warning("Prometheus 指标初始化失败: %s", exc)


async def _resilient_loop(coro_factory, name: str, restart_delay: float = 5.0):
    while True:
        try:
            await coro_factory()
            return
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("后台任务 [%s] 异常退出，%ds 后自动重启", name, restart_delay)
            await asyncio.sleep(restart_delay)
            restart_delay = min(restart_delay * 2, 300)


async def _acquire_scheduler_lock() -> bool:
    if settings.DESKTOP_MODE:
        return True
    try:
        from redis.asyncio import from_url as redis_async_from_url
        r = redis_async_from_url(settings.REDIS_URL, socket_connect_timeout=0.5)
        acquired = await r.set("rag:scheduler_leader", os.getpid(), nx=True, ex=120)
        if acquired:
            _renewal = asyncio.create_task(_renew_scheduler_lock(r))
            _renewal.set_name("bg:scheduler_lock_renewal")
            # Store for shutdown tracking (will be added to bg_tasks via app.state)
            _acquire_scheduler_lock._renewal_task = _renewal
            logger.info("✓ 本 Worker (pid=%d) 获得后台调度器 Leader 锁", os.getpid())
            return True
        leader_pid = await r.get("rag:scheduler_leader")
        logger.info("后台调度器由 Worker pid=%s 运行，本 Worker 跳过", leader_pid)
        await r.aclose()
        return False
    except Exception:
        logger.warning("Redis 不可用，默认启动后台调度器（单 Worker 模式）")
        return True


async def _renew_scheduler_lock(redis_client):
    """Periodically renew the scheduler leader lock. Logs errors instead of crashing silently."""
    try:
        while True:
            await asyncio.sleep(60)
            try:
                await redis_client.set("rag:scheduler_leader", os.getpid(), ex=120)
            except Exception:
                logger.warning(
                    "调度器锁续期失败 (pid=%d)，锁可能在 120s 后过期导致多 Worker 同时调度",
                    os.getpid(),
                )
    except asyncio.CancelledError:
        try:
            await redis_client.delete("rag:scheduler_leader")
            await redis_client.aclose()
        except Exception:
            pass


def start_background_tasks() -> list[asyncio.Task]:
    tasks: list[asyncio.Task] = []

    try:
        from app.services.web_crawl_scheduler import run_scheduler_loop
        tasks.append(asyncio.create_task(
            _resilient_loop(run_scheduler_loop, "web_crawl_scheduler"),
            name="bg:web_crawl_scheduler",
        ))
        logger.info("✓ Web 定时抓取调度器已启动")
    except Exception as exc:
        logger.warning("Web 定时抓取调度器启动失败: %s", exc)

    try:
        from app.services.automation_service import run_automation_scheduler_loop
        tasks.append(asyncio.create_task(
            _resilient_loop(run_automation_scheduler_loop, "automation_scheduler"),
            name="bg:automation_scheduler",
        ))
        logger.info("✓ 自动化任务调度器已启动")
    except Exception as exc:
        logger.warning("自动化任务调度器启动失败: %s", exc)

    try:
        from app.cloud.client import is_cloud_enabled
        if is_cloud_enabled():
            from app.cloud.sync import heartbeat_loop, usage_report_loop, user_data_sync_loop, user_status_check_loop, notification_check_loop, model_sync_loop, operation_log_sync_loop
            interval_hb = settings.CLOUD_HEARTBEAT_INTERVAL
            interval_usage = settings.CLOUD_USAGE_REPORT_INTERVAL
            tasks.append(asyncio.create_task(
                _resilient_loop(lambda: heartbeat_loop(interval_hb), "cloud_heartbeat"),
                name="bg:cloud_heartbeat",
            ))
            tasks.append(asyncio.create_task(
                _resilient_loop(lambda: usage_report_loop(interval_usage), "cloud_usage"),
                name="bg:cloud_usage",
            ))
            tasks.append(asyncio.create_task(
                _resilient_loop(lambda: user_data_sync_loop(interval_usage), "cloud_user_data"),
                name="bg:cloud_user_data",
            ))
            tasks.append(asyncio.create_task(
                _resilient_loop(lambda: user_status_check_loop(interval_hb), "cloud_user_status"),
                name="bg:cloud_user_status",
            ))
            tasks.append(asyncio.create_task(
                _resilient_loop(lambda: notification_check_loop(600), "cloud_notifications"),
                name="bg:cloud_notifications",
            ))
            tasks.append(asyncio.create_task(
                _resilient_loop(lambda: model_sync_loop(interval_usage), "cloud_model_sync"),
                name="bg:cloud_model_sync",
            ))
            tasks.append(asyncio.create_task(
                _resilient_loop(lambda: operation_log_sync_loop(interval_usage), "cloud_operation_log_sync"),
                name="bg:cloud_operation_log_sync",
            ))
            if settings.REMOTE_RELAY_ENABLED:
                from app.cloud.relay import relay_host_loop
                tasks.append(asyncio.create_task(
                    _resilient_loop(relay_host_loop, "cloud_remote_relay"),
                    name="bg:cloud_remote_relay",
                ))
            logger.info("✓ 云端同步已启动 (心跳: %ds, 用量上报: %ds, 状态检查: %ds)", interval_hb, interval_usage, interval_hb)
        else:
            logger.info("✓ 云端连接未配置，跳过")
    except Exception as exc:
        logger.warning("云端同步启动失败: %s", exc)

    return tasks


async def cancel_tasks(tasks: list[asyncio.Task]) -> None:
    for task in tasks:
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    try:
        from app.cloud.client import close_client
        await close_client()
    except Exception:
        pass
    try:
        from app.core.mcp_client import get_mcp_manager
        await get_mcp_manager().disconnect_all()
    except Exception:
        pass


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    setup_logging()
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    is_production = not settings.DEBUG and not settings.DESKTOP_MODE
    validate_production_config(is_production)

    await initialize_database()
    await bootstrap_admin()
    await seed_models()
    await seed_default_kb()
    await migrate_keys()
    await recover_stale_sources()
    await recover_stuck_documents()
    probe_redis(is_production)
    await seed_skills()
    await seed_prompt_templates()
    await init_mcp_connections()
    is_leader = await _acquire_scheduler_lock()
    bg_tasks = start_background_tasks() if is_leader else []
    # Include scheduler lock renewal task if it was created
    _renewal = getattr(_acquire_scheduler_lock, "_renewal_task", None)
    if _renewal and not _renewal.done():
        bg_tasks.append(_renewal)
    app.state.bg_tasks = bg_tasks

    logger.info("✓ %s started (debug=%s)", settings.APP_NAME, settings.DEBUG)
    yield

    await cancel_tasks(bg_tasks)
    logger.info("✓ %s shutting down", settings.APP_NAME)
