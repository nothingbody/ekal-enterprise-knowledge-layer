from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class WebSourceCreate(BaseModel):
    kb_id: int
    url: str = Field(min_length=1, max_length=2000)
    source_type: Literal["html", "json", "rss", "sitemap"] = "html"
    crawl_interval_hours: Optional[int] = Field(default=None, ge=1, le=8760)
    auto_reindex: bool = True
    use_browser: bool = False


class WebSourceScheduleUpdate(BaseModel):
    crawl_interval_hours: Optional[int] = Field(default=None, ge=1, le=8760)
    auto_reindex: Optional[bool] = None


class WebSourceResponse(BaseModel):
    id: int
    url: str
    source_type: str = "html"
    title: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    crawl_interval_hours: Optional[int] = None
    last_crawled_at: Optional[str] = None
    content_hash: Optional[str] = None
    auto_reindex: bool = True
    next_crawl_at: Optional[str] = None
    crawl_count: int = 0
    use_browser: bool = False
