"""
Celery tasks for async document processing.
Handles document parsing, embedding, and web crawling in the background.
"""
import asyncio
from app.celery_app import celery


def _run_async(coro):
    """Run an async coroutine in a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _auto_tag_document(db, doc_id: int, chunks: list, user_id: int):
    """Generate auto-tags for a document using LLM (best-effort, non-blocking)."""
    import json as _json
    from sqlalchemy import select, update
    from app.models.document import Document
    from app.models.model_config import ModelConfig, ModelType
    from app.core.llm_client import chat_completion

    # Find a default LLM model
    result = await db.execute(
        select(ModelConfig).where(
            ModelConfig.user_id == user_id,
            ModelConfig.model_type == ModelType.LLM,
            ModelConfig.is_default == True,
        )
    )
    llm = result.scalar_one_or_none()
    if not llm:
        return

    # Use first 2000 chars of content for tagging
    preview = "\n".join(chunks[:5])[:2000]
    messages = [
        {"role": "system", "content": "你是一个文档分类助手。根据以下文档内容，生成 3-5 个简短的中文标签（每个 2-4 个字）。只返回 JSON 数组格式，例如: [\"标签1\", \"标签2\", \"标签3\"]"},
        {"role": "user", "content": preview},
    ]
    response = await chat_completion(llm, messages, stream=False)
    # Parse tags from LLM response
    try:
        tags = _json.loads(response.strip())
        if isinstance(tags, list) and all(isinstance(t, str) for t in tags):
            await db.execute(
                update(Document).where(Document.id == doc_id)
                .values(auto_tags=_json.dumps(tags[:5], ensure_ascii=False))
            )
            await db.commit()
    except (_json.JSONDecodeError, TypeError):
        pass  # LLM returned non-JSON, skip


@celery.task(bind=True, max_retries=1, default_retry_delay=60)
def reindex_kb_task(self, kb_id: int, embedding_model_id: int):
    """Drop the vector collection and re-embed all chunks for a KB."""
    import logging
    logger = logging.getLogger(__name__)
    try:
        _run_async(_async_reindex_kb(kb_id, embedding_model_id))
    except Exception as exc:
        logger.error("知识库重建索引失败 (kb_id=%s): %s", kb_id, exc)
        raise


async def _async_reindex_kb(kb_id: int, embedding_model_id: int):
    from collections import defaultdict
    from app.database import async_session
    from app.models.document import DocumentChunk
    from app.models.knowledge_base import KnowledgeBase
    from app.services.embedding_service import embed_and_store, delete_collection
    from app.services.document_service import _invalidate_bm25
    from sqlalchemy import select, update

    import logging as _logging
    _logger = _logging.getLogger(__name__)
    async with async_session() as db:
        try:
            delete_collection(kb_id)
        except Exception as exc:
            _logger.debug("Failed to delete old vector collection for kb %s: %s", kb_id, exc)

        chunk_result = await db.execute(
            select(DocumentChunk)
            .where(DocumentChunk.kb_id == kb_id)
            .order_by(DocumentChunk.doc_id, DocumentChunk.chunk_index)
        )
        all_chunks = chunk_result.scalars().all()
        if not all_chunks:
            return

        doc_chunks: dict = defaultdict(list)
        for c in all_chunks:
            doc_chunks[c.doc_id].append(c)

        for doc_id, chunks in doc_chunks.items():
            texts = [c.content for c in chunks]
            await embed_and_store(db, kb_id, embedding_model_id, texts, doc_id)

        _invalidate_bm25(kb_id)

        # Clear reindexing flag
        kb_result = await db.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
        )
        kb_obj = kb_result.scalar_one_or_none()
        if kb_obj:
            kb_obj.reindexing = False
            await db.commit()
        _logger.info("知识库重建索引完成 kb_id=%s, chunks=%d", kb_id, len(all_chunks))


@celery.task(bind=True, max_retries=3, default_retry_delay=30)
def process_document_task(self, doc_id: int, kb_id: int):
    """Parse, chunk, embed a document and update its status."""
    import logging
    logger = logging.getLogger(__name__)
    try:
        _run_async(_async_process_and_embed(doc_id, kb_id))
    except Exception as exc:
        logger.warning("文档处理失败 (doc_id=%s, attempt=%s/%s): %s",
                       doc_id, self.request.retries + 1, self.max_retries + 1, exc)
        try:
            self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            logger.error("文档处理最终失败 (doc_id=%s): %s", doc_id, exc)
            _run_async(_mark_doc_failed(doc_id, str(exc)))


async def _async_process_and_embed(doc_id: int, kb_id: int):
    from app.database import async_session
    from app.models.document import Document, DocumentStatus
    from app.models.knowledge_base import KnowledgeBase
    from app.services.document_service import process_document, mark_document_completed
    from app.services.embedding_service import embed_and_store
    from sqlalchemy import select, update

    async with async_session() as db:
        try:
            # Idempotency check: skip if already completed
            _doc_check = await db.execute(
                select(Document.status).where(Document.id == doc_id)
            )
            _doc_status = _doc_check.scalar_one_or_none()
            if _doc_status and _doc_status.value == "COMPLETED":
                import logging as _ilog
                _ilog.getLogger(__name__).info("Document %s already COMPLETED, skipping", doc_id)
                return

            result = await process_document(db, doc_id)
            if result:
                kb_id_r, chunks, doc_id_r = result
                kb_result = await db.execute(
                    select(KnowledgeBase).where(KnowledgeBase.id == kb_id_r)
                )
                kb = kb_result.scalar_one_or_none()
                if kb and kb.embedding_model_id:
                    await embed_and_store(db, kb_id_r, kb.embedding_model_id, chunks, doc_id_r)
                    await mark_document_completed(db, doc_id_r)

                    # Auto-tag: generate tags from first 2000 chars using LLM (best-effort)
                    try:
                        await _auto_tag_document(db, doc_id_r, chunks, kb.user_id)
                    except Exception as tag_err:
                        import logging as _tlog
                        _tlog.getLogger(__name__).debug("Auto-tag failed (doc_id=%s): %s", doc_id_r, tag_err)

                    # Knowledge compilation: compile chunks into wiki articles (best-effort)
                    try:
                        from app.core.knowledge_compilation.config import KnowledgeCompilationConfig
                        comp_config = KnowledgeCompilationConfig.from_json(
                            getattr(kb, "knowledge_compilation_config", None)
                        )
                        if comp_config and comp_config.auto_compile_on_ingest:
                            import logging as _clog
                            _clog.getLogger(__name__).info(
                                "Starting knowledge compilation for doc_id=%s (kb_id=%s)", doc_id_r, kb_id_r
                            )
                            if comp_config.incremental_synthesis:
                                from app.core.knowledge_compilation.synthesizer import synthesize_new_document
                                await synthesize_new_document(db, kb_id_r, doc_id_r, chunks, comp_config, kb.user_id)
                            else:
                                from app.core.knowledge_compilation.compiler import compile_chunks_to_articles
                                await compile_chunks_to_articles(db, kb_id_r, doc_id_r, chunks, comp_config, kb.user_id)
                    except Exception as comp_err:
                        import logging as _clog
                        _clog.getLogger(__name__).debug(
                            "Knowledge compilation failed (doc_id=%s): %s", doc_id_r, comp_err
                        )

                    # Graph RAG: extract entity triples (best-effort)
                    try:
                        from app.config import settings as _settings
                        if getattr(_settings, 'GRAPH_RAG_ENABLED', False):
                            from app.core.agentic_rag.graph_rag.entity_extractor import extract_triples_from_chunks
                            from app.models.entity_triple import EntityTriple
                            from app.core.agentic_rag.graph_rag.graph_store import invalidate_graph_cache

                            from app.models.model_config import ModelConfig as _MC, ModelType as _MT
                            _llm_r = await db.execute(
                                select(_MC).where(_MC.user_id == kb.user_id, _MC.model_type == _MT.LLM, _MC.is_default == True)
                            )
                            _llm = _llm_r.scalar_one_or_none()
                            if _llm:
                                chunk_texts = [c.content for c in chunks[:50]]  # limit to first 50 chunks
                                chunk_idxs = [c.chunk_index for c in chunks[:50]]
                                triples = await extract_triples_from_chunks(chunk_texts, chunk_idxs, _llm)
                                for t in triples:
                                    db.add(EntityTriple(
                                        kb_id=kb_id_r, doc_id=doc_id_r, chunk_index=t.source_chunk_index,
                                        subject=t.subject, predicate=t.predicate, object=t.object,
                                        subject_type=t.subject_type, object_type=t.object_type,
                                        confidence=t.confidence,
                                    ))
                                await db.commit()
                                invalidate_graph_cache(kb_id_r)
                                import logging as _glog
                                _glog.getLogger(__name__).info(
                                    "Graph RAG: extracted %d triples for doc_id=%s", len(triples), doc_id_r
                                )
                    except Exception as _graph_err:
                        import logging as _glog
                        _glog.getLogger(__name__).debug(
                            "Graph triple extraction failed (doc_id=%s): %s", doc_id_r, _graph_err
                        )
                else:
                    await db.execute(
                        update(Document).where(Document.id == doc_id_r)
                        .values(
                            status=DocumentStatus.FAILED,
                            error_message="知识库未配置 Embedding 模型",
                        )
                    )
                    await db.commit()
        except Exception as e:
            try:
                await db.execute(
                    update(Document).where(Document.id == doc_id)
                    .values(status=DocumentStatus.FAILED, error_message=str(e)[:500])
                )
                await db.commit()
            except Exception as mark_err:
                import logging as _logging
                _logging.getLogger(__name__).error(
                    "Failed to mark document %s as failed: %s", doc_id, mark_err
                )
            raise


async def _mark_doc_failed(doc_id: int, error: str):
    from app.database import async_session
    from app.models.document import Document, DocumentStatus
    from sqlalchemy import update

    async with async_session() as db:
        await db.execute(
            update(Document).where(Document.id == doc_id)
            .values(status=DocumentStatus.FAILED, error_message=error[:500])
        )
        await db.commit()


@celery.task(bind=True, max_retries=3, default_retry_delay=60)
def crawl_web_source_task(self, source_id: int):
    """Crawl a web URL, extract text, chunk and embed it."""
    import logging
    logger = logging.getLogger(__name__)
    try:
        _run_async(_async_crawl_url(source_id))
    except Exception as exc:
        logger.warning("网页抓取失败 (source_id=%s, attempt=%s/%s): %s",
                       source_id, self.request.retries + 1, self.max_retries + 1, exc)
        try:
            self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            logger.error("网页抓取最终失败 (source_id=%s): %s", source_id, exc)


async def _fetch_with_browser(url: str, validate_url_safe) -> tuple[str, str | None]:
    """Fetch a URL using Playwright headless browser for JavaScript-rendered pages."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise RuntimeError("浏览器引擎（Playwright）未安装，桌面版暂不支持「使用浏览器抓取」功能。请关闭该选项后重试。")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page(
                user_agent="Mozilla/5.0 (compatible; RAGBot/1.0)",
            )
            page.set_default_timeout(30000)
            resp = await page.goto(url, wait_until="networkidle")

            if resp and resp.url != url:
                validate_url_safe(resp.url)

            title = await page.title() or None
            html = await page.content()
            return html, title
        finally:
            await browser.close()


async def _fetch_static_html(url: str, validate_url_safe) -> tuple[str, str | None]:
    """Fetch HTML with httpx when browser rendering is unavailable."""
    import httpx

    max_response_bytes = 10 * 1024 * 1024
    browser_ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(url, headers={
            "User-Agent": browser_ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })
        resp.raise_for_status()
        final_url = str(resp.url)
        if final_url != url:
            validate_url_safe(final_url)
        ct = (resp.headers.get("content-type") or "").lower().split(";")[0].strip()
        if ct and not ct.startswith("text/") and ct != "application/xhtml+xml":
            raise ValueError(f"unsupported content type: {ct}; only HTML/text pages are supported")
        content_length = resp.headers.get("content-length")
        if content_length and int(content_length) > max_response_bytes:
            raise ValueError(
                f"response body too large ({int(content_length)} bytes), "
                f"limit is {max_response_bytes // 1024 // 1024}MB"
            )
        raw_bytes = resp.content
        if len(raw_bytes) > max_response_bytes:
            raise ValueError(
                f"response body too large ({len(raw_bytes)} bytes), "
                f"limit is {max_response_bytes // 1024 // 1024}MB"
            )
        html = raw_bytes.decode(resp.encoding or "utf-8", errors="replace")
    return html, None


async def _fetch_text_url(url: str, validate_url_safe, accept: str, source_type: str) -> tuple[str, str]:
    """Fetch a lightweight text response for structured web sources."""
    import httpx

    max_response_bytes = 10 * 1024 * 1024
    browser_ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(url, headers={
            "User-Agent": browser_ua,
            "Accept": accept,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })
        resp.raise_for_status()
        final_url = str(resp.url)
        if final_url != url:
            validate_url_safe(final_url)

        content_length = resp.headers.get("content-length")
        if content_length and int(content_length) > max_response_bytes:
            raise ValueError(
                f"response body too large ({int(content_length)} bytes), "
                f"limit is {max_response_bytes // 1024 // 1024}MB"
            )

        raw_bytes = resp.content
        if len(raw_bytes) > max_response_bytes:
            raise ValueError(
                f"response body too large ({len(raw_bytes)} bytes), "
                f"limit is {max_response_bytes // 1024 // 1024}MB"
            )

        ct = (resp.headers.get("content-type") or "").lower().split(";")[0].strip()
        if source_type in {"rss", "sitemap"} and ct:
            xml_like = "xml" in ct or ct.startswith("text/")
            if not xml_like:
                raise ValueError(f"unsupported content type for XML source: {ct}")

        return raw_bytes.decode(resp.encoding or "utf-8", errors="replace"), ct


def _normalize_web_source_type(value: str | None) -> str:
    value = (value or "html").lower().strip()
    return value if value in {"html", "json", "rss", "sitemap"} else "html"


def _extract_html_text(html: str, url: str, title: str | None = None) -> tuple[str, str]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    resolved_title = title or (soup.title.string if soup.title else url)
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    return resolved_title, text


def _json_to_text(payload) -> str:
    lines: list[str] = []
    max_lines = 4000

    def walk(value, path: str) -> None:
        if len(lines) >= max_lines:
            return
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                walk(child, child_path)
        elif isinstance(value, list):
            for idx, child in enumerate(value[:500]):
                walk(child, f"{path}[{idx}]")
            if len(value) > 500 and len(lines) < max_lines:
                lines.append(f"{path}: ... ({len(value) - 500} more items)")
        elif value is not None:
            text = str(value).strip()
            if text:
                lines.append(f"{path}: {text}" if path else text)

    walk(payload, "")
    return "\n".join(lines)


def _extract_json_text(raw_text: str, url: str) -> tuple[str, str]:
    import json

    payload = json.loads(raw_text)
    title = url
    if isinstance(payload, dict):
        for key in ("title", "name", "subject"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                title = value.strip()
                break
    text = _json_to_text(payload)
    return title, text


def _tag_text(node, *names: str) -> str:
    for name in names:
        tag = node.find(name)
        if tag:
            if tag.has_attr("href"):
                return str(tag.get("href") or "").strip()
            value = tag.get_text(" ", strip=True)
            if value:
                return value
    return ""


def _extract_feed_text(raw_xml: str, url: str) -> tuple[str, str]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(raw_xml, "xml")
    channel = soup.find("channel") or soup.find("feed") or soup
    title = _tag_text(channel, "title") or url
    lines = [f"Feed: {title}", f"Source: {url}", ""]

    items = soup.find_all("item") or soup.find_all("entry")
    for idx, item in enumerate(items[:300], start=1):
        item_title = _tag_text(item, "title")
        link = _tag_text(item, "link", "guid", "id")
        published = _tag_text(item, "pubDate", "published", "updated")
        summary = _tag_text(item, "description", "summary", "content", "content:encoded")
        lines.extend([
            f"Item {idx}: {item_title or link or '(untitled)'}",
            f"Link: {link}" if link else "",
            f"Published: {published}" if published else "",
            summary,
            "",
        ])
    if len(items) > 300:
        lines.append(f"... {len(items) - 300} more feed items omitted")

    return title, "\n".join(line for line in lines if line is not None).strip()


def _extract_sitemap_text(raw_xml: str, url: str) -> tuple[str, str]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(raw_xml, "xml")
    lines = [f"Sitemap: {url}", ""]

    sitemap_nodes = soup.find_all("sitemap")
    url_nodes = soup.find_all("url")
    if sitemap_nodes:
        lines.append("Nested sitemaps:")
        for idx, node in enumerate(sitemap_nodes[:500], start=1):
            loc = _tag_text(node, "loc")
            lastmod = _tag_text(node, "lastmod")
            lines.append(f"{idx}. {loc}" + (f" | lastmod: {lastmod}" if lastmod else ""))
        if len(sitemap_nodes) > 500:
            lines.append(f"... {len(sitemap_nodes) - 500} more sitemap entries omitted")

    if url_nodes:
        lines.append("URLs:")
        for idx, node in enumerate(url_nodes[:1000], start=1):
            loc = _tag_text(node, "loc")
            lastmod = _tag_text(node, "lastmod")
            changefreq = _tag_text(node, "changefreq")
            priority = _tag_text(node, "priority")
            meta = [part for part in (
                f"lastmod: {lastmod}" if lastmod else "",
                f"changefreq: {changefreq}" if changefreq else "",
                f"priority: {priority}" if priority else "",
            ) if part]
            lines.append(f"{idx}. {loc}" + (f" | {'; '.join(meta)}" if meta else ""))
        if len(url_nodes) > 1000:
            lines.append(f"... {len(url_nodes) - 1000} more URLs omitted")

    return "Sitemap", "\n".join(lines).strip()


async def _fetch_structured_source(url: str, source_type: str, validate_url_safe) -> tuple[str, str]:
    if source_type == "json":
        raw_text, _ = await _fetch_text_url(url, validate_url_safe, "application/json,text/plain,*/*;q=0.8", source_type)
        return _extract_json_text(raw_text, url)
    if source_type == "rss":
        raw_text, _ = await _fetch_text_url(
            url,
            validate_url_safe,
            "application/rss+xml,application/atom+xml,application/xml,text/xml,*/*;q=0.8",
            source_type,
        )
        return _extract_feed_text(raw_text, url)
    if source_type == "sitemap":
        raw_text, _ = await _fetch_text_url(url, validate_url_safe, "application/xml,text/xml,*/*;q=0.8", source_type)
        return _extract_sitemap_text(raw_text, url)
    raise ValueError(f"unsupported web source type: {source_type}")


async def _async_crawl_url(source_id: int):
    import logging
    from datetime import datetime, timezone
    from app.database import async_session
    from app.models.web_source import WebSource, WebSourceStatus
    from app.models.knowledge_base import KnowledgeBase
    from app.models.document import Document, DocumentChunk, DocumentStatus
    from app.services.knowledge_base_service import refresh_kb_counts as _refresh_kb_counts
    from app.services.document_service import _invalidate_bm25
    from app.services.web_crawl_scheduler import compute_content_hash
    from sqlalchemy import select, update, delete as sa_delete

    _logger = logging.getLogger(__name__)

    async with async_session() as db:
        try:
            result = await db.execute(select(WebSource).where(WebSource.id == source_id))
            source = result.scalar_one_or_none()
            if not source:
                return

            kb_id = source.kb_id
            old_content_hash = source.content_hash

            kb_check = await db.execute(
                select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
            )
            kb_row = kb_check.scalar_one_or_none()
            if not kb_row or kb_row.deleted_at is not None:
                _logger.info("知识库已删除，跳过抓取 (source_id=%s, kb_id=%s)", source_id, kb_id)
                return

            await db.execute(
                update(WebSource).where(WebSource.id == source_id).values(status=WebSourceStatus.CRAWLING)
            )
            await db.commit()

            from app.core.url_safety import validate_url_safe
            validate_url_safe(source.url)

            source_type = _normalize_web_source_type(getattr(source, "source_type", None))
            if source_type == "html":
                if source.use_browser:
                    try:
                        html, title = await _fetch_with_browser(source.url, validate_url_safe)
                    except Exception as exc:
                        _logger.warning(
                            "Browser web fetch unavailable for source_id=%s, falling back to HTTP fetch: %s",
                            source_id, exc,
                        )
                        html, title = await _fetch_static_html(source.url, validate_url_safe)
                else:
                    html, title = await _fetch_static_html(source.url, validate_url_safe)
                title, text = _extract_html_text(html, source.url, title)
            else:
                title, text = await _fetch_structured_source(source.url, source_type, validate_url_safe)

            if not text or not text.strip():
                raise ValueError("网页内容为空，无法提取有效文本")

            now = datetime.now(timezone.utc)
            new_hash = compute_content_hash(text)
            content_changed = old_content_hash is None or old_content_hash != new_hash
            is_recrawl = old_content_hash is not None

            source.title = title[:500] if title else None
            source.content = text
            source.content_hash = new_hash
            source.last_crawled_at = now
            source.crawl_count = (source.crawl_count or 0) + 1

            if is_recrawl and not content_changed:
                _logger.info("网页内容未变化，跳过文档更新 (source_id=%s)", source_id)
                source.status = WebSourceStatus.COMPLETED
                await db.commit()
                return

            if is_recrawl and not source.auto_reindex:
                _logger.info("网页内容已变化但 auto_reindex=False，跳过文档更新 (source_id=%s)", source_id)
                source.status = WebSourceStatus.COMPLETED
                await db.commit()
                return

            file_path_key = source.url[:1000]

            # ── Delete old documents from the same web source ──
            old_docs_result = await db.execute(
                select(Document).where(
                    Document.kb_id == kb_id,
                    Document.file_path == file_path_key,
                    Document.file_type == "web",
                )
            )
            old_docs = old_docs_result.scalars().all()
            old_doc_ids = [d.id for d in old_docs]
            if old_doc_ids:
                await db.execute(
                    sa_delete(DocumentChunk).where(DocumentChunk.doc_id.in_(old_doc_ids))
                )
                await db.execute(
                    sa_delete(Document).where(Document.id.in_(old_doc_ids))
                )
                try:
                    from app.services.embedding_service import delete_doc_chunks_from_collection
                    for doc_id in old_doc_ids:
                        delete_doc_chunks_from_collection(kb_id, doc_id)
                except Exception as vec_err:
                    _logger.warning("Web source 旧文档向量清理失败: %s", vec_err)

            # ── Create new document ──
            import re as _re
            safe_title = _re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', (title or 'page'))[:80]
            extension = {"html": "html", "json": "json", "rss": "xml", "sitemap": "xml"}.get(source_type, "txt")
            doc = Document(
                kb_id=kb_id,
                filename=f"web_{safe_title}.{extension}",
                file_path=source.url[:1000],
                file_size=len(text.encode()),
                file_type="web",
                status=DocumentStatus.EMBEDDING,
            )
            db.add(doc)
            await db.flush()
            doc_id = doc.id

            from app.core.chunking import split_text
            kb_result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
            kb = kb_result.scalar_one_or_none()
            strategy = getattr(kb, 'chunk_strategy', 'fixed') or 'fixed'
            cs = getattr(kb, 'chunk_size', None)
            co = getattr(kb, 'chunk_overlap', None)
            chunks = split_text(text, strategy=strategy, chunk_size=cs, chunk_overlap=co)

            for idx, chunk_text in enumerate(chunks):
                chunk = DocumentChunk(
                    doc_id=doc_id, kb_id=kb_id,
                    content=chunk_text, chunk_index=idx,
                )
                db.add(chunk)

            if kb and kb.embedding_model_id:
                await db.flush()
                from app.services.embedding_service import embed_and_store
                await embed_and_store(db, kb_id, kb.embedding_model_id, chunks, doc_id)

            # Use direct UPDATE to avoid stale ORM object issues
            await db.execute(
                update(Document).where(Document.id == doc_id)
                .values(status=DocumentStatus.COMPLETED, chunk_count=len(chunks))
            )
            await db.execute(
                update(WebSource).where(WebSource.id == source_id)
                .values(status=WebSourceStatus.COMPLETED)
            )
            await db.commit()
            await _refresh_kb_counts(db, kb_id)
            _invalidate_bm25(kb_id)

            _logger.info("网页抓取完成: source_id=%s changed=%s crawl_count=%s",
                         source_id, content_changed, source.crawl_count)

        except Exception as e:
            raw = str(e)
            # Translate technical errors to user-friendly messages
            if "403" in raw or "Forbidden" in raw:
                friendly = "该网站禁止抓取（403），请尝试其他页面地址"
            elif "432" in raw or "431" in raw:
                friendly = "该网站有反爬机制，拒绝了请求，请尝试其他页面地址"
            elif "404" in raw or "Not Found" in raw:
                friendly = "页面不存在（404），请检查网址是否正确"
            elif "Connection refused" in raw or "ConnectError" in raw:
                friendly = "无法连接到该网站，请检查网址或网络"
            elif "timeout" in raw.lower() or "Timeout" in raw:
                friendly = "连接超时，网站响应太慢或网络不稳定"
            elif "SSL" in raw or "certificate" in raw.lower():
                friendly = "网站证书验证失败，请检查网址是否以 https 开头"
            elif "内容为空" in raw:
                friendly = "网页内容为空，该页面可能需要登录或由 JavaScript 动态加载"
            elif "不支持的内容类型" in raw or "unsupported content type" in raw:
                friendly = raw
            elif "JSONDecodeError" in raw or "Expecting value" in raw:
                friendly = "接口返回内容不是有效 JSON，请检查数据类型或接口地址"
            else:
                friendly = f"抓取失败：{raw[:200]}"

            try:
                await db.rollback()
                await db.execute(
                    update(WebSource).where(WebSource.id == source_id)
                    .values(
                        status=WebSourceStatus.FAILED,
                        error_message=friendly[:500],
                        last_crawled_at=datetime.now(timezone.utc),
                    )
                )
                await db.commit()
            except Exception as mark_err:
                _logger.error("标记 web source %s 为失败状态时出错: %s", source_id, mark_err)
            raise
