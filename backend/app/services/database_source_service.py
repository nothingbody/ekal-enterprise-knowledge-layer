import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import MetaData, Table, create_engine, delete, inspect, select, text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.chunking import split_text
from app.core.encryption import decrypt_value, encrypt_value, is_encrypted
from app.models.database_source import DatabaseSource, DatabaseSourceStatus, DatabaseSyncRun, DatabaseType, SyncRunStatus
from app.models.document import Document, DocumentChunk, DocumentStatus
from app.models.knowledge_base import KnowledgeBase
from app.schemas.database_source import DatabaseSourceCreate, DatabaseSourceUpdate
from app.services.knowledge_base_service import refresh_kb_counts as _refresh_kb_counts
from app.services.embedding_service import delete_doc_chunks_from_collection, embed_and_store


logger = logging.getLogger(__name__)


DEFAULT_PORTS = {
    DatabaseType.POSTGRESQL.value: 5432,
    DatabaseType.MYSQL.value: 3306,
    DatabaseType.TRINO.value: 8080,
}


def _enum_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    return value.value if hasattr(value, "value") else str(value)


def _parse_table_names(value: Optional[str]) -> list[str]:
    if not value:
        return []
    try:
        data = json.loads(value)
        if isinstance(data, list):
            return [str(item).strip() for item in data if str(item).strip()]
    except Exception:
        pass
    return []


# ---------- sync text quality helpers ----------

_BASE64_RE = re.compile(r'^[A-Za-z0-9+/=]{80,}$')


def _is_noise_value(v: Any) -> bool:
    """Return True if the value looks like base64, binary blob, or other
    encoded noise that is useless for RAG retrieval."""
    if v is None:
        return False
    s = str(v)
    if len(s) > 500:
        return True                          # very long values are noise
    if isinstance(v, (bytes, bytearray)):
        return True
    if _BASE64_RE.match(s):
        return True                          # looks like base64
    return False


def _format_row_text(row: dict) -> str:
    """Format a DB row as a human-readable line, skipping noise fields."""
    parts: list[str] = []
    for k, v in row.items():
        if _is_noise_value(v):
            continue
        val = str(v) if v is not None else ""
        # Truncate moderately long values
        if len(val) > 200:
            val = val[:200] + "…"
        parts.append(f"{k}: {val}")
    return "; ".join(parts) if parts else ""


def _parse_column_filter(value: Optional[str]) -> Optional[dict]:
    if not value:
        return None
    try:
        data = json.loads(value)
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if isinstance(v, list)}
    except Exception:
        pass
    return None


def _decrypt_password(value: Optional[str]) -> str:
    if not value:
        return ""
    if is_encrypted(value):
        return decrypt_value(value, settings.SECRET_KEY)
    return value


def serialize_database_source(source: DatabaseSource) -> dict:
    return {
        "id": source.id,
        "kb_id": source.kb_id,
        "name": source.name,
        "db_type": _enum_value(source.db_type),
        "host": source.host,
        "port": source.port,
        "database_name": source.database_name,
        "schema_name": source.schema_name,
        "username": source.username,
        "table_names": _parse_table_names(source.table_names),
        "column_filter": _parse_column_filter(source.column_filter),
        "row_limit": source.row_limit,
        "has_password": bool(source.password_encrypted),
        "status": _enum_value(source.status),
        "last_synced_at": source.last_synced_at,
        "last_error": source.last_error,
        "created_at": source.created_at,
        "updated_at": source.updated_at,
    }


def _validate_source_config(data: dict):
    db_type = data.get("db_type")
    if hasattr(db_type, "value"):
        db_type = db_type.value
    if not data.get("host"):
        raise ValueError("数据库主机不能为空")
    if not data.get("database_name"):
        raise ValueError("数据库名称不能为空")
    if not data.get("username"):
        raise ValueError("数据库用户名不能为空")


def _build_connection_url(source: DatabaseSource):
    db_type = _enum_value(source.db_type)
    if db_type == DatabaseType.POSTGRESQL.value:
        driver = "postgresql+psycopg2"
    elif db_type == DatabaseType.MYSQL.value:
        driver = "mysql+pymysql"
    elif db_type == DatabaseType.TRINO.value:
        driver = "trino"
    else:
        raise ValueError("暂不支持的数据库类型")

    host = source.host or None
    port = source.port or DEFAULT_PORTS.get(db_type)
    password = _decrypt_password(source.password_encrypted) or None

    if db_type == DatabaseType.TRINO.value:
        catalog = source.database_name or "hive"
        schema = source.schema_name or "default"
        return URL.create(
            drivername=driver,
            username=source.username or "trino",
            password=password,
            host=host,
            port=port,
            database=f"{catalog}/{schema}",
        )

    return URL.create(
        drivername=driver,
        username=source.username or None,
        password=password,
        host=host,
        port=port,
        database=source.database_name or None,
    )


CONNECT_TIMEOUT = 10
QUERY_TIMEOUT = 30
SCAN_TIMEOUT = 3


def scan_local_databases() -> list[dict]:
    """Scan localhost for running MySQL/PostgreSQL and list their databases."""
    import socket

    discovered = []

    # ── MySQL (use pymysql directly for reliable auth) ──
    mysql_credentials = [
        ("root", ""),
        ("root", "root"),
        ("root", "123456"),
        ("root", "password"),
        ("root", "mysql"),
    ]
    if _port_open("127.0.0.1", 3306):
        import pymysql
        for user, pwd in mysql_credentials:
            try:
                conn = pymysql.connect(host="127.0.0.1", port=3306, user=user, password=pwd, connect_timeout=SCAN_TIMEOUT)
                cur = conn.cursor()
                cur.execute("SHOW DATABASES")
                skip = {"information_schema", "mysql", "performance_schema", "sys"}
                for (db_name,) in cur.fetchall():
                    if db_name.lower() in skip:
                        continue
                    try:
                        cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = %s", (db_name,))
                        table_count = cur.fetchone()[0]
                    except Exception:
                        table_count = 0
                    discovered.append({
                        "db_type": "mysql",
                        "host": "127.0.0.1",
                        "port": 3306,
                        "database_name": db_name,
                        "username": user,
                        "has_password": bool(pwd),
                        "table_count": table_count,
                    })
                conn.close()
                break
            except Exception:
                continue

    # ── PostgreSQL ──
    pg_credentials = [
        ("postgres", "postgres"),
        ("postgres", ""),
        ("postgres", "123456"),
        ("postgres", "password"),
    ]
    if _port_open("127.0.0.1", 5432):
        for user, pwd in pg_credentials:
            try:
                url = URL.create("postgresql+psycopg2", username=user, password=pwd or None, host="127.0.0.1", port=5432, database="postgres")
                eng = create_engine(url, connect_args={"connect_timeout": SCAN_TIMEOUT})
                with eng.connect() as conn:
                    rows = conn.execute(text("SELECT datname FROM pg_database WHERE datistemplate = false")).fetchall()
                    skip = {"postgres"}
                    for (db_name,) in rows:
                        if db_name.lower() in skip:
                            continue
                        try:
                            t_rows = conn.execute(text(
                                "SELECT COUNT(*) FROM information_schema.tables "
                                "WHERE table_catalog = :db AND table_schema = 'public'"
                            ), {"db": db_name}).fetchone()
                            table_count = t_rows[0] if t_rows else 0
                        except Exception:
                            table_count = 0
                        discovered.append({
                            "db_type": "postgresql",
                            "host": "127.0.0.1",
                            "port": 5432,
                            "database_name": db_name,
                            "username": user,
                            "has_password": bool(pwd),
                            "table_count": table_count,
                        })
                eng.dispose()
                break
            except Exception:
                continue

    return discovered


def list_server_databases(db_type: str, host: str, port: int | None, username: str, password: str | None) -> list[dict]:
    """Connect to a database server and list all user databases (like Navicat)."""
    import pymysql

    results = []

    if db_type == "mysql":
        _port = port or 3306
        conn = pymysql.connect(host=host, port=_port, user=username, password=password or "", connect_timeout=CONNECT_TIMEOUT)
        cur = conn.cursor()
        cur.execute("SHOW DATABASES")
        skip = {"information_schema", "mysql", "performance_schema", "sys"}
        for (db_name,) in cur.fetchall():
            if db_name.lower() in skip:
                continue
            try:
                cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = %s", (db_name,))
                table_count = cur.fetchone()[0]
            except Exception:
                table_count = 0
            results.append({
                "database_name": db_name,
                "table_count": table_count,
            })
        conn.close()

    elif db_type == "postgresql":
        _port = port or 5432
        url = URL.create("postgresql+psycopg2", username=username, password=password or None, host=host, port=_port, database="postgres")
        eng = create_engine(url, connect_args={"connect_timeout": CONNECT_TIMEOUT})
        with eng.connect() as conn:
            rows = conn.execute(text("SELECT datname FROM pg_database WHERE datistemplate = false")).fetchall()
            skip = {"postgres"}
            for (db_name,) in rows:
                if db_name.lower() in skip:
                    continue
                try:
                    t_rows = conn.execute(text(
                        "SELECT COUNT(*) FROM information_schema.tables "
                        "WHERE table_catalog = :db AND table_schema = 'public'"
                    ), {"db": db_name}).fetchone()
                    table_count = t_rows[0] if t_rows else 0
                except Exception:
                    table_count = 0
                results.append({
                    "database_name": db_name,
                    "table_count": table_count,
                })
        eng.dispose()

    return results


def _port_open(host: str, port: int) -> bool:
    import socket
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except (OSError, ConnectionRefusedError):
        return False


def _quote_qualified_name(engine, table_name: str, schema_name: Optional[str] = None) -> str:
    preparer = engine.dialect.identifier_preparer
    parts = []
    if schema_name:
        parts.append(preparer.quote_identifier(schema_name))
    parts.append(preparer.quote_identifier(table_name))
    return ".".join(parts)


def _get_stable_order_clause(engine, inspector, table_name: str, schema_name: Optional[str], columns: list[str]) -> str:
    """Return an ORDER BY clause that makes LIMIT deterministic.

    Priority: primary-key columns > first column > empty (last resort).
    All identifiers are dialect-safe quoted.
    """
    preparer = engine.dialect.identifier_preparer
    pk_cols: list[str] = []
    try:
        pk_info = inspector.get_pk_constraint(table_name, schema=schema_name)
        pk_cols = pk_info.get("constrained_columns", []) if pk_info else []
    except Exception:
        pass

    order_cols = pk_cols if pk_cols else (columns[:1] if columns else [])
    if not order_cols:
        return ""
    quoted = ", ".join(preparer.quote_identifier(c) for c in order_cols)
    return f" ORDER BY {quoted}"


def _create_external_engine(source: DatabaseSource):
    db_type = _enum_value(source.db_type)
    connect_args: dict = {}
    if db_type == DatabaseType.POSTGRESQL.value:
        connect_args = {"connect_timeout": CONNECT_TIMEOUT, "options": f"-c statement_timeout={QUERY_TIMEOUT * 1000}"}
    elif db_type == DatabaseType.MYSQL.value:
        connect_args = {"connect_timeout": CONNECT_TIMEOUT, "read_timeout": QUERY_TIMEOUT, "write_timeout": QUERY_TIMEOUT}
    elif db_type == DatabaseType.TRINO.value:
        connect_args = {}
    return create_engine(
        _build_connection_url(source),
        pool_pre_ping=True,
        connect_args=connect_args,
    )


def _test_connection_sync(source: DatabaseSource) -> dict:
    engine = _create_external_engine(source)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        # Also fetch tables for the create wizard
        try:
            tables = _list_tables_sync.__wrapped__(source) if hasattr(_list_tables_sync, '__wrapped__') else _list_tables_from_engine(engine, source)
        except Exception:
            tables = []
        return {"success": True, "message": "连接成功", "tables": tables}
    finally:
        engine.dispose()


def _list_tables_from_engine(engine, source: DatabaseSource) -> list[dict]:
    schema_name = source.schema_name or None
    try:
        insp = inspect(engine)
        items = []
        for table_name in insp.get_table_names(schema=schema_name):
            columns = insp.get_columns(table_name, schema=schema_name)
            items.append({"name": table_name, "kind": "table", "columns": [{"name": c["name"], "type": str(c["type"])} for c in columns]})
        for view_name in insp.get_view_names(schema=schema_name):
            columns = insp.get_columns(view_name, schema=schema_name)
            items.append({"name": view_name, "kind": "view", "columns": [{"name": c["name"], "type": str(c["type"])} for c in columns]})
        items.sort(key=lambda item: (item["kind"], item["name"]))
        return items
    except Exception:
        return []


def _list_tables_sync(source: DatabaseSource) -> list[dict]:
    engine = _create_external_engine(source)
    schema_name = source.schema_name or None
    try:
        inspector = inspect(engine)
        items = []
        for table_name in inspector.get_table_names(schema=schema_name):
            columns = inspector.get_columns(table_name, schema=schema_name)
            items.append({
                "name": table_name,
                "kind": "table",
                "columns": [{"name": c["name"], "type": str(c["type"])} for c in columns],
            })
        for view_name in inspector.get_view_names(schema=schema_name):
            columns = inspector.get_columns(view_name, schema=schema_name)
            items.append({
                "name": view_name,
                "kind": "view",
                "columns": [{"name": c["name"], "type": str(c["type"])} for c in columns],
            })
        items.sort(key=lambda item: (item["kind"], item["name"]))
        return items
    finally:
        engine.dispose()


def _fetch_sync_payloads(source: DatabaseSource) -> list[dict]:
    engine = _create_external_engine(source)
    schema_name = source.schema_name or None
    selected_tables = set(_parse_table_names(source.table_names))
    col_filter = _parse_column_filter(source.column_filter) or {}
    row_limit = max(int(source.row_limit or 200), 1)
    batch_size = 500
    preparer = engine.dialect.identifier_preparer
    try:
        inspector = inspect(engine)
        names = inspector.get_table_names(schema=schema_name)
        names += [name for name in inspector.get_view_names(schema=schema_name) if name not in names]
        if selected_tables:
            names = [name for name in names if name in selected_tables]
        payloads = []
        # Use a single connection for all table reads to get a consistent snapshot
        with engine.connect() as conn:
            for table_name in names:
                # Use inspector + raw SQL instead of Table autoload to avoid
                # SQLAlchemy MySQL dialect bug with foreign key reflection
                # (KeyError: 'TABLENAME' in _correct_for_mysql_bugs_88718_96365)
                col_infos = inspector.get_columns(table_name, schema=schema_name)
                all_columns = [c["name"] for c in col_infos]
                # Apply column filter: only keep selected columns for this table
                if table_name in col_filter and col_filter[table_name]:
                    valid_cols = [c for c in col_filter[table_name] if c in all_columns]
                    columns = valid_cols if valid_cols else all_columns
                else:
                    columns = all_columns
                qualified = _quote_qualified_name(engine, table_name, schema_name)
                order_clause = _get_stable_order_clause(engine, inspector, table_name, schema_name, columns)
                select_cols = ", ".join(preparer.quote_identifier(c) for c in columns)

                row_lines: list[str] = []
                total_fetched = 0
                remaining = row_limit
                while remaining > 0:
                    page_size = min(batch_size, remaining)
                    batch = conn.execute(
                        text(f"SELECT {select_cols} FROM {qualified}{order_clause} LIMIT :lim OFFSET :off"),
                        {"lim": page_size, "off": total_fetched},
                    ).mappings().all()
                    if not batch:
                        break
                    for row in batch:
                        line = _format_row_text(dict(row))
                        if line:
                            row_lines.append(line)
                    total_fetched += len(batch)
                    remaining -= len(batch)
                    if len(batch) < page_size:
                        break

                body = "\n".join([
                    f"数据源名称：{source.name}",
                    f"数据库类型：{_enum_value(source.db_type)}",
                    f"数据库名称：{source.database_name or ''}",
                    f"模式：{source.schema_name or ''}",
                    f"表名：{table_name}",
                    f"字段：{', '.join(columns)}",
                    "记录：",
                    "\n".join(row_lines) if row_lines else "（空表）",
                ])
                payloads.append({
                    "table_name": table_name,
                    "columns": columns,
                    "text": body,
                    "row_count": total_fetched,
                })
        return payloads
    finally:
        engine.dispose()


def _source_doc_prefix(source_id: int) -> str:
    return f"db://source/{source_id}/table/"


async def _list_database_source_documents(db: AsyncSession, source_id: int, kb_id: int) -> list[Document]:
    prefix = _source_doc_prefix(source_id)
    result = await db.execute(
        select(Document).where(
            Document.kb_id == kb_id,
            Document.file_type == "database",
            Document.file_path.like(f"{prefix}%"),
        )
    )
    return result.scalars().all()


async def _delete_database_documents_in_db(db: AsyncSession, docs: list[Document]) -> list[int]:
    doc_ids: list[int] = []
    for doc in docs:
        doc_ids.append(doc.id)
        await db.execute(delete(DocumentChunk).where(DocumentChunk.doc_id == doc.id))
        await db.delete(doc)
    return doc_ids


def _delete_database_document_vectors(kb_id: int, doc_ids: list[int]) -> None:
    for doc_id in doc_ids:
        try:
            delete_doc_chunks_from_collection(kb_id, doc_id)
        except Exception as exc:
            logger.warning(
                "数据库源向量清理失败 (kb_id=%s, doc_id=%s): %s",
                kb_id,
                doc_id,
                exc,
            )


def _invalidate_retrieval_cache(kb_id: int) -> None:
    try:
        from app.services.retrieval_service import invalidate_bm25_cache

        invalidate_bm25_cache(kb_id)
    except Exception as exc:
        logger.warning("数据库源 BM25 缓存失效失败 (kb_id=%s): %s", kb_id, exc)


def serialize_sync_run(run: DatabaseSyncRun) -> dict:
    return {
        "id": run.id,
        "source_id": run.source_id,
        "status": run.status.value if hasattr(run.status, "value") else run.status,
        "table_count": run.table_count or 0,
        "row_count": run.row_count or 0,
        "chunk_count": run.chunk_count or 0,
        "duration_seconds": run.duration_seconds,
        "tables_detail": run.tables_detail,
        "error_message": run.error_message,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
    }


async def list_sync_runs(db: AsyncSession, source_id: int, limit: int = 20) -> list[dict]:
    result = await db.execute(
        select(DatabaseSyncRun)
        .where(DatabaseSyncRun.source_id == source_id)
        .order_by(DatabaseSyncRun.started_at.desc())
        .limit(limit)
    )
    return [serialize_sync_run(r) for r in result.scalars().all()]


async def list_database_sources(db: AsyncSession, kb_id: int) -> list[dict]:
    result = await db.execute(
        select(DatabaseSource)
        .where(DatabaseSource.kb_id == kb_id)
        .order_by(DatabaseSource.created_at.desc())
    )
    return [serialize_database_source(item) for item in result.scalars().all()]


async def get_database_source(db: AsyncSession, source_id: int) -> Optional[DatabaseSource]:
    result = await db.execute(select(DatabaseSource).where(DatabaseSource.id == source_id))
    return result.scalar_one_or_none()


async def create_database_source(db: AsyncSession, data: DatabaseSourceCreate) -> dict:
    payload = data.model_dump()
    _validate_source_config(payload)
    source = DatabaseSource(
        kb_id=data.kb_id,
        name=data.name,
        db_type=DatabaseType(data.db_type),
        host=data.host,
        port=data.port or DEFAULT_PORTS.get(data.db_type),
        database_name=data.database_name,
        schema_name=data.schema_name,
        username=data.username,
        password_encrypted=encrypt_value(data.password, settings.SECRET_KEY) if data.password else None,
        table_names=json.dumps(data.table_names, ensure_ascii=False) if data.table_names else None,
        column_filter=json.dumps(data.column_filter, ensure_ascii=False) if data.column_filter else None,
        row_limit=data.row_limit,
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return serialize_database_source(source)


async def update_database_source_record(db: AsyncSession, source: DatabaseSource, data: DatabaseSourceUpdate) -> dict:
    from app.services.text_to_sql_service import invalidate_engine_cache
    invalidate_engine_cache(source.id)

    update_data = data.model_dump(exclude_unset=True)
    old_kb_id = source.kb_id
    merged = {
        "db_type": update_data.get("db_type", _enum_value(source.db_type)),
        "host": update_data.get("host", source.host),
        "port": update_data.get("port", source.port),
        "database_name": update_data.get("database_name", source.database_name),
        "schema_name": update_data.get("schema_name", source.schema_name),
        "username": update_data.get("username", source.username),
    }
    _validate_source_config(merged)

    if "password" in update_data:
        raw_password = update_data.pop("password")
        update_data["password_encrypted"] = encrypt_value(raw_password, settings.SECRET_KEY) if raw_password else None
    if "db_type" in update_data:
        update_data["db_type"] = DatabaseType(update_data["db_type"])
    if "table_names" in update_data:
        update_data["table_names"] = json.dumps(update_data["table_names"], ensure_ascii=False) if update_data["table_names"] else None
    if "column_filter" in update_data:
        update_data["column_filter"] = json.dumps(update_data["column_filter"], ensure_ascii=False) if update_data["column_filter"] else None
    if "db_type" in update_data and update_data["db_type"].value in DEFAULT_PORTS and "port" not in update_data:
        update_data["port"] = DEFAULT_PORTS[update_data["db_type"].value]

    if "kb_id" in update_data and update_data["kb_id"] != source.kb_id:
        await delete_database_source_documents(db, source.id, source.kb_id)

    for key, value in update_data.items():
        setattr(source, key, value)
    source.status = DatabaseSourceStatus.PENDING
    source.last_error = None
    await db.commit()
    await db.refresh(source)
    if source.kb_id != old_kb_id:
        await _refresh_kb_counts(db, old_kb_id)
        await _refresh_kb_counts(db, source.kb_id)
    return serialize_database_source(source)


async def delete_database_source_record(db: AsyncSession, source: DatabaseSource):
    from app.services.text_to_sql_service import invalidate_engine_cache
    invalidate_engine_cache(source.id)

    await delete_database_source_documents(db, source.id, source.kb_id)
    await db.delete(source)
    await db.commit()
    await _refresh_kb_counts(db, source.kb_id)


async def test_database_source_connection(source: DatabaseSource) -> dict:
    return await asyncio.to_thread(_test_connection_sync, source)


async def list_database_source_tables(source: DatabaseSource) -> list[dict]:
    return await asyncio.to_thread(_list_tables_sync, source)


async def delete_database_source_documents(db: AsyncSession, source_id: int, kb_id: int):
    docs = await _list_database_source_documents(db, source_id, kb_id)
    doc_ids = await _delete_database_documents_in_db(db, docs)
    await db.commit()
    if doc_ids:
        _delete_database_document_vectors(kb_id, doc_ids)
        _invalidate_retrieval_cache(kb_id)


STALE_SYNC_TIMEOUT_MINUTES = 10


async def _is_sync_stale(db: AsyncSession, source_id: int) -> bool:
    """Check if the latest RUNNING sync run for this source is older than the timeout."""
    result = await db.execute(
        select(DatabaseSyncRun)
        .where(DatabaseSyncRun.source_id == source_id, DatabaseSyncRun.status == SyncRunStatus.RUNNING)
        .order_by(DatabaseSyncRun.started_at.desc())
        .limit(1)
    )
    run = result.scalar_one_or_none()
    if not run:
        return True
    if not run.started_at:
        return True
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=STALE_SYNC_TIMEOUT_MINUTES)
    started = run.started_at if run.started_at.tzinfo else run.started_at.replace(tzinfo=timezone.utc)
    return started < cutoff


async def _mark_stale_runs(db: AsyncSession, source_id: int):
    """Mark all RUNNING sync runs for this source as FAILED."""
    from sqlalchemy import update as sa_update
    await db.execute(
        sa_update(DatabaseSyncRun)
        .where(DatabaseSyncRun.source_id == source_id, DatabaseSyncRun.status == SyncRunStatus.RUNNING)
        .values(
            status=SyncRunStatus.FAILED,
            error_message="同步超时，已自动标记为失败",
            finished_at=datetime.now(timezone.utc),
        )
    )


async def recover_stale_syncing_sources(db: AsyncSession):
    """Startup recovery: reset any sources stuck in SYNCING status."""
    result = await db.execute(
        select(DatabaseSource).where(DatabaseSource.status == DatabaseSourceStatus.SYNCING)
    )
    stale_sources = result.scalars().all()
    if not stale_sources:
        return
    for source in stale_sources:
        if await _is_sync_stale(db, source.id):
            logger.warning("启动恢复: source_id=%s 同步卡死，重置为 FAILED", source.id)
            source.status = DatabaseSourceStatus.FAILED
            source.last_error = "应用重启时检测到同步卡死，已自动重置"
            await _mark_stale_runs(db, source.id)
    await db.commit()


async def sync_database_source(db: AsyncSession, source_id: int):
    source = await get_database_source(db, source_id)
    if not source:
        raise ValueError("数据库源不存在")

    # ── concurrency guard with stale recovery ──
    current_status = source.status.value if hasattr(source.status, "value") else source.status
    if current_status == DatabaseSourceStatus.SYNCING.value:
        if not await _is_sync_stale(db, source_id):
            raise ValueError("该数据库源正在同步中")
        logger.warning("检测到 source_id=%s 同步卡死，强制重置", source_id)
        source.status = DatabaseSourceStatus.FAILED
        source.last_error = "同步超时，已自动重置"
        await _mark_stale_runs(db, source_id)
        await db.commit()

    kb_result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == source.kb_id))
    kb = kb_result.scalar_one_or_none()
    if not kb:
        raise ValueError("知识库不存在")
    if not kb.embedding_model_id:
        raise ValueError("知识库未配置 Embedding 模型")
    kb_id = source.kb_id

    # ── create sync run record ──
    run = DatabaseSyncRun(source_id=source_id, status=SyncRunStatus.RUNNING)
    db.add(run)
    source.status = DatabaseSourceStatus.SYNCING
    source.last_error = None
    await db.commit()
    await db.refresh(run)
    t_start = time.monotonic()

    new_doc_ids: list[int] = []
    old_doc_ids: list[int] = []
    tables_detail: list[dict] = []
    total_rows = 0
    total_chunks = 0
    failed_tables: list[str] = []

    async def _update_run_progress(detail_msg: str = ""):
        """Flush current progress to DB so frontend can poll it."""
        try:
            from sqlalchemy import update as sa_update
            await db.execute(
                sa_update(DatabaseSyncRun).where(DatabaseSyncRun.id == run.id).values(
                    table_count=len(tables_detail) + len(failed_tables),
                    row_count=total_rows,
                    chunk_count=total_chunks,
                    tables_detail=json.dumps(tables_detail, ensure_ascii=False),
                    error_message=detail_msg or None,
                )
            )
            await db.commit()
        except Exception:
            pass  # best-effort progress update

    try:
        # Update progress: reading tables
        await _update_run_progress("正在读取数据库表结构...")
        table_payloads = await asyncio.to_thread(_fetch_sync_payloads, source)
        await _update_run_progress(f"已读取 {len(table_payloads)} 张表，正在处理...")
        old_docs = await _list_database_source_documents(db, source.id, kb_id)

        strategy = getattr(kb, "chunk_strategy", "fixed") or "fixed"
        chunk_size = getattr(kb, "chunk_size", None)
        chunk_overlap = getattr(kb, "chunk_overlap", None)

        # Phase 1: Create all docs and chunks in DB (fast, no API calls)
        all_embed_tasks = []
        for payload in table_payloads:
            t_table = time.monotonic()
            table_name = payload["table_name"]
            try:
                text_content = payload["text"]
                doc = Document(
                    kb_id=kb_id,
                    filename=f"db_{source.name}_{table_name}.txt",
                    file_path=f"{_source_doc_prefix(source.id)}{table_name}",
                    file_size=len(text_content.encode("utf-8")),
                    file_type="database",
                    status=DocumentStatus.EMBEDDING,
                )
                db.add(doc)
                await db.flush()
                new_doc_ids.append(doc.id)

                chunks = split_text(text_content, strategy=strategy, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
                metadatas = []
                for idx, chunk_text in enumerate(chunks):
                    metadata = {
                        "source_type": "database",
                        "source_id": source.id,
                        "table_name": table_name,
                        "chunk_index": idx,
                    }
                    metadatas.append(metadata)
                    db.add(DocumentChunk(
                        doc_id=doc.id,
                        kb_id=kb_id,
                        content=chunk_text,
                        chunk_index=idx,
                        metadata_=json.dumps(metadata, ensure_ascii=False),
                    ))

                doc.chunk_count = len(chunks)
                total_rows += payload.get("row_count", 0)
                total_chunks += len(chunks)

                if kb.embedding_model_id and chunks:
                    all_embed_tasks.append({
                        "doc": doc, "chunks": chunks, "metadatas": metadatas,
                        "table_name": table_name, "row_count": payload.get("row_count", 0),
                        "t_table": t_table,
                    })
                else:
                    doc.status = DocumentStatus.COMPLETED
                    tables_detail.append({
                        "table": table_name, "status": "ok",
                        "rows": payload.get("row_count", 0), "chunks": len(chunks),
                        "seconds": round(time.monotonic() - t_table, 2),
                    })
            except Exception as table_exc:
                logger.warning("同步表 %s 失败: %s", table_name, table_exc)
                failed_tables.append(table_name)
                tables_detail.append({
                    "table": table_name, "status": "failed",
                    "error": str(table_exc)[:200],
                    "seconds": round(time.monotonic() - t_table, 2),
                })

        # Phase 2: Embed all tables concurrently (the slow part)
        if all_embed_tasks:
            await db.flush()

            async def _embed_one(task):
                try:
                    await embed_and_store(db, kb_id, kb.embedding_model_id, task["chunks"], task["doc"].id, metadatas=task["metadatas"])
                    task["doc"].status = DocumentStatus.COMPLETED
                    tables_detail.append({
                        "table": task["table_name"], "status": "ok",
                        "rows": task["row_count"], "chunks": len(task["chunks"]),
                        "seconds": round(time.monotonic() - task["t_table"], 2),
                    })
                except Exception as exc:
                    logger.warning("嵌入表 %s 失败: %s", task["table_name"], exc)
                    failed_tables.append(task["table_name"])
                    tables_detail.append({
                        "table": task["table_name"], "status": "failed",
                        "error": str(exc)[:200],
                        "seconds": round(time.monotonic() - task["t_table"], 2),
                    })
                # Update progress after each table
                done = len(tables_detail)
                total_tables = len(all_embed_tasks)
                await _update_run_progress(f"向量化进度: {done}/{total_tables} 张表")

            # Run up to 3 tables concurrently for embedding
            sem = asyncio.Semaphore(3)
            async def _embed_with_sem(task):
                async with sem:
                    await _embed_one(task)

            await asyncio.gather(*[_embed_with_sem(t) for t in all_embed_tasks])

        old_doc_ids = await _delete_database_documents_in_db(db, old_docs)

        duration = round(time.monotonic() - t_start, 2)
        if failed_tables and new_doc_ids:
            run_status = SyncRunStatus.PARTIAL
            src_status = DatabaseSourceStatus.COMPLETED
        elif failed_tables and not new_doc_ids:
            run_status = SyncRunStatus.FAILED
            src_status = DatabaseSourceStatus.FAILED
        else:
            run_status = SyncRunStatus.COMPLETED
            src_status = DatabaseSourceStatus.COMPLETED

        run.status = run_status
        run.table_count = len(table_payloads)
        run.row_count = total_rows
        run.chunk_count = total_chunks
        run.duration_seconds = duration
        run.tables_detail = json.dumps(tables_detail, ensure_ascii=False)
        run.finished_at = datetime.now(timezone.utc)
        if failed_tables:
            run.error_message = f"失败的表: {', '.join(failed_tables)}"

        source.status = src_status
        source.last_synced_at = datetime.now(timezone.utc)
        source.last_error = run.error_message
        await db.commit()
        if old_doc_ids:
            _delete_database_document_vectors(kb_id, old_doc_ids)
        _invalidate_retrieval_cache(kb_id)
        await _refresh_kb_counts(db, kb_id)
    except Exception as exc:
        await db.rollback()
        if new_doc_ids:
            _delete_database_document_vectors(kb_id, new_doc_ids)
        duration = round(time.monotonic() - t_start, 2)
        # Update the ORIGINAL run record (already committed as RUNNING) to FAILED
        from sqlalchemy import update as sa_update
        await db.execute(
            sa_update(DatabaseSyncRun)
            .where(DatabaseSyncRun.id == run.id)
            .values(
                status=SyncRunStatus.FAILED,
                table_count=len(tables_detail),
                row_count=total_rows,
                chunk_count=total_chunks,
                duration_seconds=duration,
                tables_detail=json.dumps(tables_detail, ensure_ascii=False) if tables_detail else None,
                error_message=str(exc)[:500],
                finished_at=datetime.now(timezone.utc),
            )
        )
        source = await get_database_source(db, source_id)
        if source:
            source.status = DatabaseSourceStatus.FAILED
            source.last_error = str(exc)[:500]
        await db.commit()
        await _refresh_kb_counts(db, kb_id)
        raise
