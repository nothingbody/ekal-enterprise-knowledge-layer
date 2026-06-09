"""Skill service — seed built-in skills, manage installs, build per-request registries."""

from __future__ import annotations

import json
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update as sa_update

from app.models.skill import Skill, SkillType
from app.models.skill_install import SkillInstall

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Built-in skill definitions (slug → metadata)
# ---------------------------------------------------------------------------

BUILTIN_SKILLS: list[dict] = [
    {
        "slug": "knowledge_search",
        "name": "知识库搜索",
        "description": "在关联的知识库中检索与问题相关的文档片段",
        "category": "retrieval",
        "config": json.dumps({"tool_class": "KnowledgeSearchTool"}),
    },
    {
        "slug": "sql_query",
        "name": "数据库查询",
        "description": "将自然语言转换为 SQL 并查询关联的数据库",
        "category": "data",
        "config": json.dumps({"tool_class": "SQLQueryTool"}),
    },
    {
        "slug": "calculator",
        "name": "计算器",
        "description": "执行数学表达式计算",
        "category": "utility",
        "config": json.dumps({"tool_class": "CalculatorTool"}),
    },
    {
        "slug": "current_time",
        "name": "当前时间",
        "description": "获取当前日期和时间",
        "category": "utility",
        "config": json.dumps({"tool_class": "CurrentTimeTool"}),
    },
    {
        "slug": "web_search",
        "name": "网络搜索",
        "description": "搜索互联网获取实时信息",
        "category": "retrieval",
        "config": json.dumps({"tool_class": "WebSearchTool"}),
    },
]


async def seed_builtin_skills(db: AsyncSession) -> int:
    """Ensure all built-in skills exist in the database. Returns count of newly created."""
    created = 0
    for defn in BUILTIN_SKILLS:
        exists = (await db.execute(
            select(Skill.id).where(Skill.slug == defn["slug"])
        )).scalar_one_or_none()
        if exists:
            continue
        skill = Skill(
            name=defn["name"],
            slug=defn["slug"],
            description=defn["description"],
            category=defn.get("category", "general"),
            skill_type=SkillType.BUILTIN.value,
            config=defn.get("config"),
            is_public=True,
        )
        db.add(skill)
        created += 1
    if created:
        await db.commit()
        logger.info("Seeded %d built-in skills", created)
    return created


async def auto_install_builtins(db: AsyncSession, user_id: int) -> int:
    """Auto-install any missing built-in skills for a user."""
    builtin_skills = (await db.execute(
        select(Skill).where(Skill.skill_type == SkillType.BUILTIN.value, Skill.is_public == True)
    )).scalars().all()

    installed_skill_ids = {
        row[0]
        for row in (await db.execute(
            select(SkillInstall.skill_id).where(SkillInstall.user_id == user_id)
        )).all()
    }

    count = 0
    for skill in builtin_skills:
        if skill.id in installed_skill_ids:
            continue
        install = SkillInstall(user_id=user_id, skill_id=skill.id, is_active=True)
        db.add(install)
        count += 1
    if count:
        await db.commit()
    return count


# ---------------------------------------------------------------------------
# Build per-request ToolRegistry based on user's installed skills
# ---------------------------------------------------------------------------

# Map of builtin slug → tool class import path
_BUILTIN_TOOL_MAP: dict[str, str] = {
    "knowledge_search": "app.core.tools.builtin.knowledge_search.KnowledgeSearchTool",
    "sql_query": "app.core.tools.builtin.sql_query.SQLQueryTool",
    "calculator": "app.core.tools.builtin.calculator.CalculatorTool",
    "current_time": "app.core.tools.builtin.current_time.CurrentTimeTool",
    "web_search": "app.core.tools.builtin.web_search.WebSearchTool",
}


# Only allow importing tool classes from these package prefixes
_ALLOWED_IMPORT_PREFIXES = (
    "app.core.tools.builtin.",
    "app.core.tools.",
)


def _import_tool_class(dotted_path: str):
    """Dynamically import a tool class from a dotted module path.

    Only allows imports from whitelisted package prefixes to prevent
    arbitrary code execution via database manipulation.
    """
    if not any(dotted_path.startswith(prefix) for prefix in _ALLOWED_IMPORT_PREFIXES):
        raise ImportError(
            f"Tool import blocked: '{dotted_path}' is not in allowed prefixes "
            f"{_ALLOWED_IMPORT_PREFIXES}"
        )
    module_path, class_name = dotted_path.rsplit(".", 1)
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


async def build_user_registry(db: AsyncSession, user_id: int):
    """Build a ToolRegistry containing only the skills the user has installed & activated."""
    from app.core.tools.registry import ToolRegistry

    registry = ToolRegistry()

    # 1. Get user's active skill installs
    result = await db.execute(
        select(SkillInstall, Skill)
        .join(Skill, SkillInstall.skill_id == Skill.id)
        .where(SkillInstall.user_id == user_id, SkillInstall.is_active == True)
    )
    rows = result.all()

    for install, skill in rows:
        try:
            if skill.skill_type == SkillType.BUILTIN.value:
                _register_builtin(registry, skill)
            elif skill.skill_type == SkillType.MCP.value:
                _register_mcp(registry, skill, install)
            elif skill.skill_type == SkillType.PROMPT.value:
                _register_prompt(registry, skill)
        except Exception:
            logger.warning("Failed to load skill %s", skill.slug, exc_info=True)

    return registry


def _register_builtin(registry, skill: Skill) -> None:
    """Register a built-in tool into the registry."""
    import_path = _BUILTIN_TOOL_MAP.get(skill.slug)
    if not import_path:
        return
    try:
        tool_cls = _import_tool_class(import_path)
        registry.register(tool_cls())
    except Exception:
        logger.warning("Cannot import builtin tool: %s", import_path, exc_info=True)


def _register_mcp(registry, skill: Skill, install: SkillInstall) -> None:
    """Register MCP tools for a skill backed by an MCP server."""
    config = json.loads(skill.config) if skill.config else {}
    server_config_id = config.get("mcp_server_config_id")
    if not server_config_id:
        return

    from app.core.mcp_client import get_mcp_manager
    manager = get_mcp_manager()
    if not manager.is_connected(server_config_id):
        return

    from app.core.tools.mcp_bridge import McpToolWrapper
    tools = manager.get_all_tools()
    for tool_info in tools:
        if tool_info.server_config_id != server_config_id:
            continue
        wrapper = McpToolWrapper(
            tool_name=tool_info.name,
            tool_description=tool_info.description,
            input_schema=tool_info.input_schema,
            server_config_id=tool_info.server_config_id,
            server_name=tool_info.server_name,
        )
        registry.register(wrapper)


def _register_prompt(registry, skill: Skill) -> None:
    """Register a prompt-template skill as a PromptSkillTool."""
    config = json.loads(skill.config) if skill.config else {}
    prompt_template = config.get("prompt_template", "")
    if not prompt_template:
        logger.warning("Prompt skill %s has empty template, skipping", skill.slug)
        return

    from app.core.tools.prompt_skill import PromptSkillTool
    tool = PromptSkillTool(
        name=skill.slug,
        description=skill.description or skill.name,
        prompt_template=prompt_template,
        output_format=config.get("output_format", "text"),
        variables=config.get("variables"),
    )
    registry.register(tool)


# ---------------------------------------------------------------------------
# Prompt skill helpers
# ---------------------------------------------------------------------------

async def create_prompt_skill(
    db: AsyncSession,
    *,
    user_id: int,
    name: str,
    slug: str,
    description: str = "",
    prompt_template: str,
    output_format: str = "text",
    variables: list[str] | None = None,
    category: str = "prompt",
    is_public: bool = False,
    icon_url: str | None = None,
) -> Skill:
    """Create a new prompt-type skill and return the persisted object."""
    existing = (await db.execute(
        select(Skill.id).where(Skill.slug == slug)
    )).scalar_one_or_none()
    if existing:
        raise ValueError(f"技能标识 '{slug}' 已存在")

    if not variables:
        from app.core.tools.prompt_skill import PromptSkillTool
        variables = PromptSkillTool._detect_variables(prompt_template)

    config = json.dumps({
        "prompt_template": prompt_template,
        "output_format": output_format,
        "variables": variables,
    }, ensure_ascii=False)

    skill = Skill(
        name=name,
        slug=slug,
        description=description,
        icon_url=icon_url,
        category=category,
        skill_type=SkillType.PROMPT.value,
        config=config,
        is_public=is_public,
        author_id=user_id,
    )
    db.add(skill)
    await db.flush()

    install = SkillInstall(
        user_id=user_id,
        skill_id=skill.id,
        is_active=True,
    )
    db.add(install)
    skill.install_count = (skill.install_count or 0) + 1

    await db.commit()
    await db.refresh(skill)
    return skill


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------

async def list_marketplace(
    db: AsyncSession, category: Optional[str] = None,
    search: Optional[str] = None, page: int = 1, page_size: int = 50,
) -> dict:
    """List public skills in the marketplace."""
    filters = [Skill.is_public == True]
    if category:
        filters.append(Skill.category == category)
    if search:
        import re as _re
        escaped = _re.sub(r'([%_\\])', r'\\\1', search)
        filters.append(Skill.name.ilike(f"%{escaped}%"))

    total = (await db.execute(
        select(func.count(Skill.id)).where(*filters)
    )).scalar() or 0

    result = await db.execute(
        select(Skill).where(*filters)
        .order_by(Skill.install_count.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [_skill_to_dict(s) for s in result.scalars().all()]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


async def list_installed(db: AsyncSession, user_id: int, workspace_id: Optional[int] = None) -> list[dict]:
    """List skills installed by the user."""
    filters = [SkillInstall.user_id == user_id]
    if workspace_id:
        filters.append(SkillInstall.workspace_id == workspace_id)
    else:
        filters.append(SkillInstall.workspace_id.is_(None))

    result = await db.execute(
        select(SkillInstall, Skill)
        .join(Skill, SkillInstall.skill_id == Skill.id)
        .where(*filters)
        .order_by(SkillInstall.created_at.desc())
    )
    items = []
    for install, skill in result.all():
        d = _skill_to_dict(skill)
        d["install_id"] = install.id
        d["is_active"] = install.is_active
        d["config_override"] = install.config_override
        items.append(d)
    return items


async def install_skill(db: AsyncSession, user_id: int, skill_id: int, workspace_id: Optional[int] = None) -> dict:
    """Install a skill for the user."""
    # Check skill exists
    skill = (await db.execute(select(Skill).where(Skill.id == skill_id))).scalar_one_or_none()
    if not skill:
        raise ValueError("技能不存在")

    # Check not already installed
    existing = (await db.execute(
        select(SkillInstall).where(
            SkillInstall.user_id == user_id,
            SkillInstall.skill_id == skill_id,
            SkillInstall.workspace_id == workspace_id if workspace_id else SkillInstall.workspace_id.is_(None),
        )
    )).scalar_one_or_none()
    if existing:
        raise ValueError("技能已安装")

    install = SkillInstall(user_id=user_id, skill_id=skill_id, workspace_id=workspace_id, is_active=True)
    db.add(install)
    # Atomic increment to prevent race conditions
    from sqlalchemy import update as sa_update
    await db.execute(
        sa_update(Skill).where(Skill.id == skill_id)
        .values(install_count=Skill.install_count + 1)
    )
    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            raise ValueError("技能已安装")
        raise
    await db.refresh(install)

    d = _skill_to_dict(skill)
    d["install_id"] = install.id
    d["is_active"] = install.is_active
    return d


async def uninstall_skill(db: AsyncSession, user_id: int, install_id: int) -> bool:
    result = await db.execute(
        select(SkillInstall).where(SkillInstall.id == install_id, SkillInstall.user_id == user_id)
    )
    install = result.scalar_one_or_none()
    if not install:
        return False
    skill_id = install.skill_id
    await db.delete(install)
    # Atomic decrement on uninstall
    from sqlalchemy import update as sa_update
    await db.execute(
        sa_update(Skill).where(Skill.id == skill_id, Skill.install_count > 0)
        .values(install_count=Skill.install_count - 1)
    )
    await db.commit()
    return True


async def update_install(db: AsyncSession, user_id: int, install_id: int, **kwargs) -> Optional[dict]:
    result = await db.execute(
        select(SkillInstall).where(SkillInstall.id == install_id, SkillInstall.user_id == user_id)
    )
    install = result.scalar_one_or_none()
    if not install:
        return None
    for k, v in kwargs.items():
        if hasattr(install, k) and v is not None:
            setattr(install, k, v)
    await db.commit()
    await db.refresh(install)

    skill = (await db.execute(select(Skill).where(Skill.id == install.skill_id))).scalar_one_or_none()
    d = _skill_to_dict(skill) if skill else {}
    d["install_id"] = install.id
    d["is_active"] = install.is_active
    d["config_override"] = install.config_override
    return d


def _skill_to_dict(s: Skill) -> dict:
    return {
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
