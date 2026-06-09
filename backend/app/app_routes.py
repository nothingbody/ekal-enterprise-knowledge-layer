import asyncio
import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app._version import __version__
from app.api import auth, users, knowledge_bases, documents, chat, models, system, published_apps, web_sources, workspaces, kb_transfer, api_keys, database_sources, memories, channels, mcp_servers, skills, automations, agents, diagnostics, tts, prompt_templates, quota, analytics, knowledge_compilation, trajectories, remote_relay
from app.config import settings
from app.database import engine

logger = logging.getLogger("rag_platform")


API_V1 = "/api/v1"


def register_api_routes(app: FastAPI) -> None:
    app.include_router(auth.router, prefix=f"{API_V1}/auth", tags=["认证"])
    app.include_router(users.router, prefix=f"{API_V1}/users", tags=["用户管理"])
    app.include_router(models.router, prefix=f"{API_V1}/models", tags=["模型管理"])
    app.include_router(knowledge_bases.router, prefix=f"{API_V1}/knowledge-bases", tags=["知识库"])
    app.include_router(documents.router, prefix=f"{API_V1}/documents", tags=["文档管理"])
    app.include_router(chat.router, prefix=f"{API_V1}/chat", tags=["智能对话"])
    app.include_router(system.router, prefix=f"{API_V1}/system", tags=["系统管理"])
    app.include_router(published_apps.router, prefix=f"{API_V1}/apps", tags=["应用发布"])
    app.include_router(web_sources.router, prefix=f"{API_V1}/web-sources", tags=["Web数据源"])
    app.include_router(database_sources.router, prefix=f"{API_V1}/database-sources", tags=["数据库数据源"])
    app.include_router(workspaces.router, prefix=f"{API_V1}/workspaces", tags=["工作空间"])
    app.include_router(workspaces.invitation_router, prefix=API_V1, tags=["工作空间邀请"])
    app.include_router(remote_relay.router, prefix=f"{API_V1}/relay", tags=["远程知识库转发"])
    app.include_router(kb_transfer.router, prefix=f"{API_V1}/kb-transfer", tags=["知识库导入导出"])
    app.include_router(api_keys.router, prefix=f"{API_V1}/api-keys", tags=["API Key 管理"])
    app.include_router(memories.router, prefix=f"{API_V1}/memories", tags=["用户记忆"])
    app.include_router(channels.router, prefix=f"{API_V1}/channels", tags=["渠道管理"])
    app.include_router(channels.webhook_router, prefix=API_V1, tags=["渠道 Webhook"])
    app.include_router(mcp_servers.router, prefix=f"{API_V1}/mcp-servers", tags=["MCP 服务器"])
    app.include_router(skills.router, prefix=f"{API_V1}/skills", tags=["技能市场"])
    app.include_router(automations.router, prefix=f"{API_V1}/automations", tags=["自动化任务"])
    app.include_router(automations.webhook_router, prefix=API_V1, tags=["自动化 Webhook"])
    app.include_router(agents.router, prefix=f"{API_V1}/agents", tags=["多Agent协作"])
    app.include_router(diagnostics.router, prefix=f"{API_V1}/diagnostics", tags=["系统诊断"])
    app.include_router(tts.router, prefix=f"{API_V1}/tts", tags=["语音合成"])
    app.include_router(prompt_templates.router, prefix=f"{API_V1}/prompt-templates", tags=["输出模板"])
    app.include_router(quota.router, prefix=f"{API_V1}/quota", tags=["用量配额"])
    app.include_router(analytics.router, prefix=API_V1, tags=["运营分析"])
    app.include_router(knowledge_compilation.router, prefix=f"{API_V1}/knowledge-compilation", tags=["知识编译"])
    app.include_router(trajectories.router, prefix=f"{API_V1}/trajectories", tags=["轨迹分析"])


def register_system_endpoints(app: FastAPI) -> None:
    @app.get(f"{API_V1}/shutdown")
    @app.get("/api/shutdown", include_in_schema=False)
    async def shutdown(request: Request):
        if not getattr(settings, "DESKTOP_MODE", False):
            return JSONResponse({"detail": "Only available in desktop mode"}, status_code=403)
        expected = (os.environ.get("SHUTDOWN_SECRET") or "").strip()
        provided = (request.headers.get("x-shutdown-token") or request.query_params.get("token") or "").strip()
        if not expected or not provided or provided != expected:
            return JSONResponse({"detail": "Unauthorized"}, status_code=403)
        import signal
        logger.info("Received shutdown request, stopping server...")

        async def _do_shutdown():
            await asyncio.sleep(0.5)
            os.kill(os.getpid(), signal.SIGTERM)

        asyncio.ensure_future(_do_shutdown())
        return {"status": "shutting_down"}

    @app.get(f"{API_V1}/health")
    @app.get("/api/health", include_in_schema=False)
    async def health_check():
        checks = {"app": settings.APP_NAME, "version": __version__}
        overall = True

        try:
            async with engine.connect() as conn:
                from sqlalchemy import text
                await conn.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as exc:
            logger.warning("Health DB check failed: %s", exc, exc_info=True)
            checks["database"] = "error"
            overall = False

        if not getattr(settings, "DESKTOP_MODE", False):
            try:
                from redis.asyncio import from_url as redis_async_from_url
                r = redis_async_from_url(settings.REDIS_URL, socket_connect_timeout=0.5)
                await r.ping()
                await r.aclose()
                checks["redis"] = "ok"
            except Exception as exc:
                logger.warning("Health Redis check failed: %s", exc, exc_info=True)
                checks["redis"] = "unavailable"

            try:
                if settings.CHROMA_MODE == "client":
                    import httpx
                    resp = httpx.get(f"http://{settings.CHROMA_HOST}:{settings.CHROMA_PORT}/api/v1/heartbeat", timeout=3)
                    checks["chromadb"] = "ok" if resp.status_code == 200 else "degraded"
                else:
                    checks["chromadb"] = "embedded"
            except Exception as exc:
                logger.warning("Health ChromaDB check failed: %s", exc, exc_info=True)
                checks["chromadb"] = "error"

            try:
                from app.celery_app import celery as celery_app
                inspect = celery_app.control.inspect(timeout=1.0)
                ping_result = await asyncio.to_thread(inspect.ping)
                if ping_result:
                    worker_count = len(ping_result)
                    checks["celery"] = f"ok ({worker_count} worker{'s' if worker_count > 1 else ''})"
                else:
                    checks["celery"] = "no workers"
            except Exception as exc:
                logger.warning("Health Celery check failed: %s", exc, exc_info=True)
                checks["celery"] = "unavailable"
        else:
            checks["mode"] = "desktop"
            checks["chromadb"] = "embedded"

        bg_tasks: list[asyncio.Task] = getattr(app.state, "bg_tasks", [])
        if bg_tasks:
            scheduler_info = {}
            for t in bg_tasks:
                label = t.get_name() if t.get_name() else "unknown"
                if t.done():
                    scheduler_info[label] = "stopped"
                    overall = False
                else:
                    scheduler_info[label] = "running"
            checks["schedulers"] = scheduler_info

        checks["status"] = "ok" if overall else "degraded"
        return checks


def _resolve_frontend_dist() -> Path:
    env_dir = os.environ.get("FRONTEND_DIST_DIR")
    if env_dir:
        return Path(env_dir)
    import sys
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidate = exe_dir.parent / "frontend" / "dist"
        if candidate.is_dir():
            return candidate
    if getattr(sys, "_MEIPASS", None):
        return Path(sys._MEIPASS).parent / "frontend" / "dist"
    return Path(__file__).parent.parent.parent / "frontend" / "dist"


def register_desktop_frontend(app: FastAPI) -> None:
    frontend_dist = _resolve_frontend_dist()
    if settings.DESKTOP_MODE:
        if frontend_dist.is_dir():
            logger.info("前端静态文件目录: %s", frontend_dist)
        else:
            logger.error("前端静态文件目录不存在: %s — 页面将无法加载（白屏）", frontend_dist)
    if settings.DESKTOP_MODE and frontend_dist.is_dir():
        app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="static-assets")

        @app.get("/{full_path:path}")
        async def serve_spa(request: Request, full_path: str):
            if full_path.startswith("api/"):
                return JSONResponse(status_code=404, content={"detail": "Not found"})
            file_path = (frontend_dist / full_path).resolve()
            frontend_root = frontend_dist.resolve()
            if full_path and file_path.is_file() and str(file_path).startswith(str(frontend_root)):
                return FileResponse(str(file_path))
            return FileResponse(str(frontend_dist / "index.html"))
