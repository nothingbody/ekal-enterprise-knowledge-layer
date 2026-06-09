import logging

from fastapi import FastAPI
from sqlalchemy import select, func

from app.config import settings
from app._version import __version__
from app.database import async_session
from app.models.user import User
from app.api import (
    auth, users, organizations, devices, stats, skills, admin,
    model_configs, knowledge_bases, chat, workspaces, notifications,
    system, releases, site_content, relay,
)


logger = logging.getLogger("central_server")

API_V1 = "/api/v1"


def register_api_routes(app: FastAPI) -> None:
    app.include_router(auth.router, prefix=f"{API_V1}/auth", tags=["认证"])
    app.include_router(users.router, prefix=f"{API_V1}/users", tags=["用户管理"])
    app.include_router(organizations.router, prefix=f"{API_V1}/organizations", tags=["组织管理"])
    app.include_router(devices.router, prefix=f"{API_V1}/devices", tags=["设备管理"])
    app.include_router(stats.router, prefix=f"{API_V1}/stats", tags=["用量统计"])
    app.include_router(skills.router, prefix=f"{API_V1}/skills", tags=["技能市场"])
    app.include_router(admin.router, prefix=f"{API_V1}/admin", tags=["管理后台"])
    app.include_router(model_configs.router, prefix=f"{API_V1}/models", tags=["模型管理"])
    app.include_router(knowledge_bases.router, prefix=f"{API_V1}/knowledge-bases", tags=["知识库"])
    app.include_router(chat.router, prefix=f"{API_V1}/chat", tags=["对话"])
    app.include_router(workspaces.router, prefix=f"{API_V1}/workspaces", tags=["工作空间"])
    app.include_router(relay.router, prefix=f"{API_V1}/relay", tags=["远程知识库转发"])
    app.include_router(notifications.router, prefix=f"{API_V1}/notifications", tags=["通知"])
    app.include_router(system.router, prefix=f"{API_V1}/system", tags=["系统管理"])
    app.include_router(releases.router, prefix=f"{API_V1}/releases", tags=["版本管理"])
    app.include_router(site_content.router, prefix=f"{API_V1}/site", tags=["官网内容"])


def register_health_endpoint(app: FastAPI) -> None:
    @app.get(f"{API_V1}/health")
    async def health():
        checks: dict = {"database": "unknown", "redis": "unknown"}
        overall = "ok"

        try:
            async with async_session() as db:
                await db.execute(select(func.count(User.id)))
            checks["database"] = "ok"
        except Exception as exc:
            logger.warning("Health DB check failed: %s", exc, exc_info=True)
            checks["database"] = "error"
            overall = "degraded"

        try:
            from redis.asyncio import from_url as redis_from_url
            r = redis_from_url(settings.REDIS_URL, socket_connect_timeout=2)
            await r.ping()
            await r.aclose()
            checks["redis"] = "ok"
        except Exception:
            checks["redis"] = "unavailable"

        return {
            "status": overall,
            "service": settings.APP_NAME,
            "version": __version__,
            "api_version": "v1",
            "checks": checks,
        }
