"""Website content management — CMS-like model for managing public site pages."""

import enum

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Enum as SAEnum, UniqueConstraint
from sqlalchemy.sql import func

from app.models.base import Base


class ContentType(str, enum.Enum):
    ANNOUNCEMENT = "announcement"
    CHANGELOG = "changelog"
    FAQ = "faq"
    PAGE = "page"


class SiteContent(Base):
    __tablename__ = "site_contents"
    __table_args__ = (
        UniqueConstraint("content_type", "slug", name="uq_site_content_type_slug"),
    )

    id = Column(Integer, primary_key=True, index=True)
    content_type = Column(SAEnum(ContentType), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    slug = Column(String(100), nullable=True, index=True)
    body = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    sort_order = Column(Integer, default=0)
    is_published = Column(Boolean, default=True)
    version = Column(String(20), nullable=True)
    extra = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
