"""Tests for the VectorStore abstraction layer."""
import pytest
from unittest.mock import patch, MagicMock
from app.core.vector_store.chroma_store import ChromaVectorStore


class TestChromaVectorStore:
    @patch("app.core.vector_store.chroma_store.chromadb")
    @patch("app.core.vector_store.chroma_store.os.makedirs")
    def test_add_and_query(self, mock_makedirs, mock_chromadb):
        mock_collection = MagicMock()
        mock_client = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_chromadb.PersistentClient.return_value = mock_client

        store = ChromaVectorStore()

        store.add(
            collection_name="kb_1",
            ids=["doc_1_chunk_0"],
            embeddings=[[0.1, 0.2, 0.3]],
            documents=["hello world"],
            metadatas=[{"doc_id": 1, "kb_id": 1, "chunk_index": 0}],
        )
        mock_collection.add.assert_called_once()

    @patch("app.core.vector_store.chroma_store.chromadb")
    @patch("app.core.vector_store.chroma_store.os.makedirs")
    def test_upsert(self, mock_makedirs, mock_chromadb):
        mock_collection = MagicMock()
        mock_client = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_chromadb.PersistentClient.return_value = mock_client

        store = ChromaVectorStore()
        store.upsert(
            collection_name="kb_1",
            ids=["doc_1_chunk_0"],
            embeddings=[[0.1, 0.2]],
            documents=["updated"],
            metadatas=[{"doc_id": 1}],
        )
        mock_collection.upsert.assert_called_once()

    @patch("app.core.vector_store.chroma_store.chromadb")
    @patch("app.core.vector_store.chroma_store.os.makedirs")
    def test_delete_by_ids(self, mock_makedirs, mock_chromadb):
        mock_collection = MagicMock()
        mock_client = MagicMock()
        mock_client.get_collection.return_value = mock_collection
        mock_chromadb.PersistentClient.return_value = mock_client

        store = ChromaVectorStore()
        store.delete_by_ids("kb_1", ["doc_1_chunk_0"])
        mock_collection.delete.assert_called_once_with(ids=["doc_1_chunk_0"])

    @patch("app.core.vector_store.chroma_store.chromadb")
    @patch("app.core.vector_store.chroma_store.os.makedirs")
    def test_delete_by_filter(self, mock_makedirs, mock_chromadb):
        mock_collection = MagicMock()
        mock_client = MagicMock()
        mock_client.get_collection.return_value = mock_collection
        mock_chromadb.PersistentClient.return_value = mock_client

        store = ChromaVectorStore()
        store.delete_by_filter("kb_1", {"doc_id": 5})
        mock_collection.delete.assert_called_once_with(where={"doc_id": 5})

    @patch("app.core.vector_store.chroma_store.chromadb")
    @patch("app.core.vector_store.chroma_store.os.makedirs")
    def test_delete_collection(self, mock_makedirs, mock_chromadb):
        mock_client = MagicMock()
        mock_chromadb.PersistentClient.return_value = mock_client

        store = ChromaVectorStore()
        store.delete_collection("kb_1")
        mock_client.delete_collection.assert_called_once_with(name="kb_1")

    @patch("app.core.vector_store.chroma_store.chromadb")
    @patch("app.core.vector_store.chroma_store.os.makedirs")
    def test_query_returns_results(self, mock_makedirs, mock_chromadb):
        mock_collection = MagicMock()
        mock_collection.metadata = {"hnsw:space": "cosine"}
        mock_collection.query.return_value = {
            "documents": [["doc content 1", "doc content 2"]],
            "distances": [[0.1, 0.3]],
            "metadatas": [[{"doc_id": 1}, {"doc_id": 2}]],
        }
        mock_client = MagicMock()
        mock_client.get_collection.return_value = mock_collection
        mock_chromadb.PersistentClient.return_value = mock_client

        store = ChromaVectorStore()
        results = store.query("kb_1", [0.1, 0.2, 0.3], top_k=2)

        assert len(results) == 2
        assert results[0]["content"] == "doc content 1"
        assert results[0]["score"] == pytest.approx(0.9)
        assert results[1]["metadata"]["doc_id"] == 2

    @patch("app.core.vector_store.chroma_store.chromadb")
    @patch("app.core.vector_store.chroma_store.os.makedirs")
    def test_query_empty_collection(self, mock_makedirs, mock_chromadb):
        mock_client = MagicMock()
        mock_client.get_collection.side_effect = Exception("not found")
        mock_chromadb.PersistentClient.return_value = mock_client

        store = ChromaVectorStore()
        results = store.query("kb_999", [0.1, 0.2], top_k=5)
        assert results == []
