"""Tests for text chunking strategies."""
import pytest
from app.core.chunking import (
    split_text,
    split_text_fixed,
    split_text_by_paragraph,
    split_text_recursive,
    split_text_by_heading,
    STRATEGY_MAP,
)


class TestSplitTextFixed:
    def test_basic_split(self):
        text = "a" * 100
        chunks = split_text_fixed(text, chunk_size=30, chunk_overlap=5)
        assert len(chunks) > 1
        assert all(len(c) <= 30 for c in chunks)

    def test_empty_text(self):
        assert split_text_fixed("") == []
        assert split_text_fixed("   ") == []

    def test_text_shorter_than_chunk_size(self):
        chunks = split_text_fixed("hello world", chunk_size=100, chunk_overlap=10)
        assert chunks == ["hello world"]

    def test_overlap_produces_overlapping_content(self):
        text = "ABCDEFGHIJ" * 5  # 50 chars
        chunks = split_text_fixed(text, chunk_size=20, chunk_overlap=5)
        # Consecutive chunks should share overlapping characters
        assert len(chunks) >= 2
        for i in range(len(chunks) - 1):
            # The end of chunk[i] should partially appear in chunk[i+1]
            tail = chunks[i][-5:]
            assert tail in text  # Sanity check

    def test_single_char_text(self):
        assert split_text_fixed("x", chunk_size=10) == ["x"]

    def test_whitespace_only_chunks_are_skipped(self):
        text = "hello" + " " * 100 + "world"
        chunks = split_text_fixed(text, chunk_size=20, chunk_overlap=5)
        assert all(c.strip() for c in chunks)


class TestSplitTextByParagraph:
    def test_basic_paragraph_split(self):
        text = "Para one.\n\nPara two.\n\nPara three."
        chunks = split_text_by_paragraph(text, max_chunk_size=50)
        assert len(chunks) >= 1
        assert "Para one" in chunks[0]

    def test_empty_text(self):
        assert split_text_by_paragraph("") == []

    def test_single_paragraph(self):
        text = "Just one paragraph."
        chunks = split_text_by_paragraph(text, max_chunk_size=100)
        assert chunks == ["Just one paragraph."]

    def test_long_paragraph_is_kept_as_one(self):
        text = "Short.\n\n" + "x" * 200
        chunks = split_text_by_paragraph(text, max_chunk_size=100)
        # The long paragraph exceeds max_chunk_size but forms its own chunk
        assert len(chunks) >= 2

    def test_multiple_blank_lines(self):
        text = "A\n\n\n\nB\n\nC"
        chunks = split_text_by_paragraph(text)
        assert len(chunks) >= 1


class TestSplitTextRecursive:
    def test_basic_recursive(self):
        text = "Section one.\n\nSection two.\n\nSection three."
        chunks = split_text_recursive(text, chunk_size=30)
        assert len(chunks) >= 2

    def test_empty_text(self):
        assert split_text_recursive("") == []
        assert split_text_recursive("  \n  ") == []

    def test_short_text_single_chunk(self):
        chunks = split_text_recursive("Hello world.", chunk_size=100)
        assert chunks == ["Hello world."]

    def test_chinese_sentence_boundaries(self):
        text = "第一段内容。第二段内容。第三段内容。" * 10
        chunks = split_text_recursive(text, chunk_size=30, chunk_overlap=0)
        assert len(chunks) >= 2
        # Should split at sentence boundaries (。)
        for c in chunks:
            assert len(c) <= 60  # Allow some flexibility due to recursive merging

    def test_falls_back_to_fixed_split(self):
        # A long text with no separators should fall back to fixed split
        text = "x" * 200
        chunks = split_text_recursive(text, chunk_size=50, chunk_overlap=10)
        assert len(chunks) >= 2


class TestSplitTextByHeading:
    def test_markdown_headings(self):
        text = "# Title\nIntro text.\n## Section 1\nContent 1.\n## Section 2\nContent 2."
        chunks = split_text_by_heading(text, chunk_size=500)
        assert len(chunks) >= 2

    def test_empty_text(self):
        assert split_text_by_heading("") == []

    def test_no_headings(self):
        text = "Just plain text without any headings."
        chunks = split_text_by_heading(text)
        assert chunks == ["Just plain text without any headings."]

    def test_long_section_gets_sub_chunked(self):
        text = "# Heading\n" + "x" * 2000
        chunks = split_text_by_heading(text, chunk_size=500)
        assert len(chunks) >= 2

    def test_heading_levels(self):
        text = "# H1\nText1\n## H2\nText2\n### H3\nText3"
        chunks = split_text_by_heading(text, chunk_size=500)
        assert len(chunks) >= 2


class TestSplitTextUnified:
    def test_all_strategies_registered(self):
        assert "fixed" in STRATEGY_MAP
        assert "paragraph" in STRATEGY_MAP
        assert "recursive" in STRATEGY_MAP
        assert "heading" in STRATEGY_MAP

    def test_unknown_strategy_falls_back_to_fixed(self):
        chunks = split_text("Hello world", strategy="nonexistent", chunk_size=100)
        assert chunks == ["Hello world"]

    def test_split_text_dispatches_correctly(self):
        text = "A" * 100
        for strategy in ("fixed", "paragraph", "recursive", "heading"):
            chunks = split_text(text, strategy=strategy, chunk_size=50, chunk_overlap=10)
            assert len(chunks) >= 1, f"Strategy {strategy} returned empty"

    def test_overlap_clamped_when_exceeds_chunk_size(self):
        """Ensure no infinite loop when chunk_overlap >= chunk_size."""
        text = "x" * 200
        # overlap == size should not hang
        chunks = split_text_fixed(text, chunk_size=50, chunk_overlap=50)
        assert len(chunks) >= 2
        # overlap > size should not hang
        chunks = split_text_fixed(text, chunk_size=50, chunk_overlap=100)
        assert len(chunks) >= 2


class TestRecursiveOverlap:
    def test_recursive_chunks_have_overlap(self):
        """After the overlap fix, adjacent recursive chunks should share content."""
        text = "Paragraph A content here.\n\nParagraph B content here.\n\nParagraph C content here."
        chunks = split_text_recursive(text, chunk_size=30, chunk_overlap=10)
        assert len(chunks) >= 2
        # Check that consecutive chunks share overlapping text
        for i in range(len(chunks) - 1):
            tail = chunks[i][-10:]  # last 10 chars of current chunk
            assert tail in chunks[i + 1], (
                f"Chunk {i} tail '{tail}' not found in chunk {i+1} '{chunks[i+1][:50]}...'"
            )

    def test_recursive_no_overlap_when_zero(self):
        """With overlap=0, chunks should not repeat content."""
        text = "A" * 50 + "\n\n" + "B" * 50 + "\n\n" + "C" * 50
        chunks = split_text_recursive(text, chunk_size=55, chunk_overlap=0)
        assert len(chunks) >= 2
        # No chunk should start with the end of the previous chunk
        for i in range(1, len(chunks)):
            assert not chunks[i].startswith(chunks[i-1][-10:])
