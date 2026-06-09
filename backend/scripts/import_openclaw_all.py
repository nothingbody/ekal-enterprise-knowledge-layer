#!/usr/bin/env python3
"""Bulk-import ALL OpenClaw skills from the GitHub repository.

Usage (from the backend directory):
    python -m scripts.import_openclaw_all

The script:
  1. Shallow-clones the openclaw/skills GitHub repo
  2. Walks every skills/{owner}/{slug}/ directory
  3. Reads _meta.json + SKILL.md
  4. Inserts into the local `skills` table (skips duplicates with oc- prefix)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DESKTOP_MODE", "1")

from sqlalchemy import select
from app.database import engine, async_session, Base
from app.models.skill import Skill

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("import_openclaw")

TARBALL_URL = "https://github.com/openclaw/skills/archive/refs/heads/main.tar.gz"
SLUG_PREFIX = "oc-"


def download_and_extract(dest: str) -> str:
    """Download tarball and extract; returns path to the repo root inside dest."""
    import io
    import tarfile
    import urllib.request

    log.info("Downloading %s ...", TARBALL_URL)
    with urllib.request.urlopen(TARBALL_URL, timeout=120) as resp:
        data = resp.read()
    log.info("Downloaded %.1f MB, extracting ...", len(data) / 1024 / 1024)

    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        tar.extractall(dest)

    extracted = list(Path(dest).iterdir())
    repo_root = str(extracted[0]) if extracted else dest
    log.info("Extracted to %s", repo_root)
    return repo_root


def parse_skill_dir(skill_path: Path) -> dict | None:
    meta_file = skill_path / "_meta.json"
    skill_file = skill_path / "SKILL.md"

    if not meta_file.exists():
        return None

    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
    except Exception:
        return None

    owner = meta.get("owner", "")
    slug = meta.get("slug", skill_path.name)
    display_name = meta.get("displayName", slug)
    version_info = meta.get("latest", {})
    version = version_info.get("version", "1.0.0")

    description = ""
    instruction = ""
    if skill_file.exists():
        try:
            content = skill_file.read_text(encoding="utf-8")
            # Parse YAML frontmatter for description
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    frontmatter = parts[1]
                    for line in frontmatter.split("\n"):
                        stripped = line.strip()
                        if stripped.startswith("description:"):
                            description = stripped[len("description:"):].strip().strip("|").strip()
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

    full_slug = f"{SLUG_PREFIX}{slug}"
    if len(full_slug) > 100:
        full_slug = full_slug[:100]

    return {
        "slug": full_slug,
        "name": display_name[:100],
        "description": description[:500],
        "category": "openclaw",
        "skill_type": "prompt",
        "config": config,
        "is_public": True,
        "version": (version[:20] if version else "1.0.0"),
    }


def collect_skills(repo_dir: str) -> list[dict]:
    skills_root = Path(repo_dir) / "skills"
    if not skills_root.is_dir():
        log.error("skills/ directory not found in repo")
        return []

    results: list[dict] = []
    for owner_dir in sorted(skills_root.iterdir()):
        if not owner_dir.is_dir():
            continue
        for skill_dir in sorted(owner_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            parsed = parse_skill_dir(skill_dir)
            if parsed:
                results.append(parsed)

    return results


async def import_to_db(skills_data: list[dict]) -> tuple[int, int]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    inserted = 0
    skipped = 0
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
                    skipped += 1
                    continue
                skill = Skill(
                    name=data["name"],
                    slug=data["slug"],
                    description=data["description"],
                    category=data["category"],
                    skill_type=data["skill_type"],
                    config=data["config"],
                    is_public=data["is_public"],
                    version=data["version"],
                )
                db.add(skill)
                inserted += 1

            await db.commit()

        if (i + batch_size) % 500 == 0 or i + batch_size >= len(skills_data):
            log.info("Progress: %d / %d processed", min(i + batch_size, len(skills_data)), len(skills_data))

    return inserted, skipped


async def main():
    tmp_dir = tempfile.mkdtemp(prefix="openclaw_skills_")
    try:
        repo_root = download_and_extract(tmp_dir)
        skills_data = collect_skills(repo_root)
        log.info("Found %d skills to import", len(skills_data))

        if not skills_data:
            log.warning("No skills found, exiting.")
            return

        inserted, skipped = await import_to_db(skills_data)
        log.info("Done! Inserted: %d, Skipped (duplicate): %d", inserted, skipped)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
