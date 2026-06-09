from app.tasks.document_tasks import (
    _extract_feed_text,
    _extract_json_text,
    _extract_sitemap_text,
    _normalize_web_source_type,
)


def test_extract_json_text_flattens_nested_payload():
    title, text = _extract_json_text(
        '{"title":"API title","items":[{"name":"Alpha","score":0.95}]}',
        "https://api.example.com/data",
    )

    assert title == "API title"
    assert "items[0].name: Alpha" in text
    assert "items[0].score: 0.95" in text


def test_extract_feed_text_reads_rss_items():
    title, text = _extract_feed_text(
        """
        <rss>
          <channel>
            <title>News Feed</title>
            <item>
              <title>First item</title>
              <link>https://example.com/first</link>
              <description>First summary</description>
            </item>
          </channel>
        </rss>
        """,
        "https://example.com/rss.xml",
    )

    assert title == "News Feed"
    assert "Item 1: First item" in text
    assert "https://example.com/first" in text
    assert "First summary" in text


def test_extract_sitemap_text_reads_url_entries():
    title, text = _extract_sitemap_text(
        """
        <urlset>
          <url>
            <loc>https://example.com/a</loc>
            <lastmod>2026-01-01</lastmod>
          </url>
        </urlset>
        """,
        "https://example.com/sitemap.xml",
    )

    assert title == "Sitemap"
    assert "https://example.com/a" in text
    assert "lastmod: 2026-01-01" in text


def test_normalize_web_source_type_defaults_unknown_to_html():
    assert _normalize_web_source_type(None) == "html"
    assert _normalize_web_source_type("JSON") == "json"
    assert _normalize_web_source_type("browser") == "html"
