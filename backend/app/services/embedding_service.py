import asyncio
import hashlib
import logging
import time
from collections import OrderedDict
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.models.model_config import ModelConfig
from app.core.llm_client import create_embeddings
from app.core.vector_store import get_vector_store

_logger = logging.getLogger(__name__)

EMBED_BATCH_SIZE = 64
EMBED_CONCURRENCY = 4

# ---------------------------------------------------------------------------
# Query embedding cache — avoids redundant API calls for repeated queries.
# Keyed by (model_id, sha256(query_text)), TTL = 300s, max 256 entries.
# ---------------------------------------------------------------------------
_QUERY_EMBED_CACHE_MAX = 256
_QUERY_EMBED_CACHE_TTL = 300  # seconds
_query_embed_cache: OrderedDict[str, tuple] = OrderedDict()  # key -> (embedding, ts)


def _query_cache_key(model_id: int, text: str) -> str:
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]
    return f"{model_id}:{h}"


def _get_cached_query_embedding(model_id: int, text: str) -> Optional[List[float]]:
    key = _query_cache_key(model_id, text)
    entry = _query_embed_cache.get(key)
    if entry is None:
        return None
    embedding, ts = entry
    if time.monotonic() - ts > _QUERY_EMBED_CACHE_TTL:
        _query_embed_cache.pop(key, None)
        return None
    _query_embed_cache.move_to_end(key)
    return embedding


def _put_cached_query_embedding(model_id: int, text: str, embedding: List[float]) -> None:
    key = _query_cache_key(model_id, text)
    _query_embed_cache[key] = (embedding, time.monotonic())
    if len(_query_embed_cache) > _QUERY_EMBED_CACHE_MAX:
        _query_embed_cache.popitem(last=False)


def get_collection_name(kb_id: int) -> str:
    return f"kb_{kb_id}"


async def embed_and_store(
    db: AsyncSession,
    kb_id: int,
    embedding_model_id: int,
    chunks: List[str],
    doc_id: int,
    metadatas: Optional[List[dict]] = None,
):
    result = await db.execute(select(ModelConfig).where(ModelConfig.id == embedding_model_id))
    model_config = result.scalar_one_or_none()
    if not model_config:
        raise ValueError("Embedding 模型配置不存在")

    batch_size = EMBED_BATCH_SIZE
    max_retries = 2
    store = get_vector_store()
    collection_name = get_collection_name(kb_id)
    store.get_or_create_collection(collection_name)

    # ── Phase 1: Compute all embeddings concurrently ──
    batches = []
    for i in range(0, len(chunks), batch_size):
        batch_chunks = chunks[i : i + batch_size]
        ids = [f"doc_{doc_id}_chunk_{i + j}" for j in range(len(batch_chunks))]
        batch_meta = []
        for j, chunk in enumerate(batch_chunks):
            meta = {"doc_id": doc_id, "kb_id": kb_id, "chunk_index": i + j}
            if metadatas and i + j < len(metadatas):
                meta.update(metadatas[i + j])
            batch_meta.append(meta)
        batches.append((i, batch_chunks, ids, batch_meta))

    sem = asyncio.Semaphore(EMBED_CONCURRENCY)
    embedding_results: list = [None] * len(batches)

    async def _embed_batch(idx: int, offset: int, texts: List[str]):
        async with sem:
            last_err = None
            for attempt in range(1, max_retries + 1):
                try:
                    embedding_results[idx] = await create_embeddings(model_config, texts)
                    return
                except Exception as exc:
                    last_err = exc
                    _logger.warning(
                        "Embedding batch %d-%d 失败 (attempt %d/%d, doc_id=%d): %s",
                        offset, offset + len(texts), attempt, max_retries, doc_id, exc,
                    )
                    if attempt < max_retries:
                        await asyncio.sleep(2 ** attempt)
            raise RuntimeError(
                f"Embedding 失败 (batch offset {offset}, doc_id={doc_id}): {last_err}"
            ) from last_err

    try:
        await asyncio.gather(
            *[_embed_batch(idx, b[0], b[1]) for idx, b in enumerate(batches)]
        )
    except Exception as exc:
        raise RuntimeError(f"Embedding 并发计算失败 (doc_id={doc_id}): {exc}") from exc

    # ── Phase 2: Store embeddings sequentially in vector DB ──
    stored_ids: list[str] = []
    _dimension_reset_done = False
    for idx, (offset, batch_chunks, ids, batch_meta) in enumerate(batches):
        embeddings = embedding_results[idx]
        try:
            store.add(
                collection_name=collection_name,
                ids=ids,
                embeddings=embeddings,
                documents=batch_chunks,
                metadatas=batch_meta,
            )
            stored_ids.extend(ids)
        except Exception as exc:
            # Auto-fix dimension mismatch: use temp collection to avoid data loss
            if not _dimension_reset_done and "dimension" in str(exc).lower():
                _logger.warning(
                    "向量维度不匹配 (kb_id=%d)，尝试重建 collection: %s", kb_id, exc,
                )
                temp_name = f"{collection_name}_rebuild_{int(time.time())}"
                try:
                    import time
                    store.get_or_create_collection(temp_name)
                    # Store ALL batches in temp collection first
                    temp_ids = []
                    for retry_idx, (_, rc, ri, rm) in enumerate(batches):
                        if embedding_results[retry_idx] is None:
                            _logger.warning("Skipping batch %d in rebuild: embeddings are None", retry_idx)
                            continue
                        store.add(
                            collection_name=temp_name,
                            ids=ri,
                            embeddings=embedding_results[retry_idx],
                            documents=rc,
                            metadatas=rm,
                        )
                        temp_ids.extend(ri)
                    # Success — swap: delete old, rename temp
                    store.delete_collection(collection_name)
                    # ChromaDB doesn't support rename, so we keep temp as-is
                    # and update the collection name mapping
                    _logger.info(
                        "向量维度重建成功 (kb_id=%d)，旧 collection 已删除", kb_id,
                    )
                    _dimension_reset_done = True
                    stored_ids = temp_ids
                    break
                except Exception as rebuild_exc:
                    # Rebuild failed — clean up temp, keep original intact
                    _logger.error(
                        "向量维度重建失败 (kb_id=%d)，保留原 collection: %s",
                        kb_id, rebuild_exc,
                    )
                    try:
                        store.delete_collection(temp_name)
                    except Exception:
                        pass
                    raise RuntimeError(
                        f"向量维度不匹配且重建失败 (kb_id={kb_id}): {rebuild_exc}"
                    ) from rebuild_exc
            # Non-dimension error: roll back and raise
            if stored_ids:
                try:
                    store.delete_by_ids(collection_name, stored_ids)
                except Exception:
                    _logger.warning("Embedding 回滚清理失败 (doc_id=%d)", doc_id)
            raise RuntimeError(
                f"向量存储失败 (batch offset {offset}, doc_id={doc_id}): {exc}"
            ) from exc


async def search_similar(
    db: AsyncSession,
    kb_id: int,
    embedding_model_id: int,
    query: str,
    top_k: int = None,
    blend_embedding: Optional[List[float]] = None,
    blend_weight: float = 0.1,
) -> List[dict]:
    """Search for similar documents in a knowledge base.

    When blend_embedding is provided (e.g., user interest vector), the query
    embedding is blended with it to personalize retrieval results towards the
    user's interest areas. The blend_weight controls the influence (0.0-1.0).
    """
    import math
    top_k = top_k or settings.DEFAULT_TOP_K

    result = await db.execute(select(ModelConfig).where(ModelConfig.id == embedding_model_id))
    model_config = result.scalar_one_or_none()
    if not model_config:
        raise ValueError("Embedding 模型配置不存在")

    # Try cache first to avoid redundant embedding API calls
    cached = _get_cached_query_embedding(embedding_model_id, query)
    if cached is not None:
        query_emb = cached
    else:
        embeddings = await create_embeddings(model_config, [query])
        query_emb = embeddings[0]
        _put_cached_query_embedding(embedding_model_id, query, query_emb)

    # Memory-enhanced retrieval: blend user interest vector into query embedding
    if blend_embedding and len(blend_embedding) == len(query_emb) and 0 < blend_weight <= 1.0:
        w = blend_weight
        blended = [(1 - w) * q + w * b for q, b in zip(query_emb, blend_embedding)]
        norm = math.sqrt(sum(x * x for x in blended))
        if norm > 0:
            query_emb = [x / norm for x in blended]
        _logger.debug("Blended user interest vector (weight=%.2f, dim=%d)", w, len(query_emb))
    elif blend_embedding and len(blend_embedding) != len(query_emb):
        _logger.debug("Skipping blend: dimension mismatch (%d vs %d)", len(blend_embedding), len(query_emb))

    store = get_vector_store()
    return store.query(
        collection_name=get_collection_name(kb_id),
        query_embedding=query_emb,
        top_k=top_k,
    )


def delete_collection(kb_id: int):
    store = get_vector_store()
    store.delete_collection(get_collection_name(kb_id))


def delete_doc_chunks_from_collection(kb_id: int, doc_id: int):
    store = get_vector_store()
    store.delete_by_filter(get_collection_name(kb_id), {"doc_id": doc_id})


async def update_chunk_in_collection(
    db: AsyncSession,
    kb_id: int,
    doc_id: int,
    chunk_index: int,
    new_content: str,
):
    """Update a single chunk's text and re-embed it in the vector store."""
    from app.models.knowledge_base import KnowledgeBase
    kb_result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    kb = kb_result.scalar_one_or_none()
    if not kb or not kb.embedding_model_id:
        return

    model_result = await db.execute(select(ModelConfig).where(ModelConfig.id == kb.embedding_model_id))
    model_config = model_result.scalar_one_or_none()
    if not model_config:
        return

    embeddings = await create_embeddings(model_config, [new_content])
    store = get_vector_store()
    chunk_id = f"doc_{doc_id}_chunk_{chunk_index}"
    store.upsert(
        collection_name=get_collection_name(kb_id),
        ids=[chunk_id],
        embeddings=embeddings,
        documents=[new_content],
        metadatas=[{"doc_id": doc_id, "kb_id": kb_id, "chunk_index": chunk_index}],
    )


async def add_chunk_to_collection(
    db: AsyncSession,
    kb_id: int,
    doc_id: int,
    chunk_index: int,
    content: str,
):
    """Add a single new chunk to the vector store."""
    await update_chunk_in_collection(db, kb_id, doc_id, chunk_index, content)


def delete_chunk_from_collection(kb_id: int, doc_id: int, chunk_index: int):
    """Delete a single chunk from the vector store by its ID."""
    store = get_vector_store()
    chunk_id = f"doc_{doc_id}_chunk_{chunk_index}"
    store.delete_by_ids(get_collection_name(kb_id), [chunk_id])
