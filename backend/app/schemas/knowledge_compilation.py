"""Pydantic schemas for Knowledge Compilation API."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Compiled Article schemas
# ---------------------------------------------------------------------------

class CompiledArticleResponse(BaseModel):
    id: int
    kb_id: int
    title: str
    content: str
    summary: Optional[str] = None
    tags: Optional[List[str]] = None
    source_doc_ids: Optional[List[int]] = None
    version: int = 1
    status: str = "compiled"
    token_count: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ArticleUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=500)
    content: Optional[str] = None
    summary: Optional[str] = None
    tags: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# Health Report schemas
# ---------------------------------------------------------------------------

class HealthFinding(BaseModel):
    type: str  # contradiction, outdated, gap, redundancy
    severity: str  # high, medium, low
    description: str
    affected_doc_ids: Optional[List[int]] = None
    affected_article_ids: Optional[List[int]] = None
    suggested_action: Optional[str] = None


class HealthReportResponse(BaseModel):
    id: int
    kb_id: int
    status: str
    summary: Optional[dict] = None
    findings: Optional[List[HealthFinding]] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    token_cost: Optional[int] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Cross Reference schemas
# ---------------------------------------------------------------------------

class ArticleCrossRefResponse(BaseModel):
    id: int
    from_article_id: int
    from_article_title: Optional[str] = None
    to_article_id: int
    to_article_title: Optional[str] = None
    relationship_type: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Compilation Config schemas
# ---------------------------------------------------------------------------

class CompilationConfigRequest(BaseModel):
    enabled: bool = False
    auto_compile_on_ingest: bool = True
    compilation_model_id: Optional[int] = None
    max_tokens_per_article: int = Field(default=4000, ge=500, le=32000)
    max_chunks_per_group: int = Field(default=12, ge=3, le=30)
    health_check_enabled: bool = False
    health_check_interval_hours: int = Field(default=168, ge=1, le=720)
    incremental_synthesis: bool = True
    synthesis_similarity_threshold: float = Field(default=0.65, ge=0.0, le=1.0)


class CompilationConfigResponse(BaseModel):
    enabled: bool = False
    auto_compile_on_ingest: bool = True
    compilation_model_id: Optional[int] = None
    max_tokens_per_article: int = 4000
    max_chunks_per_group: int = 12
    health_check_enabled: bool = False
    health_check_interval_hours: int = 168
    incremental_synthesis: bool = True
    synthesis_similarity_threshold: float = 0.65


# ---------------------------------------------------------------------------
# Compilation Status
# ---------------------------------------------------------------------------

class CompilationStatusResponse(BaseModel):
    enabled: bool
    total_articles: int
    compiled_articles: int
    outdated_articles: int
    drafting_articles: int
    last_compiled_at: Optional[datetime] = None
    last_health_check_at: Optional[datetime] = None
    health_score: Optional[float] = None
