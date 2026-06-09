import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models.user import User
from app.models.skill import MarketSkill
from app.schemas import SkillPublish, SkillResponse, SkillReviewAction, PaginatedResponse
from app.core.security import get_current_user, get_current_user_optional, get_admin_user
from app.services import skill_service as svc

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/marketplace", response_model=PaginatedResponse)
async def marketplace(
    category: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Public marketplace — only approved skills."""
    return await svc.list_marketplace(db, category, search, page, page_size)


@router.get("/{skill_id}")
async def get_skill(
    skill_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """已上架技能：任何人可见。未上架：仅作者本人或管理员可见（需带 Bearer）。"""
    try:
        return await svc.get_skill_by_id(db, skill_id, current_user)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/{skill_id}/download")
async def download_skill(
    skill_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Record a download and return skill config."""
    try:
        return await svc.record_download(db, skill_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/publish", response_model=SkillResponse)
async def publish_skill(
    data: SkillPublish,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await svc.publish(db, data, current_user.id, current_user.username)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ── Admin: skill management ──

@router.get("/admin/all", response_model=PaginatedResponse)
async def admin_list_skills(
    status: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    return await svc.list_admin_skills(db, status, search, page, page_size, category=category)


@router.post("/admin/{skill_id}/review")
async def review_skill(
    skill_id: int,
    data: SkillReviewAction,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    try:
        result = await svc.review_skill(db, skill_id, admin.id, admin.username, data.status, data.comment)
        return {"message": f"技能已{result}"}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/admin/{skill_id}/detail")
async def admin_get_skill_detail(
    skill_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    """Admin: get full skill detail including config."""
    try:
        return await svc.get_admin_detail(db, skill_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.put("/admin/{skill_id}")
async def admin_update_skill(
    skill_id: int,
    data: dict,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Admin: update skill name, description, category, etc."""
    try:
        changed = await svc.update_skill(db, skill_id, data, admin.username)
        return {"ok": True, "updated": changed}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/admin/{skill_id}")
async def admin_delete_skill(
    skill_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Admin: delete a single skill."""
    try:
        skill_name = await svc.delete_skill(db, skill_id, admin.username)
        return {"ok": True, "message": f"已删除「{skill_name}」"}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.delete("/admin/openclaw/all")
async def delete_all_openclaw_skills(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    """Delete all OpenClaw skills from the market."""
    count = await svc.delete_all_openclaw(db)
    return {"ok": True, "deleted": count}


# ---------------------------------------------------------------------------
# Bulk import OpenClaw skills
# ---------------------------------------------------------------------------

@router.post("/admin/openclaw/import-all")
async def import_all_openclaw(
    background_tasks: BackgroundTasks,
    _admin: User = Depends(get_admin_user),
):
    """Download openclaw/skills tarball and bulk-import every skill into market_skills."""
    progress = await svc.get_import_progress()
    if progress.get("running"):
        return {"status": "already_running", "progress": progress}

    await svc.set_import_progress({"running": True, "inserted": 0, "skipped": 0, "total": 0, "error": None})
    background_tasks.add_task(svc.run_openclaw_bulk_import, _admin.id)
    return {"status": "started", "message": "后台批量导入已启动"}


@router.post("/admin/openclaw/import-local")
async def import_local_skills(
    background_tasks: BackgroundTasks,
    _admin: User = Depends(get_admin_user),
):
    """Import skills from the local skills/skills/ directory (pre-downloaded/translated)."""
    progress = await svc.get_import_progress()
    if progress.get("running"):
        return {"status": "already_running", "progress": progress}

    await svc.set_import_progress({"running": True, "inserted": 0, "skipped": 0, "total": 0, "error": None})
    background_tasks.add_task(svc.run_local_import, _admin.id)
    return {"status": "started", "message": "本地技能批量导入已启动"}


@router.post("/admin/openclaw/import-upload")
async def import_openclaw_upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    _admin: User = Depends(get_admin_user),
):
    """Accept uploaded tarball (tar.gz) and import skills from it."""
    progress = await svc.get_import_progress()
    if progress.get("running"):
        return {"status": "already_running", "progress": progress}

    if not file.filename or not file.filename.endswith((".tar.gz", ".tgz")):
        raise HTTPException(400, "请上传 .tar.gz 格式的文件")

    content = await file.read()
    if len(content) < 1000:
        raise HTTPException(400, "文件太小，请确认上传的是完整的 tar.gz 文件")

    await svc.set_import_progress({"running": True, "inserted": 0, "skipped": 0, "total": 0, "error": None})
    background_tasks.add_task(svc.run_openclaw_import_from_bytes, _admin.id, content)
    return {"status": "started", "message": f"已接收文件 ({len(content) / 1024 / 1024:.1f} MB)，后台导入已启动"}


@router.get("/admin/openclaw/import-progress")
async def openclaw_import_progress(
    _admin: User = Depends(get_admin_user),
):
    return await svc.get_import_progress()


# ---------------------------------------------------------------------------
# Batch translate OpenClaw skills
# ---------------------------------------------------------------------------

@router.post("/admin/openclaw/translate-batch")
async def translate_openclaw_batch(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Batch-translate all English OpenClaw skills to Chinese using a shared LLM."""
    progress = await svc.get_translate_progress()
    if progress.get("running"):
        return {"status": "already_running", "progress": progress}

    from app.models.model_config import ModelConfig as MC, ModelType as MT
    default_model = (await db.execute(
        select(MC).where(MC.model_type == MT.LLM, MC.is_shared == True)
        .order_by(MC.is_default.desc())
        .limit(1)
    )).scalar_one_or_none()
    if not default_model:
        raise HTTPException(400, "请先配置一个共享的 LLM 模型")

    oc_count = (await db.execute(
        select(func.count(MarketSkill.id)).where(MarketSkill.slug.like("oc-%"))
    )).scalar() or 0
    if oc_count == 0:
        raise HTTPException(400, "没有已导入的 OpenClaw 技能")

    await svc.set_translate_progress({
        "running": True, "translated": 0, "skipped": 0, "failed": 0, "total": oc_count, "error": None,
    })
    background_tasks.add_task(svc.run_batch_translate, default_model.id)
    return {"status": "started", "total": oc_count, "message": "后台批量翻译已启动"}


@router.get("/admin/openclaw/translate-progress")
async def translate_progress(
    _admin: User = Depends(get_admin_user),
):
    return await svc.get_translate_progress()


# ---------------------------------------------------------------------------
# Admin fix endpoints
# ---------------------------------------------------------------------------

@router.post("/admin/fix-openclaw-paths")
async def admin_fix_openclaw_paths(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    return await svc.fix_openclaw_paths(db)


@router.post("/admin/fix-empty-names")
async def admin_fix_empty_names(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    """Fill in empty skill names by deriving a readable name from the slug."""
    return await svc.fix_empty_names(db)


@router.post("/admin/fix-categories")
async def admin_fix_categories(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    """Re-categorize all 'openclaw' category skills based on slug/description keywords."""
    return await svc.fix_categories(db)
