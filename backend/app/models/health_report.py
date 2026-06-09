from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.database import Base


class HealthReportStatus(str, enum.Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class HealthReport(Base):
    __tablename__ = "health_reports"

    id = Column(Integer, primary_key=True, index=True)
    kb_id = Column(Integer, ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(20), default=HealthReportStatus.RUNNING.value, nullable=False)
    summary = Column(Text, nullable=True)  # JSON: {score, contradiction_count, outdated_count, gap_count, redundancy_count}
    findings = Column(Text, nullable=True)  # JSON array of finding objects
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    token_cost = Column(Integer, nullable=True)

    knowledge_base = relationship("KnowledgeBase", back_populates="health_reports")
