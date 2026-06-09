from typing import Optional, Literal

from fastapi import HTTPException
from sqlalchemy import and_, or_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_base import KnowledgeBase
from app.models.document import Document, DocumentStatus
from app.models.workspace import Workspace, WorkspaceKnowledgeBase, WorkspaceMember, WorkspaceRole


WRITE_ROLES = {WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.MEMBER}
MANAGE_ROLES = {WorkspaceRole.OWNER, WorkspaceRole.ADMIN}


def _role_value(role: Optional[WorkspaceRole]) -> Optional[str]:
    return role.value if role else None


def _build_access_payload(
    kb: KnowledgeBase,
    workspace_id: Optional[int],
    workspace_name: Optional[str],
    member_role: Optional[WorkspaceRole],
    user_id: int,
) -> dict:
    is_creator = kb.user_id == user_id
    can_read = is_creator or member_role is not None
    can_write = is_creator or member_role in WRITE_ROLES
    can_manage = is_creator or member_role in MANAGE_ROLES
    return {
        "kb": kb,
        "workspace_id": workspace_id,
        "workspace_name": workspace_name,
        "access_role": "owner" if is_creator else _role_value(member_role),
        "can_read": can_read,
        "can_write": can_write,
        "can_manage": can_manage,
    }


async def get_kb_access_info(db: AsyncSession, kb_id: int, user_id: int) -> Optional[dict]:
    result = await db.execute(
        select(KnowledgeBase, WorkspaceKnowledgeBase.workspace_id, Workspace.name, WorkspaceMember.role)
        .outerjoin(WorkspaceKnowledgeBase, WorkspaceKnowledgeBase.kb_id == KnowledgeBase.id)
        .outerjoin(Workspace, Workspace.id == WorkspaceKnowledgeBase.workspace_id)
        .outerjoin(
            WorkspaceMember,
            and_(
                WorkspaceMember.workspace_id == WorkspaceKnowledgeBase.workspace_id,
                WorkspaceMember.user_id == user_id,
            ),
        )
        .where(KnowledgeBase.id == kb_id, KnowledgeBase.deleted_at.is_(None))
    )
    row = result.first()
    if not row:
        return None

    kb, workspace_id, workspace_name, member_role = row
    return _build_access_payload(kb, workspace_id, workspace_name, member_role, user_id)


async def require_kb_access(
    db: AsyncSession,
    kb_id: int,
    user_id: int,
    mode: Literal["read", "write", "manage"] = "read",
) -> dict:
    access = await get_kb_access_info(db, kb_id, user_id)
    if not access:
        raise HTTPException(status_code=404, detail="知识库不存在")

    allowed = {
        "read": access["can_read"],
        "write": access["can_write"],
        "manage": access["can_manage"],
    }[mode]
    if not allowed:
        raise HTTPException(status_code=403, detail="无权访问该知识库")
    return access


async def list_accessible_kbs(db: AsyncSession, user_id: int) -> list[dict]:
    result = await db.execute(
        select(KnowledgeBase, WorkspaceKnowledgeBase.workspace_id, Workspace.name, WorkspaceMember.role)
        .outerjoin(WorkspaceKnowledgeBase, WorkspaceKnowledgeBase.kb_id == KnowledgeBase.id)
        .outerjoin(Workspace, Workspace.id == WorkspaceKnowledgeBase.workspace_id)
        .outerjoin(
            WorkspaceMember,
            and_(
                WorkspaceMember.workspace_id == WorkspaceKnowledgeBase.workspace_id,
                WorkspaceMember.user_id == user_id,
            ),
        )
        .where(
            or_(KnowledgeBase.user_id == user_id, WorkspaceMember.user_id == user_id),
            KnowledgeBase.deleted_at.is_(None),
        )
        .order_by(KnowledgeBase.updated_at.desc())
    )

    items = []
    seen = set()
    for kb, workspace_id, workspace_name, member_role in result.all():
        if kb.id in seen:
            continue
        seen.add(kb.id)
        items.append(_build_access_payload(kb, workspace_id, workspace_name, member_role, user_id))
    return items


async def list_accessible_kb_ids(
    db: AsyncSession,
    user_id: int,
    mode: Literal["read", "write", "manage"] = "read",
) -> list[int]:
    items = await list_accessible_kbs(db, user_id)
    flag_name = {
        "read": "can_read",
        "write": "can_write",
        "manage": "can_manage",
    }[mode]
    return [item["kb"].id for item in items if item[flag_name]]


async def ensure_workspace_member(db: AsyncSession, workspace_id: int, user_id: int) -> WorkspaceMember:
    """Verify the user is a member of the workspace (any role). Raises 403 if not."""
    result = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=403, detail="无权访问该工作空间")
    return member


async def ensure_workspace_write_access(db: AsyncSession, workspace_id: int, user_id: int) -> WorkspaceMember:
    result = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=403, detail="无权访问该工作空间")
    if member.role not in WRITE_ROLES:
        raise HTTPException(status_code=403, detail="当前角色无权在该工作空间创建或修改知识库")
    return member


async def set_kb_workspace(db: AsyncSession, kb_id: int, workspace_id: Optional[int]) -> None:
    result = await db.execute(
        select(WorkspaceKnowledgeBase).where(WorkspaceKnowledgeBase.kb_id == kb_id)
    )
    link = result.scalar_one_or_none()

    if workspace_id is None:
        if link:
            await db.delete(link)
            await db.commit()
        return

    if link:
        link.workspace_id = workspace_id
    else:
        link = WorkspaceKnowledgeBase(workspace_id=workspace_id, kb_id=kb_id)
        db.add(link)
    await db.commit()


async def compute_processing_counts(db: AsyncSession, kb_ids: list[int]) -> dict[int, int]:
    """Return {kb_id: processing_doc_count} for the given KB IDs."""
    if not kb_ids:
        return {}
    processing_statuses = [DocumentStatus.UPLOADING, DocumentStatus.PARSING, DocumentStatus.EMBEDDING]
    result = await db.execute(
        select(Document.kb_id, func.count(Document.id))
        .where(Document.kb_id.in_(kb_ids), Document.status.in_(processing_statuses))
        .group_by(Document.kb_id)
    )
    return dict(result.all())


async def compute_failed_counts(db: AsyncSession, kb_ids: list[int]) -> dict[int, int]:
    """Return {kb_id: failed_doc_count} for the given KB IDs."""
    if not kb_ids:
        return {}
    result = await db.execute(
        select(Document.kb_id, func.count(Document.id))
        .where(Document.kb_id.in_(kb_ids), Document.status == DocumentStatus.FAILED)
        .group_by(Document.kb_id)
    )
    return dict(result.all())


def serialize_kb(access: dict, processing_count: int = 0, failed_count: int = 0) -> dict:
    kb = access["kb"]
    return {
        "id": kb.id,
        "user_id": kb.user_id,
        "name": kb.name,
        "description": kb.description,
        "embedding_model_id": kb.embedding_model_id,
        "chunk_strategy": kb.chunk_strategy,
        "chunk_size": kb.chunk_size,
        "chunk_overlap": kb.chunk_overlap,
        "search_mode": kb.search_mode,
        "welcome_message": kb.welcome_message,
        "suggested_questions": kb.suggested_questions,
        "prompt_template": kb.prompt_template,
        "doc_count": kb.doc_count,
        "chunk_count": kb.chunk_count,
        "processing_count": processing_count,
        "failed_count": failed_count,
        "created_at": kb.created_at,
        "updated_at": kb.updated_at,
        "workspace_id": access["workspace_id"],
        "workspace_name": access["workspace_name"],
        "access_role": access["access_role"],
        "can_write": access["can_write"],
        "can_manage": access["can_manage"],
    }
