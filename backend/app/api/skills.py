"""Skill marketplace API endpoints."""

import asyncio
import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db, async_session
from app.models.user import User
from app.models.skill import Skill
from app.models.model_config import ModelConfig, ModelType
from app.core.security import get_current_user, get_current_user_optional, get_admin_user
from app.services.skill_service import (
    list_marketplace,
    list_installed,
    install_skill,
    uninstall_skill,
    update_install,
    auto_install_builtins,
    create_prompt_skill,
)
from app.services import skill_chain_service

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class SkillInstallRequest(BaseModel):
    skill_id: int
    workspace_id: Optional[int] = None


class SkillInstallUpdate(BaseModel):
    is_active: Optional[bool] = None
    config_override: Optional[str] = None


class SkillCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    slug: str = Field(min_length=1, max_length=100)
    description: str = ""
    icon_url: Optional[str] = None
    category: str = "general"
    skill_type: str = Field(default="mcp", pattern="^(builtin|mcp|custom|prompt)$")
    config: Optional[str] = None
    is_public: bool = False


class SkillUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    icon_url: Optional[str] = None
    category: Optional[str] = None
    config: Optional[str] = None
    is_public: Optional[bool] = None
    prompt_template: Optional[str] = None
    output_format: Optional[str] = Field(None, pattern="^(text|json|markdown)$")
    variables: Optional[list[str]] = None


class PromptSkillCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    slug: str = Field(min_length=1, max_length=100)
    description: str = ""
    prompt_template: str = Field(min_length=1)
    output_format: str = Field(default="text", pattern="^(text|json|markdown)$")
    variables: Optional[list[str]] = None
    icon_url: Optional[str] = None
    category: str = "prompt"
    is_public: bool = False


class ChainCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    steps: list[dict] = Field(min_length=1)
    is_public: bool = False


class ChainUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    steps: Optional[list[dict]] = None
    is_public: Optional[bool] = None


class ChainExecuteRequest(BaseModel):
    initial_input: str = Field(min_length=1)
    llm_model_id: Optional[int] = None
    kb_id: Optional[int] = None


# ---------------------------------------------------------------------------
# Marketplace
# ---------------------------------------------------------------------------

@router.get("/marketplace")
async def get_marketplace(
    category: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    source: Optional[str] = Query(None, pattern="^(local|cloud|all)$"),
    db: AsyncSession = Depends(get_db),
    _current_user: User | None = Depends(get_current_user_optional),
):
    from app.cloud.client import is_cloud_enabled

    def _tag_marketplace_source(payload: dict, src: str) -> dict:
        if isinstance(payload, dict):
            for item in payload.get("items") or []:
                if isinstance(item, dict):
                    item["marketplace_source"] = src
        return payload

    if not is_cloud_enabled() or source == "local":
        local_result = await list_marketplace(db, category=category, search=search, page=page, page_size=page_size)
        return _tag_marketplace_source(local_result, "local")

    try:
        from app.cloud.sync import ensure_cloud_token
        token = await ensure_cloud_token()
        from app.cloud.client import cloud_marketplace
        cloud_result = await cloud_marketplace(
            token=token, category=category, search=search, page=page, page_size=page_size
        )
        return _tag_marketplace_source(cloud_result, "cloud")
    except Exception:
        logger.warning("Failed to fetch marketplace from central server, falling back to local", exc_info=True)
        local_result = await list_marketplace(db, category=category, search=search, page=page, page_size=page_size)
        return _tag_marketplace_source(local_result, "local")


# ---------------------------------------------------------------------------
# User installs
# ---------------------------------------------------------------------------

@router.get("/installed")
async def get_installed_skills(
    workspace_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    # 未登录：返回空列表，避免与技能市场并行请求时 401 触发前端强制登出
    if current_user is None:
        return []
    # Auto-install builtins on first access
    await auto_install_builtins(db, current_user.id)
    return await list_installed(db, current_user.id, workspace_id=workspace_id)


@router.post("/cloud-install")
async def install_cloud_skill(
    data: SkillInstallRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Download a skill from the central server and install it locally."""
    from app.cloud.client import is_cloud_enabled, cloud_download_skill
    from app.cloud.sync import ensure_cloud_token

    if not is_cloud_enabled():
        raise HTTPException(400, "未配置中心服务器")

    token = await ensure_cloud_token()
    if not token:
        raise HTTPException(401, "未登录中心服务器")

    try:
        cloud_skill = await cloud_download_skill(token, data.skill_id)
    except Exception as exc:
        raise HTTPException(502, f"从中心服务器下载技能失败: {exc}")

    slug = cloud_skill.get("slug", "")
    existing = (await db.execute(select(Skill).where(Skill.slug == slug))).scalar_one_or_none()

    if existing:
        try:
            return await install_skill(db, current_user.id, existing.id, data.workspace_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    skill = Skill(
        name=cloud_skill.get("name", slug),
        slug=slug,
        description=cloud_skill.get("description", ""),
        category=cloud_skill.get("category", "general"),
        skill_type=cloud_skill.get("skill_type", "custom"),
        config=cloud_skill.get("config"),
        version=cloud_skill.get("version", "1.0.0"),
        is_public=True,
        author_id=current_user.id,
    )
    db.add(skill)
    await db.flush()

    from app.models.skill_install import SkillInstall as SkillInstallModel
    install = SkillInstallModel(user_id=current_user.id, skill_id=skill.id, workspace_id=data.workspace_id, is_active=True)
    db.add(install)
    skill.install_count = 1
    await db.commit()
    await db.refresh(skill)

    d = _skill_dict(skill)
    d["install_id"] = install.id
    d["is_active"] = True
    d["_source"] = "cloud"
    return d


@router.post("/install")
async def install_skill_endpoint(
    data: SkillInstallRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await install_skill(db, current_user.id, data.skill_id, data.workspace_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.delete("/installed/{install_id}")
async def uninstall_skill_endpoint(
    install_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ok = await uninstall_skill(db, current_user.id, install_id)
    if not ok:
        raise HTTPException(404, "安装记录不存在")
    return {"ok": True}


@router.put("/installed/{install_id}")
async def update_installed_skill(
    install_id: int,
    data: SkillInstallUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await update_install(db, current_user.id, install_id, **data.model_dump(exclude_none=True))
    if not result:
        raise HTTPException(404, "安装记录不存在")
    return result


# ---------------------------------------------------------------------------
# Skill management (create / edit / delete — for admins / authors)
# ---------------------------------------------------------------------------

@router.post("/")
async def create_skill(
    data: SkillCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Check slug uniqueness
    existing = (await db.execute(select(Skill).where(Skill.slug == data.slug))).scalar_one_or_none()
    if existing:
        raise HTTPException(409, f"技能标识 '{data.slug}' 已存在")

    # Validate config structure based on skill_type
    if data.config:
        try:
            import json as _json
            config_obj = _json.loads(data.config) if isinstance(data.config, str) else data.config
            if data.skill_type == "prompt" and "prompt_template" not in config_obj:
                raise HTTPException(400, "Prompt 类型技能的 config 必须包含 prompt_template 字段")
            if data.skill_type == "mcp" and "mcp_server_config_id" not in config_obj:
                raise HTTPException(400, "MCP 类型技能的 config 必须包含 mcp_server_config_id 字段")
        except (_json.JSONDecodeError, TypeError):
            raise HTTPException(400, "config 格式无效，必须为合法 JSON")

    skill = Skill(
        name=data.name,
        slug=data.slug,
        description=data.description,
        icon_url=data.icon_url,
        category=data.category,
        skill_type=data.skill_type,
        config=data.config,
        is_public=data.is_public,
        author_id=current_user.id,
    )
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    return _skill_dict(skill)


# ---------------------------------------------------------------------------
# Prompt skills
# ---------------------------------------------------------------------------

@router.post("/prompt-skills")
async def create_prompt_skill_endpoint(
    data: PromptSkillCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a prompt-template skill."""
    try:
        skill = await create_prompt_skill(
            db,
            user_id=current_user.id,
            name=data.name,
            slug=data.slug,
            description=data.description,
            prompt_template=data.prompt_template,
            output_format=data.output_format,
            variables=data.variables,
            category=data.category,
            is_public=data.is_public,
            icon_url=data.icon_url,
        )
        return _skill_dict(skill)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/prompt-skills")
async def list_own_prompt_skills(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Skill)
        .where(
            Skill.author_id == current_user.id,
            Skill.skill_type == "prompt",
        )
        .order_by(Skill.created_at.desc())
    )
    return [_skill_dict(skill) for skill in result.scalars().all()]


# ---------------------------------------------------------------------------
# Skill chains
# ---------------------------------------------------------------------------

@router.post("/chains")
async def create_chain(
    data: ChainCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await skill_chain_service.create_chain(
            db,
            user_id=current_user.id,
            name=data.name,
            description=data.description,
            steps=data.steps,
            is_public=data.is_public,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/chains")
async def list_chains(
    include_public: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await skill_chain_service.list_chains(db, current_user.id, include_public=include_public)


@router.get("/chains/{chain_id}")
async def get_chain(
    chain_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await skill_chain_service.get_chain(
        db,
        chain_id,
        user_id=current_user.id,
        allow_public=True,
    )
    if not result:
        raise HTTPException(404, "技能链不存在")
    return result


@router.put("/chains/{chain_id}")
async def update_chain(
    chain_id: int,
    data: ChainUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        result = await skill_chain_service.update_chain(
            db,
            current_user.id,
            chain_id,
            name=data.name,
            description=data.description,
            steps=data.steps,
            is_public=data.is_public,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if not result:
        raise HTTPException(404, "技能链不存在或无权限修改")
    return result


@router.post("/chains/{chain_id}/execute")
async def execute_chain(
    chain_id: int,
    data: ChainExecuteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Execute a skill chain with the given initial input."""
    model_config = None
    if data.llm_model_id:
        model_config = (await db.execute(
            select(ModelConfig).where(ModelConfig.id == data.llm_model_id)
        )).scalar_one_or_none()

    if not model_config:
        model_config = (await db.execute(
            select(ModelConfig).where(
                ModelConfig.user_id == current_user.id,
                ModelConfig.model_type == ModelType.LLM,
                ModelConfig.is_default == True,
            )
        )).scalar_one_or_none()

    if not model_config:
        raise HTTPException(400, "未找到可用的 LLM 模型，请先配置模型")

    try:
        return await skill_chain_service.execute_chain(
            db,
            current_user.id,
            chain_id,
            data.initial_input,
            model_config,
            kb_id=data.kb_id,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except RuntimeError as exc:
        raise HTTPException(500, str(exc))


@router.delete("/chains/{chain_id}")
async def delete_chain(
    chain_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ok = await skill_chain_service.delete_chain(db, current_user.id, chain_id)
    if not ok:
        raise HTTPException(404, "技能链不存在或无权限删除")
    return {"ok": True}


class SkillRating(BaseModel):
    rating: float = Field(ge=1, le=5)


@router.post("/installed/{install_id}/rate")
async def rate_skill(
    install_id: int,
    data: SkillRating,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Rate an installed skill (1-5 stars)."""
    from app.models.skill_install import SkillInstall
    from sqlalchemy import func as sa_func

    install = (await db.execute(
        select(SkillInstall).where(SkillInstall.id == install_id, SkillInstall.user_id == current_user.id)
    )).scalar_one_or_none()
    if not install:
        raise HTTPException(404, "未找到该安装记录")

    install.rating = data.rating
    await db.flush()

    avg_result = await db.execute(
        select(sa_func.avg(SkillInstall.rating), sa_func.count(SkillInstall.rating))
        .where(SkillInstall.skill_id == install.skill_id, SkillInstall.rating.isnot(None))
    )
    avg_row = avg_result.one()
    skill = (await db.execute(select(Skill).where(Skill.id == install.skill_id))).scalar_one_or_none()
    if skill:
        skill.avg_rating = round(float(avg_row[0]), 2) if avg_row[0] else None
        skill.rating_count = int(avg_row[1] or 0)

    await db.commit()
    return {"ok": True, "avg_rating": skill.avg_rating if skill else None, "rating_count": skill.rating_count if skill else 0}


@router.get("/templates")
async def list_skill_templates():
    """Return predefined skill templates (static list; no auth — used on skills page load)."""
    return [
        {
            "name": "文本翻译",
            "slug": "translate",
            "description": "将文本翻译为指定语言",
            "category": "utility",
            "prompt_template": "请将以下文本翻译为 {{target_language}}。保持原始格式和语气，确保译文自然流畅。\n\n原文：\n{{text}}",
            "output_format": "text",
        },
        {
            "name": "内容摘要",
            "slug": "summarize",
            "description": "将长文本压缩为简洁的摘要",
            "category": "data",
            "prompt_template": "请将以下内容压缩为一段简洁的摘要，保留关键信息和核心观点，摘要长度不超过 {{max_length}} 字。\n\n内容：\n{{text}}",
            "output_format": "text",
        },
        {
            "name": "代码审查",
            "slug": "code-review",
            "description": "对代码进行审查，提出改进建议",
            "category": "utility",
            "prompt_template": "请对以下 {{language}} 代码进行审查，从以下方面给出建议：\n1. 代码质量和可读性\n2. 潜在的 bug 或安全问题\n3. 性能优化机会\n4. 最佳实践建议\n\n```{{language}}\n{{code}}\n```",
            "output_format": "markdown",
        },
        {
            "name": "数据提取",
            "slug": "extract-data",
            "description": "从非结构化文本中提取结构化数据",
            "category": "data",
            "prompt_template": "请从以下文本中提取结构化信息，以 JSON 格式返回。\n\n需要提取的字段：{{fields}}\n\n文本：\n{{text}}",
            "output_format": "json",
        },
        {
            "name": "邮件起草",
            "slug": "draft-email",
            "description": "根据要点起草专业邮件",
            "category": "general",
            "prompt_template": "请根据以下要点起草一封{{tone}}的邮件。\n\n收件人：{{recipient}}\n主题：{{subject}}\n要点：\n{{key_points}}",
            "output_format": "text",
        },
        {
            "name": "会议纪要",
            "slug": "meeting-notes",
            "description": "将会议记录整理为结构化纪要",
            "category": "general",
            "prompt_template": "请将以下会议记录整理为结构化的会议纪要，包含：\n1. 会议概要\n2. 讨论要点\n3. 决议事项\n4. 待办事项（含负责人和截止日期）\n\n会议记录：\n{{transcript}}",
            "output_format": "markdown",
        },
    ]


def _skill_dict(s: Skill) -> dict:
    data = {
        "id": s.id,
        "name": s.name,
        "slug": s.slug,
        "description": s.description,
        "icon_url": s.icon_url,
        "category": s.category,
        "skill_type": s.skill_type,
        "config": s.config,
        "is_public": s.is_public,
        "author_id": s.author_id,
        "install_count": s.install_count,
        "total_use_count": getattr(s, "total_use_count", 0) or 0,
        "avg_rating": getattr(s, "avg_rating", None),
        "rating_count": getattr(s, "rating_count", 0) or 0,
        "version": s.version,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }
    if s.skill_type == "prompt":
        try:
            config = json.loads(s.config) if s.config else {}
        except (json.JSONDecodeError, TypeError):
            config = {}
        data["prompt_template"] = config.get("prompt_template", "")
        data["output_format"] = config.get("output_format", "text")
        data["variables"] = config.get("variables") or []
    return data


# ---------------------------------------------------------------------------
# OpenClaw Skills integration
# ---------------------------------------------------------------------------

@router.get("/openclaw/search")
async def search_openclaw_skills(
    q: str = Query("", min_length=0),
    current_user: User = Depends(get_current_user),
):
    """Search skills from the OpenClaw community registry."""
    import httpx

    if not q.strip():
        q = "agent"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://clawhub.ai/api/search",
                params={"q": q},
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            return {"results": [
                {
                    "slug": r.get("slug", ""),
                    "name": r.get("displayName", r.get("slug", "")),
                    "summary": r.get("summary", ""),
                    "version": r.get("version"),
                    "score": r.get("score"),
                }
                for r in results
            ]}
    except Exception as exc:
        raise HTTPException(502, f"OpenClaw 搜索失败: {exc}")


@router.get("/openclaw/detail/{slug}")
async def get_openclaw_skill_detail(
    slug: str,
    current_user: User = Depends(get_current_user),
):
    """Get detailed info for a specific OpenClaw skill."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://clawhub.ai/api/skill",
                params={"slug": slug},
            )
            resp.raise_for_status()
            data = resp.json()

            owner = data.get("owner", {}).get("handle", "openclaw")
            skill_md = ""
            try:
                md_resp = await client.get(
                    f"https://raw.githubusercontent.com/openclaw/skills/main/skills/{owner}/{slug}/SKILL.md",
                    timeout=5,
                )
                if md_resp.status_code == 200:
                    skill_md = md_resp.text
            except Exception:
                pass
            data["skill_md"] = skill_md

            return data
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(404, "OpenClaw 技能不存在")
        raise HTTPException(502, f"OpenClaw 查询失败: {exc}")
    except Exception as exc:
        raise HTTPException(502, f"OpenClaw 查询失败: {exc}")


@router.post("/openclaw/import/{slug}")
async def import_openclaw_skill(
    slug: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Import an OpenClaw skill as a prompt skill into the local system."""
    import httpx

    existing = (await db.execute(
        select(Skill).where(Skill.slug == f"oc-{slug}")
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(409, f"技能 '{slug}' 已导入")

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://clawhub.ai/api/skill",
                params={"slug": slug},
            )
            resp.raise_for_status()
            data = resp.json()
            skill_info = data.get("skill", {})
            owner = data.get("owner", {}).get("handle", "openclaw")

            instruction = skill_info.get("summary", "")
            try:
                md_resp = await client.get(
                    f"https://raw.githubusercontent.com/openclaw/skills/main/skills/{owner}/{slug}/SKILL.md",
                    timeout=5,
                )
                if md_resp.status_code == 200:
                    content = md_resp.text
                    body = content.split("---", 2)[-1].strip() if content.startswith("---") else content
                    if body:
                        instruction = body
            except Exception:
                pass

            config = {
                "prompt_template": instruction,
                "output_format": "text",
                "source": "openclaw",
                "openclaw_slug": slug,
                "openclaw_owner": owner,
            }

            skill = Skill(
                name=skill_info.get("displayName", slug),
                slug=f"oc-{slug}",
                description=skill_info.get("summary", "")[:500],
                category="openclaw",
                skill_type="prompt",
                config=json.dumps(config, ensure_ascii=False),
                is_public=False,
                author_id=current_user.id,
                version=data.get("latestVersion", {}).get("version", "1.0.0"),
            )
            db.add(skill)
            await db.commit()
            await db.refresh(skill)
            return {
                "message": f"已导入 OpenClaw 技能「{skill.name}」",
                "skill_id": skill.id,
                "name": skill.name,
            }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"导入失败: {exc}")


# ---------------------------------------------------------------------------
# Bulk import ALL OpenClaw skills via GitHub repo
# ---------------------------------------------------------------------------

_import_lock = asyncio.Lock()
_import_progress: dict = {"running": False, "inserted": 0, "skipped": 0, "total": 0, "error": None}

# ---------------------------------------------------------------------------
# Batch translate OpenClaw skills to Chinese via LLM
# ---------------------------------------------------------------------------

_translate_progress: dict = {
    "running": False,
    "translated": 0,
    "skipped": 0,
    "failed": 0,
    "total": 0,
    "error": None,
}


@router.post("/openclaw/translate-batch")
async def translate_openclaw_skills_batch(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Batch-translate all English OpenClaw skills to Chinese using the user's default LLM."""
    if _translate_progress["running"]:
        return {"status": "already_running", "progress": _translate_progress}

    default_model = (await db.execute(
        select(ModelConfig).where(
            ModelConfig.user_id == current_user.id,
            ModelConfig.model_type == ModelType.LLM,
            ModelConfig.is_default == True,
        )
    )).scalar_one_or_none()
    if not default_model:
        raise HTTPException(400, "请先配置默认 LLM 模型")

    oc_count = (await db.execute(
        select(func.count(Skill.id)).where(Skill.category == "openclaw")
    )).scalar() or 0
    if oc_count == 0:
        raise HTTPException(400, "没有已导入的 OpenClaw 技能")

    _translate_progress.update(
        running=True, translated=0, skipped=0, failed=0, total=oc_count, error=None,
    )
    background_tasks.add_task(_run_batch_translate, default_model.id, current_user.id)
    return {
        "status": "started",
        "total": oc_count,
        "message": "后台批量翻译已启动，请通过 GET /skills/openclaw/translate-progress 查看进度",
    }


@router.get("/openclaw/translate-progress")
async def translate_progress(current_user: User = Depends(get_current_user)):
    return _translate_progress


async def _run_batch_translate(model_config_id: int, user_id: int):
    from app.core.llm_client import chat_completion
    from sqlalchemy import func as sa_func

    batch_size = 5

    try:
        async with async_session() as db:
            model_config = (await db.execute(
                select(ModelConfig).where(ModelConfig.id == model_config_id)
            )).scalar_one_or_none()
            if not model_config:
                _translate_progress.update(running=False, error="LLM 模型配置不存在")
                return

            oc_skills = (await db.execute(
                select(Skill).where(Skill.category == "openclaw")
                .order_by(Skill.id)
            )).scalars().all()

            _translate_progress["total"] = len(oc_skills)

            for i in range(0, len(oc_skills), batch_size):
                batch = oc_skills[i:i + batch_size]
                items_for_llm = []
                batch_skills = []

                for skill in batch:
                    if _is_already_chinese(skill.name) and _is_already_chinese(skill.description or ""):
                        _translate_progress["skipped"] += 1
                        continue
                    items_for_llm.append({
                        "id": skill.id,
                        "name": skill.name,
                        "description": skill.description or "",
                    })
                    batch_skills.append(skill)

                if not items_for_llm:
                    continue

                try:
                    prompt = _build_translate_prompt(items_for_llm)
                    result = await chat_completion(
                        model_config,
                        [
                            {"role": "system", "content": "你是一个专业的技术翻译助手。将 AI 技能的名称和描述从英文翻译为简洁自然的中文。保持技术术语的准确性。只返回 JSON，不要任何解释。"},
                            {"role": "user", "content": prompt},
                        ],
                    )
                    translated = _parse_translate_result(result, items_for_llm)
                    await _apply_translations(db, translated)
                    _translate_progress["translated"] += len(translated)
                    _translate_progress["failed"] += len(items_for_llm) - len(translated)
                except Exception as exc:
                    logger.warning("Batch translate error: %s", exc, exc_info=True)
                    _translate_progress["failed"] += len(items_for_llm)

        _translate_progress["running"] = False
    except Exception as exc:
        _translate_progress.update(running=False, error=str(exc))


def _is_already_chinese(text: str) -> bool:
    if not text.strip():
        return True
    chinese_chars = sum(1 for ch in text if '\u4e00' <= ch <= '\u9fff')
    return chinese_chars / max(len(text.strip()), 1) > 0.3


def _build_translate_prompt(items: list[dict]) -> str:
    entries = json.dumps(items, ensure_ascii=False, indent=2)
    return (
        f"请将以下 AI 技能信息翻译为中文。返回相同结构的 JSON 数组，每个元素包含 id、name（中文名称，简洁）、description（中文描述，一句话）。\n\n"
        f"```json\n{entries}\n```\n\n"
        f"只返回 JSON 数组，不需要代码块标记或任何解释。"
    )


def _parse_translate_result(raw: str, originals: list[dict]) -> list[dict]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1:
            try:
                parsed = json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                return []
        else:
            return []

    if not isinstance(parsed, list):
        return []

    original_ids = {item["id"] for item in originals}
    results = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        if item_id not in original_ids:
            continue
        name = item.get("name", "")
        desc = item.get("description", "")
        if name:
            results.append({"id": item_id, "name": name[:100], "description": (desc or "")[:500]})
    return results


async def _apply_translations(db: AsyncSession, translations: list[dict]):
    from sqlalchemy import update as sa_update
    for item in translations:
        await db.execute(
            sa_update(Skill)
            .where(Skill.id == item["id"])
            .values(name=item["name"], description=item["description"])
        )
    await db.commit()


@router.post("/openclaw/import-all")
async def import_all_openclaw_skills(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_admin_user),
):
    """Clone the openclaw/skills repo and bulk-import every skill."""
    if _import_progress["running"]:
        return {"status": "already_running", "progress": _import_progress}

    _import_progress.update(running=True, inserted=0, skipped=0, total=0, error=None)
    background_tasks.add_task(_run_bulk_import, current_user.id)
    return {"status": "started", "message": "后台批量导入已启动，请通过 GET /skills/openclaw/import-progress 查看进度"}


@router.get("/openclaw/import-progress")
async def import_progress(current_user: User = Depends(get_current_user)):
    return _import_progress


async def _run_bulk_import(admin_user_id: int):
    import io
    import shutil
    import tarfile
    import tempfile
    from pathlib import Path

    import httpx

    tmp_dir = tempfile.mkdtemp(prefix="openclaw_skills_")
    try:
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            resp = await client.get("https://github.com/openclaw/skills/archive/refs/heads/main.tar.gz")
            resp.raise_for_status()

        loop = asyncio.get_event_loop()
        def _extract():
            with tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:gz") as tar:
                tar.extractall(tmp_dir)
        await loop.run_in_executor(None, _extract)

        extracted = list(Path(tmp_dir).iterdir())
        repo_root = extracted[0] if extracted else Path(tmp_dir)
        skills_root = repo_root / "skills"
        if not skills_root.is_dir():
            _import_progress.update(running=False, error=f"skills/ directory not found (root={repo_root.name})")
            return

        skills_data: list[dict] = []
        for owner_dir in sorted(skills_root.iterdir()):
            if not owner_dir.is_dir():
                continue
            for skill_dir in sorted(owner_dir.iterdir()):
                if not skill_dir.is_dir():
                    continue
                parsed = _parse_skill_dir(skill_dir, owner_dir.name)
                if parsed:
                    skills_data.append(parsed)

        _import_progress["total"] = len(skills_data)

        batch_size = 100
        for i in range(0, len(skills_data), batch_size):
            batch = skills_data[i:i + batch_size]
            async with async_session() as db:
                slugs = [s["slug"] for s in batch]
                existing = set(
                    (await db.execute(
                        select(Skill.slug).where(Skill.slug.in_(slugs))
                    )).scalars().all()
                )
                for data in batch:
                    if data["slug"] in existing:
                        _import_progress["skipped"] += 1
                        continue
                    skill = Skill(
                        name=data["name"],
                        slug=data["slug"],
                        description=data["description"],
                        category=data["category"],
                        skill_type=data["skill_type"],
                        config=data["config"],
                        is_public=True,
                        author_id=admin_user_id,
                        version=data["version"],
                    )
                    db.add(skill)
                    _import_progress["inserted"] += 1
                await db.commit()

        _import_progress["running"] = False
    except Exception as exc:
        _import_progress.update(running=False, error=str(exc))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@router.post("/import-local")
async def import_local_skills(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_admin_user),
):
    """Import skills from the local skills/skills/ directory (pre-downloaded/translated).

    This reads the skills/ directory at the project root (or DATA_DIR/skills/)
    and bulk-imports all valid skill packages into the database.
    """
    if _import_progress["running"]:
        return {"status": "already_running", "progress": _import_progress}

    _import_progress.update(running=True, inserted=0, skipped=0, total=0, error=None)
    background_tasks.add_task(_run_local_import, current_user.id)
    return {"status": "started", "message": "本地技能批量导入已启动，请通过 GET /skills/openclaw/import-progress 查看进度"}


async def _run_local_import(admin_user_id: int):
    """Scan local skills/skills/ directory and import into database."""
    from pathlib import Path
    import os
    from app.config import settings as _settings

    # Look for skills directory in multiple locations
    # The structure is skills/skills/<author>/<skill>/ — the inner "skills" contains author dirs
    candidates = [
        Path("/app/skills/skills"),  # Docker mount (highest priority)
        Path(__file__).resolve().parents[3] / "skills" / "skills",  # project_root/skills/skills/
        Path(os.environ.get("SKILLS_DIR", "")) / "skills" if os.environ.get("SKILLS_DIR") else None,
        Path(getattr(_settings, "DATA_DIR", "")) / "skills" / "skills" if getattr(_settings, "DATA_DIR", "") else None,
    ]
    skills_root = None
    for p in candidates:
        if p and p.is_dir():
            skills_root = p
            break

    if not skills_root:
        _import_progress.update(running=False, error="未找到本地 skills/skills/ 目录，请确认目录存在")
        return

    try:
        skills_data: list[dict] = []
        for owner_dir in sorted(skills_root.iterdir()):
            if not owner_dir.is_dir():
                continue
            for skill_dir in sorted(owner_dir.iterdir()):
                if not skill_dir.is_dir():
                    continue
                parsed = _parse_skill_dir(skill_dir, owner_dir.name)
                if parsed:
                    skills_data.append(parsed)

        _import_progress["total"] = len(skills_data)

        batch_size = 200
        for i in range(0, len(skills_data), batch_size):
            batch = skills_data[i:i + batch_size]
            async with async_session() as db:
                slugs = [s["slug"] for s in batch]
                existing = set(
                    (await db.execute(
                        select(Skill.slug).where(Skill.slug.in_(slugs))
                    )).scalars().all()
                )
                for data in batch:
                    if data["slug"] in existing:
                        _import_progress["skipped"] += 1
                        continue
                    try:
                        skill = Skill(
                            name=data["name"],
                            slug=data["slug"],
                            description=data["description"],
                            category=data["category"],
                            skill_type=data["skill_type"],
                            config=data["config"],
                            is_public=True,
                            author_id=admin_user_id,
                            version=data["version"],
                        )
                        db.add(skill)
                        await db.flush()
                        _import_progress["inserted"] += 1
                    except Exception:
                        await db.rollback()
                        _import_progress["skipped"] += 1
                await db.commit()

        _import_progress["running"] = False
    except Exception as exc:
        _import_progress.update(running=False, error=str(exc))


def _parse_skill_dir(skill_path, owner_fallback: str = "") -> dict | None:
    from pathlib import Path
    meta_file = skill_path / "_meta.json"
    skill_file = skill_path / "SKILL.md"

    if not meta_file.exists():
        return None

    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
    except Exception:
        return None

    owner = meta.get("owner", owner_fallback)
    slug = meta.get("slug", skill_path.name)
    display_name = meta.get("displayName", slug)
    version = (meta.get("latest") or {}).get("version", "1.0.0")

    description = ""
    instruction = ""
    if skill_file.exists():
        try:
            content = skill_file.read_text(encoding="utf-8")
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    for line in parts[1].split("\n"):
                        s = line.strip()
                        if s.startswith("description:"):
                            description = s[len("description:"):].strip().strip("|").strip()
                    body = parts[2].strip()
                else:
                    body = content
            else:
                body = content
            instruction = body[:4000] if body else ""
            if not description and body:
                first_lines = body.split("\n", 3)
                description = " ".join(l.strip("#").strip() for l in first_lines[:2] if l.strip())[:500]
        except Exception:
            pass

    config = json.dumps({
        "prompt_template": instruction,
        "output_format": "text",
        "source": "openclaw",
        "openclaw_slug": slug,
        "openclaw_owner": owner,
    }, ensure_ascii=False)

    full_slug = f"oc-{slug}"
    if len(full_slug) > 100:
        full_slug = full_slug[:100]

    return {
        "slug": full_slug,
        "name": display_name[:100],
        "description": description[:500],
        "category": "openclaw",
        "skill_type": "prompt",
        "config": config,
        "version": version[:20] if version else "1.0.0",
    }


import re as _re

_OPENCLAW_PATH_REPLACEMENTS = [
    (r"%USERPROFILE%\\\.openclaw\\workspace\\skills\\", "zhishu-data/skills/"),
    (r"%USERPROFILE%\\\.openclaw\\", "zhishu-data/"),
    (r"~/\.openclaw/workspace/skills/", "zhishu-data/skills/"),
    (r"~/\.openclaw/", "zhishu-data/"),
    (r"\$HOME/\.openclaw/workspace/skills/", "zhishu-data/skills/"),
    (r"\$HOME/\.openclaw/", "zhishu-data/"),
    (r"\$\{OPENCLAW_TMUX_SOCKET_DIR:-\$\{CLAWDBOT_TMUX_SOCKET_DIR:-\$\{TMPDIR:-/tmp\}/openclaw-tmux-sockets\}\}", "/tmp/zhishu-sockets"),
    (r"openclaw\.json", "zhishu-config.json"),
    (r"clawdbot\.json", "zhishu-config.json"),
]


@router.post("/admin/fix-openclaw-paths")
async def admin_fix_openclaw_paths(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    result = await db.execute(
        select(Skill).where(Skill.category == "openclaw", Skill.skill_type == "prompt")
    )
    skills = result.scalars().all()
    updated = 0

    for skill in skills:
        if not skill.config:
            continue
        original = skill.config
        new_config = original
        for pattern, replacement in _OPENCLAW_PATH_REPLACEMENTS:
            new_config = _re.sub(pattern, replacement, new_config)
        if new_config != original:
            skill.config = new_config
            updated += 1

    await db.commit()
    return {"total_openclaw_skills": len(skills), "updated": updated}


# ---------------------------------------------------------------------------
# Central server skill detail (proxy — must be before /{skill_id})
# ---------------------------------------------------------------------------

@router.get("/cloud/{cloud_skill_id}")
async def get_cloud_skill_detail(
    cloud_skill_id: int,
):
    """从中心服务器拉取技能详情。已上架技能可无 Token；未上架需中心侧 Token（作者/管理员）。"""
    from app.cloud.client import is_cloud_enabled, cloud_get_skill
    from app.cloud.sync import ensure_cloud_token

    if not is_cloud_enabled():
        raise HTTPException(400, "未配置中心服务器")
    token = await ensure_cloud_token()
    try:
        return await cloud_get_skill(cloud_skill_id, token)
    except Exception as exc:
        import httpx
        if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
            if exc.response.status_code == 404:
                raise HTTPException(404, "技能不存在或未上架") from exc
            logger.warning("cloud_get_skill HTTP %s", exc.response.status_code)
        else:
            logger.warning("cloud_get_skill failed: %s", exc, exc_info=True)
        raise HTTPException(502, "从中心服务器获取技能详情失败") from exc


# ---------------------------------------------------------------------------
# Skill CRUD by ID (must be LAST — /{skill_id} catches any single-segment path)
# ---------------------------------------------------------------------------

@router.get("/{skill_id}")
async def get_skill(
    skill_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(404, "技能不存在")
    if not skill.is_public and (current_user is None or skill.author_id != current_user.id):
        raise HTTPException(404, "技能不存在")
    return _skill_dict(skill)


@router.put("/{skill_id}")
async def edit_skill(
    skill_id: int,
    data: SkillUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    skill = (await db.execute(
        select(Skill).where(Skill.id == skill_id, Skill.author_id == current_user.id)
    )).scalar_one_or_none()
    if not skill:
        raise HTTPException(404, "技能不存在或无权限编辑")

    updates = data.model_dump(exclude_none=True)
    prompt_fields = {
        "prompt_template": updates.pop("prompt_template", None),
        "output_format": updates.pop("output_format", None),
        "variables": updates.pop("variables", None),
    }
    if skill.skill_type == "prompt" and any(v is not None for v in prompt_fields.values()):
        from app.core.tools.prompt_skill import PromptSkillTool
        current_config = json.loads(skill.config) if skill.config else {}
        for key, value in prompt_fields.items():
            if value is not None:
                current_config[key] = value
        if prompt_fields["prompt_template"] is not None and prompt_fields["variables"] is None:
            current_config["variables"] = PromptSkillTool._detect_variables(
                current_config.get("prompt_template", "")
            )
        updates["config"] = json.dumps(current_config, ensure_ascii=False)

    for k, v in updates.items():
        setattr(skill, k, v)
    await db.commit()
    await db.refresh(skill)
    return _skill_dict(skill)


@router.post("/{skill_id}/publish-to-cloud")
async def publish_skill_to_cloud(
    skill_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """将本地技能发布到中心服务器市场（需管理员审核后上架）。"""
    from app.cloud.client import is_cloud_enabled, cloud_publish_skill
    from app.cloud.sync import ensure_cloud_token

    if not is_cloud_enabled():
        raise HTTPException(400, "未配置中心服务器，无法发布")
    token = await ensure_cloud_token()
    if not token:
        raise HTTPException(401, "请先登录中心服务器")

    skill = (await db.execute(
        select(Skill).where(Skill.id == skill_id, Skill.author_id == current_user.id)
    )).scalar_one_or_none()
    if not skill:
        raise HTTPException(404, "技能不存在或无权限")

    if skill.skill_type not in ("prompt", "custom"):
        raise HTTPException(400, f"仅支持发布 prompt、custom 类型技能，当前为 {skill.skill_type}")

    payload = {
        "name": skill.name,
        "slug": skill.slug,
        "description": skill.description or "",
        "category": skill.category or "general",
        "skill_type": skill.skill_type,
        "version": skill.version or "1.0.0",
        "config": skill.config,
        "icon_url": skill.icon_url,
    }
    try:
        result = await cloud_publish_skill(token, payload)
        return {"message": "已提交审核，管理员通过后将出现在云端市场", "skill": result}
    except Exception as exc:
        raise HTTPException(502, f"发布失败: {exc}")


@router.delete("/{skill_id}")
async def delete_skill(
    skill_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    skill = (await db.execute(
        select(Skill).where(Skill.id == skill_id, Skill.author_id == current_user.id)
    )).scalar_one_or_none()
    if not skill:
        raise HTTPException(404, "技能不存在或无权限删除")
    await db.delete(skill)
    await db.commit()
    return {"ok": True}
