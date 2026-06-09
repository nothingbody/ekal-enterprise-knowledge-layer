"""API for website content management (CMS)."""

import json
import logging
from typing import Optional

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models.user import User
from app.models.site_content import SiteContent, ContentType
from app.core.security import get_admin_user

router = APIRouter()
logger = logging.getLogger(__name__)


def _content_to_dict(c: SiteContent) -> dict:
    extra = None
    if c.extra:
        try:
            extra = json.loads(c.extra)
        except Exception:
            extra = c.extra
    return {
        "id": c.id,
        "content_type": c.content_type.value if hasattr(c.content_type, 'value') else str(c.content_type),
        "title": c.title,
        "slug": c.slug,
        "body": c.body,
        "summary": c.summary,
        "sort_order": c.sort_order,
        "is_published": c.is_published,
        "version": c.version,
        "extra": extra,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


# ── Public endpoints (no auth, for website) ──

@router.get("/public/{content_type}")
async def public_list_content(
    content_type: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    try:
        ct = ContentType(content_type)
    except ValueError:
        raise HTTPException(400, f"Invalid content type: {content_type}")

    filters = [SiteContent.content_type == ct, SiteContent.is_published == True]
    total = (await db.execute(select(func.count(SiteContent.id)).where(*filters))).scalar() or 0
    result = await db.execute(
        select(SiteContent).where(*filters)
        .order_by(SiteContent.sort_order.desc(), SiteContent.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [_content_to_dict(c) for c in result.scalars().all()]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/public/page/{slug}")
async def public_get_page(
    slug: str,
    db: AsyncSession = Depends(get_db),
):
    content = (await db.execute(
        select(SiteContent).where(
            SiteContent.slug == slug,
            SiteContent.content_type == ContentType.PAGE,
            SiteContent.is_published == True,
        )
    )).scalar_one_or_none()
    if not content:
        raise HTTPException(404, "Page not found")
    return _content_to_dict(content)


# ── Admin endpoints ──

_SORT_MAP = {
    "sort_order": [SiteContent.sort_order.desc(), SiteContent.created_at.desc()],
    "created_at": [SiteContent.created_at.desc()],
    "updated_at": [SiteContent.updated_at.desc()],
    "title": [SiteContent.title.asc()],
}


@router.get("/admin/list")
async def admin_list_content(
    content_type: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    query = select(SiteContent)
    count_query = select(func.count(SiteContent.id))
    if content_type:
        try:
            ct = ContentType(content_type)
            query = query.where(SiteContent.content_type == ct)
            count_query = count_query.where(SiteContent.content_type == ct)
        except ValueError:
            pass
    if search:
        from app.core.utils import escape_like
        s = f"%{escape_like(search)}%"
        query = query.where(SiteContent.title.ilike(s))
        count_query = count_query.where(SiteContent.title.ilike(s))

    order_cols = _SORT_MAP.get(sort_by or "", _SORT_MAP["sort_order"])

    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(
        query.order_by(*order_cols)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [_content_to_dict(c) for c in result.scalars().all()]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/admin/batch-update")
async def admin_batch_update(
    data: dict,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    ids = data.get("ids", [])
    updates = data.get("updates", {})
    if not ids:
        raise HTTPException(400, "ids is required")

    allowed = {"is_published", "sort_order"}
    filtered = {k: v for k, v in updates.items() if k in allowed}
    if not filtered:
        raise HTTPException(400, "No valid updates provided")

    result = await db.execute(select(SiteContent).where(SiteContent.id.in_(ids)))
    rows = result.scalars().all()
    for c in rows:
        for k, v in filtered.items():
            setattr(c, k, v)
    await db.commit()
    logger.info("SITE_CONTENT_BATCH_UPDATE ids=%s updates=%s by=%s", ids, filtered, admin.username)
    return {"ok": True, "updated": len(rows)}


@router.post("/admin/batch-delete")
async def admin_batch_delete(
    data: dict,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    ids = data.get("ids", [])
    if not ids:
        raise HTTPException(400, "ids is required")

    result = await db.execute(select(SiteContent).where(SiteContent.id.in_(ids)))
    rows = result.scalars().all()
    for c in rows:
        await db.delete(c)
    await db.commit()
    logger.info("SITE_CONTENT_BATCH_DELETE ids=%s by=%s", ids, admin.username)
    return {"ok": True, "deleted": len(rows)}


@router.post("/admin/create")
async def admin_create_content(
    data: dict,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    try:
        ct = ContentType(data.get("content_type", ""))
    except ValueError:
        raise HTTPException(400, "Invalid content_type")

    title = data.get("title", "").strip()
    if not title:
        raise HTTPException(400, "Title is required")

    extra = data.get("extra")
    if extra and isinstance(extra, dict):
        extra = json.dumps(extra, ensure_ascii=False)

    sort_order = data.get("sort_order", 0)
    if sort_order == 0:
        max_sort = (await db.execute(
            select(func.max(SiteContent.sort_order)).where(SiteContent.content_type == ct)
        )).scalar() or 0
        sort_order = max_sort + 10

    content = SiteContent(
        content_type=ct,
        title=title,
        slug=data.get("slug", "").strip() or None,
        body=data.get("body", ""),
        summary=data.get("summary", ""),
        sort_order=sort_order,
        is_published=data.get("is_published", True),
        version=data.get("version"),
        extra=extra,
    )
    db.add(content)
    await db.commit()
    await db.refresh(content)
    logger.info("SITE_CONTENT_CREATE id=%d type=%s title=%s by=%s", content.id, ct.value, title, admin.username)
    return _content_to_dict(content)


@router.put("/admin/{content_id}")
async def admin_update_content(
    content_id: int,
    data: dict,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    content = (await db.execute(
        select(SiteContent).where(SiteContent.id == content_id)
    )).scalar_one_or_none()
    if not content:
        raise HTTPException(404, "Content not found")

    allowed = {"title", "slug", "body", "summary", "sort_order", "is_published", "version", "content_type"}
    for field in allowed:
        if field in data:
            val = data[field]
            if field == "content_type":
                try:
                    val = ContentType(val)
                except ValueError:
                    continue
            setattr(content, field, val)

    if "extra" in data:
        extra = data["extra"]
        if isinstance(extra, dict):
            content.extra = json.dumps(extra, ensure_ascii=False)
        else:
            content.extra = extra

    await db.commit()
    await db.refresh(content)
    logger.info("SITE_CONTENT_UPDATE id=%d by=%s", content_id, admin.username)
    return _content_to_dict(content)


@router.delete("/admin/{content_id}")
async def admin_delete_content(
    content_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    content = (await db.execute(
        select(SiteContent).where(SiteContent.id == content_id)
    )).scalar_one_or_none()
    if not content:
        raise HTTPException(404, "Content not found")

    title = content.title
    await db.delete(content)
    await db.commit()
    logger.info("SITE_CONTENT_DELETE id=%d title=%s by=%s", content_id, title, admin.username)
    return {"ok": True, "message": f"已删除「{title}」"}
