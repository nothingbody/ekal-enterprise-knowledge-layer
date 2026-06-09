"""Knowledge base business logic separated from API layer."""
import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User
from app.models.knowledge_base import KnowledgeBase
from app.models.document import Document, DocumentStatus
from app.services.permissions import require_owner_or_admin

logger = logging.getLogger(__name__)


async def get_kb_or_404(db: AsyncSession, kb_id: int) -> KnowledgeBase:
    kb = (await db.execute(
        select(KnowledgeBase).where(KnowledgeBase.id == kb_id, KnowledgeBase.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not kb:
        raise HTTPException(404, "知识库不存在")
    return kb


async def list_kbs(
    db: AsyncSession, user: User,
    workspace_id: Optional[int] = None,
    page: int = 1, page_size: int = 20,
) -> tuple[list[KnowledgeBase], int]:
    from app.core.security import check_role_level
    from app.models.user import UserRole
    filters = [KnowledgeBase.deleted_at.is_(None)]
    if workspace_id:
        filters.append(KnowledgeBase.workspace_id == workspace_id)
    if not check_role_level(user, UserRole.ADMIN):
        filters.append(KnowledgeBase.owner_id == user.id)

    total = (await db.execute(select(func.count(KnowledgeBase.id)).where(*filters))).scalar() or 0
    result = await db.execute(
        select(KnowledgeBase).where(*filters)
        .order_by(KnowledgeBase.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )
    return list(result.scalars().all()), total


async def create_kb(db: AsyncSession, user: User, data: dict) -> KnowledgeBase:
    if not data.get("workspace_id"):
        ws_id = await _ensure_default_workspace(db, user)
        data["workspace_id"] = ws_id
    kb = KnowledgeBase(owner_id=user.id, **data)
    db.add(kb)
    await db.commit()
    await db.refresh(kb)
    logger.info("KB_CREATE user=%s kb=%s", user.username, kb.name)
    return kb


async def _ensure_default_workspace(db: AsyncSession, user: User) -> int:
    """Get or create a default workspace for the user."""
    from app.models.workspace import Workspace
    result = await db.execute(
        select(Workspace).where(Workspace.owner_id == user.id, Workspace.is_active == True)
        .order_by(Workspace.created_at.asc()).limit(1)
    )
    ws = result.scalar_one_or_none()
    if ws:
        return ws.id
    ws = Workspace(name=f"{user.username} 的工作空间", owner_id=user.id, is_active=True)
    db.add(ws)
    await db.flush()
    logger.info("Auto-created default workspace for user %s", user.username)
    return ws.id


async def soft_delete_kb(db: AsyncSession, user: User, kb_id: int) -> None:
    kb = await get_kb_or_404(db, kb_id)
    require_owner_or_admin(kb.owner_id, user, "删除")
    kb.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    logger.info("KB_DELETE user=%s kb=%s", user.username, kb.name)


MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
ALLOWED_EXTENSIONS = {
    "pdf", "txt", "md", "markdown",
    "doc", "docx", "xls", "xlsx", "ppt", "pptx",
    "csv", "json", "xml", "html", "htm",
    "py", "js", "ts", "java", "go", "rs", "c", "cpp", "h",
    "yaml", "yml", "toml", "ini", "cfg", "conf", "log",
}


async def store_document(
    db: AsyncSession, user: User, kb_id: int,
    filename: str, content: bytes,
) -> Document:
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, f"文件过大，最大允许 {MAX_FILE_SIZE // 1024 // 1024}MB")

    file_ext = os.path.splitext(filename)[1].lower().lstrip(".")
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"不支持的文件类型: .{file_ext}")

    kb = await get_kb_or_404(db, kb_id)
    content_hash = hashlib.sha256(content).hexdigest()
    dot_ext = os.path.splitext(filename)[1].lower()
    storage_key = f"{kb_id}/{content_hash}{dot_ext}"
    full_path = os.path.join(settings.UPLOAD_DIR, storage_key)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "wb") as f:
        f.write(content)

    doc = Document(
        kb_id=kb_id,
        uploader_id=user.id,
        filename=filename,
        storage_key=storage_key,
        file_size=len(content),
        file_type=file_ext or "bin",
        content_hash=content_hash,
        status=DocumentStatus.UPLOADING,
    )
    db.add(doc)
    kb.doc_count = (kb.doc_count or 0) + 1
    await db.commit()
    await db.refresh(doc)
    logger.info("DOC_UPLOAD user=%s kb=%s file=%s", user.username, kb.name, filename)
    return doc


async def soft_delete_document(db: AsyncSession, kb_id: int, doc_id: int) -> None:
    doc = (await db.execute(
        select(Document).where(Document.id == doc_id, Document.kb_id == kb_id, Document.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "文档不存在")
    doc.deleted_at = datetime.now(timezone.utc)
    kb = (await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))).scalar_one_or_none()
    if kb:
        kb.doc_count = max((kb.doc_count or 1) - 1, 0)
    await db.commit()
