"""Tests for retrieval service helper functions."""
import time
import pytest
from app.services.retrieval_service import (
    _rrf_fusion,
    _chunk_dedup_key,
    _get_bm25_cached,
    _put_bm25_cached,
    invalidate_bm25_cache,
    _bm25_cache,
)


class TestRRFFusion:
    def test_single_list(self):
        results = [
            {"content": "doc1", "score": 0.9, "metadata": {}},
            {"content": "doc2", "score": 0.8, "metadata": {}},
        ]
        merged = _rrf_fusion(results)
        assert len(merged) == 2
        assert merged[0]["content"] == "doc1"
        assert merged[1]["content"] == "doc2"

    def test_two_lists_merge(self):
        list1 = [
            {"content": "doc_a_content", "score": 0.9, "metadata": {}},
            {"content": "doc_b_content", "score": 0.7, "metadata": {}},
        ]
        list2 = [
            {"content": "doc_b_content", "score": 0.95, "metadata": {}},
            {"content": "doc_c_content", "score": 0.6, "metadata": {}},
        ]
        merged = _rrf_fusion(list1, list2)
        # doc_b appears in both lists, should be ranked higher
        contents = [r["content"] for r in merged]
        assert "doc_b_content" in contents
        assert "doc_a_content" in contents
        assert "doc_c_content" in contents

    def test_empty_lists(self):
        merged = _rrf_fusion([], [])
        assert merged == []

    def test_weighted_fusion(self):
        list1 = [{"content": "only_in_1", "score": 1.0, "metadata": {}}]
        list2 = [{"content": "only_in_2", "score": 1.0, "metadata": {}}]
        # Heavily weight list1
        merged = _rrf_fusion(list1, list2, weights=[0.9, 0.1])
        assert merged[0]["content"] == "only_in_1"

    def test_deduplication_by_content_prefix(self):
        list1 = [{"content": "same content here", "score": 0.9, "metadata": {"src": "a"}}]
        list2 = [{"content": "same content here", "score": 0.8, "metadata": {"src": "b"}}]
        merged = _rrf_fusion(list1, list2)
        # Should deduplicate based on content[:100]
        assert len(merged) == 1


class TestChunkDedupKey:
    def test_key_from_metadata(self):
        r = {"content": "anything", "metadata": {"doc_id": 10, "chunk_index": 3}}
        assert _chunk_dedup_key(r) == "10:3"

    def test_key_from_content_prefix_when_no_metadata(self):
        r = {"content": "A" * 200, "metadata": {}}
        key = _chunk_dedup_key(r)
        assert key == "A" * 120  # content[:120]

    def test_key_partial_metadata_falls_back_to_content(self):
        r = {"content": "hello world", "metadata": {"doc_id": 5}}
        # chunk_index is None -> falls back to content prefix
        key = _chunk_dedup_key(r)
        assert key == "hello world"  # content[:120]

    def test_key_zero_values_treated_as_valid(self):
        r = {"content": "x", "metadata": {"doc_id": 0, "chunk_index": 0}}
        assert _chunk_dedup_key(r) == "0:0"


class TestBM25Cache:
    def setup_method(self):
        _bm25_cache.clear()

    def test_put_and_get(self):
        _put_bm25_cached(1, 100, "bm25_obj", ["chunk1", "chunk2"])
        result = _get_bm25_cached(1, 100)
        assert result is not None
        bm25_obj, chunks = result
        assert bm25_obj == "bm25_obj"
        assert chunks == ["chunk1", "chunk2"]

    def test_miss_on_different_key(self):
        _put_bm25_cached(1, 100, "obj", [])
        assert _get_bm25_cached(1, 200) is None  # different chunk_count
        assert _get_bm25_cached(2, 100) is None  # different kb_id

    def test_invalidate_specific_kb(self):
        _put_bm25_cached(1, 100, "a", [])
        _put_bm25_cached(2, 50, "b", [])
        invalidate_bm25_cache(kb_id=1)
        assert _get_bm25_cached(1, 100) is None
        assert _get_bm25_cached(2, 50) is not None

    def test_invalidate_all(self):
        _put_bm25_cached(1, 100, "a", [])
        _put_bm25_cached(2, 50, "b", [])
        invalidate_bm25_cache(kb_id=None)
        assert len(_bm25_cache) == 0

    def test_ttl_expiry(self):
        from app.services.retrieval_service import _BM25_CACHE_TTL
        _put_bm25_cached(1, 10, "obj", [])
        # Manually expire the entry
        key = (1, 10)
        bm25_obj, chunks, _ts = _bm25_cache[key]
        _bm25_cache[key] = (bm25_obj, chunks, time.monotonic() - _BM25_CACHE_TTL - 1)
        assert _get_bm25_cached(1, 10) is None

    def test_max_entries_eviction(self):
        from app.services.retrieval_service import _BM25_CACHE_MAX
        for i in range(_BM25_CACHE_MAX + 5):
            _put_bm25_cached(i, 1, f"obj_{i}", [])
        assert len(_bm25_cache) <= _BM25_CACHE_MAX
