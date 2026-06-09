"""Business logic for skill marketplace, OpenClaw import, and batch translation."""
import asyncio
import json
import logging
import re as _re
from typing import Optional

from sqlalchemy import select, func, or_, update as sa_update, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.user import User, UserRole
from app.models.skill import MarketSkill, SkillStatus, SkillReview, ReviewStatus
from app.schemas import SkillPublish, SkillResponse, PaginatedResponse


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def skill_to_response(skill: MarketSkill, author_name: Optional[str] = None) -> dict:
    d = SkillResponse.model_validate(skill).model_dump()
    d["author_name"] = author_name
    if not d.get("name"):
        slug = d.get("slug", "")
        readable = slug.removeprefix("oc-").replace("-", " ").replace("_", " ")
        d["name"] = " ".join(w.capitalize() for w in readable.split()) or slug
    return d


def is_already_chinese(text: str) -> bool:
    if not text.strip():
        return True
    chinese_chars = sum(1 for ch in text if '\u4e00' <= ch <= '\u9fff')
    return chinese_chars / max(len(text.strip()), 1) > 0.3


def parse_translate_result(raw: str, originals: list[dict]) -> list[dict]:
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


_CATEGORY_RULES: list[tuple[list[str], str]] = [
    (["github", "gitlab", "bitbucket", "git", "code", "developer", "debug", "lint",
      "compiler", "sdk", "api", "docker", "kubernetes", "k8s", "terraform", "ci",
      "cd", "pipeline", "deploy", "jest", "test", "npm", "yarn", "webpack",
      "vite", "rust", "python", "java", "swift", "react", "vue", "angular",
      "node", "deno", "bun", "postgres", "mysql", "redis", "mongo", "sql",
      "graphql", "rest", "grpc", "serverless", "lambda", "vercel", "netlify",
      "heroku", "aws", "azure", "gcp", "cloud", "devops"], "development"),
    (["database", "csv", "json", "xml", "excel", "spreadsheet", "etl", "pipeline",
      "analytics", "chart", "report", "dashboard", "metric", "bigquery",
      "snowflake", "warehouse", "tableau", "mixpanel", "amplitude", "segment",
      "prometheus", "grafana", "datadog", "newrelic", "kibana", "elastic",
      "logstash"], "data"),
    (["search", "retrieval", "rag", "embedding", "vector", "index",
      "knowledge", "semantic", "crawler", "scrape", "web-search",
      "google", "bing", "brave", "duckduckgo"], "retrieval"),
    (["slack", "discord", "telegram", "whatsapp", "email", "gmail", "outlook",
      "teams", "zoom", "meet", "calendar", "schedule", "chat", "message",
      "notify", "notification", "sms", "twilio", "sendgrid", "postmark",
      "mailchimp", "intercom"], "communication"),
    (["jira", "asana", "trello", "notion", "linear", "monday", "clickup",
      "todoist", "task", "project", "kanban", "agile", "scrum", "sprint",
      "workflow", "automate", "zapier", "make", "n8n", "airtable",
      "basecamp", "confluence"], "productivity"),
    (["write", "translate", "grammar", "blog", "article", "content",
      "copywriting", "story", "creative", "image", "photo", "video",
      "audio", "music", "art", "design", "figma", "canva", "miro",
      "sketch", "midjourney", "dall-e", "stable-diffusion"], "creative"),
    (["security", "auth", "oauth", "saml", "sso", "encrypt", "decrypt",
      "password", "vault", "okta", "onelogin", "firewall", "scan",
      "vulnerability", "pentest", "audit", "compliance"], "security"),
    (["finance", "invoice", "payment", "stripe", "paypal", "quickbooks",
      "accounting", "tax", "billing", "subscription", "revenue",
      "trading", "stock", "crypto", "exchange"], "finance"),
    (["crm", "sales", "hubspot", "salesforce", "pipedrive", "outreach",
      "lead", "prospect", "deal", "customer", "support", "zendesk",
      "freshdesk", "helpdesk", "ticket"], "sales"),
]


def infer_category(slug: str, desc: str) -> str:
    text = f"{slug} {desc}".lower()
    for keywords, category in _CATEGORY_RULES:
        for kw in keywords:
            if kw in text:
                return category
    return "general"


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


# ---------------------------------------------------------------------------
# Redis progress helpers
# ---------------------------------------------------------------------------

REDIS_IMPORT_KEY = "openclaw_import_progress"
REDIS_TRANSLATE_KEY = "openclaw_translate_progress"


async def _get_redis():
    from redis.asyncio import from_url as redis_from_url
    from app.config import settings
    return redis_from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=2)


async def set_import_progress(data: dict):
    try:
        r = await _get_redis()
        await r.set(REDIS_IMPORT_KEY, json.dumps(data), ex=3600)
        await r.aclose()
    except Exception as exc:
        logger.warning("Redis set failed: %s", exc)


async def get_import_progress() -> dict:
    default = {"running": False, "inserted": 0, "skipped": 0, "total": 0, "error": None}
    try:
        r = await _get_redis()
        raw = await r.get(REDIS_IMPORT_KEY)
        await r.aclose()
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return default


async def set_translate_progress(data: dict):
    try:
        r = await _get_redis()
        await r.set(REDIS_TRANSLATE_KEY, json.dumps(data), ex=3600)
        await r.aclose()
    except Exception as exc:
        logger.warning("Redis set translate progress failed: %s", exc)


async def get_translate_progress() -> dict:
    default = {"running": False, "translated": 0, "skipped": 0, "failed": 0, "total": 0, "error": None}
    try:
        r = await _get_redis()
        raw = await r.get(REDIS_TRANSLATE_KEY)
        await r.aclose()
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return default


# ---------------------------------------------------------------------------
# Core skill operations
# ---------------------------------------------------------------------------

async def list_marketplace(
    db: AsyncSession, category: Optional[str], search: Optional[str], page: int, page_size: int,
) -> PaginatedResponse:
    filters = [MarketSkill.status == SkillStatus.APPROVED]
    if category:
        filters.append(MarketSkill.category == category)
    if search:
        keyword = f"%{search}%"
        filters.append(or_(
            MarketSkill.name.ilike(keyword),
            MarketSkill.slug.ilike(keyword),
            MarketSkill.description.ilike(keyword),
        ))

    total = (await db.execute(select(func.count(MarketSkill.id)).where(*filters))).scalar() or 0
    result = await db.execute(
        select(MarketSkill, User.username)
        .outerjoin(User, MarketSkill.author_id == User.id)
        .where(*filters)
        .order_by(MarketSkill.download_count.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    items = [skill_to_response(skill, username) for skill, username in result.all()]
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


async def get_skill_by_id(db: AsyncSession, skill_id: int, current_user: Optional[User] = None) -> dict:
    """Return skill dict or raise ValueError with a message."""
    result = await db.execute(
        select(MarketSkill, User.username)
        .outerjoin(User, MarketSkill.author_id == User.id)
        .where(MarketSkill.id == skill_id)
    )
    row = result.first()
    if not row:
        raise ValueError("技能不存在或未上架")
    skill, username = row

    if skill.status == SkillStatus.APPROVED:
        d = skill_to_response(skill, username)
        d["config"] = skill.config
        return d

    if current_user is None:
        raise ValueError("技能不存在或未上架")

    is_admin = current_user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)
    is_author = skill.author_id is not None and skill.author_id == current_user.id
    if not (is_admin or is_author):
        raise ValueError("技能不存在或未上架")

    d = skill_to_response(skill, username)
    d["config"] = skill.config
    return d


async def record_download(db: AsyncSession, skill_id: int) -> dict:
    skill = (await db.execute(
        select(MarketSkill).where(MarketSkill.id == skill_id, MarketSkill.status == SkillStatus.APPROVED)
    )).scalar_one_or_none()
    if not skill:
        raise ValueError("技能不存在或未上架")

    await db.execute(
        sa_update(MarketSkill).where(MarketSkill.id == skill_id)
        .values(download_count=MarketSkill.download_count + 1)
    )
    await db.commit()
    return {"id": skill.id, "name": skill.name, "slug": skill.slug, "config": skill.config, "version": skill.version}


async def publish(db: AsyncSession, data: SkillPublish, author_id: int, author_name: str) -> SkillResponse:
    existing = (await db.execute(
        select(MarketSkill).where(MarketSkill.slug == data.slug)
    )).scalar_one_or_none()
    if existing:
        raise ValueError(f"技能标识 '{data.slug}' 已被占用")

    skill = MarketSkill(
        name=data.name,
        slug=data.slug,
        description=data.description,
        category=data.category,
        skill_type=data.skill_type,
        version=data.version,
        config=data.config,
        icon_url=data.icon_url,
        author_id=author_id,
        status=SkillStatus.PENDING,
    )
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    logger.info("SKILL_PUBLISH name=%s by=%s", skill.name, author_name)
    return SkillResponse.model_validate(skill)


# ---------------------------------------------------------------------------
# Admin operations
# ---------------------------------------------------------------------------

async def list_admin_skills(
    db: AsyncSession, status: Optional[str], search: Optional[str], page: int, page_size: int,
    *, category: Optional[str] = None,
) -> PaginatedResponse:
    filters = []
    if status:
        filters.append(MarketSkill.status == status)
    if category:
        filters.append(MarketSkill.category == category)
    if search:
        keyword = f"%{search}%"
        filters.append(or_(
            MarketSkill.name.ilike(keyword),
            MarketSkill.slug.ilike(keyword),
            MarketSkill.description.ilike(keyword),
        ))

    total = (await db.execute(select(func.count(MarketSkill.id)).where(*filters))).scalar() or 0
    result = await db.execute(
        select(MarketSkill, User.username)
        .outerjoin(User, MarketSkill.author_id == User.id)
        .where(*filters)
        .order_by(MarketSkill.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    items = [skill_to_response(skill, username) for skill, username in result.all()]
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


async def review_skill(db: AsyncSession, skill_id: int, reviewer_id: int, reviewer_name: str, status: str, comment: Optional[str]) -> str:
    skill = (await db.execute(
        select(MarketSkill).where(MarketSkill.id == skill_id)
    )).scalar_one_or_none()
    if not skill:
        raise ValueError("技能不存在")

    if status == "unlisted":
        skill.status = SkillStatus.UNLISTED
        review = SkillReview(
            skill_id=skill.id,
            reviewer_id=reviewer_id,
            status=ReviewStatus.REJECTED,
            comment=comment or "管理员下架",
        )
    else:
        review_status = ReviewStatus(status)
        skill.status = SkillStatus.APPROVED if review_status == ReviewStatus.APPROVED else SkillStatus.REJECTED
        review = SkillReview(
            skill_id=skill.id,
            reviewer_id=reviewer_id,
            status=review_status,
            comment=comment,
        )

    db.add(review)
    await db.commit()
    logger.info("SKILL_REVIEW skill=%s status=%s by=%s", skill.name, status, reviewer_name)
    return {"approved": "通过", "rejected": "拒绝", "unlisted": "下架"}.get(status, status)


async def get_admin_detail(db: AsyncSession, skill_id: int) -> dict:
    skill = (await db.execute(
        select(MarketSkill).where(MarketSkill.id == skill_id)
    )).scalar_one_or_none()
    if not skill:
        raise ValueError("技能不存在")
    return {
        "id": skill.id,
        "name": skill.name,
        "slug": skill.slug,
        "description": skill.description,
        "category": skill.category,
        "skill_type": skill.skill_type,
        "version": skill.version,
        "status": skill.status.value if hasattr(skill.status, 'value') else skill.status,
        "config": skill.config,
        "icon_url": skill.icon_url,
        "download_count": skill.download_count,
        "is_featured": skill.is_featured,
        "created_at": skill.created_at.isoformat() if skill.created_at else None,
        "updated_at": skill.updated_at.isoformat() if skill.updated_at else None,
    }


async def update_skill(db: AsyncSession, skill_id: int, data: dict, admin_name: str) -> list[str]:
    skill = (await db.execute(
        select(MarketSkill).where(MarketSkill.id == skill_id)
    )).scalar_one_or_none()
    if not skill:
        raise ValueError("技能不存在")

    allowed_fields = {"name", "description", "category", "version", "icon_url", "is_featured", "config"}
    changed = []
    for field in allowed_fields:
        if field in data and data[field] is not None:
            setattr(skill, field, data[field])
            changed.append(field)

    if not changed:
        raise ValueError("没有可更新的字段")

    await db.commit()
    logger.info("SKILL_UPDATE id=%d fields=%s by=%s", skill_id, ",".join(changed), admin_name)
    return changed


async def delete_skill(db: AsyncSession, skill_id: int, admin_name: str) -> str:
    skill = (await db.execute(
        select(MarketSkill).where(MarketSkill.id == skill_id)
    )).scalar_one_or_none()
    if not skill:
        raise ValueError("技能不存在")

    skill_name = skill.name
    await db.delete(skill)
    await db.commit()
    logger.info("SKILL_DELETE id=%d name=%s by=%s", skill_id, skill_name, admin_name)
    return skill_name


async def delete_all_openclaw(db: AsyncSession) -> int:
    result = await db.execute(
        sa_delete(MarketSkill).where(MarketSkill.slug.like("oc-%"))
    )
    await db.commit()
    count = result.rowcount
    logger.info("Deleted %d OpenClaw skills by admin", count)
    return count


async def fix_openclaw_paths(db: AsyncSession) -> dict:
    result = await db.execute(
        select(MarketSkill).where(MarketSkill.slug.like("oc-%"))
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


async def fix_empty_names(db: AsyncSession) -> dict:
    result = await db.execute(
        select(MarketSkill).where(or_(
            MarketSkill.name.is_(None),
            MarketSkill.name == "",
        ))
    )
    skills = result.scalars().all()
    fixed = 0

    for skill in skills:
        slug = skill.slug or ""
        readable = slug.removeprefix("oc-")
        readable = readable.replace("-", " ").replace("_", " ")
        readable = " ".join(w.capitalize() for w in readable.split())
        if readable:
            skill.name = readable[:100]
            fixed += 1

    if fixed:
        await db.commit()
    logger.info("Fixed %d empty skill names (total empty: %d)", fixed, len(skills))
    return {"total_empty": len(skills), "fixed": fixed}


async def fix_categories(db: AsyncSession) -> dict:
    result = await db.execute(
        select(MarketSkill).where(MarketSkill.slug.like("oc-%"))
    )
    skills = result.scalars().all()
    stats: dict[str, int] = {}

    for skill in skills:
        new_cat = infer_category(skill.slug or "", skill.description or "")
        if new_cat != skill.category:
            skill.category = new_cat
        stats[new_cat] = stats.get(new_cat, 0) + 1

    await db.commit()
    logger.info("Re-categorized %d skills: %s", len(skills), stats)
    return {"total": len(skills), "categories": stats}


# ---------------------------------------------------------------------------
# OpenClaw import
# ---------------------------------------------------------------------------

def _parse_openclaw_skill(skill_path, owner_fallback: str = "") -> dict | None:
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

    inferred_cat = infer_category(full_slug, description)

    return {
        "slug": full_slug,
        "name": display_name[:100],
        "description": description[:500],
        "category": inferred_cat,
        "config": config,
        "version": version[:20] if version else "1.0.0",
    }


async def _get_shared_llm_id() -> int | None:
    from app.models.model_config import ModelConfig as MC, ModelType as MT
    try:
        async with async_session() as db:
            model = (await db.execute(
                select(MC.id).where(MC.model_type == MT.LLM, MC.is_shared == True)
                .order_by(MC.is_default.desc())
                .limit(1)
            )).scalar_one_or_none()
            return model
    except Exception:
        return None


async def _translate_skills_batch(items: list[dict], model_id: int) -> dict[int, dict]:
    from app.services.llm_gateway import chat_completion as gw_chat

    to_translate = [it for it in items if not (is_already_chinese(it["name"]) and is_already_chinese(it.get("description", "")))]
    if not to_translate:
        return {}

    payload = [{"id": it["idx"], "name": it["name"], "description": it.get("description", "")} for it in to_translate]
    entries = json.dumps(payload, ensure_ascii=False, indent=2)
    prompt = (
        f"请将以下 AI 技能信息翻译为中文。返回相同结构的 JSON 数组，每个元素包含 id、name（中文名称，简洁）、description（中文描述，一句话）。\n\n"
        f"```json\n{entries}\n```\n\n"
        f"只返回 JSON 数组，不需要代码块标记或任何解释。"
    )
    messages = [
        {"role": "system", "content": "你是一个专业的技术翻译助手。将 AI 技能的名称和描述从英文翻译为简洁自然的中文。保持技术术语的准确性。只返回 JSON，不要任何解释。"},
        {"role": "user", "content": prompt},
    ]

    try:
        async with async_session() as llm_db:
            result_data = await gw_chat(llm_db, model_id, messages, max_tokens=4096)

        raw_text = ""
        choices = result_data.get("choices", [])
        if choices:
            raw_text = choices[0].get("message", {}).get("content", "")

        parsed = parse_translate_result(raw_text, payload)
        return {item["id"]: {"name": item["name"], "description": item["description"]} for item in parsed}
    except Exception as exc:
        logger.warning("Auto-translate batch failed: %s", exc)
        return {}


async def run_openclaw_bulk_import(admin_id: int):
    """Download from GitHub and import."""
    import httpx

    progress = {"running": True, "inserted": 0, "skipped": 0, "total": 0, "error": None}
    try:
        logger.info("Downloading openclaw/skills tarball ...")
        async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
            resp = await client.get("https://github.com/openclaw/skills/archive/refs/heads/main.tar.gz")
            resp.raise_for_status()
        logger.info("Downloaded %.1f MB", len(resp.content) / 1024 / 1024)
        await import_from_tarball_bytes(admin_id, resp.content, progress)
    except Exception as exc:
        logger.error("OpenClaw bulk import failed: %s", exc, exc_info=True)
        progress.update(running=False, error=str(exc))
        await set_import_progress(progress)


async def run_local_import(admin_id: int):
    """Import skills from local skills/skills/ directory."""
    from pathlib import Path
    import os

    progress = {"running": True, "inserted": 0, "skipped": 0, "total": 0, "error": None}
    try:
        # Search for skills directory in common locations
        candidates = [
            Path(os.environ.get("SKILLS_DIR", "")) / "skills",
            Path(__file__).resolve().parents[3] / "skills" / "skills",
            Path("/app/skills/skills"),
            Path("/opt/rag-platform/skills/skills"),
        ]
        skills_root = None
        for p in candidates:
            if p and p.is_dir():
                skills_root = p
                break

        if not skills_root:
            progress.update(running=False, error="未找到本地 skills/skills/ 目录")
            await set_import_progress(progress)
            return

        logger.info("Local skills import from: %s", skills_root)

        skills_data: list[dict] = []
        for owner_dir in sorted(skills_root.iterdir()):
            if not owner_dir.is_dir():
                continue
            for skill_dir in sorted(owner_dir.iterdir()):
                if not skill_dir.is_dir():
                    continue
                parsed = _parse_openclaw_skill(skill_dir, owner_dir.name)
                if parsed:
                    skills_data.append(parsed)

        progress["total"] = len(skills_data)
        await set_import_progress(progress)
        logger.info("Found %d local skills to import", len(skills_data))

        # De-duplicate by slug
        seen_slugs: set[str] = set()
        unique_skills = [d for d in skills_data if d["slug"] not in seen_slugs and not seen_slugs.add(d["slug"])]

        batch_size = 200
        for i in range(0, len(unique_skills), batch_size):
            batch = unique_skills[i:i + batch_size]
            async with async_session() as db:
                slugs = [s["slug"] for s in batch]
                existing = set(
                    (await db.execute(
                        select(MarketSkill.identifier).where(MarketSkill.identifier.in_(slugs))
                    )).scalars().all()
                )
                for data in batch:
                    if data["slug"] in existing:
                        progress["skipped"] += 1
                        continue
                    skill = MarketSkill(
                        identifier=data["slug"],
                        name=data["name"],
                        description=data.get("description", "")[:500],
                        category=data.get("category", "openclaw"),
                        skill_type=data.get("skill_type", "prompt"),
                        version=data.get("version", "1.0.0"),
                        prompt=data.get("config_prompt", ""),
                        config=data.get("config"),
                        status="approved",
                        author_name=data.get("author", "openclaw"),
                        submitted_by=admin_id,
                    )
                    db.add(skill)
                    progress["inserted"] += 1
                await db.commit()
            await set_import_progress(progress)

        progress["running"] = False
        await set_import_progress(progress)
        logger.info("Local import complete: inserted=%d skipped=%d", progress["inserted"], progress["skipped"])
    except Exception as exc:
        logger.error("Local import failed: %s", exc, exc_info=True)
        progress.update(running=False, error=str(exc))
        await set_import_progress(progress)


async def run_openclaw_import_from_bytes(admin_id: int, content: bytes):
    """Import from uploaded tarball bytes."""
    progress = {"running": True, "inserted": 0, "skipped": 0, "total": 0, "error": None}
    try:
        await import_from_tarball_bytes(admin_id, content, progress)
    except Exception as exc:
        logger.error("OpenClaw upload import failed: %s", exc, exc_info=True)
        progress.update(running=False, error=str(exc))
        await set_import_progress(progress)


async def import_from_tarball_bytes(admin_id: int, tarball_bytes: bytes, progress: dict):
    import io
    import shutil
    import tarfile
    import tempfile
    from pathlib import Path

    tmp_dir = tempfile.mkdtemp(prefix="openclaw_skills_")
    try:
        loop = asyncio.get_event_loop()
        def _extract():
            with tarfile.open(fileobj=io.BytesIO(tarball_bytes), mode="r:gz") as tar:
                tar.extractall(tmp_dir)
        await loop.run_in_executor(None, _extract)
        logger.info("Tarball extracted to %s", tmp_dir)

        extracted = list(Path(tmp_dir).iterdir())
        repo_root = extracted[0] if extracted else Path(tmp_dir)
        skills_root = repo_root / "skills"
        if not skills_root.is_dir():
            progress.update(running=False, error=f"skills/ directory not found (root={repo_root.name})")
            await set_import_progress(progress)
            return

        skills_data: list[dict] = []
        for owner_dir in sorted(skills_root.iterdir()):
            if not owner_dir.is_dir():
                continue
            for skill_dir in sorted(owner_dir.iterdir()):
                if not skill_dir.is_dir():
                    continue
                parsed = _parse_openclaw_skill(skill_dir, owner_dir.name)
                if parsed:
                    skills_data.append(parsed)

        progress["total"] = len(skills_data)
        await set_import_progress(progress)
        logger.info("Found %d skills to import", len(skills_data))

        llm_model_id = await _get_shared_llm_id()
        if llm_model_id:
            logger.info("Auto-translation enabled (model_id=%d)", llm_model_id)
        else:
            logger.info("No shared LLM configured, importing without translation")

        seen_slugs: set[str] = set()
        unique_skills: list[dict] = []
        for d in skills_data:
            if d["slug"] not in seen_slugs:
                seen_slugs.add(d["slug"])
                unique_skills.append(d)
        skills_data = unique_skills

        progress["total"] = len(skills_data)
        await set_import_progress(progress)

        translate_batch_size = 10
        insert_batch_size = 100
        for i in range(0, len(skills_data), insert_batch_size):
            batch = skills_data[i:i + insert_batch_size]
            async with async_session() as db:
                slugs = [s["slug"] for s in batch]
                existing_rows = (await db.execute(
                    select(MarketSkill).where(MarketSkill.slug.in_(slugs))
                )).scalars().all()
                existing_map = {s.slug: s for s in existing_rows}

                new_items = [d for d in batch if d["slug"] not in existing_map]
                update_items = [d for d in batch if d["slug"] in existing_map]

                translations: dict[int, dict] = {}
                if llm_model_id and new_items:
                    for j in range(0, len(new_items), translate_batch_size):
                        t_batch = new_items[j:j + translate_batch_size]
                        t_input = [{"idx": k, "name": d["name"], "description": d.get("description", "")} for k, d in enumerate(t_batch, start=j)]
                        result = await _translate_skills_batch(t_input, llm_model_id)
                        translations.update(result)

                for idx, data in enumerate(new_items):
                    tr = translations.get(idx)
                    skill = MarketSkill(
                        name=tr["name"] if tr else data["name"],
                        slug=data["slug"],
                        description=tr["description"] if tr else data["description"],
                        category=data.get("category", "openclaw"),
                        skill_type="prompt",
                        version=data["version"],
                        config=data["config"],
                        author_id=admin_id,
                        status=SkillStatus.APPROVED,
                    )
                    db.add(skill)
                    progress["inserted"] += 1

                for data in update_items:
                    existing_skill = existing_map[data["slug"]]
                    existing_skill.name = data["name"]
                    existing_skill.description = data["description"]
                    existing_skill.config = data["config"]
                    existing_skill.version = data["version"]
                    progress["skipped"] += 1

                await db.commit()
            await set_import_progress(progress)

        progress["running"] = False
        await set_import_progress(progress)
        logger.info("OpenClaw import done: inserted=%d skipped=%d total=%d",
                     progress["inserted"], progress["skipped"], progress["total"])
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Batch translate
# ---------------------------------------------------------------------------

async def run_batch_translate(model_config_id: int):
    from app.services.llm_gateway import chat_completion as gw_chat

    batch_size = 5
    progress = {"running": True, "translated": 0, "skipped": 0, "failed": 0, "total": 0, "error": None}

    try:
        async with async_session() as db:
            oc_skills = (await db.execute(
                select(MarketSkill).where(MarketSkill.slug.like("oc-%"))
                .order_by(MarketSkill.id)
            )).scalars().all()

            progress["total"] = len(oc_skills)
            await set_translate_progress(progress)

            for i in range(0, len(oc_skills), batch_size):
                batch = oc_skills[i:i + batch_size]
                items_for_llm = []

                for skill in batch:
                    if is_already_chinese(skill.name) and is_already_chinese(skill.description or ""):
                        progress["skipped"] += 1
                        continue
                    items_for_llm.append({
                        "id": skill.id,
                        "name": skill.name,
                        "description": skill.description or "",
                    })

                if not items_for_llm:
                    await set_translate_progress(progress)
                    continue

                try:
                    entries = json.dumps(items_for_llm, ensure_ascii=False, indent=2)
                    prompt = (
                        f"请将以下 AI 技能信息翻译为中文。返回相同结构的 JSON 数组，每个元素包含 id、name（中文名称，简洁）、description（中文描述，一句话）。\n\n"
                        f"```json\n{entries}\n```\n\n"
                        f"只返回 JSON 数组，不需要代码块标记或任何解释。"
                    )
                    messages = [
                        {"role": "system", "content": "你是一个专业的技术翻译助手。将 AI 技能的名称和描述从英文翻译为简洁自然的中文。保持技术术语的准确性。只返回 JSON，不要任何解释。"},
                        {"role": "user", "content": prompt},
                    ]

                    async with async_session() as llm_db:
                        result_data = await gw_chat(llm_db, model_config_id, messages, max_tokens=4096)

                    raw_text = ""
                    choices = result_data.get("choices", [])
                    if choices:
                        raw_text = choices[0].get("message", {}).get("content", "")

                    translated = parse_translate_result(raw_text, items_for_llm)

                    if translated:
                        async with async_session() as update_db:
                            for item in translated:
                                await update_db.execute(
                                    sa_update(MarketSkill)
                                    .where(MarketSkill.id == item["id"])
                                    .values(name=item["name"], description=item["description"])
                                )
                            await update_db.commit()

                    progress["translated"] += len(translated)
                    progress["failed"] += len(items_for_llm) - len(translated)
                except Exception as exc:
                    logger.warning("Batch translate error: %s", exc, exc_info=True)
                    progress["failed"] += len(items_for_llm)

                await set_translate_progress(progress)

        progress["running"] = False
        await set_translate_progress(progress)
    except Exception as exc:
        progress.update(running=False, error=str(exc))
        await set_translate_progress(progress)
