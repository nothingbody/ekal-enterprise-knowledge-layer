"""Knowledge Compiler — converts raw document chunks into structured wiki articles.

Core of the Karpathy-inspired LLM Wiki integration. Called after a document is
successfully chunked and embedded.
"""

from __future__ import annotations

import json
import logging
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.llm_client import chat_completion, chat_completion_with_usage
from app.core.knowledge_compilation.config import KnowledgeCompilationConfig
from app.core.knowledge_compilation.prompts import (
    COMPILE_CHUNKS_TO_ARTICLE,
    COMPILE_WITH_MAP_REDUCE,
    SUMMARIZE_CHUNK_GROUP,
)
from app.models.compiled_article import CompiledArticle, CompiledArticleStatus
from app.models.model_config import ModelConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _group_chunks(chunks: List[str], max_per_group: int) -> List[List[str]]:
    """Split a flat chunk list into groups of max_per_group."""
    groups: list[list[str]] = []
    for i in range(0, len(chunks), max_per_group):
        groups.append(chunks[i : i + max_per_group])
    return groups


def _format_chunks(chunks: List[str]) -> str:
    """Format a list of chunks into numbered text for the prompt."""
    parts = []
    for i, chunk in enumerate(chunks, 1):
        parts.append(f"### 片段 {i}\n{chunk}")
    return "\n\n".join(parts)


def _safe_parse_json(text: str) -> Optional[dict]:
    """Attempt to parse JSON from LLM output, handling markdown code fences."""
    text = text.strip()
    # Strip ```json ... ``` wrappers
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


async def _resolve_model(
    db: AsyncSession,
    config: KnowledgeCompilationConfig,
    kb_user_id: int,
) -> Optional[ModelConfig]:
    """Resolve the LLM model to use for compilation."""
    from app.models.model_config import ModelType

    if config.compilation_model_id:
        result = await db.execute(
            select(ModelConfig).where(ModelConfig.id == config.compilation_model_id)
        )
        model = result.scalar_one_or_none()
        if model:
            return model

    # Fallback to the KB owner's default LLM model
    result = await db.execute(
        select(ModelConfig).where(
            ModelConfig.user_id == kb_user_id,
            ModelConfig.model_type == ModelType.LLM,
            ModelConfig.is_default == True,
        )
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Core compilation
# ---------------------------------------------------------------------------

async def _compile_single_group(
    model_config: ModelConfig,
    chunks: List[str],
) -> Optional[dict]:
    """Compile a single chunk group into an article via LLM.

    Returns parsed JSON dict with keys: title, content, summary, tags.
    Returns None on failure.
    """
    prompt = COMPILE_CHUNKS_TO_ARTICLE.format(chunks=_format_chunks(chunks))
    messages = [{"role": "user", "content": prompt}]

    try:
        result = await chat_completion_with_usage(model_config, messages)
        content = result.get("content", "")
        parsed = _safe_parse_json(content)
        if parsed and "title" in parsed and "content" in parsed:
            parsed.setdefault("summary", "")
            parsed.setdefault("tags", [])
            parsed["_token_count"] = result.get("input_tokens", 0) + result.get("output_tokens", 0)
            return parsed
        logger.warning("Compilation LLM returned invalid JSON structure")
        return None
    except Exception as e:
        logger.warning("Compilation LLM call failed: %s", e)
        return None


async def _summarize_group(
    model_config: ModelConfig,
    chunks: List[str],
) -> str:
    """Summarize a chunk group (used in map-reduce for large documents)."""
    prompt = SUMMARIZE_CHUNK_GROUP.format(chunks=_format_chunks(chunks))
    messages = [{"role": "user", "content": prompt}]
    try:
        result = await chat_completion(model_config, messages, stream=False)
        return result if isinstance(result, str) else ""
    except Exception as e:
        logger.warning("Summarize LLM call failed: %s", e)
        return ""


async def _compile_via_map_reduce(
    model_config: ModelConfig,
    chunk_groups: List[List[str]],
) -> Optional[dict]:
    """Map-reduce compilation for large documents with many chunk groups.

    1. Map: summarize each group
    2. Reduce: compile summaries into a single article
    """
    # Map phase — summarize each group
    summaries: list[str] = []
    for group in chunk_groups:
        summary = await _summarize_group(model_config, group)
        if summary:
            summaries.append(summary)

    if not summaries:
        return None

    # Reduce phase — compile from summaries
    formatted = "\n\n---\n\n".join(
        f"### 摘要 {i}\n{s}" for i, s in enumerate(summaries, 1)
    )
    prompt = COMPILE_WITH_MAP_REDUCE.format(summaries=formatted)
    messages = [{"role": "user", "content": prompt}]

    try:
        result = await chat_completion_with_usage(model_config, messages)
        content = result.get("content", "")
        parsed = _safe_parse_json(content)
        if parsed and "title" in parsed and "content" in parsed:
            parsed.setdefault("summary", "")
            parsed.setdefault("tags", [])
            parsed["_token_count"] = result.get("input_tokens", 0) + result.get("output_tokens", 0)
            return parsed
        return None
    except Exception as e:
        logger.warning("Map-reduce compilation failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def compile_chunks_to_articles(
    db: AsyncSession,
    kb_id: int,
    doc_id: int,
    chunks: List[str],
    config: KnowledgeCompilationConfig,
    kb_user_id: int = 0,
) -> List[CompiledArticle]:
    """Compile document chunks into structured knowledge articles.

    This is the main entry point called after document ingestion.

    Args:
        db: Database session.
        kb_id: Knowledge base ID.
        doc_id: Source document ID.
        chunks: Raw text chunks from the document.
        config: Compilation configuration.
        kb_user_id: KB owner user ID (for model resolution).

    Returns:
        List of created CompiledArticle records.
    """
    if not chunks:
        return []

    model_config = await _resolve_model(db, config, kb_user_id)
    if not model_config:
        logger.warning("No LLM model available for compilation (kb_id=%s)", kb_id)
        return []

    max_per_group = config.max_chunks_per_group
    groups = _group_chunks(chunks, max_per_group)

    articles: list[CompiledArticle] = []

    # Decide strategy: direct compile per group or map-reduce
    use_map_reduce = len(groups) > 3  # More than 3 groups → map-reduce into 1 article

    if use_map_reduce:
        parsed = await _compile_via_map_reduce(model_config, groups)
        if parsed:
            # Build source chunk IDs for the full document
            all_chunk_ids = [f"doc_{doc_id}_chunk_{i}" for i in range(len(chunks))]
            article = CompiledArticle(
                kb_id=kb_id,
                title=parsed["title"],
                content=parsed["content"],
                summary=parsed.get("summary", ""),
                tags=json.dumps(parsed.get("tags", []), ensure_ascii=False),
                source_doc_ids=json.dumps([doc_id]),
                source_chunk_ids=json.dumps(all_chunk_ids),
                version=1,
                status=CompiledArticleStatus.COMPILED.value,
                token_count=parsed.get("_token_count", 0),
            )
            db.add(article)
            articles.append(article)
    else:
        # Compile each group into a separate article
        for group_idx, group in enumerate(groups):
            parsed = await _compile_single_group(model_config, group)
            if parsed:
                start_idx = group_idx * max_per_group
                chunk_ids = [
                    f"doc_{doc_id}_chunk_{start_idx + j}"
                    for j in range(len(group))
                ]
                article = CompiledArticle(
                    kb_id=kb_id,
                    title=parsed["title"],
                    content=parsed["content"],
                    summary=parsed.get("summary", ""),
                    tags=json.dumps(parsed.get("tags", []), ensure_ascii=False),
                    source_doc_ids=json.dumps([doc_id]),
                    source_chunk_ids=json.dumps(chunk_ids),
                    version=1,
                    status=CompiledArticleStatus.COMPILED.value,
                    token_count=parsed.get("_token_count", 0),
                )
                db.add(article)
                articles.append(article)
            else:
                # Mark as drafting for failed groups
                article = CompiledArticle(
                    kb_id=kb_id,
                    title=f"[编译失败] 文档 {doc_id} 分组 {group_idx + 1}",
                    content="编译失败，请手动重试。",
                    source_doc_ids=json.dumps([doc_id]),
                    version=1,
                    status=CompiledArticleStatus.DRAFTING.value,
                )
                db.add(article)
                articles.append(article)

    if articles:
        await db.commit()
        # Embed compiled articles into the vector store
        await _embed_compiled_articles(db, kb_id, articles, kb_user_id)

    logger.info(
        "Compiled %d articles from doc_id=%s (kb_id=%s, strategy=%s)",
        len(articles), doc_id, kb_id,
        "map_reduce" if use_map_reduce else "direct",
    )
    return articles


async def compile_entire_kb(
    db: AsyncSession,
    kb_id: int,
    config: KnowledgeCompilationConfig,
    kb_user_id: int = 0,
) -> List[CompiledArticle]:
    """Compile all documents in a knowledge base (full rebuild).

    Marks existing compiled articles as archived, then recompiles.
    """
    from app.models.document import Document, DocumentStatus, DocumentChunk
    from sqlalchemy import update

    # Archive existing articles
    await db.execute(
        update(CompiledArticle)
        .where(CompiledArticle.kb_id == kb_id)
        .where(CompiledArticle.status != CompiledArticleStatus.ARCHIVED.value)
        .values(status=CompiledArticleStatus.ARCHIVED.value)
    )
    await db.commit()

    # Fetch all completed documents
    doc_result = await db.execute(
        select(Document)
        .where(Document.kb_id == kb_id)
        .where(Document.status == DocumentStatus.COMPLETED)
        .where(Document.deleted_at.is_(None))
    )
    docs = doc_result.scalars().all()

    all_articles: list[CompiledArticle] = []
    for doc in docs:
        chunk_result = await db.execute(
            select(DocumentChunk.content)
            .where(DocumentChunk.doc_id == doc.id)
            .order_by(DocumentChunk.chunk_index)
        )
        chunks = [row[0] for row in chunk_result.all()]
        if chunks:
            articles = await compile_chunks_to_articles(
                db, kb_id, doc.id, chunks, config, kb_user_id
            )
            all_articles.extend(articles)

    return all_articles


# ---------------------------------------------------------------------------
# Embedding compiled articles into vector store
# ---------------------------------------------------------------------------

async def _embed_compiled_articles(
    db: AsyncSession,
    kb_id: int,
    articles: List[CompiledArticle],
    kb_user_id: int,
) -> None:
    """Embed compiled articles into the KB's vector collection.

    Articles are stored alongside raw chunks with metadata
    source_type='compiled_article' so they can be distinguished during retrieval.
    """
    from app.services.embedding_service import get_collection_name
    from app.core.llm_client import create_embeddings
    from app.core.vector_store import get_vector_store
    from app.models.knowledge_base import KnowledgeBase

    # Get KB embedding model
    kb_result = await db.execute(
        select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
    )
    kb = kb_result.scalar_one_or_none()
    if not kb or not kb.embedding_model_id:
        logger.warning("Cannot embed articles: KB %s has no embedding model", kb_id)
        return

    model_result = await db.execute(
        select(ModelConfig).where(ModelConfig.id == kb.embedding_model_id)
    )
    embed_model = model_result.scalar_one_or_none()
    if not embed_model:
        return

    # Prepare texts and metadata
    compilable = [a for a in articles if a.status == CompiledArticleStatus.COMPILED.value]
    if not compilable:
        return

    texts = [f"{a.title}\n\n{a.summary or ''}\n\n{a.content}" for a in compilable]
    ids = [f"article_{a.id}" for a in compilable]
    metadatas = [
        {
            "source_type": "compiled_article",
            "article_id": a.id,
            "kb_id": kb_id,
            "title": a.title,
        }
        for a in compilable
    ]

    try:
        embeddings = await create_embeddings(embed_model, texts)
        store = get_vector_store()
        collection_name = get_collection_name(kb_id)
        store.get_or_create_collection(collection_name)
        store.add(collection_name, ids, embeddings, texts, metadatas)
        logger.info("Embedded %d compiled articles into %s", len(compilable), collection_name)
    except Exception as e:
        logger.warning("Failed to embed compiled articles (kb_id=%s): %s", kb_id, e)
