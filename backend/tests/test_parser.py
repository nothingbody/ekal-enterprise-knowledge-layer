"""Tests for document parser module."""
import os
import tempfile
import pytest
from app.core.parser import parse_document, PARSER_MAP


class TestParserMap:
    def test_supported_formats(self):
        expected = {
            ".txt", ".md", ".pdf", ".doc", ".docx", ".csv", ".xlsx", ".xls", ".pptx", ".html", ".htm",
            # Image formats (LLM vision OCR)
            ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp",
        }
        assert set(PARSER_MAP.keys()) == expected

    def test_unsupported_format_raises(self):
        f = tempfile.NamedTemporaryFile(suffix=".xyz", delete=False)
        f.write(b"data")
        f.close()
        try:
            with pytest.raises(ValueError, match="不支持的文件格式"):
                parse_document(f.name)
        finally:
            os.unlink(f.name)

    def test_doc_format_in_parser_map(self):
        """Ensure .doc (legacy Word) IS in PARSER_MAP with best-effort extraction."""
        assert ".doc" in PARSER_MAP

    def test_ppt_format_not_in_parser_map(self):
        """Ensure .ppt (legacy PowerPoint) is NOT in PARSER_MAP."""
        assert ".ppt" not in PARSER_MAP


def _write_temp(suffix, content, mode="w"):
    """Helper: write a temp file, close it, return its path. Caller must unlink."""
    kwargs = {"suffix": suffix, "delete": False}
    if mode == "w":
        kwargs.update(mode="w", encoding="utf-8")
    f = tempfile.NamedTemporaryFile(**kwargs)
    if mode == "w":
        # reopen in text mode
        f.close()
        with open(f.name, "w", encoding="utf-8") as fh:
            fh.write(content)
    else:
        f.write(content)
        f.close()
    return f.name


class TestParseTxt:
    def test_basic_txt(self):
        path = _write_temp(".txt", "Hello world\nLine two")
        try:
            result = parse_document(path)
            assert "Hello world" in result
            assert "Line two" in result
        finally:
            os.unlink(path)

    def test_empty_txt(self):
        path = _write_temp(".txt", "")
        try:
            result = parse_document(path)
            assert result == ""
        finally:
            os.unlink(path)

    def test_chinese_content(self):
        path = _write_temp(".txt", "你好世界\n第二行")
        try:
            result = parse_document(path)
            assert "你好世界" in result
        finally:
            os.unlink(path)


class TestParseMarkdown:
    def test_markdown_is_parsed_as_txt(self):
        path = _write_temp(".md", "# Heading\n\nParagraph text.")
        try:
            result = parse_document(path)
            assert "# Heading" in result
            assert "Paragraph text" in result
        finally:
            os.unlink(path)


class TestParseHtml:
    def test_basic_html(self):
        path = _write_temp(".html", "<html><body><p>Hello</p><script>evil()</script></body></html>")
        try:
            result = parse_document(path)
            assert "Hello" in result
            assert "evil" not in result  # script tags should be removed
        finally:
            os.unlink(path)

    def test_htm_extension(self):
        path = _write_temp(".htm", "<html><body><p>Content</p></body></html>")
        try:
            result = parse_document(path)
            assert "Content" in result
        finally:
            os.unlink(path)


class TestDocxXmlFallback:
    """Test the XML fallback for .docx files with text in text boxes / SDT."""

    def test_extract_docx_xml_text_from_textbox(self):
        """A minimal .docx with text only inside a text box should still be extracted."""
        import zipfile
        from app.core.parser import _extract_docx_xml_text

        # Build a minimal .docx (ZIP) with text inside w:txbxContent
        doc_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
            '            xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006">'
            '<w:body>'
            '<w:p><w:r><w:t>这是文本框内容</w:t></w:r></w:p>'
            '</w:body>'
            '</w:document>'
        )
        path = tempfile.NamedTemporaryFile(suffix=".docx", delete=False).name
        try:
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("word/document.xml", doc_xml)
            result = _extract_docx_xml_text(path)
            assert any("这是文本框内容" in line for line in result)
        finally:
            os.unlink(path)

    def test_extract_docx_xml_text_empty(self):
        """An empty .docx XML should return an empty list."""
        import zipfile
        from app.core.parser import _extract_docx_xml_text

        doc_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body/>'
            '</w:document>'
        )
        path = tempfile.NamedTemporaryFile(suffix=".docx", delete=False).name
        try:
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("word/document.xml", doc_xml)
            result = _extract_docx_xml_text(path)
            assert result == []
        finally:
            os.unlink(path)


class TestParseCsv:
    def test_basic_csv(self):
        path = _write_temp(".csv", "name,age\nAlice,30\nBob,25\n")
        try:
            result = parse_document(path)
            assert "Alice" in result
            assert "Bob" in result
        finally:
            os.unlink(path)
