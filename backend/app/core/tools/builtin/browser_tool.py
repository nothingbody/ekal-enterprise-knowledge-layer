"""Browser automation tool — opens web pages and extracts content."""

from __future__ import annotations

import logging
import re
from app.core.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

def _is_url_safe(url: str) -> bool:
    """Validate URL using the centralized SSRF protection module."""
    try:
        from app.core.url_safety import validate_url_safe
        validate_url_safe(url)
        return True
    except (ValueError, Exception) as exc:
        logger.warning("Browser tool URL blocked: %s — %s", url, exc)
        return False


class BrowserTool(BaseTool):
    name = "browser"
    description = (
        "打开网页并提取页面文本内容。"
        "适用于需要获取网页实时信息、阅读在线文档等场景。"
        "注意：仅支持公开可访问的 HTTP/HTTPS 网页。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "要访问的网页 URL（必须以 http:// 或 https:// 开头）",
            },
            "extract_mode": {
                "type": "string",
                "description": "提取模式：text（纯文本）或 html（保留HTML结构）",
                "enum": ["text", "html"],
                "default": "text",
            },
        },
        "required": ["url"],
    }

    async def execute(self, **kwargs) -> ToolResult:
        url = kwargs.get("url", "")
        extract_mode = kwargs.get("extract_mode", "text")

        if not _is_url_safe(url):
            return ToolResult(success=False, error=f"不允许访问该 URL: {url}")

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return await self._fallback_httpx(url, extract_mode)

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                try:
                    context = await browser.new_context(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                    )
                    page = await context.new_page()
                    await page.goto(url, timeout=30000, wait_until="domcontentloaded")

                    if extract_mode == "text":
                        content = await page.inner_text("body")
                    else:
                        content = await page.content()

                    title = await page.title()
                finally:
                    await browser.close()

                content = content[:8000]
                return ToolResult(
                    success=True,
                    data={"text": f"页面标题: {title}\n\n{content}", "url": url, "title": title},
                    display_type="text",
                )
        except Exception as exc:
            logger.warning("Playwright failed for %s: %s, trying httpx fallback", url, exc)
            return await self._fallback_httpx(url, extract_mode)

    async def _fallback_httpx(self, url: str, extract_mode: str) -> ToolResult:
        try:
            import httpx
            from bs4 import BeautifulSoup

            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                })
                resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()

            title = soup.title.string if soup.title else url
            if extract_mode == "text":
                content = soup.get_text(separator="\n", strip=True)
            else:
                content = str(soup.body) if soup.body else str(soup)

            content = content[:8000]
            return ToolResult(
                success=True,
                data={"text": f"页面标题: {title}\n\n{content}", "url": url, "title": title},
                display_type="text",
            )
        except Exception as exc:
            return ToolResult(success=False, error=f"网页访问失败: {str(exc)}")
