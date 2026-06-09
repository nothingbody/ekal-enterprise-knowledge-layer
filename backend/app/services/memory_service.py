"""Memory service — extract, store, retrieve, and manage user memories.

Memories are extracted from conversations using LLM and stored with embeddings
for efficient vector similarity retrieval. Retrieved memories are injected into
the system prompt to give the AI long-term context about the user.
"""

import json
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func, update

from app.models.user_memory import UserMemory
from app.models.user_profile import UserProfile
from app.models.model_config import ModelConfig, ModelType
from app.core.llm_client import chat_completion, create_embeddings

logger = logging.getLogger(__name__)

TIME_DECAY_LAMBDA = 0.01  # half-life ≈ 70 days
TEMPORARY_MEMORY_TTL_DAYS = 7


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

MEMORY_EXTRACT_PROMPT = """分析以下对话内容，提取值得长期记住的信息。

提取规则：
1. 提取用户明确表达的偏好、习惯、个人信息
2. 提取用户反复提及的重要事实
3. 提取有价值的结论或决策
4. 每条记忆应该简洁、独立、可理解

输出格式：返回 JSON 数组，每个元素包含：
- content: 记忆内容（简洁的一句话）
- category: 分类（preference/fact/insight）
- memory_type: "persistent"（长期有效的偏好、事实）或 "temporary"（短期有效的临时信息，如近期计划、临时需求）
- importance: 重要程度，0.5 到 2.0 之间的浮点数（0.5=不太重要，1.0=普通，1.5=重要，2.0=非常重要）

如果没有值得记住的内容，返回空数组 []

对话内容：
{conversation}
"""

PROFILE_BUILD_PROMPT = """根据以下用户的历史记忆信息，生成一份用户画像摘要。

用户记忆列表：
{memories}

请生成以下内容，以 JSON 对象格式返回：
- profile_summary: 一段简洁的用户画像描述（100-200字）
- topics_of_interest: 用户感兴趣的主题列表（JSON 字符串数组）
- communication_style: 用户的沟通风格，从以下选项中选择一个：formal / casual / technical
- expertise_areas: 用户擅长的领域列表（JSON 字符串数组）

仅根据已有记忆进行推断，不要编造信息。如果某项信息不足以判断，对应字段返回 null。
"""


# ---------------------------------------------------------------------------
# Memory extraction
# ---------------------------------------------------------------------------

async def extract_memories_from_conversation(
    db: AsyncSession,
    user_id: int,
    conversation_id: int,
    messages: List[dict],
    llm_config: ModelConfig,
) -> List[UserMemory]:
    """Use LLM to extract memorable facts from a conversation."""
    if len(messages) < 2:
        return []

    # Build conversation text
    conv_text = "\n".join(
        f"{'用户' if m['role'] == 'user' else 'AI'}: {m['content'][:500]}"
        for m in messages[-10:]  # Last 10 messages
    )

    prompt = MEMORY_EXTRACT_PROMPT.format(conversation=conv_text)
    try:
        response = await chat_completion(
            llm_config,
            [
                {"role": "system", "content": "你是一个记忆提取助手。请严格按照JSON格式输出。"},
                {"role": "user", "content": prompt},
            ],
            stream=False,
        )

        # Parse JSON from response
        text = response.strip()
        # Handle markdown code blocks
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            text = text.rsplit("```", 1)[0]
        memories_data = json.loads(text)

        if not isinstance(memories_data, list):
            return []

        created = []
        _dedup_cache: dict = {}  # shared across batch to avoid re-loading embeddings
        now = datetime.now(timezone.utc)
        for item in memories_data[:5]:  # Max 5 memories per conversation
            content = item.get("content", "").strip()
            category = item.get("category", "general")
            if not content or len(content) < 4:
                continue

            # Check for duplicate/similar memories
            if await _is_duplicate(db, user_id, content, _cache=_dedup_cache):
                logger.debug("Skipping duplicate memory: %s", content[:50])
                continue

            mem_type = item.get("memory_type", "persistent")
            if mem_type not in ("persistent", "temporary"):
                mem_type = "persistent"

            raw_importance = item.get("importance", 1.0)
            try:
                importance = max(0.5, min(2.0, float(raw_importance)))
            except (TypeError, ValueError):
                importance = 1.0

            expires = None
            if mem_type == "temporary":
                expires = now + timedelta(days=TEMPORARY_MEMORY_TTL_DAYS)

            memory = UserMemory(
                user_id=user_id,
                content=content,
                category=category if category in ("preference", "fact", "insight") else "general",
                source=f"conversation:{conversation_id}",
                memory_type=mem_type,
                importance=importance,
                expires_at=expires,
            )
            db.add(memory)
            created.append(memory)

        if created:
            await db.commit()
            # Generate embeddings async
            for mem in created:
                await db.refresh(mem)
            await _update_embeddings(db, created, user_id)
            logger.info("Extracted %d memories from conversation %d", len(created), conversation_id)

        return created

    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.warning("Memory extraction parse error: %s", exc)
        return []
    except Exception as exc:
        logger.warning("Memory extraction failed: %s", exc)
        return []


async def _is_duplicate(
    db: AsyncSession,
    user_id: int,
    content: str,
    _cache: dict | None = None,
) -> bool:
    """Check if a very similar memory already exists.

    Layer 1: exact content match.
    Layer 2: semantic similarity > 0.92 via embedding cosine distance.

    Pass a shared ``_cache`` dict across calls in the same batch to avoid
    reloading embeddings for every candidate (fixes O(n*m) performance).
    """
    # Layer 1 — exact match
    result = await db.execute(
        select(UserMemory.id).where(
            UserMemory.user_id == user_id,
            UserMemory.content == content,
        ).limit(1)
    )
    if result.scalar_one_or_none() is not None:
        return True

    # Layer 2 — semantic similarity (use cached embeddings if available)
    if _cache is None:
        _cache = {}

    if "embed_model" not in _cache:
        _cache["embed_model"] = await find_embedding_model(db, user_id)
    embed_model = _cache["embed_model"]
    if not embed_model:
        return False

    try:
        new_embedding = (await create_embeddings(embed_model, [content]))[0]
    except Exception:
        return False

    # Load existing embeddings once per batch
    if "existing_embeddings" not in _cache:
        existing = await db.execute(
            select(UserMemory.id, UserMemory.embedding)
            .where(UserMemory.user_id == user_id)
            .limit(500)
        )
        _cache["existing_embeddings"] = [
            (row.id, row.embedding) for row in existing.all() if row.embedding
        ]

    for _mem_id, emb_raw in _cache["existing_embeddings"]:
        emb = emb_raw if isinstance(emb_raw, list) else json.loads(emb_raw)
        if _cosine_similarity(new_embedding, emb) > 0.92:
            return True

    return False


# ---------------------------------------------------------------------------
# Embedding management
# ---------------------------------------------------------------------------

async def find_embedding_model(db: AsyncSession, user_id: int) -> Optional[ModelConfig]:
    """Find the default embedding model for a user."""
    result = await db.execute(
        select(ModelConfig).where(
            ModelConfig.user_id == user_id,
            ModelConfig.model_type == ModelType.EMBEDDING,
            ModelConfig.is_default == True,
        )
    )
    return result.scalar_one_or_none()


async def _update_embeddings(
    db: AsyncSession,
    memories: List[UserMemory],
    user_id: int,
) -> None:
    """Generate and store embeddings for a list of memories."""
    embed_model = await find_embedding_model(db, user_id)
    if not embed_model:
        logger.debug("No embedding model configured, skipping memory embeddings")
        return

    texts = [m.content for m in memories]
    try:
        embeddings = await create_embeddings(embed_model, texts)
        for mem, emb in zip(memories, embeddings):
            mem.embedding = emb
        await db.commit()
    except Exception as exc:
        logger.warning("Failed to generate memory embeddings: %s", exc)


# ---------------------------------------------------------------------------
# Memory retrieval
# ---------------------------------------------------------------------------

def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _compute_final_score(
    cosine_sim: float,
    mem: UserMemory,
    now: datetime,
) -> float:
    """Combine cosine similarity with time decay, importance, and access frequency."""
    ref_time = mem.last_accessed_at or mem.created_at
    if ref_time is not None:
        if ref_time.tzinfo is None:
            ref_time = ref_time.replace(tzinfo=timezone.utc)
        days_since = max((now - ref_time).total_seconds() / 86400, 0)
    else:
        days_since = 0.0

    decay_factor = math.exp(-TIME_DECAY_LAMBDA * days_since)
    importance = getattr(mem, "importance", None) or 1.0
    access_count = getattr(mem, "access_count", None) or 0
    access_boost = 1.0 + 0.1 * math.log(access_count + 1)

    return cosine_sim * decay_factor * importance * access_boost


async def _mark_accessed(db: AsyncSession, memory_ids: List[int]) -> None:
    """Bump access_count and last_accessed_at for retrieved memories."""
    if not memory_ids:
        return
    now = datetime.now(timezone.utc)
    await db.execute(
        update(UserMemory)
        .where(UserMemory.id.in_(memory_ids))
        .values(
            access_count=UserMemory.access_count + 1,
            last_accessed_at=now,
        )
    )
    await db.commit()


async def search_memories(
    db: AsyncSession,
    user_id: int,
    query: str,
    top_k: int = 5,
    embed_model: Optional[ModelConfig] = None,
) -> List[dict]:
    """Search user memories by vector similarity with time-decay ranking.

    Returns list of dicts with 'id', 'content', 'category', 'score',
    'importance', 'access_count', 'memory_type'.
    Falls back to keyword match if no embedding model is available.
    """
    now = datetime.now(timezone.utc)

    # Exclude expired memories
    result = await db.execute(
        select(UserMemory).where(
            UserMemory.user_id == user_id,
            (UserMemory.expires_at.is_(None)) | (UserMemory.expires_at > now),
        )
        .order_by(UserMemory.updated_at.desc())
        .limit(500)
    )
    all_memories = list(result.scalars().all())

    if not all_memories:
        return []

    def _build_result(mem: UserMemory, score: float) -> dict:
        return {
            "id": mem.id,
            "content": mem.content,
            "category": mem.category,
            "score": round(score, 4),
            "importance": mem.importance,
            "access_count": mem.access_count,
            "memory_type": mem.memory_type,
        }

    hits: List[dict] = []

    # Try vector search first
    if embed_model:
        try:
            query_embedding = (await create_embeddings(embed_model, [query]))[0]
            scored = []
            for mem in all_memories:
                if mem.embedding:
                    emb = mem.embedding if isinstance(mem.embedding, list) else json.loads(mem.embedding)
                    cosine_sim = _cosine_similarity(query_embedding, emb)
                    if cosine_sim > 0.3:
                        final = _compute_final_score(cosine_sim, mem, now)
                        scored.append((mem, final))

            if scored:
                scored.sort(key=lambda x: x[1], reverse=True)
                hits = [_build_result(m, s) for m, s in scored[:top_k]]
        except Exception as exc:
            logger.warning("Vector memory search failed, falling back to keyword: %s", exc)

    # Fallback: character n-gram matching (works for Chinese + English)
    if not hits:
        query_lower = query.lower()
        query_grams = _char_bigrams(query_lower)
        if not query_grams:
            return []
        scored = []
        for mem in all_memories:
            content_grams = _char_bigrams(mem.content.lower())
            overlap = len(query_grams & content_grams)
            if overlap > 0:
                raw_score = overlap / max(len(query_grams), 1)
                final = _compute_final_score(raw_score, mem, now)
                scored.append((mem, final))

        scored.sort(key=lambda x: x[1], reverse=True)
        hits = [_build_result(m, s) for m, s in scored[:top_k] if s > 0.1]

    # Update access stats for returned memories
    if hits:
        await _mark_accessed(db, [h["id"] for h in hits])

    return hits


def _char_bigrams(text: str) -> set:
    """Generate character bigrams from text. Works for CJK and Latin."""
    text = "".join(text.split())  # remove whitespace
    if len(text) < 2:
        return {text} if text else set()
    return {text[i:i+2] for i in range(len(text) - 1)}


def build_memory_context(memories: List[dict]) -> str:
    """Format retrieved memories into a context string for the system prompt."""
    if not memories:
        return ""
    parts = ["以下是关于该用户的历史记忆，请在回答时适当参考："]
    for m in memories:
        cat_label = {"preference": "偏好", "fact": "事实", "insight": "经验"}.get(m["category"], "记忆")
        parts.append(f"- [{cat_label}] {m['content']}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# User interest vector for memory-enhanced retrieval
# ---------------------------------------------------------------------------

from collections import OrderedDict as _OrderedDict
import time as _time

_USER_INTEREST_CACHE_TTL = 300  # 5 minutes
_USER_INTEREST_CACHE_MAX = 64
_user_interest_cache: _OrderedDict = _OrderedDict()


async def compute_user_interest_vector(
    db: AsyncSession,
    user_id: int,
    embed_model: Optional[ModelConfig] = None,
    top_k: int = 20,
) -> Optional[List[float]]:
    """Compute a weighted centroid of user memory embeddings.

    Returns a single L2-normalized embedding vector representing the user's
    interest areas, or None if no memories with embeddings are available.
    Used for memory-enhanced retrieval (query vector blending).
    """
    now_dt = datetime.now(timezone.utc)

    # Fetch memories with embeddings
    result = await db.execute(
        select(UserMemory).where(
            UserMemory.user_id == user_id,
            UserMemory.embedding.isnot(None),
            (UserMemory.expires_at.is_(None)) | (UserMemory.expires_at > now_dt),
        )
        .order_by(UserMemory.importance.desc())
        .limit(top_k)
    )
    memories = list(result.scalars().all())
    if not memories:
        return None

    # Check cache
    cache_key = (user_id, len(memories))
    cached = _user_interest_cache.get(cache_key)
    if cached:
        vec, ts = cached
        if _time.monotonic() - ts < _USER_INTEREST_CACHE_TTL:
            _user_interest_cache.move_to_end(cache_key)
            return vec
        _user_interest_cache.pop(cache_key, None)

    # Compute weighted centroid
    centroid = None
    total_weight = 0.0

    for mem in memories:
        try:
            emb = mem.embedding if isinstance(mem.embedding, list) else json.loads(mem.embedding)
        except (json.JSONDecodeError, TypeError):
            continue
        if not emb:
            continue

        # Weight: importance * time decay
        importance = mem.importance or 1.0
        ref_time = mem.last_accessed_at or mem.created_at
        if ref_time and ref_time.tzinfo is None:
            ref_time = ref_time.replace(tzinfo=timezone.utc)
        days_since = max((now_dt - ref_time).total_seconds() / 86400, 0) if ref_time else 0
        decay = math.exp(-TIME_DECAY_LAMBDA * days_since)
        weight = importance * decay

        if centroid is None:
            centroid = [e * weight for e in emb]
        else:
            if len(emb) != len(centroid):
                continue  # dimension mismatch, skip
            centroid = [c + e * weight for c, e in zip(centroid, emb)]
        total_weight += weight

    if centroid is None or total_weight == 0:
        return None

    # Normalize
    centroid = [c / total_weight for c in centroid]
    norm = math.sqrt(sum(c * c for c in centroid))
    if norm > 0:
        centroid = [c / norm for c in centroid]

    # Cache
    _user_interest_cache[cache_key] = (centroid, _time.monotonic())
    if len(_user_interest_cache) > _USER_INTEREST_CACHE_MAX:
        _user_interest_cache.popitem(last=False)

    logger.debug("Computed user interest vector for user_id=%s from %d memories (dim=%d)",
                 user_id, len(memories), len(centroid))
    return centroid


# ---------------------------------------------------------------------------
# CRUD operations
# ---------------------------------------------------------------------------

async def list_memories(
    db: AsyncSession,
    user_id: int,
    category: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """List user memories with pagination."""
    filters = [UserMemory.user_id == user_id]
    if category:
        filters.append(UserMemory.category == category)

    total = (await db.execute(
        select(func.count(UserMemory.id)).where(*filters)
    )).scalar() or 0

    result = await db.execute(
        select(UserMemory)
        .where(*filters)
        .order_by(UserMemory.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [
        {
            "id": m.id,
            "content": m.content,
            "category": m.category,
            "source": m.source,
            "importance": m.importance,
            "access_count": m.access_count,
            "memory_type": m.memory_type,
            "expires_at": m.expires_at.isoformat() if m.expires_at else None,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in result.scalars().all()
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


async def create_memory(
    db: AsyncSession,
    user_id: int,
    content: str,
    category: str = "general",
) -> UserMemory:
    """Manually create a memory."""
    memory = UserMemory(
        user_id=user_id,
        content=content,
        category=category,
        source="manual",
    )
    db.add(memory)
    await db.commit()
    await db.refresh(memory)
    # Generate embedding
    await _update_embeddings(db, [memory], user_id)
    return memory


async def update_memory(
    db: AsyncSession,
    user_id: int,
    memory_id: int,
    content: str,
) -> Optional[UserMemory]:
    """Update memory content and regenerate its embedding."""
    result = await db.execute(
        select(UserMemory).where(
            UserMemory.id == memory_id,
            UserMemory.user_id == user_id,
        )
    )
    mem = result.scalar_one_or_none()
    if not mem:
        return None
    mem.content = content
    await db.commit()
    await db.refresh(mem)
    await _update_embeddings(db, [mem], user_id)
    return mem


async def delete_memory(db: AsyncSession, user_id: int, memory_id: int) -> bool:
    """Delete a specific memory."""
    result = await db.execute(
        select(UserMemory).where(
            UserMemory.id == memory_id,
            UserMemory.user_id == user_id,
        )
    )
    mem = result.scalar_one_or_none()
    if not mem:
        return False
    await db.delete(mem)
    await db.commit()
    return True


async def clear_all_memories(db: AsyncSession, user_id: int) -> int:
    """Delete all memories for a user. Returns count deleted."""
    result = await db.execute(
        select(func.count(UserMemory.id)).where(UserMemory.user_id == user_id)
    )
    count = result.scalar() or 0
    await db.execute(delete(UserMemory).where(UserMemory.user_id == user_id))
    await db.commit()
    return count


# ---------------------------------------------------------------------------
# Expired memory cleanup
# ---------------------------------------------------------------------------

async def cleanup_expired_memories(db: AsyncSession) -> int:
    """Delete memories that have expired. Returns count deleted."""
    now = datetime.now(timezone.utc)
    count_result = await db.execute(
        select(func.count(UserMemory.id)).where(
            UserMemory.expires_at.isnot(None),
            UserMemory.expires_at <= now,
        )
    )
    count = count_result.scalar() or 0
    if count > 0:
        await db.execute(
            delete(UserMemory).where(
                UserMemory.expires_at.isnot(None),
                UserMemory.expires_at <= now,
            )
        )
        await db.commit()
        logger.info("Cleaned up %d expired memories", count)
    return count


# ---------------------------------------------------------------------------
# User profile generation
# ---------------------------------------------------------------------------

async def build_user_profile(
    db: AsyncSession,
    user_id: int,
    llm_config: ModelConfig,
) -> UserProfile:
    """Analyze all user memories to build/update a profile summary via LLM."""
    # Check if we already have a recent profile and memories haven't changed
    existing = await db.execute(
        select(UserProfile).where(UserProfile.user_id == user_id)
    )
    profile = existing.scalar_one_or_none()

    # Gather all non-expired memories
    now = datetime.now(timezone.utc)
    mem_result = await db.execute(
        select(UserMemory).where(
            UserMemory.user_id == user_id,
            (UserMemory.expires_at.is_(None)) | (UserMemory.expires_at > now),
        )
        .order_by(UserMemory.importance.desc(), UserMemory.updated_at.desc())
        .limit(200)
    )
    all_memories = list(mem_result.scalars().all())

    if not all_memories:
        if not profile:
            profile = UserProfile(user_id=user_id, profile_summary="暂无足够的记忆来生成用户画像。")
            db.add(profile)
            await db.commit()
            await db.refresh(profile)
        return profile

    # Check if profile is still fresh (updated after the most recent memory change)
    if profile and profile.updated_at:
        latest_mem_update = max(
            (m.updated_at for m in all_memories if m.updated_at),
            default=None,
        )
        if latest_mem_update:
            p_updated = profile.updated_at
            m_updated = latest_mem_update
            if p_updated.tzinfo is None:
                p_updated = p_updated.replace(tzinfo=timezone.utc)
            if m_updated.tzinfo is None:
                m_updated = m_updated.replace(tzinfo=timezone.utc)
            if p_updated > m_updated:
                return profile

    # Build memory list text for the prompt
    mem_lines = []
    for m in all_memories:
        cat_label = {"preference": "偏好", "fact": "事实", "insight": "经验"}.get(m.category, "记忆")
        mem_lines.append(f"- [{cat_label}] {m.content}")
    memories_text = "\n".join(mem_lines)

    prompt = PROFILE_BUILD_PROMPT.format(memories=memories_text)
    try:
        response = await chat_completion(
            llm_config,
            [
                {"role": "system", "content": "你是一个用户画像分析助手。请严格按照JSON格式输出。"},
                {"role": "user", "content": prompt},
            ],
            stream=False,
        )

        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            text = text.rsplit("```", 1)[0]
        profile_data = json.loads(text)

        summary = profile_data.get("profile_summary") or ""
        topics = profile_data.get("topics_of_interest")
        style = profile_data.get("communication_style")
        expertise = profile_data.get("expertise_areas")

        if isinstance(topics, list):
            topics = json.dumps(topics, ensure_ascii=False)
        if isinstance(expertise, list):
            expertise = json.dumps(expertise, ensure_ascii=False)
        if style and style not in ("formal", "casual", "technical"):
            style = None

        if profile:
            profile.profile_summary = summary
            profile.topics_of_interest = topics
            profile.communication_style = style
            profile.expertise_areas = expertise
        else:
            profile = UserProfile(
                user_id=user_id,
                profile_summary=summary,
                topics_of_interest=topics,
                communication_style=style,
                expertise_areas=expertise,
            )
            db.add(profile)

        await db.commit()
        await db.refresh(profile)
        logger.info("Built/updated user profile for user_id=%d", user_id)
        return profile

    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.warning("Profile build parse error: %s", exc)
        if not profile:
            profile = UserProfile(user_id=user_id, profile_summary="画像生成失败，请稍后重试。")
            db.add(profile)
            await db.commit()
            await db.refresh(profile)
        return profile
    except Exception as exc:
        logger.warning("Profile build failed: %s", exc)
        if not profile:
            profile = UserProfile(user_id=user_id, profile_summary="画像生成失败，请稍后重试。")
            db.add(profile)
            await db.commit()
            await db.refresh(profile)
        return profile


async def get_user_profile(db: AsyncSession, user_id: int) -> Optional[UserProfile]:
    """Retrieve existing user profile without regenerating."""
    result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == user_id)
    )
    return result.scalar_one_or_none()


def build_profile_context(profile: Optional[UserProfile]) -> str:
    """Format a user profile into a context string for the system prompt."""
    if not profile or not profile.profile_summary:
        return ""
    parts = ["以下是该用户的画像信息：", f"画像摘要：{profile.profile_summary}"]
    if profile.topics_of_interest:
        parts.append(f"兴趣主题：{profile.topics_of_interest}")
    if profile.communication_style:
        style_map = {"formal": "正式", "casual": "随意", "technical": "技术性"}
        parts.append(f"沟通风格：{style_map.get(profile.communication_style, profile.communication_style)}")
    if profile.expertise_areas:
        parts.append(f"擅长领域：{profile.expertise_areas}")
    return "\n".join(parts)
