import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional

import sqlparse
from sqlparse.sql import Statement
from sqlparse.tokens import Keyword, DML
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.llm_client import chat_completion
from app.models.database_source import DatabaseSource
from app.models.model_config import ModelConfig
from app.services.database_source_service import (
    _build_connection_url,
    _enum_value,
    _list_tables_sync,
    _parse_table_names,
    DatabaseType,
)

logger = logging.getLogger(__name__)

MAX_SQL_ROWS = 200
MAX_SQL_LENGTH = 4000
BLOCKED_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE",
    "CREATE", "REPLACE", "GRANT", "REVOKE", "EXEC", "EXECUTE",
    "MERGE", "CALL", "LOAD", "COPY", "OUTFILE", "DUMPFILE",
    "ATTACH", "DETACH", "PRAGMA", "RENAME", "VACUUM", "REINDEX",
    # INTO removed: INSERT INTO already blocked by INSERT; SELECT INTO OUTFILE blocked by OUTFILE
    # ANALYZE removed: EXPLAIN ANALYZE SELECT is a common read-only diagnostic
}

TEXT_TO_SQL_SYSTEM_PROMPT = """你是一个 SQL 专家。根据用户的自然语言问题和数据库表结构，生成正确的 SQL 查询语句。

规则：
1. 只生成 SELECT 查询，禁止任何修改数据的操作（INSERT/UPDATE/DELETE/DROP 等）
2. 查询结果最多返回 {max_rows} 行，请在 SQL 中加上 LIMIT
3. 使用标准 SQL 语法，兼容 {db_type} 数据库
4. 只输出一条 SQL 语句，不要包含注释或解释
5. 用 ```sql 和 ``` 包裹 SQL 语句

数据库类型：{db_type}
数据库表结构如下：

{schema_text}
"""

RESULT_SUMMARY_PROMPT = """你是一个数据分析助手。请根据用户的问题和 SQL 查询结果，用自然语言简洁地回答用户的问题。

用户问题：{question}

执行的 SQL：
```sql
{sql}
```

查询结果（JSON 格式）：
{results}

请直接回答问题，必要时可以用表格或列表展示数据。如果结果为空，请告知用户未找到匹配的数据。
"""


def _build_schema_text(tables: list[dict]) -> str:
    parts = []
    for tbl in tables:
        cols = ", ".join(f"{c['name']} ({c['type']})" for c in tbl["columns"])
        parts.append(f"  {tbl['kind'].upper()} {tbl['name']}: {cols}")
    return "\n".join(parts)


def _validate_sql_safety(sql: str) -> None:
    if len(sql) > MAX_SQL_LENGTH:
        raise ValueError(f"SQL 语句过长（最大 {MAX_SQL_LENGTH} 字符）")

    # Reject null bytes and other control characters that could confuse parsers
    if any(ord(c) < 0x09 for c in sql) or '\x00' in sql:
        raise ValueError("SQL 中包含非法控制字符")

    # Parse with sqlparse for AST-level validation
    parsed_statements = sqlparse.parse(sql)
    if not parsed_statements:
        raise ValueError("无法解析 SQL 语句")
    if len(parsed_statements) > 1:
        raise ValueError("不允许执行多条 SQL 语句")

    stmt: Statement = parsed_statements[0]
    stmt_type = stmt.get_type()
    if stmt_type and stmt_type.upper() not in ("SELECT", "UNKNOWN"):
        raise ValueError(f"只允许执行 SELECT 查询，检测到: {stmt_type}")

    # Recursively walk ALL tokens (including nested sub-statements / parenthesized groups)
    _walk_tokens_recursive(stmt)

    # Regex fallback: strip comments and re-check
    cleaned = re.sub(r'--[^\n]*', ' ', sql)
    cleaned = re.sub(r'/\*.*?\*/', ' ', cleaned, flags=re.DOTALL)
    # Normalize Unicode whitespace variants that could bypass token splitting
    cleaned = re.sub(r'[\u00a0\u2000-\u200b\u3000]', ' ', cleaned)
    cleaned = cleaned.strip().rstrip(";").strip()

    if ";" in cleaned:
        raise ValueError("不允许执行多条 SQL 语句")

    upper = cleaned.upper()
    if not upper.startswith("SELECT") and not upper.startswith("WITH"):
        raise ValueError("只允许执行 SELECT 查询")

    tokens_set = set(re.split(r'[\s(),.;]+', upper))
    found = tokens_set & BLOCKED_KEYWORDS
    if found:
        raise ValueError(f"SQL 中包含不允许的操作: {', '.join(found)}")

    # Detect SELECT ... INTO <table> (SQL Server DDL-via-SELECT) that is not OUTFILE/DUMPFILE
    if re.search(r'\bINTO\b\s+(?!OUTFILE|DUMPFILE|@)\w', upper):
        raise ValueError("SQL 中包含不允许的 INTO 写入操作")


def _walk_tokens_recursive(token_list) -> None:
    """Recursively walk sqlparse token tree and reject any dangerous DML/keywords."""
    for token in token_list.tokens:
        if token.is_group:
            _walk_tokens_recursive(token)
        else:
            val = token.value.upper().strip()
            if token.ttype in (DML,) and val not in ("SELECT",):
                raise ValueError(f"只允许 SELECT 操作，检测到: {token.value}")
            if token.ttype in (Keyword,) and val in BLOCKED_KEYWORDS:
                raise ValueError(f"SQL 中包含不允许的操作: {token.value}")


def _extract_sql_from_response(response: str) -> str:
    if "```sql" in response:
        start = response.index("```sql") + 6
        end = response.find("```", start)
        if end == -1:
            return response[start:].strip()
        return response[start:end].strip()
    if "```" in response:
        start = response.index("```") + 3
        end = response.find("```", start)
        if end == -1:
            return response[start:].strip()
        return response[start:end].strip()
    lines = [l.strip() for l in response.strip().splitlines() if l.strip()]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Engine pool cache — reuse engines across queries for the same source.
# Keyed by source.id, max 8 entries.  Disposed on eviction.
# ---------------------------------------------------------------------------
_engine_cache: Dict[int, Any] = {}
_ENGINE_CACHE_MAX = 8


def invalidate_engine_cache(source_id: int) -> None:
    """Evict a cached engine when source credentials/config change."""
    engine = _engine_cache.pop(source_id, None)
    if engine:
        try:
            engine.dispose()
        except Exception:
            pass


def _get_or_create_engine(source: DatabaseSource):
    from sqlalchemy import create_engine

    if source.id in _engine_cache:
        return _engine_cache[source.id]

    db_type = _enum_value(source.db_type) or "postgresql"
    connect_args: dict = {}
    if db_type == DatabaseType.POSTGRESQL.value:
        connect_args = {"connect_timeout": 10, "options": "-c statement_timeout=30000 -c default_transaction_read_only=on"}
    elif db_type == DatabaseType.MYSQL.value:
        connect_args = {"connect_timeout": 10, "read_timeout": 30, "write_timeout": 1}

    engine = create_engine(
        _build_connection_url(source),
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=3,
        pool_recycle=600,
        connect_args=connect_args,
    )

    # Evict oldest if cache is full
    if len(_engine_cache) >= _ENGINE_CACHE_MAX:
        oldest_key = next(iter(_engine_cache))
        old_engine = _engine_cache.pop(oldest_key, None)
        if old_engine:
            try:
                old_engine.dispose()
            except Exception:
                pass

    _engine_cache[source.id] = engine
    return engine


def _execute_readonly_sql(source: DatabaseSource, sql: str, max_rows: int = MAX_SQL_ROWS) -> Dict[str, Any]:
    db_type = _enum_value(source.db_type) or "postgresql"
    engine = _get_or_create_engine(source)

    with engine.connect() as conn:
        # Set read-only mode per database type
        readonly_set = False
        if db_type == DatabaseType.POSTGRESQL.value:
            try:
                conn.execute(text("SET TRANSACTION READ ONLY"))
                readonly_set = True
            except Exception as ro_err:
                # PostgreSQL: refuse to execute without readonly protection
                raise RuntimeError(
                    f"PostgreSQL 只读事务设置失败，拒绝执行查询以防止潜在写操作: {ro_err}"
                ) from ro_err
        elif db_type == DatabaseType.MYSQL.value:
            try:
                conn.execute(text("SET SESSION TRANSACTION READ ONLY"))
                readonly_set = True
            except Exception as ro_err:
                logger.warning("MySQL 只读事务设置失败: %s，依赖 SQL 安全校验防护", ro_err)

        if not readonly_set and db_type not in (DatabaseType.POSTGRESQL.value,):
            logger.warning("Text-to-SQL 未能启用只读模式，依赖 SQL 安全校验防护写操作")

        # Set query timeout to prevent hung connections (30 seconds)
        try:
            if db_type == DatabaseType.POSTGRESQL.value:
                conn.execute(text("SET statement_timeout = '30s'"))
            elif db_type == DatabaseType.MYSQL.value:
                conn.execute(text("SET max_execution_time = 30000"))
        except Exception:
            pass  # Best-effort timeout; SQL safety validation is the primary guard

        result = conn.execute(text(sql))
        columns = list(result.keys())
        rows = []
        for i, row in enumerate(result.mappings()):
            if i >= max_rows:
                break
            rows.append({k: _serialize_value(v) for k, v in row.items()})
        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": len(rows) >= max_rows,
        }


def _serialize_value(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (int, float, bool, str)):
        return v
    return str(v)


async def generate_sql(
    llm_config: ModelConfig,
    question: str,
    schema_text: str,
    db_type: str,
) -> str:
    system_prompt = TEXT_TO_SQL_SYSTEM_PROMPT.format(
        max_rows=MAX_SQL_ROWS,
        db_type=db_type,
        schema_text=schema_text,
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]
    response = await chat_completion(llm_config, messages, stream=False)
    sql = _extract_sql_from_response(response)
    if not sql:
        raise ValueError("LLM 未能生成有效的 SQL 语句")
    _validate_sql_safety(sql)
    return sql


async def summarize_sql_results(
    llm_config: ModelConfig,
    question: str,
    sql: str,
    results: Dict[str, Any],
) -> str:
    results_json = json.dumps(results["rows"][:50], ensure_ascii=False, default=str)
    prompt = RESULT_SUMMARY_PROMPT.format(
        question=question,
        sql=sql,
        results=results_json,
    )
    messages = [
        {"role": "system", "content": "你是一个数据分析助手，请用中文回答。"},
        {"role": "user", "content": prompt},
    ]
    response = await chat_completion(llm_config, messages, stream=False)
    return response


async def text_to_sql_query(
    db: AsyncSession,
    source: DatabaseSource,
    llm_config: ModelConfig,
    question: str,
    summarize: bool = True,
) -> Dict[str, Any]:
    tables = await asyncio.to_thread(_list_tables_sync, source)
    selected = set(_parse_table_names(source.table_names))
    if selected:
        tables = [t for t in tables if t["name"] in selected]
    if not tables:
        raise ValueError("该数据库源没有可用的表")

    schema_text = _build_schema_text(tables)
    db_type = _enum_value(source.db_type) or "postgresql"

    sql = await generate_sql(llm_config, question, schema_text, db_type)
    logger.info("Text-to-SQL generated: %s", sql)

    MAX_ATTEMPTS = 2
    last_error: Optional[Exception] = None

    for attempt in range(MAX_ATTEMPTS):
        try:
            results = await asyncio.to_thread(_execute_readonly_sql, source, sql)
            break
        except Exception as exc:
            last_error = exc
            if attempt < MAX_ATTEMPTS - 1:
                logger.warning(
                    "Text-to-SQL 第 %d 次执行失败，准备重试: %s", attempt + 1, exc,
                )
                # Sanitize error message: only pass error type and generic hint,
                # not raw details which could influence LLM to generate unsafe SQL
                _err_type = type(exc).__name__
                _err_hint = str(exc)[:100].replace("'", "").replace('"', "")
                retry_question = (
                    f"{question}\n\n"
                    f"上次生成的 SQL 执行失败（{_err_type}：{_err_hint}）。请修正 SQL。\n"
                    f"上次生成的 SQL：{sql}"
                )
                sql = await generate_sql(llm_config, retry_question, schema_text, db_type)
                _validate_sql_safety(sql)
                logger.info("Text-to-SQL retry generated (validated): %s", sql)
            else:
                logger.error("Text-to-SQL 重试后仍然失败: %s", exc)
                raise last_error

    answer = None
    if summarize:
        try:
            answer = await summarize_sql_results(llm_config, question, sql, results)
        except Exception as exc:
            logger.warning("SQL result summarization failed: %s", exc)
            answer = None

    return {
        "sql": sql,
        "results": results,
        "answer": answer,
    }
