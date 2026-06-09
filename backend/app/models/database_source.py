import enum

from sqlalchemy import Column, Float, Integer, String, DateTime, ForeignKey, Text, Enum as SAEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class DatabaseType(str, enum.Enum):
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    TRINO = "trino"


class DatabaseSourceStatus(str, enum.Enum):
    PENDING = "pending"
    SYNCING = "syncing"
    COMPLETED = "completed"
    FAILED = "failed"


class SyncRunStatus(str, enum.Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class DatabaseSource(Base):
    __tablename__ = "database_sources"

    id = Column(Integer, primary_key=True, index=True)
    kb_id = Column(Integer, ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    db_type = Column(SAEnum(DatabaseType), nullable=False)
    host = Column(String(255), nullable=True)
    port = Column(Integer, nullable=True)
    database_name = Column(String(255), nullable=True)
    schema_name = Column(String(255), nullable=True)
    username = Column(String(255), nullable=True)
    password_encrypted = Column(Text, nullable=True)
    table_names = Column(Text, nullable=True)
    column_filter = Column(Text, nullable=True)  # JSON: {"table_name": ["col1", "col2"]}
    row_limit = Column(Integer, default=200)
    status = Column(SAEnum(DatabaseSourceStatus), default=DatabaseSourceStatus.PENDING)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    knowledge_base = relationship("KnowledgeBase", back_populates="database_sources")
    sync_runs = relationship("DatabaseSyncRun", back_populates="source", cascade="all, delete-orphan", lazy="dynamic")


class DatabaseSyncRun(Base):
    __tablename__ = "database_sync_runs"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("database_sources.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(SAEnum(SyncRunStatus), default=SyncRunStatus.RUNNING, nullable=False)
    table_count = Column(Integer, default=0)
    row_count = Column(Integer, default=0)
    chunk_count = Column(Integer, default=0)
    duration_seconds = Column(Float, nullable=True)
    tables_detail = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)

    source = relationship("DatabaseSource", back_populates="sync_runs")
