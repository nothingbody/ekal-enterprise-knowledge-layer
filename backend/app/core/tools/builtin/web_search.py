"""Web search tool — queries the internet for real-time information.

Supports multiple backends:
  1. Tavily API (if TAVILY_API_KEY is set) — best quality
  2. DuckDuckGo HTML search (no API key) — reliable fallback
  3. DuckDuckGo Instant Answer API — last resort
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from app.core.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class WebSearchTool(BaseTool):
    name = "web_search"
    description = (
        "搜索互联网获取实时信息。"
        "当用户询问最新事件、实时数据或你不确定的事实时使用此工具。"
        "输入搜索关键词，返回搜索结果摘要。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词",
            },
            "max_results": {
                "type": "integer",
                "description": "最大返回结果数（默认5）",
                "default": 5,
            },
        },
        "required": ["query"],
    }

    async def execute(self, **kwargs) -> ToolResult:
        query = kwargs.get("query", "").strip()
        max_results = min(int(kwargs.get("max_results", 5)), 20)  # Cap at 20
        if not query:
            return ToolResult(success=False, error="搜索关键词不能为空")

        try:
            results = await _search(query, max_results)
            if not results:
                return ToolResult(
                    success=True,
                    data=f"未找到与 '{query}' 相关的搜索结果。",
                )
            return ToolResult(
                success=True,
                data={"text": results, "query": query},
                display_type="text",
            )
        except Exception as exc:
            logger.warning("Web search failed: %s", exc)
            return ToolResult(success=False, error=f"搜索失败: {str(exc)}")


async def _search(query: str, max_results: int = 5) -> str:
    """Try search backends in order of quality."""
    from app.config import settings

    tavily_key = getattr(settings, "TAVILY_API_KEY", None) or ""
    if tavily_key:
        try:
            return await _search_tavily(query, tavily_key, max_results)
        except Exception as exc:
            logger.warning("Tavily search failed, falling back: %s", exc)

    try:
        return await _search_ddg_html(query, max_results)
    except Exception as exc:
        logger.warning("DDG HTML search failed, falling back: %s", exc)

    return await _search_ddg_instant(query)


async def _search_tavily(query: str, api_key: str, max_results: int) -> str:
    """Use Tavily Search API for high-quality results."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://api.tavily.com/search",
            json={
                "query": query,
                "max_results": max_results,
                "include_answer": True,
                "search_depth": "basic",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        resp.raise_for_status()
        data = resp.json()

    parts: list[str] = []

    answer = data.get("answer", "").strip()
    if answer:
        parts.append(f"**AI 摘要**: {answer}\n")

    results = data.get("results", [])
    if results:
        parts.append("搜索结果:")
        for i, r in enumerate(results[:max_results], 1):
            title = r.get("title", "")
            content = r.get("content", "")[:300]
            url = r.get("url", "")
            parts.append(f"\n{i}. **{title}**")
            parts.append(f"   {content}")
            if url:
                parts.append(f"   链接: {url}")

    return "\n".join(parts) if parts else ""


async def _search_ddg_html(query: str, max_results: int = 5) -> str:
    """Scrape DuckDuckGo HTML search results (no API key needed)."""
    from bs4 import BeautifulSoup

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        resp = await client.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            },
        )
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    results = soup.select(".result__body")

    if not results:
        return ""

    parts: list[str] = [f"搜索结果 ({query}):"]
    for i, result in enumerate(results[:max_results], 1):
        title_el = result.select_one(".result__title a")
        snippet_el = result.select_one(".result__snippet")

        title = title_el.get_text(strip=True) if title_el else ""
        url = title_el.get("href", "") if title_el else ""
        snippet = snippet_el.get_text(strip=True) if snippet_el else ""

        if url and url.startswith("//duckduckgo.com/l/"):
            url_match = re.search(r"uddg=([^&]+)", url)
            if url_match:
                from urllib.parse import unquote
                url = unquote(url_match.group(1))

        if title or snippet:
            parts.append(f"\n{i}. **{title}**")
            if snippet:
                parts.append(f"   {snippet}")
            if url:
                parts.append(f"   链接: {url}")

    return "\n".join(parts) if len(parts) > 1 else ""


async def _search_ddg_instant(query: str) -> str:
    """DuckDuckGo Instant Answer API (limited but always available)."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get("https://api.duckduckgo.com/", params={
            "q": query, "format": "json", "no_redirect": "1",
            "no_html": "1", "skip_disambig": "1",
        })
        resp.raise_for_status()
        data = resp.json()

    parts: list[str] = []

    abstract = data.get("AbstractText", "").strip()
    if abstract:
        source = data.get("AbstractSource", "")
        url = data.get("AbstractURL", "")
        parts.append(f"**{source}**: {abstract}")
        if url:
            parts.append(f"来源: {url}")

    answer = data.get("Answer", "").strip()
    if answer:
        parts.append(f"回答: {answer}")

    related = data.get("RelatedTopics", [])
    if related:
        parts.append("\n相关结果:")
        for i, topic in enumerate(related[:5], 1):
            text = topic.get("Text", "").strip()
            url = topic.get("FirstURL", "")
            if text:
                parts.append(f"{i}. {text}")
                if url:
                    parts.append(f"   链接: {url}")

    return "\n".join(parts) if parts else ""
