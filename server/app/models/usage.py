from sqlalchemy import Column, Integer, String, DateTime, Date, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import Base


class UsageReport(Base):
    __tablename__ = "usage_reports"
    __table_args__ = (
        UniqueConstraint("user_id", "device_id", "report_date", name="uq_usage_report"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id = Column(String(100), nullable=True, index=True)
    report_date = Column(Date, nullable=False, index=True)
    token_count = Column(Integer, default=0)
    conversation_count = Column(Integer, default=0)
    message_count = Column(Integer, default=0)
    kb_count = Column(Integer, default=0)
    doc_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="usage_reports")
