"""Skill chain service — CRUD and sequential execution of skill chains."""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.skill import Skill, SkillType
from app.models.skill_install import SkillInstall
from app.models.skill_chain import SkillChain

logger = logging.getLogger(__name__)

_STEP_REF_PATTERN = re.compile(r"\{\{(\w+)\.output\}\}")


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

async def create_chain(
    db: AsyncSession,
    *,
    user_id: int,
    name: str,
    description: str | None = None,
    steps: list[dict],
    is_public: bool = False,
) -> dict:
    """Create a new skill chain after validating the steps."""
    if not steps:
        raise ValueError("技能链至少需要一个步骤")

    skill_ids = [s["skill_id"] for s in steps]
    await _validate_skills_installed(db, user_id, skill_ids)
    _validate_step_references(steps)

    chain = SkillChain(
        user_id=user_id,
        name=name,
        description=description,
        steps=json.dumps(steps, ensure_ascii=False),
        is_public=is_public,
    )
    db.add(chain)
    await db.commit()
    await db.refresh(chain)
    return _chain_to_dict(chain)


async def list_chains(
    db: AsyncSession,
    user_id: int,
    include_public: bool = False,
) -> list[dict]:
    """List chains owned by the user, optionally including public ones."""
    filters = [SkillChain.user_id == user_id]
    if include_public:
        from sqlalchemy import or_
        filters = [or_(SkillChain.user_id == user_id, SkillChain.is_public == True)]

    result = await db.execute(
        select(SkillChain).where(*filters).order_by(SkillChain.created_at.desc())
    )
    return [_chain_to_dict(c) for c in result.scalars().all()]


async def get_chain(
    db: AsyncSession,
    chain_id: int,
    *,
    user_id: int | None = None,
    allow_public: bool = True,
) -> Optional[dict]:
    chain = (await db.execute(
        select(SkillChain).where(SkillChain.id == chain_id)
    )).scalar_one_or_none()
    if not chain:
        return None
    if user_id is not None and chain.user_id != user_id:
        if not (allow_public and chain.is_public):
            return None
    return _chain_to_dict(chain)


async def update_chain(
    db: AsyncSession,
    user_id: int,
    chain_id: int,
    *,
    name: str | None = None,
    description: str | None = None,
    steps: list[dict] | None = None,
    is_public: bool | None = None,
) -> dict | None:
    chain = (await db.execute(
        select(SkillChain).where(SkillChain.id == chain_id, SkillChain.user_id == user_id)
    )).scalar_one_or_none()
    if not chain:
        return None

    if steps is not None:
        if not steps:
            raise ValueError("技能链至少需要一个步骤")
        skill_ids = [s["skill_id"] for s in steps]
        await _validate_skills_installed(db, user_id, skill_ids)
        _validate_step_references(steps)
        chain.steps = json.dumps(steps, ensure_ascii=False)
    if name is not None:
        chain.name = name
    if description is not None:
        chain.description = description
    if is_public is not None:
        chain.is_public = is_public

    await db.commit()
    await db.refresh(chain)
    return _chain_to_dict(chain)


async def delete_chain(db: AsyncSession, user_id: int, chain_id: int) -> bool:
    chain = (await db.execute(
        select(SkillChain).where(SkillChain.id == chain_id, SkillChain.user_id == user_id)
    )).scalar_one_or_none()
    if not chain:
        return False
    await db.delete(chain)
    await db.commit()
    return True


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

async def execute_chain(
    db: AsyncSession,
    user_id: int,
    chain_id: int,
    initial_input: str,
    model_config,
    *,
    kb_id: int | None = None,
) -> dict:
    """Execute a skill chain step-by-step.

    Each step's output is stored under its ``output_key`` and can be
    referenced by subsequent steps via ``{{output_key.output}}``.

    Returns::

        {
            "steps": [
                {"step_index": 0, "skill_slug": "...", "output": "...", "success": True},
                ...
            ],
            "final_output": "..."
        }
    """
    chain = (await db.execute(
        select(SkillChain).where(SkillChain.id == chain_id)
    )).scalar_one_or_none()
    if not chain:
        raise ValueError("技能链不存在")

    if chain.user_id != user_id and not chain.is_public:
        raise ValueError("无权执行该技能链")

    steps: list[dict] = json.loads(chain.steps)
    skill_ids = [s["skill_id"] for s in steps]
    skills_by_id = await _load_skills_map(db, skill_ids)
    await _validate_chain_skill_access(
        db,
        user_id=user_id,
        chain_owner_id=chain.user_id,
        allow_public_chain=bool(chain.is_public),
        skills_by_id=skills_by_id,
    )

    context: dict[str, str] = {"initial_input": initial_input}
    step_results: list[dict] = []

    for idx, step in enumerate(steps):
        skill = skills_by_id.get(step["skill_id"])
        if not skill:
            step_results.append({
                "step_index": idx,
                "skill_slug": None,
                "output": None,
                "success": False,
                "error": f"技能 id={step['skill_id']} 不存在",
            })
            continue

        input_mapping: dict = step.get("input_mapping", {})
        resolved_inputs = _resolve_inputs(input_mapping, context)

        try:
            output = await _execute_single_step(
                skill, resolved_inputs, model_config,
                db=db, user_id=user_id, kb_id=kb_id,
            )
            output_key = step.get("output_key", f"step{idx}")
            context[f"{output_key}.output"] = output
            step_results.append({
                "step_index": idx,
                "skill_slug": skill.slug,
                "output": output,
                "success": True,
            })
        except Exception as exc:
            logger.exception("Chain step %d (%s) failed", idx, skill.slug)
            step_results.append({
                "step_index": idx,
                "skill_slug": skill.slug,
                "output": None,
                "success": False,
                "error": str(exc),
            })
            break

    final_output = ""
    for sr in reversed(step_results):
        if sr.get("success") and sr.get("output"):
            final_output = sr["output"]
            break

    return {"steps": step_results, "final_output": final_output}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _validate_skills_installed(db: AsyncSession, user_id: int, skill_ids: list[int]) -> None:
    """Raise if any skill in *skill_ids* is not installed by the user."""
    if not skill_ids:
        return
    result = await db.execute(
        select(SkillInstall.skill_id).where(
            SkillInstall.user_id == user_id,
            SkillInstall.skill_id.in_(skill_ids),
            SkillInstall.is_active == True,
        )
    )
    installed = {row[0] for row in result.all()}
    missing = set(skill_ids) - installed
    if missing:
        raise ValueError(f"以下技能未安装或未激活: {missing}")


async def _validate_chain_skill_access(
    db: AsyncSession,
    *,
    user_id: int,
    chain_owner_id: int,
    allow_public_chain: bool,
    skills_by_id: dict[int, Skill],
) -> None:
    """Validate whether the current user may execute all skills referenced by a chain."""
    skill_ids = list(skills_by_id.keys())
    if not skill_ids:
        return

    result = await db.execute(
        select(SkillInstall.skill_id).where(
            SkillInstall.user_id == user_id,
            SkillInstall.skill_id.in_(skill_ids),
            SkillInstall.is_active == True,
        )
    )
    installed = {row[0] for row in result.all()}

    missing: set[int] = set()
    for skill_id, skill in skills_by_id.items():
        if skill_id in installed:
            continue
        if user_id == chain_owner_id:
            missing.add(skill_id)
            continue
        if allow_public_chain and (skill.is_public or skill.author_id == chain_owner_id):
            continue
        missing.add(skill_id)

    if missing:
        raise ValueError(f"以下技能未安装、未激活或不可访问: {missing}")


def _validate_step_references(steps: list[dict]) -> None:
    """Ensure every ``{{key.output}}`` reference in input_mapping points to a
    preceding step's output_key or to ``initial_input``."""
    known_keys = {"initial_input"}
    for idx, step in enumerate(steps):
        mapping = step.get("input_mapping", {})
        for _field, value in mapping.items():
            if not isinstance(value, str):
                continue
            for ref in _STEP_REF_PATTERN.findall(value):
                if ref not in known_keys:
                    raise ValueError(
                        f"步骤 {idx} 引用了未知的 output_key '{ref}'，"
                        f"可用的有: {known_keys}"
                    )
        output_key = step.get("output_key", f"step{idx}")
        known_keys.add(output_key)


async def _load_skills_map(db: AsyncSession, skill_ids: list[int]) -> dict[int, Skill]:
    result = await db.execute(
        select(Skill).where(Skill.id.in_(skill_ids))
    )
    return {s.id: s for s in result.scalars().all()}


def _resolve_inputs(input_mapping: dict, context: dict[str, str]) -> dict[str, str]:
    """Replace ``{{key.output}}`` and ``{{initial_input}}`` with actual values."""
    resolved: dict[str, str] = {}
    for field, template in input_mapping.items():
        if not isinstance(template, str):
            resolved[field] = template
            continue

        def _replacer(m: re.Match) -> str:
            ref = m.group(1)
            full_key = f"{ref}.output"
            return context.get(full_key, context.get(ref, m.group(0)))

        resolved[field] = _STEP_REF_PATTERN.sub(_replacer, template)
        resolved[field] = resolved[field].replace("{{initial_input}}", context.get("initial_input", ""))
    return resolved


async def _execute_single_step(
    skill: Skill,
    inputs: dict,
    model_config,
    *,
    db: AsyncSession | None = None,
    user_id: int | None = None,
    kb_id: int | None = None,
) -> str:
    """Execute one skill and return its output as a string."""
    config = json.loads(skill.config) if skill.config else {}

    if skill.skill_type == SkillType.PROMPT.value:
        from app.core.tools.prompt_skill import PromptSkillTool
        tool = PromptSkillTool(
            name=skill.slug,
            description=skill.description or skill.name,
            prompt_template=config.get("prompt_template", ""),
            output_format=config.get("output_format", "text"),
            variables=config.get("variables"),
            model_config=model_config,
        )
        result = await tool.execute(**inputs)
        if not result.success:
            raise RuntimeError(result.error or "Prompt 技能执行失败")
        return result.to_message_content()

    if skill.skill_type == SkillType.BUILTIN.value:
        from app.services.skill_service import _BUILTIN_TOOL_MAP, _import_tool_class
        import_path = _BUILTIN_TOOL_MAP.get(skill.slug)
        if not import_path:
            raise RuntimeError(f"未知的内置技能: {skill.slug}")
        tool_cls = _import_tool_class(import_path)
        tool = tool_cls()
        injected = {**inputs, "_db": db, "_user_id": user_id, "_kb_id": kb_id}
        result = await tool.execute(**injected)
        if not result.success:
            raise RuntimeError(result.error or "内置技能执行失败")
        return result.to_message_content()

    raise RuntimeError(f"技能链暂不支持类型 '{skill.skill_type}' 的技能")


def _chain_to_dict(c: SkillChain) -> dict:
    return {
        "id": c.id,
        "user_id": c.user_id,
        "name": c.name,
        "description": c.description,
        "steps": json.loads(c.steps) if isinstance(c.steps, str) else c.steps,
        "is_public": c.is_public,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }
