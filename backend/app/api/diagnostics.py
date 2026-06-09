"""System diagnostics API — automated health checks with fix suggestions."""

import logging
import os
import shutil
from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text

from app.database import get_db, engine
from app.config import settings
from app.models.user import User
from app.core.security import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


class DiagnosticResult(BaseModel):
    name: str
    status: str  # ok | warning | error
    message: str
    suggestion: str = ""


async def _check_database() -> DiagnosticResult:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return DiagnosticResult(name="数据库连接", status="ok", message="数据库连接正常")
    except Exception as exc:
        return DiagnosticResult(
            name="数据库连接", status="error",
            message=f"数据库连接失败: {exc}",
            suggestion="请检查 DATABASE_URL 配置是否正确",
        )


async def _check_vector_store() -> DiagnosticResult:
    try:
        if settings.VECTOR_STORE_TYPE == "chroma":
            if settings.CHROMA_MODE == "embedded":
                data_dir = settings.CHROMA_DATA_DIR
                if os.path.exists(data_dir):
                    return DiagnosticResult(name="向量存储", status="ok", message="ChromaDB 嵌入式模式运行正常")
                return DiagnosticResult(
                    name="向量存储", status="warning",
                    message="ChromaDB 数据目录不存在，将在首次使用时创建",
                    suggestion="上传文档后将自动初始化向量存储",
                )
            else:
                import httpx
                resp = httpx.get(
                    f"http://{settings.CHROMA_HOST}:{settings.CHROMA_PORT}/api/v1/heartbeat",
                    timeout=3,
                )
                if resp.status_code == 200:
                    return DiagnosticResult(name="向量存储", status="ok", message="ChromaDB 客户端模式连接正常")
                return DiagnosticResult(
                    name="向量存储", status="error",
                    message=f"ChromaDB 返回状态码 {resp.status_code}",
                    suggestion="请确认 ChromaDB 服务是否已启动",
                )
        return DiagnosticResult(name="向量存储", status="ok", message=f"使用 {settings.VECTOR_STORE_TYPE}")
    except Exception as exc:
        return DiagnosticResult(
            name="向量存储", status="error",
            message=f"向量存储检查失败: {exc}",
            suggestion="请检查向量存储配置",
        )


async def _check_llm_models(db: AsyncSession, user_id: int) -> DiagnosticResult:
    from app.models.model_config import ModelConfig, ModelType
    result = await db.execute(
        select(func.count(ModelConfig.id)).where(
            ModelConfig.user_id == user_id,
            ModelConfig.model_type == ModelType.LLM,
        )
    )
    count = result.scalar() or 0
    if count == 0:
        return DiagnosticResult(
            name="LLM 模型", status="error",
            message="未配置任何 LLM 模型",
            suggestion="请前往「模型管理」页面添加至少一个 LLM 模型",
        )
    result2 = await db.execute(
        select(func.count(ModelConfig.id)).where(
            ModelConfig.user_id == user_id,
            ModelConfig.model_type == ModelType.LLM,
            ModelConfig.is_default == True,
        )
    )
    has_default = (result2.scalar() or 0) > 0
    if not has_default:
        return DiagnosticResult(
            name="LLM 模型", status="warning",
            message=f"已配置 {count} 个 LLM 模型，但未设置默认模型",
            suggestion="建议设置一个默认 LLM 模型",
        )
    return DiagnosticResult(name="LLM 模型", status="ok", message=f"已配置 {count} 个 LLM 模型")


async def _check_embedding_models(db: AsyncSession, user_id: int) -> DiagnosticResult:
    from app.models.model_config import ModelConfig, ModelType
    result = await db.execute(
        select(func.count(ModelConfig.id)).where(
            ModelConfig.user_id == user_id,
            ModelConfig.model_type == ModelType.EMBEDDING,
        )
    )
    count = result.scalar() or 0
    if count == 0:
        return DiagnosticResult(
            name="Embedding 模型", status="error",
            message="未配置任何 Embedding 模型",
            suggestion="请前往「模型管理」页面添加 Embedding 模型，否则无法创建知识库",
        )
    return DiagnosticResult(name="Embedding 模型", status="ok", message=f"已配置 {count} 个 Embedding 模型")


async def _check_knowledge_bases(db: AsyncSession, user_id: int) -> DiagnosticResult:
    from app.models.knowledge_base import KnowledgeBase
    result = await db.execute(
        select(func.count(KnowledgeBase.id)).where(
            KnowledgeBase.user_id == user_id,
            KnowledgeBase.deleted_at.is_(None),
        )
    )
    count = result.scalar() or 0
    if count == 0:
        return DiagnosticResult(
            name="知识库", status="warning",
            message="尚未创建知识库",
            suggestion="前往「知识库管理」创建您的第一个知识库",
        )
    return DiagnosticResult(name="知识库", status="ok", message=f"已创建 {count} 个知识库")


async def _check_stale_tasks(db: AsyncSession) -> DiagnosticResult:
    from app.models.document import Document, DocumentStatus
    result = await db.execute(
        select(func.count(Document.id)).where(
            Document.status.in_([
                DocumentStatus.UPLOADING,
                DocumentStatus.PARSING,
                DocumentStatus.EMBEDDING,
            ])
        )
    )
    count = result.scalar() or 0
    if count > 0:
        return DiagnosticResult(
            name="任务状态", status="warning",
            message=f"有 {count} 个文档处理任务可能卡住",
            suggestion="可尝试重启服务自动恢复，或手动重新上传相关文档",
        )
    return DiagnosticResult(name="任务状态", status="ok", message="无卡住的处理任务")


async def _check_disk_space() -> DiagnosticResult:
    try:
        total, used, free = shutil.disk_usage(settings.UPLOAD_DIR)
        free_gb = free / (1024 ** 3)
        total_gb = total / (1024 ** 3)
        usage_pct = (used / total) * 100
        if free_gb < 1:
            return DiagnosticResult(
                name="磁盘空间", status="error",
                message=f"磁盘可用空间不足: {free_gb:.1f} GB (使用率 {usage_pct:.0f}%)",
                suggestion="请清理磁盘空间或迁移到更大的存储",
            )
        if free_gb < 5:
            return DiagnosticResult(
                name="磁盘空间", status="warning",
                message=f"磁盘空间较低: {free_gb:.1f} GB 可用 / {total_gb:.0f} GB 总计",
                suggestion="建议清理不必要的文件",
            )
        return DiagnosticResult(
            name="磁盘空间", status="ok",
            message=f"{free_gb:.1f} GB 可用 / {total_gb:.0f} GB 总计 (使用率 {usage_pct:.0f}%)",
        )
    except Exception as exc:
        return DiagnosticResult(
            name="磁盘空间", status="warning",
            message=f"无法检测磁盘空间: {exc}",
        )


async def _check_mcp_servers(db: AsyncSession, user_id: int) -> DiagnosticResult:
    from app.models.mcp_server import McpServerConfig
    result = await db.execute(
        select(func.count(McpServerConfig.id)).where(
            McpServerConfig.user_id == user_id,
            McpServerConfig.is_active == True,
        )
    )
    active = result.scalar() or 0
    if active == 0:
        return DiagnosticResult(
            name="MCP 服务", status="ok",
            message="未配置 MCP 服务器（可选功能）",
        )
    return DiagnosticResult(name="MCP 服务", status="ok", message=f"{active} 个 MCP 服务器已启用")


@router.get("/run", response_model=List[DiagnosticResult])
async def run_diagnostics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    checks = [
        await _check_database(),
        await _check_vector_store(),
        await _check_llm_models(db, current_user.id),
        await _check_embedding_models(db, current_user.id),
        await _check_knowledge_bases(db, current_user.id),
        await _check_stale_tasks(db),
        await _check_disk_space(),
        await _check_mcp_servers(db, current_user.id),
    ]
    return checks
