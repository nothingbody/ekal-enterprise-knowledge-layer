import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import select, func

from app.config import settings
from app._version import __version__
from app.database import engine, async_session
from app.models.base import Base
from app.models.user import User, UserRole
from app.models.system_config import SystemConfig
from app.core.security import hash_password


logger = logging.getLogger("central_server")


async def _ensure_schema_compat():
    """Add missing columns to existing PostgreSQL tables."""
    from sqlalchemy import text, inspect as sa_inspect
    _COMPAT_COLUMNS = [
        ("users", "last_login_ip", "VARCHAR(45)"),
    ]
    try:
        async with engine.begin() as conn:
            for table, column, col_type in _COMPAT_COLUMNS:
                exists = await conn.run_sync(
                    lambda sync_conn: column in [c["name"] for c in sa_inspect(sync_conn).get_columns(table)]
                )
                if not exists:
                    await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
                    logger.info("Added missing column: %s.%s", table, column)
    except Exception as e:
        logger.warning("Schema compat check failed: %s", e)


async def _ensure_super_admin():
    """Create the default super admin if no users exist."""
    async with async_session() as db:
        count = (await db.execute(select(func.count(User.id)))).scalar() or 0
        if count > 0:
            return
        admin = User(
            username="admin",
            email=settings.ADMIN_EMAIL,
            hashed_password=hash_password(settings.ADMIN_PASSWORD),
            role=UserRole.SUPER_ADMIN,
            is_active=True,
        )
        db.add(admin)
        try:
            await db.commit()
            logger.info("Default super admin created: admin / %s", settings.ADMIN_EMAIL)
        except Exception:
            await db.rollback()
            logger.info("Super admin already exists (created by another worker)")


async def _seed_site_content():
    """Populate initial website content if the table is empty."""
    from app.models.site_content import SiteContent, ContentType
    from sqlalchemy import delete as sa_delete
    async with async_session() as db:
        count = (await db.execute(select(func.count(SiteContent.id)))).scalar() or 0
        if count > 0:
            # Clean up duplicates if any (keep lowest ID for each title+type pair)
            all_rows = (await db.execute(
                select(SiteContent).order_by(SiteContent.id)
            )).scalars().all()
            seen = set()
            to_delete = []
            for row in all_rows:
                key = (row.content_type, row.title)
                if key in seen:
                    to_delete.append(row.id)
                else:
                    seen.add(key)
            if to_delete:
                await db.execute(sa_delete(SiteContent).where(SiteContent.id.in_(to_delete)))
                await db.commit()
                logger.info("Cleaned %d duplicate site_content entries", len(to_delete))
            return

        seed_data = [
            {"content_type": ContentType.CHANGELOG, "title": "MCP 协议 & 稳定性提升", "version": "v0.9.0", "sort_order": 90,
             "extra": '{"release_date":"2026-03-17"}',
             "body": "## 🚀 新功能\n- MCP 服务器管理 — 通过 UI 配置和管理 MCP 外部工具服务器\n- 数据恢复 — 支持从备份文件恢复全部数据\n- 桌面版自动更新 — 自动检测新版本并下载安装\n- 心跳信息增强 — 上报设备详细信息和使用统计\n- 用量回填 — 自动补报最近 7 天因网络故障未上报的用量数据\n\n## 🛠 改进\n- SQLite WAL 模式 — 大幅提升桌面版数据库并发读写性能\n- 串行任务队列 — 消除桌面版多线程写入冲突\n- 热备份 — 使用 SQLite backup API 代替文件复制\n- RRF 分数归一化 — 检索结果评分更直观\n- 前端字体异步加载 — 消除渲染阻塞\n\n## 🐛 修复\n- 修复 2FA 验证接口遗漏 token 函数导入的问题\n- 修复备份完成后临时文件未清理的问题"},
            {"content_type": ContentType.CHANGELOG, "title": "多 Agent 协作 & 自动化", "version": "v0.8.0", "sort_order": 80,
             "extra": '{"release_date":"2026-02-15"}',
             "body": "## 🚀 新功能\n- 多 Agent 协作 — 创建多个专业 Agent 进行跨知识库问答\n- 自动化任务 — 定时、Webhook 和事件驱动的自动化工作流\n- 技能市场 — 从云端发现和安装 Agent 技能\n- 渠道管理 — 接入企业微信、钉钉、飞书、Telegram 等平台\n- 用户记忆 — AI 自动记忆用户偏好和历史信息"},
            {"content_type": ContentType.CHANGELOG, "title": "工作空间 & 团队协作", "version": "v0.7.0", "sort_order": 70,
             "extra": '{"release_date":"2026-01-10"}',
             "body": "## 🚀 新功能\n- 工作空间 — 团队共享知识库和模型配置\n- 邀请链接 — 生成邀请链接邀请成员加入工作空间\n- 应用发布 — 将知识库发布为公开智能问答应用\n- 系统诊断 — 一键检测系统配置和连接状态"},
            {"content_type": ContentType.FAQ, "title": "知枢是免费的吗？", "sort_order": 100,
             "body": "是的，知枢完全免费。唯一的费用是 LLM API 调用费用（如 OpenAI、Claude 等），如果使用本地模型（如 Ollama）则完全免费。"},
            {"content_type": ContentType.FAQ, "title": "数据安全如何保障？", "sort_order": 90,
             "body": "知枢支持 100% 私有部署，所有数据保存在你自己的服务器或本地电脑上。API Key 加密存储，支持两步验证 (2FA)，完整的操作审计日志，JWT 令牌黑名单机制。"},
            {"content_type": ContentType.FAQ, "title": "支持哪些 AI 模型？", "sort_order": 80,
             "body": "支持所有 OpenAI 兼容接口的模型，包括 GPT-4o、Claude 4、DeepSeek-V3、通义千问等。也支持通过 Ollama 运行本地模型（如 Llama、Qwen 等），实现完全离线使用。"},
            {"content_type": ContentType.FAQ, "title": "桌面版和服务器版有什么区别？", "sort_order": 70,
             "body": "桌面版适合个人使用，一键安装开箱即用，数据保存在本地。服务器版适合团队/企业，支持多用户管理、工作空间协作、设备管理、用量统计等功能，使用 Docker Compose 部署。"},
            {"content_type": ContentType.FAQ, "title": "如何从其他平台迁移？", "sort_order": 60,
             "body": "知枢支持知识库的导入导出功能，可以将文档批量上传。对于已有的向量数据库，可以通过 API 进行数据迁移。"},
            {"content_type": ContentType.FAQ, "title": "支持多少种文档格式？", "sort_order": 50,
             "body": "支持 15+ 种格式：PDF、Word (.doc/.docx)、Excel (.xls/.xlsx)、PPT (.pptx)、Markdown、HTML、TXT、CSV、JSON、XML、Python/JS/Java 等代码文件、图片（OCR）。"},
            {"content_type": ContentType.FAQ, "title": "可以接入哪些消息渠道？", "sort_order": 40,
             "body": "目前支持企业微信、钉钉、飞书、Telegram、Discord、Slack 等主流平台，通过 Webhook 配置即可接入。"},
            {"content_type": ContentType.FAQ, "title": "有技术支持吗？", "sort_order": 30,
             "body": "你可以通过邮件联系技术支持团队。我们也提供详细的使用文档和 FAQ 帮助你快速上手。"},
            {"content_type": ContentType.ANNOUNCEMENT, "title": "知枢 v0.9.0 发布", "sort_order": 100,
             "summary": "新增 MCP 协议支持、数据恢复、桌面版自动更新等功能",
             "body": "知枢 v0.9.0 已发布！本次更新新增 MCP 服务器管理、数据恢复、桌面版自动更新等重要功能，同时大幅提升了桌面版的稳定性和性能。\n\n[查看完整更新日志](/changelog.html)"},
            {"content_type": ContentType.PAGE, "title": "关于我们", "slug": "about", "sort_order": 100,
             "body": "# 关于知枢\n\n知枢是一个 RAG 智能知识平台，致力于让企业知识与 AI 深度融合。\n\n## 我们的愿景\n\n让每一个组织都能轻松构建自己的智能知识库，让知识不再沉睡在文档和数据库中，而是真正活起来，为每一位成员提供智能化的知识服务。\n\n## 联系方式\n\n- 邮箱：support@zhishu.ai\n- GitHub：[RAG数据平台](https://gitee.com/w947366965/rag)\n\n## 技术支持\n\n如果你在使用过程中遇到任何问题，欢迎通过以下方式联系我们：\n- 提交 Issue\n- 发送邮件到技术支持邮箱"},
        ]

        for item in seed_data:
            content = SiteContent(**{k: v for k, v in item.items()}, is_published=True)
            db.add(content)
        await db.commit()
        logger.info("Seeded %d site content entries", len(seed_data))


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    from app.core.log_buffer import setup_log_buffer
    setup_log_buffer()
    _is_production = not settings.DEBUG
    if not settings.SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY is required. Generate one with: "
            "python -c \"import secrets; print(secrets.token_urlsafe(64))\""
        )
    weak_admin_passwords = {"admin" + "123456"}
    if (not settings.ADMIN_PASSWORD) or (_is_production and settings.ADMIN_PASSWORD in weak_admin_passwords):
        raise RuntimeError(
            "ADMIN_PASSWORD must be set to a strong initial password before startup."
        )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ensured")
    await _ensure_schema_compat()
    await _ensure_super_admin()
    await _seed_site_content()
    if settings.REMOTE_RELAY_ENABLED:
        try:
            from app.services.relay_manager import relay_manager
            await relay_manager.start()
        except Exception as exc:
            logger.warning("Relay manager failed to start: %s", exc)

    try:
        async with async_session() as db:
            for row in (await db.execute(select(SystemConfig))).scalars().all():
                if row.key == "allow_registration":
                    settings.ALLOW_REGISTRATION = str(row.value or "").lower() in ("1", "true", "yes")
                elif row.key == "invite_code":
                    settings.INVITE_CODE = row.value or ""
    except Exception as e:
        logger.warning("Could not load system config from DB (table may not exist): %s", e)

    logger.info("%s started", settings.APP_NAME)
    yield
    if settings.REMOTE_RELAY_ENABLED:
        try:
            from app.services.relay_manager import relay_manager
            await relay_manager.stop()
        except Exception:
            pass
    try:
        from app.services.llm_gateway import close_gateway
        await close_gateway()
    except Exception:
        pass
    await engine.dispose()
