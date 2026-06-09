"""
ChromaDB implementation of the VectorStore interface.
"""
import importlib
import logging
import os
import sys
import types
from typing import List

# ---------------------------------------------------------------------------
# ChromaDB 0.6.x instantiates its default ONNXMiniLM_L6_V2 embedding function
# at *module import time* (CollectionCommon class definition).  That EF requires
# onnxruntime + tokenizers, both excluded from desktop PyInstaller builds.
# We inject lightweight stubs into sys.modules so `import chromadb` succeeds.
# The stubs are never actually called — we always pass _noop_ef to every
# collection operation.
# ---------------------------------------------------------------------------
def _ensure_stub(mod_name: str, attrs: dict | None = None) -> None:
    """Register a stub module in sys.modules if the real one is unavailable."""
    try:
        importlib.import_module(mod_name)
    except Exception:
        stub = types.ModuleType(mod_name)
        stub.__spec__ = None
        for k, v in (attrs or {}).items():
            setattr(stub, k, v)
        sys.modules[mod_name] = stub

_ensure_stub("onnxruntime")
_ensure_stub("tokenizers", {"Tokenizer": type("Tokenizer", (), {})})

import chromadb  # noqa: E402  — must come after stubs
from chromadb.api.types import EmbeddingFunction, Embeddings, Documents

logger = logging.getLogger(__name__)

from app.config import settings
from app.core.vector_store.base import VectorStore


class _NoOpEmbeddingFunction(EmbeddingFunction):
    """Dummy embedding function — the platform computes embeddings externally.

    Prevents ChromaDB from instantiating the default ONNXMiniLM_L6_V2
    which requires onnxruntime (excluded from desktop builds).
    """

    def __call__(self, input: Documents) -> Embeddings:
        raise NotImplementedError("External embeddings are used")


_noop_ef = _NoOpEmbeddingFunction()

# Use cosine distance — the standard metric for modern embedding models.
# Existing L2 collections keep their original setting (get_or_create is safe).
_COLLECTION_METADATA = {"hnsw:space": "cosine"}


class ChromaVectorStore(VectorStore):
    def __init__(self):
        if getattr(settings, 'CHROMA_MODE', 'embedded') == 'embedded':
            os.makedirs(settings.CHROMA_DATA_DIR, exist_ok=True)
            self._client = chromadb.PersistentClient(path=settings.CHROMA_DATA_DIR)
        else:
            self._client = chromadb.HttpClient(host=settings.CHROMA_HOST, port=settings.CHROMA_PORT)

    def get_or_create_collection(self, name: str) -> None:
        self._client.get_or_create_collection(
            name=name, embedding_function=_noop_ef, metadata=_COLLECTION_METADATA,
        )

    def add(
        self,
        collection_name: str,
        ids: List[str],
        embeddings: List[List[float]],
        documents: List[str],
        metadatas: List[dict],
    ) -> None:
        collection = self._client.get_or_create_collection(
            name=collection_name, embedding_function=_noop_ef, metadata=_COLLECTION_METADATA,
        )
        collection.add(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)

    def query(
        self,
        collection_name: str,
        query_embedding: List[float],
        top_k: int = 5,
    ) -> List[dict]:
        try:
            collection = self._client.get_collection(name=collection_name, embedding_function=_noop_ef)
        except Exception:
            return []

        try:
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            logger.error("向量检索失败 (collection=%s): %s", collection_name, exc)
            return []

        # Determine distance space to compute a meaningful similarity score.
        # cosine distance ∈ [0, 2]: score = 1 - d  (cosine similarity)
        # L2 distance     ∈ [0, ∞): score = 1/(1+d) (bounded 0‑1)
        meta = collection.metadata or {}
        is_cosine = (meta.get("hnsw:space") == "cosine")

        search_results = []
        if results["documents"] and results["documents"][0]:
            for idx, doc in enumerate(results["documents"][0]):
                dist = results["distances"][0][idx] if results["distances"] else 0
                score = (1 - dist) if is_cosine else (1.0 / (1.0 + dist))
                search_results.append({
                    "content": doc,
                    "score": score,
                    "metadata": results["metadatas"][0][idx] if results["metadatas"] else {},
                })
        logger.debug(
            "向量检索 collection=%s top_k=%d returned=%d space=%s",
            collection_name, top_k, len(search_results),
            meta.get("hnsw:space", "l2"),
        )
        return search_results

    def upsert(
        self,
        collection_name: str,
        ids: List[str],
        embeddings: List[List[float]],
        documents: List[str],
        metadatas: List[dict],
    ) -> None:
        collection = self._client.get_or_create_collection(
            name=collection_name, embedding_function=_noop_ef, metadata=_COLLECTION_METADATA,
        )
        collection.upsert(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)

    def delete_by_ids(self, collection_name: str, ids: List[str]) -> None:
        try:
            collection = self._client.get_collection(name=collection_name, embedding_function=_noop_ef)
            collection.delete(ids=ids)
        except Exception:
            logger.debug("delete_by_ids skipped: collection '%s' not found", collection_name)

    def delete_by_filter(self, collection_name: str, filter_dict: dict) -> None:
        try:
            collection = self._client.get_collection(name=collection_name, embedding_function=_noop_ef)
            collection.delete(where=filter_dict)
        except Exception:
            logger.debug("delete_by_filter skipped: collection '%s' not found", collection_name)

    def delete_collection(self, name: str) -> None:
        try:
            self._client.delete_collection(name=name)
        except Exception:
            logger.debug("delete_collection skipped: collection '%s' not found", name)
