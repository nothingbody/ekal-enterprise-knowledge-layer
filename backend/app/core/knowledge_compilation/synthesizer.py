"""Incremental Knowledge Synthesizer — updates existing articles when new documents arrive.

When a new document is added to a KB with compilation enabled, this module:
1. Finds existing compiled articles related to the new content
2. Updates them to integrate the new information
3. Creates new articles for unmatched content
4. Builds cross-references between articles
"""

from __future__ import annotations

import json
import logging
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.knowledge_compilation.config import KnowledgeCompilationConfig
from app.core.knowledge_compilation.compiler import (
    compile_chunks_to_articles,
    _resolve_model,
    _safe_parse_json,
    _format_chunks,
    _group_chunks,
)
from app.core.knowledge_compilation.prompts import SYNTHESIZE_INTO_ARTICLE
from app.core.llm_client import chat_completion_with_usage, create_embeddings
from app.core.vector_store import get_vector_store
from app.models.compiled_article import CompiledArticle, CompiledArticleStatus, ArticleCrossRef
from app.models.model_config import ModelConfig
from app.services.embedding_service import get_collection_name

logger = logging.getLogger(__name__)


async def _find_related_articles(
    db: AsyncSession,
    kb_id: int,
    chunks: List[str],
    embed_model: ModelConfig,
    threshold: float,
) -> dict[int, List[str]]:
    """Find existing compiled articles related to new chunks.

    Returns: {article_id: [related_chunk_texts]}
    """
    store = get_vector_store()
    collection_name = get_collection_name(kb_id)

    article_chunk_map: dict[int, list[str]] = {}

    # Sample up to 5 chunks for similarity search (avoid excessive API calls)
    sample_chunks = chunks[:5] if len(chunks) > 5 else chunks

    for chunk_text in sample_chunks:
        try:
            embeddings = await create_embeddings(embed_model, [chunk_text])
            if not embeddings or not embeddings[0]:
                continue

            results = store.query(
                collection_name,
                query_embedding=embeddings[0],
                top_k=10,
            )

            for result in results:
                meta = result.get("metadata", {})
                if meta.get("source_type") != "compiled_article":
                    continue
                score = result.get("score", 0)
                if score < threshold:
                    continue
                article_id = meta.get("article_id")
                if article_id:
                    if article_id not in article_chunk_map:
                        article_chunk_map[article_id] = []
                    article_chunk_map[article_id].append(chunk_text)
        except Exception as e:
            logger.debug("Similarity search failed for chunk: %s", e)
            continue

    return article_chunk_map


async def _update_article_with_new_info(
    db: AsyncSession,
    article: CompiledArticle,
    new_chunks: List[str],
    model_config: ModelConfig,
    doc_id: int,
) -> Optional[bool]:
    """Update an existing article with new information via LLM.

    Returns True if contradictions were detected, False if none, None on failure.
    """
    prompt = SYNTHESIZE_INTO_ARTICLE.format(
        article_title=article.title,
        article_content=article.content,
        new_chunks=_format_chunks(new_chunks),
    )
    messages = [{"role": "user", "content": prompt}]

    try:
        result = await chat_completion_with_usage(model_config, messages)
        content = result.get("content", "")
        parsed = _safe_parse_json(content)

        if not parsed or "content" not in parsed:
            logger.warning("Synthesis LLM returned invalid JSON for article %s", article.id)
            return None

        # Update the article
        article.title = parsed.get("title", article.title)
        article.content = parsed["content"]
        article.summary = parsed.get("summary", article.summary)
        if parsed.get("tags"):
            article.tags = json.dumps(parsed["tags"], ensure_ascii=False)

        # Update source tracking
        existing_doc_ids = json.loads(article.source_doc_ids or "[]")
        if doc_id not in existing_doc_ids:
            existing_doc_ids.append(doc_id)
            article.source_doc_ids = json.dumps(existing_doc_ids)

        # Also append new chunk IDs to source_chunk_ids
        existing_chunk_ids = json.loads(article.source_chunk_ids or "[]")
        for i, _ in enumerate(new_chunks):
            cid = f"doc_{doc_id}_chunk_{i}"
            if cid not in existing_chunk_ids:
                existing_chunk_ids.append(cid)
        article.source_chunk_ids = json.dumps(existing_chunk_ids)

        article.version += 1
        article.token_count = (article.token_count or 0) + result.get("input_tokens", 0) + result.get("output_tokens", 0)

        # Check for contradictions
        has_contradictions = parsed.get("has_contradictions", False)
        contradictions = parsed.get("contradictions", [])

        if has_contradictions and contradictions:
            logger.info(
                "Contradictions detected in article %s: %s",
                article.id, contradictions,
            )

        return has_contradictions

    except Exception as e:
        logger.warning("Failed to synthesize into article %s: %s", article.id, e)
        return None


async def synthesize_new_document(
    db: AsyncSession,
    kb_id: int,
    doc_id: int,
    chunks: List[str],
    config: KnowledgeCompilationConfig,
    kb_user_id: int = 0,
) -> None:
    """Synthesize new document content into existing compiled articles.

    This is the main entry point for incremental synthesis,
    called after document ingestion when incremental_synthesis is enabled.

    Flow:
    1. Find existing articles related to the new chunks
    2. Update related articles with new info
    3. Compile remaining unmatched chunks into new articles
    4. Create cross-references
    """
    if not chunks:
        return

    model_config = await _resolve_model(db, config, kb_user_id)
    if not model_config:
        logger.warning("No LLM model for synthesis (kb_id=%s), falling back to direct compile", kb_id)
        await compile_chunks_to_articles(db, kb_id, doc_id, chunks, config, kb_user_id)
        return

    # Get embedding model for similarity search
    from app.models.knowledge_base import KnowledgeBase
    kb_result = await db.execute(
        select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
    )
    kb = kb_result.scalar_one_or_none()
    if not kb or not kb.embedding_model_id:
        await compile_chunks_to_articles(db, kb_id, doc_id, chunks, config, kb_user_id)
        return

    embed_model_result = await db.execute(
        select(ModelConfig).where(ModelConfig.id == kb.embedding_model_id)
    )
    embed_model = embed_model_result.scalar_one_or_none()
    if not embed_model:
        await compile_chunks_to_articles(db, kb_id, doc_id, chunks, config, kb_user_id)
        return

    # Step 1: Find related articles
    article_chunk_map = await _find_related_articles(
        db, kb_id, chunks, embed_model, config.synthesis_similarity_threshold
    )

    matched_chunks: set[str] = set()
    updated_article_ids: list[int] = []

    # Step 2: Update related articles
    if article_chunk_map:
        article_ids = list(article_chunk_map.keys())
        articles_result = await db.execute(
            select(CompiledArticle).where(
                CompiledArticle.id.in_(article_ids),
                CompiledArticle.status == CompiledArticleStatus.COMPILED.value,
                CompiledArticle.deleted_at.is_(None),
            )
        )
        articles = {a.id: a for a in articles_result.scalars().all()}

        for article_id, related_chunks in article_chunk_map.items():
            article = articles.get(article_id)
            if not article:
                continue

            has_contradictions = await _update_article_with_new_info(
                db, article, related_chunks, model_config, doc_id
            )
            matched_chunks.update(related_chunks)
            updated_article_ids.append(article_id)

    # Step 3: Compile unmatched chunks into new articles
    unmatched = [c for c in chunks if c not in matched_chunks]
    new_articles: list[CompiledArticle] = []

    if unmatched:
        new_articles = await compile_chunks_to_articles(
            db, kb_id, doc_id, unmatched, config, kb_user_id
        )

    # Step 4: Create cross-references between new and updated articles
    if new_articles and updated_article_ids:
        for new_article in new_articles:
            if new_article.status != CompiledArticleStatus.COMPILED.value:
                continue
            for existing_id in updated_article_ids:
                ref = ArticleCrossRef(
                    from_article_id=new_article.id,
                    to_article_id=existing_id,
                    relationship_type="related",
                )
                db.add(ref)

    await db.commit()

    # Re-embed updated articles in vector store
    if updated_article_ids:
        updated_articles_result = await db.execute(
            select(CompiledArticle).where(
                CompiledArticle.id.in_(updated_article_ids)
            )
        )
        updated_articles = updated_articles_result.scalars().all()
        from app.core.knowledge_compilation.compiler import _embed_compiled_articles
        await _embed_compiled_articles(db, kb_id, list(updated_articles), kb_user_id)

    logger.info(
        "Synthesis complete (kb_id=%s, doc_id=%s): updated=%d, new=%d",
        kb_id, doc_id, len(updated_article_ids), len(new_articles),
    )
