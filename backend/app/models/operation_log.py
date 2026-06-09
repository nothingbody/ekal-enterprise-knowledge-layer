import asyncio

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Float
from sqlalchemy.sql import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Base


class OperationLog(Base):
    __tablename__ = "operation_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action = Column(String(100), nullable=False)
    resource_type = Column(String(50), nullable=True)
    resource_id = Column(Integer, nullable=True)
    detail = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    latency_ms = Column(Float, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


def add_log_and_sync(db: AsyncSession, **kwargs) -> OperationLog:
    """Create an OperationLog and schedule an immediate cloud sync.

    Usage: ``add_log_and_sync(db, user_id=1, action="create_kb", ...)``
    The caller must still ``await db.commit()`` after this call.
    """
    log = OperationLog(**kwargs)
    db.add(log)
    try:
        from app.cloud.sync import trigger_operation_log_sync
        asyncio.ensure_future(trigger_operation_log_sync())
    except Exception:
        pass
    return log
