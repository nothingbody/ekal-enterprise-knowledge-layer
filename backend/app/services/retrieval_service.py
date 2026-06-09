import asyncio
import logging
import time
from collections import OrderedDict
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.knowledge_base import KnowledgeBase
from app.models.document import Document, DocumentChunk, DocumentStatus
from app.models.model_config import ModelConfig, ModelType
from app.services.embedding_service import search_similar
from app.services.access_service import list_accessible_kb_ids
from app.schemas.chat import RetrievalResult
from app.core.llm_client import rerank_documents
from app.core.query_rewrite import rewrite_query, generate_multi_queries, condense_question, condense_and_expand
from app.config import settings

logger = logging.getLogger(__name__)

BM25_MAX_CHUNKS = 10_000

# ---------------------------------------------------------------------------
# BM25 index cache — keyed by (kb_id, chunk_count) so it auto-invalidates
# when documents are added/removed.  TTL = 300s, max 32 entries.
# ---------------------------------------------------------------------------
_BM25_CACHE_MAX = 32
_BM25_CACHE_TTL = 300  # seconds
_bm25_cache: OrderedDict[tuple, tuple] = OrderedDict()  # key -> (bm25, all_chunks, ts)


def _get_bm25_cached(kb_id: int, chunk_count: int):
    """Return (bm25, all_chunks) from cache or None."""
    key = (kb_id, chunk_count)
    entry = _bm25_cache.get(key)
    if entry is None:
        return None
    bm25_obj, chunks, ts = entry
    if time.monotonic() - ts > _BM25_CACHE_TTL:
        _bm25_cache.pop(key, None)
        return None
    _bm25_cache.move_to_end(key)
    return bm25_obj, chunks


def _put_bm25_cached(kb_id: int, chunk_count: int, bm25_obj, chunks):
    key = (kb_id, chunk_count)
    _bm25_cache[key] = (bm25_obj, chunks, time.monotonic())
    if len(_bm25_cache) > _BM25_CACHE_MAX:
        _bm25_cache.popitem(last=False)


def invalidate_bm25_cache(kb_id: Optional[int] = None):
    if kb_id is None:
        _bm25_cache.clear()
        return
    for key in [key for key in list(_bm25_cache.keys()) if key[0] == kb_id]:
        _bm25_cache.pop(key, None)


async def _filter_results_to_existing_documents(db: AsyncSession, results: List[dict]) -> List[dict]:
    if not results:
        return results

    doc_ids = {
        r.get("metadata", {}).get("doc_id")
        for r in results
        if r.get("metadata", {}).get("doc_id") is not None
    }
    if not doc_ids:
        return []

    valid_doc_ids = set((await db.execute(
        select(Document.id).where(
            Document.id.in_(doc_ids),
            Document.status == DocumentStatus.COMPLETED,
        )
    )).scalars().all())

    filtered = [r for r in results if r.get("metadata", {}).get("doc_id") in valid_doc_ids]
    dropped = len(results) - len(filtered)
    if dropped > 0:
        logger.debug("过滤掉 %s 条已失效的检索结果", dropped)
    return filtered


async def _bm25_search(db: AsyncSession, kb_id: int, query: str, top_k: int = 10) -> List[dict]:
    from rank_bm25 import BM25Okapi
    import jieba

    # Check total count first to avoid loading unlimited data into memory
    total = (await db.execute(
        select(func.count(DocumentChunk.id))
        .select_from(DocumentChunk)
        .join(Document, Document.id == DocumentChunk.doc_id)
        .where(
            DocumentChunk.kb_id == kb_id,
            Document.status == DocumentStatus.COMPLETED,
        )
    )).scalar() or 0
    if total == 0:
        logger.info("BM25 检索跳过: kb_id=%s 无已完成文档切片", kb_id)
        return []

    if total > BM25_MAX_CHUNKS:
        logger.warning(
            "知识库 kb_id=%s 共 %d 个切片，超过 BM25 上限 %d，仅检索最近的切片",
            kb_id, total, BM25_MAX_CHUNKS,
        )

    # Try cache first (use actual total as cache key so changes are detected)
    cached = _get_bm25_cached(kb_id, total)
    if cached:
        bm25, all_chunks = cached
    else:
        query_stmt = (
            select(DocumentChunk)
            .join(Document, Document.id == DocumentChunk.doc_id)
            .where(
                DocumentChunk.kb_id == kb_id,
                Document.status == DocumentStatus.COMPLETED,
            )
            .order_by(DocumentChunk.id.desc())
            .limit(BM25_MAX_CHUNKS)
        )
        result = await db.execute(query_stmt)
        all_chunks = result.scalars().all()
        if not all_chunks:
            return []

        # Build BM25 index in thread pool to avoid blocking the event loop
        contents = [c.content for c in all_chunks]

        def _build_index():
            corpus = [list(jieba.cut(text)) for text in contents]
            return BM25Okapi(corpus)

        bm25 = await asyncio.to_thread(_build_index)
        _put_bm25_cached(kb_id, total, bm25, all_chunks)

    # Tokenize query in thread pool too (jieba.cut is CPU-bound)
    query_tokens = await asyncio.to_thread(lambda: list(jieba.cut(query)))
    scores = bm25.get_scores(query_tokens)

    indexed = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)

    results = []
    for i, score in indexed[:top_k]:
        chunk = all_chunks[i]
        if score > 0:
            results.append({
                "content": chunk.content,
                "score": float(score),
                "metadata": {"doc_id": chunk.doc_id, "kb_id": chunk.kb_id, "chunk_index": chunk.chunk_index},
            })
    return results


def _chunk_dedup_key(r: dict) -> str:
    """Generate a dedup key from metadata (doc_id + chunk_index) or content prefix."""
    meta = r.get("metadata", {})
    doc_id = meta.get("doc_id")
    chunk_idx = meta.get("chunk_index")
    if doc_id is not None and chunk_idx is not None:
        return f"{doc_id}:{chunk_idx}"
    return r["content"][:120]


def _rrf_fusion(
    *result_lists: List[dict],
    k: int = 60,
    weights: Optional[List[float]] = None,
) -> List[dict]:
    """Reciprocal Rank Fusion to merge multiple result lists with deduplication."""
    n = len(result_lists)
    if weights is None:
        weights = [1.0 / n] * n

    scores = {}
    content_map = {}

    for list_idx, results in enumerate(result_lists):
        w = weights[list_idx] if list_idx < len(weights) else 1.0 / n
        for rank, r in enumerate(results):
            key = _chunk_dedup_key(r)
            scores[key] = scores.get(key, 0) + w * (1.0 / (k + rank + 1))
            if key not in content_map:
                content_map[key] = r

    sorted_keys = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
    if not sorted_keys:
        return []
    max_score = scores[sorted_keys[0]]
    normalizer = max_score if max_score > 0 else 1.0
    return [{**content_map[key], "score": scores[key] / normalizer} for key in sorted_keys]


async def _expand_context_window(
    db: AsyncSession,
    results: List[dict],
    window: int = 1,
) -> List[dict]:
    """Expand each result with neighboring chunks from the same document.

    For each matched chunk, fetch `window` chunks before and after it,
    then merge their content into the result for richer LLM context.

    Uses a single batch query instead of per-result queries to avoid N+1.
    """
    if window <= 0 or not results:
        return results

    # Phase 1: Collect all needed (doc_id, chunk_index) pairs
    neighbor_cache: dict[tuple[int, int], str] = {}
    all_needed: list[tuple[int, int]] = []
    result_ranges: list[tuple] = []  # (doc_id, chunk_idx, start_idx, end_idx) per result

    for r in results:
        meta = r.get("metadata", {})
        doc_id = meta.get("doc_id")
        chunk_idx = meta.get("chunk_index")

        if doc_id is None or chunk_idx is None:
            result_ranges.append((None, None, 0, 0))
            continue

        start_idx = max(0, chunk_idx - window)
        end_idx = chunk_idx + window
        result_ranges.append((doc_id, chunk_idx, start_idx, end_idx))

        for i in range(start_idx, end_idx + 1):
            if i != chunk_idx:
                all_needed.append((doc_id, i))

    # Phase 2: Batch fetch all neighbor chunks in a single query
    if all_needed:
        # Deduplicate
        unique_needed = list(set(all_needed))
        # Group by doc_id for efficient IN queries
        from collections import defaultdict
        by_doc: dict[int, list[int]] = defaultdict(list)
        for doc_id, idx in unique_needed:
            by_doc[doc_id].append(idx)

        # Single query per doc_id (typically 1-3 docs)
        for doc_id, indices in by_doc.items():
            rows = (await db.execute(
                select(DocumentChunk.chunk_index, DocumentChunk.content)
                .where(
                    DocumentChunk.doc_id == doc_id,
                    DocumentChunk.chunk_index.in_(indices),
                )
            )).all()
            for row in rows:
                neighbor_cache[(doc_id, row.chunk_index)] = row.content

    # Phase 3: Assemble expanded content
    expanded = []
    for i, r in enumerate(results):
        doc_id, chunk_idx, start_idx, end_idx = result_ranges[i]
        if doc_id is None:
            expanded.append(r)
            continue

        parts = []
        for j in range(start_idx, end_idx + 1):
            if j == chunk_idx:
                parts.append(r["content"])
            elif (doc_id, j) in neighbor_cache:
                parts.append(neighbor_cache[(doc_id, j)])

        new_r = r.copy()
        new_r["content"] = "\n\n".join(parts)
        expanded.append(new_r)

    return expanded


async def _search_single_kb(
    db: AsyncSession,
    kb: KnowledgeBase,
    query: str,
    fetch_k: int,
    blend_embedding: Optional[List[float]] = None,
    blend_weight: float = 0.1,
) -> List[dict]:
    """Search a single knowledge base with the configured search mode."""
    search_mode = getattr(kb, 'search_mode', 'hybrid') or 'hybrid'
    vector_fetch_k = max(fetch_k * 2, fetch_k + 10)

    _blend_kw = {"blend_embedding": blend_embedding, "blend_weight": blend_weight}

    if search_mode == "vector":
        vector_results = await search_similar(db, kb.id, kb.embedding_model_id, query, vector_fetch_k, **_blend_kw)
        return await _filter_results_to_existing_documents(db, vector_results)
    elif search_mode == "keyword":
        return await _bm25_search(db, kb.id, query, fetch_k)
    else:
        vector_results = await search_similar(db, kb.id, kb.embedding_model_id, query, vector_fetch_k, **_blend_kw)
        keyword_results = await _bm25_search(db, kb.id, query, fetch_k)
        vector_results = await _filter_results_to_existing_documents(db, vector_results)
        w = getattr(kb, 'vector_weight', None) or settings.VECTOR_SEARCH_WEIGHT
        fused = _rrf_fusion(vector_results, keyword_results, weights=[w, 1 - w])

        # Graph RAG: merge graph-sourced results if enabled
        if settings.GRAPH_RAG_ENABLED:
            try:
                from app.core.agentic_rag.graph_rag.graph_retriever import graph_retrieve
                graph_results = await graph_retrieve(db, kb.id, query, top_k=fetch_k)
                if graph_results:
                    fused = _rrf_fusion(fused, graph_results, weights=[0.7, 0.3])
            except Exception as _g_exc:
                logger.debug("Graph retrieval failed for kb_id=%s: %s", kb.id, _g_exc)

        return fused


async def _find_default_model(
    db: AsyncSession,
    model_type: ModelType,
    *user_ids: int,
) -> Optional[ModelConfig]:
    """Find default model by trying each user_id in order."""
    for uid in user_ids:
        if uid is None:
            continue
        result = await db.execute(
            select(ModelConfig).where(
                ModelConfig.user_id == uid,
                ModelConfig.model_type == model_type,
                ModelConfig.is_default == True,
            )
        )
        model = result.scalar_one_or_none()
        if model:
            return model
    return None


async def _get_negative_feedback_chunk_ids(db: AsyncSession, kb_id: int, user_id: int) -> set:
    """Get chunk keys (doc_id:chunk_index) that received negative feedback in recent conversations.

    Uses feedback from the last 100 assistant messages to avoid scanning entire history.
    """
    from app.models.chat_history import ChatMessage, ChatConversation
    import json as _json

    # Find recent negative feedback messages for this KB
    result = await db.execute(
        select(ChatMessage.references)
        .join(ChatConversation, ChatMessage.conversation_id == ChatConversation.id)
        .where(
            ChatConversation.kb_id == kb_id,
            ChatConversation.user_id == user_id,
            ChatMessage.feedback == "negative",
            ChatMessage.references.isnot(None),
        )
        .order_by(ChatMessage.created_at.desc())
        .limit(100)
    )
    neg_chunk_keys = set()
    for (refs_json,) in result.all():
        try:
            refs = _json.loads(refs_json)
            for ref in refs:
                doc_id = ref.get("doc_id")
                chunk_index = ref.get("chunk_index")
                if doc_id is not None and chunk_index is not None:
                    neg_chunk_keys.add(f"{doc_id}:{chunk_index}")
        except (TypeError, _json.JSONDecodeError):
            continue
    return neg_chunk_keys


async def retrieve(
    db: AsyncSession,
    kb_id: int,
    query: str,
    top_k: int = 5,
    enable_rewrite: bool = True,
    score_threshold: float = None,
    user_id: Optional[int] = None,
    chat_history: Optional[List[dict]] = None,
    metadata_out: Optional[dict] = None,
    # Pipeline control params (from Agentic RAG orchestrator)
    force_multi_query: Optional[bool] = None,
    force_rerank: Optional[bool] = None,
    override_context_window: Optional[int] = None,
    fetch_k_multiplier: float = 1.0,
    # Memory-enhanced retrieval
    blend_embedding: Optional[List[float]] = None,
    blend_weight: float = 0.1,
) -> List[RetrievalResult]:
    kb_result = await db.execute(
        select(KnowledgeBase).where(KnowledgeBase.id == kb_id, KnowledgeBase.deleted_at.is_(None))
    )
    kb = kb_result.scalar_one_or_none()
    if not kb or not kb.embedding_model_id:
        reason = "知识库不存在或已删除" if not kb else "知识库未配置 Embedding 模型"
        logger.warning("检索跳过: kb_id=%s 原因=%s", kb_id, reason)
        if metadata_out is not None:
            metadata_out["skip_reason"] = reason
        return []

    llm_for_rewrite = None
    if enable_rewrite:
        llm_for_rewrite = await _find_default_model(db, ModelType.LLM, kb.user_id, user_id)

    fetch_k = int(top_k * 3 * fetch_k_multiplier)

    # Determine whether to use multi-query expansion
    use_multi_query = True  # default: condense_and_expand does both
    if force_multi_query is False:
        use_multi_query = False
    elif force_multi_query is True:
        use_multi_query = True

    if llm_for_rewrite and use_multi_query:
        queries = await condense_and_expand(llm_for_rewrite, query, chat_history)
        logger.info("查询改写: 原始=%r → 扩展=%r", query, queries)
        # Run sequentially — AsyncSession is NOT safe for concurrent access
        _blend_kw = {"blend_embedding": blend_embedding, "blend_weight": blend_weight}
        all_result_lists = []
        for q in queries:
            all_result_lists.append(await _search_single_kb(db, kb, q, fetch_k, **_blend_kw))
        raw_results = _rrf_fusion(*all_result_lists)
    elif llm_for_rewrite and not use_multi_query:
        # Only condense (resolve references), skip multi-query expansion
        condensed = await condense_question(llm_for_rewrite, query, chat_history or [])
        logger.info("查询凝练(无扩展): 原始=%r → %r", query, condensed)
        raw_results = await _search_single_kb(db, kb, condensed, fetch_k,
                                              blend_embedding=blend_embedding, blend_weight=blend_weight)
    else:
        logger.info("查询改写跳过 (无 LLM), 原始查询=%r", query)
        raw_results = await _search_single_kb(db, kb, query, fetch_k,
                                              blend_embedding=blend_embedding, blend_weight=blend_weight)

    if raw_results:
        scores = [r.get("score", 0) for r in raw_results]
        logger.info(
            "检索结果: kb_id=%s count=%d top_score=%.4f min_score=%.4f",
            kb_id, len(raw_results), max(scores), min(scores),
        )
    else:
        logger.warning("检索结果为空: kb_id=%s query=%r", kb_id, query[:100])

    reranker = None
    if force_rerank is not False:
        reranker = await _find_default_model(db, ModelType.RERANKER, kb.user_id, user_id)
    reranker_used = False

    if reranker and raw_results:
        try:
            docs_text = [r["content"] for r in raw_results]
            reranked = await rerank_documents(reranker, query, docs_text)
            reranked_results = []
            for idx, score in reranked[:top_k]:
                if idx < len(raw_results):
                    item = raw_results[idx].copy()
                    item["score"] = score
                    reranked_results.append(item)
            raw_results = reranked_results if reranked_results else raw_results[:top_k]
            reranker_used = bool(reranked_results)
        except Exception as e:
            logger.warning("Reranker 调用失败 (model_id=%s): %s", reranker.id, e)
            raw_results = raw_results[:top_k]
    else:
        raw_results = raw_results[:top_k]

    if metadata_out is not None:
        metadata_out["reranker_used"] = reranker_used

    # Feedback-driven retrieval improvement: downweight chunks that received negative feedback
    if user_id and raw_results:
        try:
            neg_chunk_ids = await _get_negative_feedback_chunk_ids(db, kb_id, user_id)
            if neg_chunk_ids:
                for i, r in enumerate(raw_results):
                    chunk_key = f"{r.get('doc_id')}:{r.get('chunk_index')}"
                    if chunk_key in neg_chunk_ids:
                        raw_results[i] = {**r, "score": r.get("score", 0) * 0.5}
                        logger.debug("Feedback downweight: chunk %s score halved", chunk_key)
        except Exception as _fb_exc:
            logger.debug("Feedback lookup failed: %s", _fb_exc)

    filter_info = None
    if score_threshold is not None and raw_results:
        before_count = len(raw_results)
        max_score = max(r.get("score", 0) for r in raw_results)
        raw_results = [r for r in raw_results if r.get("score", 0) >= score_threshold]
        if len(raw_results) < before_count:
            logger.info("score_threshold=%.4f 过滤: %d → %d 条",
                         score_threshold, before_count, len(raw_results))
            if not raw_results:
                filter_info = {
                    "filtered_all": True,
                    "before_count": before_count,
                    "threshold": score_threshold,
                    "max_score": round(max_score, 4),
                }
    if metadata_out is not None and filter_info:
        metadata_out["filter_info"] = filter_info

    context_window = override_context_window if override_context_window is not None else (kb.context_window if kb and kb.context_window is not None else 1)
    if context_window and context_window > 0:
        raw_results = await _expand_context_window(db, raw_results, window=context_window)

    return await _resolve_doc_names(db, raw_results)


async def retrieve_multi_kb(
    db: AsyncSession,
    kb_ids: List[int],
    query: str,
    top_k: int = 5,
    user_id: Optional[int] = None,
    score_threshold: float = None,
) -> List[RetrievalResult]:
    """Search across multiple knowledge bases and merge results."""
    allowed_kb_ids = None
    if user_id is not None:
        allowed_kb_ids = set(await list_accessible_kb_ids(db, user_id, "read"))

    # Filter by access control BEFORE querying DB to avoid wasted I/O
    filtered_kb_ids = kb_ids
    if allowed_kb_ids is not None:
        filtered_kb_ids = [kid for kid in kb_ids if kid in allowed_kb_ids]

    eligible_kbs = []
    for kb_id in filtered_kb_ids:
        kb_result = await db.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == kb_id, KnowledgeBase.deleted_at.is_(None))
        )
        kb = kb_result.scalar_one_or_none()
        if not kb or not kb.embedding_model_id:
            continue
        eligible_kbs.append(kb)

    if not eligible_kbs:
        return []

    fetch_k = top_k * 2
    # Run sequentially — AsyncSession is NOT safe for concurrent access
    all_result_lists = []
    for kb in eligible_kbs:
        all_result_lists.append(await _search_single_kb(db, kb, query, fetch_k))

    if not all_result_lists:
        return []

    merged = _rrf_fusion(*all_result_lists)[:top_k]
    if score_threshold is not None:
        merged = [r for r in merged if r.get("score", 0) >= score_threshold]
    return await _resolve_doc_names(db, merged)


async def _resolve_doc_names(db: AsyncSession, raw_results: List[dict]) -> List[RetrievalResult]:
    doc_ids = set()
    article_ids = set()
    for r in raw_results:
        meta = r.get("metadata", {})
        if meta.get("source_type") == "compiled_article":
            article_id = meta.get("article_id")
            if article_id:
                article_ids.add(article_id)
        else:
            doc_id = meta.get("doc_id")
            if doc_id:
                doc_ids.add(doc_id)

    doc_name_map = {}
    if doc_ids:
        doc_result = await db.execute(
            select(Document.id, Document.filename).where(
                Document.id.in_(doc_ids),
                Document.status == DocumentStatus.COMPLETED,
            )
        )
        for row in doc_result:
            doc_name_map[row.id] = row.filename

    # Resolve compiled article titles
    article_title_map = {}
    if article_ids:
        from app.models.compiled_article import CompiledArticle
        article_result = await db.execute(
            select(CompiledArticle.id, CompiledArticle.title).where(
                CompiledArticle.id.in_(article_ids),
            )
        )
        for row in article_result:
            article_title_map[row.id] = row.title

    results = []
    for r in raw_results:
        meta = r.get("metadata", {})
        if meta.get("source_type") == "compiled_article":
            article_id = meta.get("article_id")
            if article_id and article_id not in article_title_map:
                continue
            results.append(RetrievalResult(
                content=r["content"],
                score=r["score"],
                doc_name=f"[编译文章] {article_title_map.get(article_id, '')}",
                chunk_index=0,
                source_type="compiled_article",
            ))
        else:
            doc_id = meta.get("doc_id")
            if doc_id is not None and doc_id not in doc_name_map:
                continue
            results.append(RetrievalResult(
                content=r["content"],
                score=r["score"],
                doc_name=doc_name_map.get(doc_id, ""),
                chunk_index=meta.get("chunk_index", 0),
                source_type=meta.get("source_type"),
            ))
    return results
