from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Enum as SAEnum, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.database import Base


class WebSourceStatus(str, enum.Enum):
    PENDING = "pending"
    CRAWLING = "crawling"
    COMPLETED = "completed"
    FAILED = "failed"


class WebSourceType(str, enum.Enum):
    HTML = "html"
    JSON = "json"
    RSS = "rss"
    SITEMAP = "sitemap"


class WebSource(Base):
    __tablename__ = "web_sources"

    id = Column(Integer, primary_key=True, index=True)
    kb_id = Column(Integer, ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    url = Column(String(2000), nullable=False)
    source_type = Column(String(20), default=WebSourceType.HTML.value, nullable=False, server_default=WebSourceType.HTML.value)
    title = Column(String(500), nullable=True)
    content = Column(Text, nullable=True)
    status = Column(SAEnum(WebSourceStatus), default=WebSourceStatus.PENDING)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    crawl_interval_hours = Column(Integer, nullable=True, default=None)
    last_crawled_at = Column(DateTime(timezone=True), nullable=True)
    content_hash = Column(String(64), nullable=True)
    auto_reindex = Column(Boolean, default=True, nullable=False, server_default="1")
    next_crawl_at = Column(DateTime(timezone=True), nullable=True)
    crawl_count = Column(Integer, default=0, nullable=False, server_default="0")
    use_browser = Column(Boolean, default=False, nullable=False, server_default="0")

    knowledge_base = relationship("KnowledgeBase")
