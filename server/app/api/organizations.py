import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models.user import User
from app.models.organization import Organization, OrgMember, OrgRole
from app.schemas import OrgCreate, OrgResponse, OrgUpdate, OrgMemberAdd, OrgMemberResponse, PaginatedResponse
from app.core.security import get_admin_user
from app.core.audit import record_audit

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/", response_model=PaginatedResponse)
async def list_organizations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    filters = [Organization.deleted_at.is_(None)]
    if search:
        from app.core.utils import escape_like
        filters.append(Organization.name.ilike(f"%{escape_like(search)}%"))

    total = (await db.execute(select(func.count(Organization.id)).where(*filters))).scalar() or 0

    member_count_sub = (
        select(OrgMember.org_id, func.count(OrgMember.id).label("member_count"))
        .group_by(OrgMember.org_id)
        .subquery()
    )
    result = await db.execute(
        select(Organization, func.coalesce(member_count_sub.c.member_count, 0).label("mc"))
        .outerjoin(member_count_sub, Organization.id == member_count_sub.c.org_id)
        .where(*filters)
        .order_by(Organization.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    items = []
    for org, mc in result.all():
        d = OrgResponse.model_validate(org).model_dump()
        d["member_count"] = mc
        items.append(d)

    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("/", response_model=OrgResponse)
async def create_organization(
    data: OrgCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    org = Organization(
        name=data.name,
        description=data.description,
        owner_id=admin.id,
        max_members=data.max_members,
    )
    db.add(org)
    await db.flush()
    db.add(OrgMember(org_id=org.id, user_id=admin.id, role=OrgRole.OWNER))
    await db.commit()
    await db.refresh(org)
    logger.info("ORG_CREATE name=%s by=%s", org.name, admin.username)
    d = OrgResponse.model_validate(org).model_dump()
    d["member_count"] = 1
    return d


@router.put("/{org_id}", response_model=OrgResponse)
async def update_organization(
    org_id: int,
    data: OrgUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    result = await db.execute(select(Organization).where(Organization.id == org_id, Organization.deleted_at.is_(None)))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(404, "组织不存在")

    if data.name is not None:
        org.name = data.name
    if data.description is not None:
        org.description = data.description
    if data.max_members is not None:
        org.max_members = data.max_members
    if data.is_active is not None:
        org.is_active = data.is_active

    await db.commit()
    await db.refresh(org)
    member_count = (await db.execute(
        select(func.count(OrgMember.id)).where(OrgMember.org_id == org.id)
    )).scalar() or 0
    d = OrgResponse.model_validate(org).model_dump()
    d["member_count"] = member_count
    return d


@router.get("/{org_id}", response_model=OrgResponse)
async def get_organization(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    result = await db.execute(select(Organization).where(Organization.id == org_id, Organization.deleted_at.is_(None)))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(404, "组织不存在")
    member_count = (await db.execute(
        select(func.count(OrgMember.id)).where(OrgMember.org_id == org.id)
    )).scalar() or 0
    d = OrgResponse.model_validate(org).model_dump()
    d["member_count"] = member_count
    return d


@router.delete("/{org_id}")
async def delete_organization(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    result = await db.execute(select(Organization).where(Organization.id == org_id, Organization.deleted_at.is_(None)))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(404, "组织不存在")
    from datetime import datetime, timezone
    org.deleted_at = datetime.now(timezone.utc)
    org.is_active = False
    await db.commit()
    await record_audit(
        db, user_id=_admin.id, username=_admin.username,
        action="delete_org", resource_type="organization", resource_id=str(org_id),
        detail=f"deleted org {org.name}",
    )
    return {"message": "组织已删除"}


@router.get("/{org_id}/members")
async def list_org_members(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    org = (await db.execute(select(Organization).where(Organization.id == org_id, Organization.deleted_at.is_(None)))).scalar_one_or_none()
    if not org:
        raise HTTPException(404, "组织不存在")

    result = await db.execute(
        select(OrgMember, User)
        .join(User, OrgMember.user_id == User.id)
        .where(OrgMember.org_id == org_id, User.deleted_at.is_(None))
        .order_by(OrgMember.joined_at.asc())
    )
    items = []
    for member, user in result.all():
        items.append(OrgMemberResponse(
            id=member.id,
            user_id=user.id,
            username=user.username,
            email=user.email,
            role=member.role.value,
            joined_at=member.joined_at,
            plan=getattr(user, 'plan', None),
            token_used=getattr(user, 'token_used', 0) or 0,
            token_credit=getattr(user, 'token_credit', 0) or 0,
            last_login_at=getattr(user, 'last_login_at', None),
        ))
    return items


@router.post("/{org_id}/members")
async def add_org_member(
    org_id: int,
    data: OrgMemberAdd,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    org = (await db.execute(select(Organization).where(Organization.id == org_id, Organization.deleted_at.is_(None)))).scalar_one_or_none()
    if not org:
        raise HTTPException(404, "组织不存在")

    member_count = (await db.execute(
        select(func.count(OrgMember.id)).where(OrgMember.org_id == org_id)
    )).scalar() or 0
    if member_count >= org.max_members:
        raise HTTPException(400, f"组织成员已达上限 ({org.max_members})")

    existing = (await db.execute(
        select(OrgMember).where(OrgMember.org_id == org_id, OrgMember.user_id == data.user_id)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(400, "用户已是该组织成员")

    user = (await db.execute(select(User).where(User.id == data.user_id, User.deleted_at.is_(None)))).scalar_one_or_none()
    if not user:
        raise HTTPException(404, "用户不存在")

    member = OrgMember(org_id=org_id, user_id=data.user_id, role=OrgRole(data.role))
    db.add(member)
    user.org_id = org_id
    await db.commit()
    return {"message": "成员已添加"}


@router.put("/{org_id}/members/{user_id}/role")
async def update_member_role(
    org_id: int,
    user_id: int,
    role: str = Query(..., description="New role: owner, admin, member"),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    result = await db.execute(
        select(OrgMember).where(OrgMember.org_id == org_id, OrgMember.user_id == user_id)
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(404, "成员不存在")
    try:
        member.role = OrgRole(role)
    except ValueError:
        raise HTTPException(400, f"无效角色: {role}，可选: owner, admin, member")
    await db.commit()
    return {"message": "角色已更新"}


@router.delete("/{org_id}/members/{user_id}")
async def remove_org_member(
    org_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    org = (await db.execute(select(Organization).where(Organization.id == org_id, Organization.deleted_at.is_(None)))).scalar_one_or_none()
    if not org:
        raise HTTPException(404, "组织不存在")

    result = await db.execute(
        select(OrgMember).where(OrgMember.org_id == org_id, OrgMember.user_id == user_id)
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(404, "成员不存在")

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user and user.org_id == org_id:
        user.org_id = None

    await db.delete(member)
    await db.commit()
    return {"message": "成员已移除"}
