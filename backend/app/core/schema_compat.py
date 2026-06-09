"""
SQLite schema compatibility layer.

When the application starts with an existing rag.db that was created by an
older version, newly added columns will be missing.  This module inspects the
live schema and issues ALTER TABLE … ADD COLUMN for any gaps so that the ORM
doesn't crash on missing columns.

Only invoked when the database engine is SQLite.
"""
import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

# (table, column, column_definition)
_COMPAT_COLUMNS: list[tuple[str, str, str]] = [
    ("users", "must_change_password", "BOOLEAN DEFAULT 0"),
    ("users", "cloud_user_id", "INTEGER"),
    ("users", "totp_secret", "VARCHAR(200)"),
    ("users", "totp_enabled", "BOOLEAN DEFAULT 0"),
    ("users", "last_login_ip", "VARCHAR(45)"),
    ("users", "last_login_at", "DATETIME"),
    ("knowledge_bases", "deleted_at", "DATETIME"),
    ("documents", "deleted_at", "DATETIME"),
    ("published_apps", "api_key_hash", "VARCHAR(64)"),
    ("published_apps", "default_chat_mode", "VARCHAR(32) DEFAULT 'auto'"),
    ("published_apps", "daily_limit", "INTEGER DEFAULT 100"),
    ("api_keys", "key_hash", "VARCHAR(64)"),
    ("api_keys", "key_preview", "VARCHAR(20)"),
    ("channels", "workspace_id", "INTEGER REFERENCES workspaces(id) ON DELETE SET NULL"),
    # Token usage tracking (step 4)
    ("chat_conversations", "total_input_tokens", "INTEGER DEFAULT 0"),
    ("chat_conversations", "total_output_tokens", "INTEGER DEFAULT 0"),
    # Context compaction (step 5)
    ("chat_messages", "msg_type", "VARCHAR(20) DEFAULT 'chat'"),
    # Model failover (step 6)
    ("model_configs", "fallback_model_ids", "TEXT"),
    # Context engine summary (pluggable ContextEngine)
    ("chat_conversations", "context_summary", "TEXT"),
    # Document file automation
    ("documents", "auto_tags", "TEXT"),
    ("documents", "content_hash", "VARCHAR(64)"),
    ("documents", "expires_at", "DATETIME"),
    ("documents", "is_archived", "BOOLEAN DEFAULT 0"),
    # Web source crawl scheduling
    ("web_sources", "crawl_interval_hours", "INTEGER"),
    ("web_sources", "last_crawled_at", "DATETIME"),
    ("web_sources", "content_hash", "VARCHAR(64)"),
    ("web_sources", "auto_reindex", "BOOLEAN DEFAULT 1"),
    ("web_sources", "next_crawl_at", "DATETIME"),
    ("web_sources", "crawl_count", "INTEGER DEFAULT 0"),
    ("web_sources", "use_browser", "BOOLEAN DEFAULT 0"),
    ("web_sources", "source_type", "VARCHAR(20) DEFAULT 'html'"),
    # Memory enhancements
    ("user_memories", "importance", "FLOAT DEFAULT 1.0"),
    ("user_memories", "access_count", "INTEGER DEFAULT 0"),
    ("user_memories", "last_accessed_at", "DATETIME"),
    ("user_memories", "expires_at", "DATETIME"),
    ("user_memories", "memory_type", "VARCHAR(20) DEFAULT 'persistent'"),
    ("skill_chains", "updated_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
    # Knowledge base prompt template binding
    ("knowledge_bases", "prompt_template_id", "INTEGER REFERENCES prompt_templates(id) ON DELETE SET NULL"),
    # Knowledge compilation (Karpathy LLM Wiki integration)
    ("knowledge_bases", "knowledge_compilation_config", "TEXT"),
]

# Tables that might not exist at all in older databases
_COMPAT_TABLES: dict[str, str] = {
    "user_quotas": """
        CREATE TABLE IF NOT EXISTS user_quotas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            plan VARCHAR(30) DEFAULT 'trial' NOT NULL,
            trial_total INTEGER DEFAULT 50 NOT NULL,
            trial_used INTEGER DEFAULT 0 NOT NULL,
            token_credit BIGINT DEFAULT 0 NOT NULL,
            token_used BIGINT DEFAULT 0 NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """,
    "usage_logs": """
        CREATE TABLE IF NOT EXISTS usage_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            conversation_id INTEGER,
            model_name VARCHAR(200),
            input_tokens INTEGER DEFAULT 0 NOT NULL,
            output_tokens INTEGER DEFAULT 0 NOT NULL,
            total_tokens INTEGER DEFAULT 0 NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """,
    "prompt_templates": """
        CREATE TABLE IF NOT EXISTS prompt_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            name VARCHAR(200) NOT NULL,
            description TEXT,
            content TEXT NOT NULL,
            category VARCHAR(50) DEFAULT 'custom',
            is_builtin BOOLEAN DEFAULT 0 NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """,
    "workspace_invitations": """
        CREATE TABLE IF NOT EXISTS workspace_invitations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            invite_token VARCHAR(64) UNIQUE NOT NULL,
            role VARCHAR(16) DEFAULT 'member' NOT NULL,
            created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            expires_at DATETIME,
            max_uses INTEGER,
            use_count INTEGER DEFAULT 0 NOT NULL,
            is_active BOOLEAN DEFAULT 1 NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """,
    "workspace_model_configs": """
        CREATE TABLE IF NOT EXISTS workspace_model_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            model_config_id INTEGER NOT NULL REFERENCES model_configs(id) ON DELETE CASCADE,
            shared_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """,
    "database_sync_runs": """
        CREATE TABLE IF NOT EXISTS database_sync_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER NOT NULL REFERENCES database_sources(id) ON DELETE CASCADE,
            status VARCHAR(20) NOT NULL DEFAULT 'running',
            table_count INTEGER DEFAULT 0,
            row_count INTEGER DEFAULT 0,
            chunk_count INTEGER DEFAULT 0,
            duration_seconds FLOAT,
            tables_detail TEXT,
            error_message TEXT,
            started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            finished_at DATETIME
        )
    """,
    "user_memories": """
        CREATE TABLE IF NOT EXISTS user_memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            content TEXT NOT NULL,
            category VARCHAR(32) DEFAULT 'general',
            source VARCHAR(100),
            embedding TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """,
    "channel_sessions": """
        CREATE TABLE IF NOT EXISTS channel_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            sender_id VARCHAR(256) NOT NULL,
            conversation_id INTEGER REFERENCES chat_conversations(id) ON DELETE SET NULL,
            last_active_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            idle_timeout_minutes INTEGER DEFAULT 1440 NOT NULL,
            is_expired BOOLEAN DEFAULT 0 NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(channel_id, sender_id)
        )
    """,
    "channel_schedules": """
        CREATE TABLE IF NOT EXISTS channel_schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            cron_expr VARCHAR(64) NOT NULL,
            prompt TEXT NOT NULL,
            target_sender_id VARCHAR(256),
            is_active BOOLEAN DEFAULT 1 NOT NULL,
            last_run_at DATETIME,
            next_run_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """,
    "skills": """
        CREATE TABLE IF NOT EXISTS skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(100) NOT NULL,
            slug VARCHAR(100) UNIQUE NOT NULL,
            description TEXT DEFAULT '',
            icon_url VARCHAR(512),
            category VARCHAR(50) DEFAULT 'general',
            skill_type VARCHAR(16) NOT NULL DEFAULT 'builtin',
            config TEXT,
            is_public BOOLEAN DEFAULT 0 NOT NULL,
            author_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            install_count INTEGER DEFAULT 0 NOT NULL,
            version VARCHAR(32) DEFAULT '1.0.0',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """,
    "skill_installs": """
        CREATE TABLE IF NOT EXISTS skill_installs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            skill_id INTEGER NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
            workspace_id INTEGER REFERENCES workspaces(id) ON DELETE SET NULL,
            is_active BOOLEAN DEFAULT 1 NOT NULL,
            config_override TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, skill_id, workspace_id)
        )
    """,
    "mcp_server_configs": """
        CREATE TABLE IF NOT EXISTS mcp_server_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            workspace_id INTEGER REFERENCES workspaces(id) ON DELETE SET NULL,
            name VARCHAR(100) NOT NULL,
            transport_type VARCHAR(16) NOT NULL DEFAULT 'http',
            command VARCHAR(256),
            args TEXT,
            env TEXT,
            url VARCHAR(512),
            headers TEXT,
            tool_filter TEXT,
            is_active BOOLEAN DEFAULT 1 NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """,
    "user_profiles": """
        CREATE TABLE IF NOT EXISTS user_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            profile_summary TEXT,
            topics_of_interest TEXT,
            communication_style VARCHAR(50),
            expertise_areas TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """,
    "skill_chains": """
        CREATE TABLE IF NOT EXISTS skill_chains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name VARCHAR(200) NOT NULL,
            description TEXT,
            steps TEXT NOT NULL,
            is_public BOOLEAN DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """,
    "automation_tasks": """
        CREATE TABLE IF NOT EXISTS automation_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name VARCHAR(200) NOT NULL,
            description TEXT,
            task_type VARCHAR(30) NOT NULL,
            cron_expression VARCHAR(100),
            interval_minutes INTEGER,
            webhook_token VARCHAR(64) UNIQUE,
            event_trigger VARCHAR(100),
            config TEXT NOT NULL,
            is_active BOOLEAN DEFAULT 1 NOT NULL,
            last_run_at DATETIME,
            last_status VARCHAR(20),
            last_error TEXT,
            run_count INTEGER DEFAULT 0 NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """,
    "automation_logs": """
        CREATE TABLE IF NOT EXISTS automation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL REFERENCES automation_tasks(id) ON DELETE CASCADE,
            status VARCHAR(20) NOT NULL,
            output TEXT,
            error_message TEXT,
            duration_ms FLOAT,
            triggered_by VARCHAR(30),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """,
    "devices": """
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            device_id VARCHAR(100) UNIQUE NOT NULL,
            device_name VARCHAR(200),
            os_info VARCHAR(200),
            app_version VARCHAR(50),
            is_active BOOLEAN DEFAULT 1 NOT NULL,
            last_heartbeat DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """,
    "channels": """
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL,
            platform VARCHAR(32) NOT NULL,
            kb_id INTEGER REFERENCES knowledge_bases(id) ON DELETE SET NULL,
            llm_model_id INTEGER REFERENCES model_configs(id) ON DELETE SET NULL,
            chat_mode VARCHAR(16) DEFAULT 'auto',
            config TEXT DEFAULT '{}',
            is_active BOOLEAN DEFAULT 1,
            webhook_token VARCHAR(64) UNIQUE,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """,
    # --- Knowledge Compilation (Karpathy LLM Wiki) ---
    "compiled_articles": """
        CREATE TABLE IF NOT EXISTS compiled_articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kb_id INTEGER NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
            title VARCHAR(500) NOT NULL,
            content TEXT NOT NULL,
            summary TEXT,
            tags TEXT,
            source_doc_ids TEXT,
            source_chunk_ids TEXT,
            version INTEGER DEFAULT 1 NOT NULL,
            status VARCHAR(20) DEFAULT 'compiled' NOT NULL,
            token_count INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            deleted_at DATETIME
        )
    """,
    "article_cross_refs": """
        CREATE TABLE IF NOT EXISTS article_cross_refs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_article_id INTEGER NOT NULL REFERENCES compiled_articles(id) ON DELETE CASCADE,
            to_article_id INTEGER NOT NULL REFERENCES compiled_articles(id) ON DELETE CASCADE,
            relationship_type VARCHAR(50) NOT NULL DEFAULT 'related',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """,
    "health_reports": """
        CREATE TABLE IF NOT EXISTS health_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kb_id INTEGER NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
            status VARCHAR(20) DEFAULT 'running' NOT NULL,
            summary TEXT,
            findings TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME,
            token_cost INTEGER
        )
    """,
    # --- Graph RAG (Entity Triples) ---
    "entity_triples": """
        CREATE TABLE IF NOT EXISTS entity_triples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kb_id INTEGER NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
            doc_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL,
            subject VARCHAR(200) NOT NULL,
            predicate VARCHAR(100) NOT NULL,
            object VARCHAR(200) NOT NULL,
            subject_type VARCHAR(20) DEFAULT 'ENTITY' NOT NULL,
            object_type VARCHAR(20) DEFAULT 'ENTITY' NOT NULL,
            confidence FLOAT DEFAULT 0.8,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """,
    # --- Trajectory-aware RAG ---
    "rag_trajectories": """
        CREATE TABLE IF NOT EXISTS rag_trajectories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trajectory_id VARCHAR(64) UNIQUE NOT NULL,
            conversation_id INTEGER REFERENCES chat_conversations(id) ON DELETE CASCADE,
            message_id INTEGER REFERENCES chat_messages(id) ON DELETE SET NULL,
            kb_id INTEGER NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            original_query TEXT NOT NULL,
            outcome VARCHAR(20) NOT NULL,
            step_count INTEGER DEFAULT 0 NOT NULL,
            total_duration_ms FLOAT NOT NULL,
            config_snapshot TEXT,
            steps_json TEXT NOT NULL,
            reward_score FLOAT,
            user_feedback VARCHAR(20),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """,
}


def ensure_schema_compat(db_url: str) -> None:
    """Check and patch an existing SQLite database for missing columns/tables."""
    # Extract file path from SQLite URL
    # Formats: sqlite:///path  or  sqlite+aiosqlite:///path
    if ":///" not in db_url:
        return
    db_path = db_url.split("///", 1)[1]
    if not db_path or not Path(db_path).exists():
        return  # fresh database, create_all will handle everything

    logger.info("Running SQLite schema compatibility check on %s", db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    patched = 0

    try:
        # 1. Ensure missing tables
        for table_name, create_sql in _COMPAT_TABLES.items():
            cursor.execute(create_sql.strip())
            patched_table = cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            ).fetchone()
            if patched_table:
                logger.debug("Table %s: ok", table_name)

        # 2. Ensure missing columns
        for table, column, col_def in _COMPAT_COLUMNS:
            existing = {
                row[1]
                for row in cursor.execute(f"PRAGMA table_info({table})").fetchall()
            }
            if column not in existing:
                alter = f"ALTER TABLE {table} ADD COLUMN {column} {col_def}"
                cursor.execute(alter)
                logger.info("Added missing column: %s.%s", table, column)
                patched += 1
            else:
                logger.debug("Column %s.%s: ok", table, column)

        conn.commit()
    except Exception:
        logger.exception("Schema compatibility check failed")
        conn.rollback()
    finally:
        conn.close()

    if patched:
        logger.info("Schema compat: patched %d column(s)", patched)
    else:
        logger.info("Schema compat: no patches needed")
