"""Knowledge Health Checker — detects contradictions, gaps, outdated info, and redundancy.

Produces a HealthReport with actionable findings for each knowledge base.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sa_func

from app.core.knowledge_compilation.config import KnowledgeCompilationConfig
from app.core.knowledge_compilation.prompts import DETECT_CONTRADICTIONS, HEALTH_CHECK_ARTICLE
from app.core.llm_client import chat_completion_with_usage, create_embeddings
from app.core.vector_store import get_vector_store
from app.models.compiled_article import CompiledArticle, CompiledArticleStatus
from app.models.document import Document
from app.models.health_report import HealthReport, HealthReportStatus
from app.models.model_config import ModelConfig
from app.services.embedding_service import get_collection_name

logger = logging.getLogger(__name__)


def _safe_parse_json(text: str) -> Optional[dict]:
    text = text.strip()
    if text.startswith("```"):
        first_nl = text.find("\n")
        if first_nl != -1:
            text = text[first_nl + 1:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


async def _resolve_model(
    db: AsyncSession, kb_user_id: int
) -> Optional[ModelConfig]:
    from app.models.model_config import ModelType
    result = await db.execute(
        select(ModelConfig).where(
            ModelConfig.user_id == kb_user_id,
            ModelConfig.model_type == ModelType.LLM,
            ModelConfig.is_default == True,
        )
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Individual check routines
# ---------------------------------------------------------------------------

async def _check_article_quality(
    article: CompiledArticle,
    model_config: ModelConfig,
) -> list[dict]:
    """Run LLM quality check on a single article."""
    prompt = HEALTH_CHECK_ARTICLE.format(
        title=article.title,
        content=article.content,
    )
    messages = [{"role": "user", "content": prompt}]
    try:
        result = await chat_completion_with_usage(model_config, messages)
        parsed = _safe_parse_json(result.get("content", ""))
        if not parsed:
            return []

        findings = []
        token_cost = result.get("input_tokens", 0) + result.get("output_tokens", 0)
        for issue in parsed.get("issues", []):
            findings.append({
                "type": issue.get("type", "quality"),
                "severity": issue.get("severity", "medium"),
                "description": issue.get("description", ""),
                "affected_article_ids": [article.id],
                "suggested_action": issue.get("suggestion", ""),
                "_token_cost": token_cost // max(len(parsed.get("issues", [])), 1),
            })
        return findings
    except Exception as e:
        logger.debug("Article quality check failed for %s: %s", article.id, e)
        return []


async def _check_contradictions_pair(
    article_a: CompiledArticle,
    article_b: CompiledArticle,
    model_config: ModelConfig,
) -> list[dict]:
    """Check two articles for contradictions."""
    prompt = DETECT_CONTRADICTIONS.format(
        article_a_title=article_a.title,
        article_a_content=article_a.content[:3000],
        article_b_title=article_b.title,
        article_b_content=article_b.content[:3000],
    )
    messages = [{"role": "user", "content": prompt}]
    try:
        result = await chat_completion_with_usage(model_config, messages)
        parsed = _safe_parse_json(result.get("content", ""))
        if not parsed or not parsed.get("has_contradictions"):
            return []

        findings = []
        token_cost = result.get("input_tokens", 0) + result.get("output_tokens", 0)
        for c in parsed.get("contradictions", []):
            findings.append({
                "type": "contradiction",
                "severity": c.get("severity", "medium"),
                "description": c.get("description", ""),
                "affected_article_ids": [article_a.id, article_b.id],
                "suggested_action": f"Review claims: [{article_a.title}] vs [{article_b.title}]",
                "_token_cost": token_cost // max(len(parsed.get("contradictions", [])), 1),
            })
        return findings
    except Exception as e:
        logger.debug("Contradiction check failed: %s", e)
        return []


async def _find_similar_article_pairs(
    db: AsyncSession,
    kb_id: int,
    articles: List[CompiledArticle],
    embed_model: ModelConfig,
    max_pairs: int = 30,
) -> List[tuple[CompiledArticle, CompiledArticle]]:
    """Find pairs of similar articles using embedding similarity.

    Uses vector store to avoid O(n^2) comparison.
    """
    store = get_vector_store()
    collection_name = get_collection_name(kb_id)

    pairs: list[tuple[CompiledArticle, CompiledArticle]] = []
    seen: set[tuple[int, int]] = set()
    article_map = {a.id: a for a in articles}

    for article in articles[:20]:  # Cap at 20 articles to limit API calls
        try:
            text = f"{article.title}\n{article.summary or ''}"
            embeddings = await create_embeddings(embed_model, [text])
            if not embeddings or not embeddings[0]:
                continue

            results = store.query(
                collection_name,
                query_embedding=embeddings[0],
                top_k=10,
            )

            for r in results:
                meta = r.get("metadata", {})
                if meta.get("source_type") != "compiled_article":
                    continue
                other_id = meta.get("article_id")
                if not other_id or other_id == article.id:
                    continue
                pair_key = tuple(sorted((article.id, other_id)))
                if pair_key in seen:
                    continue
                seen.add(pair_key)
                other = article_map.get(other_id)
                if other:
                    pairs.append((article, other))
                    if len(pairs) >= max_pairs:
                        return pairs
        except Exception:
            continue

    return pairs


async def _check_expired_documents(
    db: AsyncSession,
    kb_id: int,
) -> list[dict]:
    """Check for documents that have expired or are about to expire."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Document).where(
            Document.kb_id == kb_id,
            Document.deleted_at.is_(None),
            Document.expires_at.isnot(None),
            Document.expires_at <= now,
        )
    )
    expired_docs = result.scalars().all()

    findings = []
    for doc in expired_docs:
        findings.append({
            "type": "outdated",
            "severity": "high",
            "description": f"文档「{doc.filename}」已过期（过期时间: {doc.expires_at}）",
            "affected_doc_ids": [doc.id],
            "suggested_action": "更新或删除该文档",
        })
    return findings


async def _check_redundancy(
    db: AsyncSession,
    kb_id: int,
    articles: List[CompiledArticle],
    embed_model: ModelConfig,
) -> list[dict]:
    """Detect near-duplicate articles using embedding similarity."""
    store = get_vector_store()
    collection_name = get_collection_name(kb_id)
    findings = []
    seen: set[tuple[int, int]] = set()

    for article in articles[:15]:
        try:
            text = f"{article.title}\n{article.summary or ''}"
            embeddings = await create_embeddings(embed_model, [text])
            if not embeddings or not embeddings[0]:
                continue

            results = store.query(
                collection_name,
                query_embedding=embeddings[0],
                top_k=10,
            )

            for r in results:
                meta = r.get("metadata", {})
                if meta.get("source_type") != "compiled_article":
                    continue
                other_id = meta.get("article_id")
                score = r.get("score", 0)
                if not other_id or other_id == article.id:
                    continue
                if score < 0.92:  # Very high similarity = likely redundant
                    continue
                pair_key = tuple(sorted((article.id, other_id)))
                if pair_key in seen:
                    continue
                seen.add(pair_key)
                findings.append({
                    "type": "redundancy",
                    "severity": "low",
                    "description": f"文章「{article.title}」与另一篇文章高度相似（相似度: {score:.2f}）",
                    "affected_article_ids": [article.id, other_id],
                    "suggested_action": "考虑合并这两篇文章",
                })
        except Exception:
            continue

    return findings


# ---------------------------------------------------------------------------
# Main health check
# ---------------------------------------------------------------------------

async def run_health_check(
    db: AsyncSession,
    kb_id: int,
    config: KnowledgeCompilationConfig,
    kb_user_id: int = 0,
) -> Optional[HealthReport]:
    """Run a comprehensive health check on the knowledge base.

    Checks:
    1. Individual article quality (outdated, gaps, quality issues)
    2. Cross-article contradictions
    3. Expired documents
    4. Redundant articles

    Returns a persisted HealthReport.
    """
    from app.models.knowledge_base import KnowledgeBase

    # Create report record
    report = HealthReport(
        kb_id=kb_id,
        status=HealthReportStatus.RUNNING.value,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    try:
        model_config = await _resolve_model(db, kb_user_id)
        if not model_config:
            report.status = HealthReportStatus.FAILED.value
            report.summary = json.dumps({"error": "未找到可用的 LLM 模型"})
            await db.commit()
            return report

        # Get embedding model
        kb_result = await db.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
        )
        kb = kb_result.scalar_one_or_none()
        embed_model = None
        if kb and kb.embedding_model_id:
            em_result = await db.execute(
                select(ModelConfig).where(ModelConfig.id == kb.embedding_model_id)
            )
            embed_model = em_result.scalar_one_or_none()

        # Load compiled articles
        articles_result = await db.execute(
            select(CompiledArticle).where(
                CompiledArticle.kb_id == kb_id,
                CompiledArticle.status == CompiledArticleStatus.COMPILED.value,
                CompiledArticle.deleted_at.is_(None),
            )
        )
        articles = articles_result.scalars().all()

        all_findings: list[dict] = []
        total_tokens = 0

        # 1. Article quality checks (sample up to 10)
        for article in articles[:10]:
            findings = await _check_article_quality(article, model_config)
            for f in findings:
                total_tokens += f.pop("_token_cost", 0)
            all_findings.extend(findings)

        # 2. Contradiction checks (only if we have embedding model)
        if embed_model and len(articles) >= 2:
            pairs = await _find_similar_article_pairs(
                db, kb_id, articles, embed_model, max_pairs=15
            )
            for a, b in pairs:
                findings = await _check_contradictions_pair(a, b, model_config)
                for f in findings:
                    total_tokens += f.pop("_token_cost", 0)
                all_findings.extend(findings)

        # 3. Expired document checks
        expired_findings = await _check_expired_documents(db, kb_id)
        all_findings.extend(expired_findings)

        # 4. Redundancy checks
        if embed_model and articles:
            redundancy_findings = await _check_redundancy(db, kb_id, articles, embed_model)
            all_findings.extend(redundancy_findings)

        # Compute summary score
        severity_weights = {"high": 10, "medium": 5, "low": 2}
        total_penalty = sum(
            severity_weights.get(f.get("severity", "low"), 0)
            for f in all_findings
        )
        score = max(0, 100 - total_penalty)

        # Count by type
        type_counts: dict[str, int] = {}
        for f in all_findings:
            t = f.get("type", "other")
            type_counts[t] = type_counts.get(t, 0) + 1

        summary = {
            "score": score,
            "total_findings": len(all_findings),
            **{f"{t}_count": c for t, c in type_counts.items()},
            "articles_checked": min(len(articles), 10),
            "total_articles": len(articles),
        }

        report.status = HealthReportStatus.COMPLETED.value
        report.summary = json.dumps(summary, ensure_ascii=False)
        report.findings = json.dumps(all_findings, ensure_ascii=False)
        report.completed_at = datetime.now(timezone.utc)
        report.token_cost = total_tokens

        await db.commit()
        logger.info(
            "Health check completed (kb_id=%s): score=%d, findings=%d",
            kb_id, score, len(all_findings),
        )
        return report

    except Exception as e:
        report.status = HealthReportStatus.FAILED.value
        report.summary = json.dumps({"error": str(e)[:500]})
        report.completed_at = datetime.now(timezone.utc)
        await db.commit()
        logger.error("Health check failed (kb_id=%s): %s", kb_id, e)
        return report
