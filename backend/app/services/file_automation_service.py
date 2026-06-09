import hashlib
import json
import logging
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentChunk, DocumentStatus
from app.models.knowledge_base import KnowledgeBase

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

async def compute_file_hash(file_path: str) -> str:
    """Compute SHA256 hash of a file's content."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            sha256.update(chunk)
    return sha256.hexdigest()


def compute_bytes_hash(data: bytes) -> str:
    """Compute SHA256 hash from in-memory bytes."""
    return hashlib.sha256(data).hexdigest()


async def check_duplicate(
    db: AsyncSession, kb_id: int, content_hash: str
) -> Optional[Document]:
    """Check if a document with the same content hash already exists in this KB."""
    result = await db.execute(
        select(Document).where(
            Document.kb_id == kb_id,
            Document.content_hash == content_hash,
        )
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Auto-tagging
# ---------------------------------------------------------------------------

_STOP_WORDS_ZH = frozenset([
    "的", "了", "是", "在", "我", "有", "和", "人", "这", "中", "大", "为",
    "上", "个", "不", "以", "会", "到", "说", "时", "要", "没", "出", "就",
    "也", "得", "里", "后", "自", "年", "前", "两", "同", "已", "对", "都",
    "下", "过", "子", "用", "现", "而", "把", "好", "与", "进", "种", "还",
    "将", "多", "日", "三", "小", "于", "此", "无", "然", "他们", "她们",
    "我们", "你们", "它们", "他", "她", "它", "你", "您", "所", "被", "从",
    "能", "但", "让", "又", "等", "最", "给", "当", "很", "更", "应该",
    "如何", "什么", "哪些", "这些", "那些", "因为", "所以", "如果", "虽然",
])

_STOP_WORDS_EN = frozenset(
    "the a an is are was were be been being have has had do does did "
    "will would shall should can could may might must need dare "
    "i me my we our you your he him his she her it its they them their "
    "this that these those and or but not no nor for of to in on at by "
    "with from up about into over after as so if than too very just also "
    "which what who whom how when where why all each every both few many "
    "some any such only own same other new old more most one two first".split()
)


def _extract_keywords(text: str, top_n: int = 8) -> list[str]:
    """Extract top keywords using character bigram frequency (works for CJK + Latin)."""
    text_lower = text.lower()
    words_en = re.findall(r"[a-zA-Z]{3,}", text_lower)
    words_zh = re.findall(r"[\u4e00-\u9fff]{2,4}", text_lower)

    counter: Counter = Counter()

    for w in words_en:
        if w not in _STOP_WORDS_EN and len(w) >= 3:
            counter[w] += 1

    for w in words_zh:
        if w not in _STOP_WORDS_ZH:
            counter[w] += 1

    most_common = counter.most_common(top_n * 3)
    tags = []
    seen = set()
    for word, _count in most_common:
        if word not in seen:
            seen.add(word)
            tags.append(word)
        if len(tags) >= top_n:
            break
    return tags


async def auto_tag_document(
    db: AsyncSession, doc_id: int, llm_config=None
) -> list[str]:
    """Generate tags for a document based on its content chunks.

    Uses LLM if available, otherwise falls back to keyword extraction.
    Tags are stored as JSON in document.auto_tags.
    """
    result = await db.execute(
        select(DocumentChunk.content)
        .where(DocumentChunk.doc_id == doc_id)
        .order_by(DocumentChunk.chunk_index)
        .limit(5)
    )
    chunks = [row[0] for row in result.all()]
    if not chunks:
        _logger.info("文档无切片，跳过自动标签 (doc_id=%s)", doc_id)
        return []

    combined_text = "\n".join(chunks)[:6000]

    tags: list[str] = []

    if llm_config:
        try:
            tags = await _llm_generate_tags(combined_text, llm_config)
        except Exception as exc:
            _logger.warning(
                "LLM 生成标签失败，回退到关键词提取 (doc_id=%s): %s",
                doc_id, exc,
            )
            tags = []

    if not tags:
        tags = _extract_keywords(combined_text)

    tags_json = json.dumps(tags, ensure_ascii=False)
    await db.execute(
        update(Document).where(Document.id == doc_id).values(auto_tags=tags_json)
    )
    await db.commit()

    _logger.info("自动标签完成 (doc_id=%s): %s", doc_id, tags)
    return tags


async def _llm_generate_tags(text: str, llm_config) -> list[str]:
    """Use LLM to generate tags from document text."""
    from app.core.llm_client import chat_completion

    prompt = (
        "请根据以下文档内容，生成 3-8 个简短的标签关键词，"
        "用 JSON 数组格式返回，例如 [\"标签1\", \"标签2\"]。"
        "只返回 JSON 数组，不要其他文字。\n\n"
        f"文档内容：\n{text[:4000]}"
    )
    messages = [
        {"role": "system", "content": "你是一个文档标签提取助手。请严格按照 JSON 数组格式输出。"},
        {"role": "user", "content": prompt},
    ]
    response = await chat_completion(llm_config, messages, stream=False)
    text_resp = response.strip()
    if text_resp.startswith("```"):
        text_resp = text_resp.split("\n", 1)[1] if "\n" in text_resp else text_resp[3:]
        text_resp = text_resp.rsplit("```", 1)[0]
    match = re.search(r"\[.*?\]", text_resp, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError("LLM 回覆中未找到 JSON 数组")


# ---------------------------------------------------------------------------
# Expiry management
# ---------------------------------------------------------------------------

async def check_expiring_documents(
    db: AsyncSession, days_ahead: int = 7, kb_id: int | None = None,
) -> list[dict]:
    """Find documents that will expire within the given number of days."""
    now = datetime.now(timezone.utc)
    deadline = now + timedelta(days=days_ahead)

    filters = [
        Document.expires_at.isnot(None),
        Document.expires_at <= deadline,
        Document.expires_at > now,
        Document.is_archived == False,  # noqa: E712
    ]
    if kb_id is not None:
        filters.append(Document.kb_id == kb_id)

    result = await db.execute(
        select(Document).where(and_(*filters)).order_by(Document.expires_at)
    )
    docs = result.scalars().all()
    return [
        {
            "id": d.id,
            "kb_id": d.kb_id,
            "filename": d.filename,
            "expires_at": d.expires_at.isoformat() if d.expires_at else None,
            "days_remaining": max(0, (d.expires_at - now).days) if d.expires_at else None,
        }
        for d in docs
    ]


async def archive_expired_documents(db: AsyncSession) -> int:
    """Archive documents that have passed their expiry date. Returns count archived."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        update(Document)
        .where(
            and_(
                Document.expires_at.isnot(None),
                Document.expires_at <= now,
                Document.is_archived == False,  # noqa: E712
            )
        )
        .values(is_archived=True)
    )
    await db.commit()
    count = result.rowcount or 0
    if count:
        _logger.info("已归档 %d 篇过期文档", count)
    return count


# ---------------------------------------------------------------------------
# Knowledge base suggestion
# ---------------------------------------------------------------------------

async def suggest_knowledge_base(
    db: AsyncSession, user_id: int, filename: str, content_preview: str
) -> list[dict]:
    """Suggest which knowledge bases a document might belong to.

    Compare filename / content with existing KB descriptions and document tags.
    Return list of {kb_id, kb_name, confidence} sorted by confidence desc.
    """
    result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.user_id == user_id,
            KnowledgeBase.deleted_at.is_(None),
        )
    )
    kbs = result.scalars().all()
    if not kbs:
        return []

    query_text = (filename + " " + content_preview).lower()
    query_words = set(re.findall(r"[a-zA-Z]{2,}|[\u4e00-\u9fff]+", query_text))

    scored: list[dict] = []
    for kb in kbs:
        score = 0.0
        kb_text = ((kb.name or "") + " " + (kb.description or "")).lower()
        kb_words = set(re.findall(r"[a-zA-Z]{2,}|[\u4e00-\u9fff]+", kb_text))
        for qw in query_words:
            for kw in kb_words:
                if len(qw) >= 2 and len(kw) >= 2 and (qw in kw or kw in qw):
                    score += 0.2

        if not kb_words:
            scored.append({"kb_id": kb.id, "kb_name": kb.name, "confidence": 0.0})
            continue

        overlap = query_words & kb_words
        if overlap:
            score = len(overlap) / max(len(kb_words), 1)

        doc_result = await db.execute(
            select(Document.auto_tags)
            .where(
                Document.kb_id == kb.id,
                Document.auto_tags.isnot(None),
            )
            .limit(20)
        )
        tag_rows = doc_result.scalars().all()
        all_tags: set[str] = set()
        for raw in tag_rows:
            if raw:
                try:
                    all_tags.update(t.lower() for t in json.loads(raw))
                except (json.JSONDecodeError, TypeError):
                    pass

        tag_overlap = query_words & all_tags
        if tag_overlap:
            score += len(tag_overlap) * 0.15

        score = min(score, 1.0)
        scored.append({"kb_id": kb.id, "kb_name": kb.name, "confidence": round(score, 3)})

    scored.sort(key=lambda x: x["confidence"], reverse=True)
    return [s for s in scored if s["confidence"] > 0][:5]
