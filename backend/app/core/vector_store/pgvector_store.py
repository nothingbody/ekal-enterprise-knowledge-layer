"""
PGVector implementation of the VectorStore interface.
Requires the pgvector extension in PostgreSQL and asyncpg driver.
Tables are created lazily per collection.
"""
import logging
from typing import List

from app.config import settings
from app.database import get_sync_database_url
from app.core.vector_store.base import VectorStore

_logger = logging.getLogger(__name__)


class PGVectorStore(VectorStore):
    """
    Uses raw SQL via asyncpg for vector operations on PostgreSQL + pgvector.
    Each 'collection' maps to a table named 'vec_{collection_name}'.
    """

    def __init__(self):
        self._db_url = get_sync_database_url(settings.DATABASE_URL)
        self._pool = None
        self._loop = None

    def _get_sync_dsn(self) -> str:
        return get_sync_database_url(settings.DATABASE_URL)

    def _get_loop(self):
        """Get or create a dedicated event loop for sync-to-async bridging."""
        if self._loop is None or self._loop.is_closed():
            import asyncio
            self._loop = asyncio.new_event_loop()
        return self._loop

    def _run_sync(self, coro):
        """Run an async coroutine from a sync context using a dedicated loop."""
        return self._get_loop().run_until_complete(coro)

    def _get_pool(self):
        if self._pool is None:
            import asyncpg
            dsn = self._get_sync_dsn()
            self._pool = self._run_sync(asyncpg.create_pool(dsn, min_size=1, max_size=5))
        return self._pool

    def close(self):
        """Release connection pool and event loop resources."""
        if self._pool is not None:
            try:
                self._run_sync(self._pool.close())
            except Exception as e:
                _logger.warning("PGVectorStore pool close failed: %s", e)
            self._pool = None
        if self._loop is not None and not self._loop.is_closed():
            try:
                self._loop.close()
            except Exception:
                pass
            self._loop = None

    def _table_name(self, collection_name: str) -> str:
        import re
        # Strict sanitization: only allow alphanumeric and underscore
        safe = re.sub(r'[^a-zA-Z0-9_]', '_', collection_name)
        return f"vec_{safe}"

    def get_or_create_collection(self, name: str) -> None:
        self._run_sync(self._ensure_table(name))

    async def _ensure_table(self, name: str):
        table = self._table_name(name)
        pool = self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {table} (
                    id TEXT PRIMARY KEY,
                    embedding vector,
                    document TEXT,
                    metadata JSONB DEFAULT '{{}}'
                )
            """)
            await conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{table}_embedding
                ON {table} USING ivfflat (embedding vector_cosine_ops)
            """)

    def add(
        self,
        collection_name: str,
        ids: List[str],
        embeddings: List[List[float]],
        documents: List[str],
        metadatas: List[dict],
    ) -> None:
        self._run_sync(
            self._add_async(collection_name, ids, embeddings, documents, metadatas)
        )

    async def _add_async(self, collection_name, ids, embeddings, documents, metadatas):
        import json
        table = self._table_name(collection_name)
        pool = self._get_pool()
        # Prepare rows for batch upsert
        rows = []
        for i in range(len(ids)):
            emb_str = "[" + ",".join(str(v) for v in embeddings[i]) + "]"
            meta_json = json.dumps(metadatas[i]) if metadatas[i] else "{}"
            rows.append((ids[i], emb_str, documents[i], meta_json))
        async with pool.acquire() as conn:
            # Use executemany for batch insert instead of row-by-row
            await conn.executemany(
                f"INSERT INTO {table} (id, embedding, document, metadata) VALUES ($1, $2::vector, $3, $4::jsonb) "
                f"ON CONFLICT (id) DO UPDATE SET embedding=$2::vector, document=$3, metadata=$4::jsonb",
                rows,
            )

    def query(
        self,
        collection_name: str,
        query_embedding: List[float],
        top_k: int = 5,
    ) -> List[dict]:
        return self._run_sync(
            self._query_async(collection_name, query_embedding, top_k)
        )

    async def _query_async(self, collection_name, query_embedding, top_k):
        import json
        table = self._table_name(collection_name)
        emb_str = "[" + ",".join(str(v) for v in query_embedding) + "]"
        pool = self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT document, metadata, 1 - (embedding <=> $1::vector) AS score "
                f"FROM {table} ORDER BY embedding <=> $1::vector LIMIT $2",
                emb_str, top_k,
            )
        results = []
        for row in rows:
            meta = json.loads(row["metadata"]) if row["metadata"] else {}
            results.append({
                "content": row["document"],
                "score": float(row["score"]),
                "metadata": meta,
            })
        return results

    def upsert(
        self,
        collection_name: str,
        ids: List[str],
        embeddings: List[List[float]],
        documents: List[str],
        metadatas: List[dict],
    ) -> None:
        self.add(collection_name, ids, embeddings, documents, metadatas)

    def delete_by_ids(self, collection_name: str, ids: List[str]) -> None:
        self._run_sync(self._delete_ids_async(collection_name, ids))

    async def _delete_ids_async(self, collection_name, ids):
        table = self._table_name(collection_name)
        pool = self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"DELETE FROM {table} WHERE id = ANY($1)", ids)

    def delete_by_filter(self, collection_name: str, filter_dict: dict) -> None:
        self._run_sync(self._delete_filter_async(collection_name, filter_dict))

    async def _delete_filter_async(self, collection_name, filter_dict):
        import json
        import re
        table = self._table_name(collection_name)
        pool = self._get_pool()
        conditions = []
        values = []
        for i, (k, v) in enumerate(filter_dict.items(), 1):
            # Sanitize key: only allow alphanumeric + underscore to prevent SQL injection
            if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', k):
                raise ValueError(f"Invalid metadata key: {k}")
            conditions.append(f"metadata->>'{k}' = ${i}")
            values.append(str(v))
        if not conditions:
            return
        where = " AND ".join(conditions)
        async with pool.acquire() as conn:
            await conn.execute(f"DELETE FROM {table} WHERE {where}", *values)

    def delete_collection(self, name: str) -> None:
        self._run_sync(self._drop_table(name))

    async def _drop_table(self, name):
        table = self._table_name(name)
        pool = self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"DROP TABLE IF EXISTS {table}")
