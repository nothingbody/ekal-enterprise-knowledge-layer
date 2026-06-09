"""
Factory for creating vector store instances based on configuration.
"""
import threading

from app.config import settings
from app.core.vector_store.base import VectorStore

_instance: VectorStore = None
_lock = threading.Lock()


def _is_postgresql_database_url(database_url: str) -> bool:
    return database_url.lower().startswith("postgresql")


def get_vector_store() -> VectorStore:
    """Get the singleton vector store instance based on VECTOR_STORE_TYPE setting."""
    global _instance
    if _instance is not None:
        return _instance

    with _lock:
        if _instance is not None:
            return _instance

        store_type = getattr(settings, "VECTOR_STORE_TYPE", "chroma")

        if store_type == "pgvector":
            if not _is_postgresql_database_url(settings.DATABASE_URL):
                raise RuntimeError("VECTOR_STORE_TYPE=pgvector 仅支持 PostgreSQL 主库，请改用 PostgreSQL 或将 VECTOR_STORE_TYPE 设置为 chroma")
            from app.core.vector_store.pgvector_store import PGVectorStore
            _instance = PGVectorStore()
        else:
            from app.core.vector_store.chroma_store import ChromaVectorStore
            _instance = ChromaVectorStore()

    return _instance
