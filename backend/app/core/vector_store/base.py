"""
Abstract base class for vector store implementations.
All vector stores must implement this interface.
"""
from abc import ABC, abstractmethod
from typing import List, Optional


class VectorStore(ABC):
    """Unified interface for vector storage backends."""

    @abstractmethod
    def get_or_create_collection(self, name: str) -> None:
        """Ensure a collection/table exists."""
        ...

    @abstractmethod
    def add(
        self,
        collection_name: str,
        ids: List[str],
        embeddings: List[List[float]],
        documents: List[str],
        metadatas: List[dict],
    ) -> None:
        """Add vectors with documents and metadata."""
        ...

    @abstractmethod
    def query(
        self,
        collection_name: str,
        query_embedding: List[float],
        top_k: int = 5,
    ) -> List[dict]:
        """Query for similar vectors. Returns list of {content, score, metadata}."""
        ...

    @abstractmethod
    def upsert(
        self,
        collection_name: str,
        ids: List[str],
        embeddings: List[List[float]],
        documents: List[str],
        metadatas: List[dict],
    ) -> None:
        """Insert or update vectors."""
        ...

    @abstractmethod
    def delete_by_ids(self, collection_name: str, ids: List[str]) -> None:
        """Delete vectors by their IDs."""
        ...

    @abstractmethod
    def delete_by_filter(self, collection_name: str, filter_dict: dict) -> None:
        """Delete vectors matching a metadata filter."""
        ...

    @abstractmethod
    def delete_collection(self, name: str) -> None:
        """Drop an entire collection."""
        ...
