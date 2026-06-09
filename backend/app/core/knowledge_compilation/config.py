"""Configuration model for Knowledge Compilation feature."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class KnowledgeCompilationConfig(BaseModel):
    """Per-KB configuration for knowledge compilation.

    Follows the same pattern as AgenticRAGConfig — stored as a JSON blob
    in KnowledgeBase.knowledge_compilation_config.
    """

    # --- Master switch ---
    enabled: bool = False

    # --- Compilation settings ---
    auto_compile_on_ingest: bool = Field(
        default=True,
        description="Automatically compile chunks into articles after document ingestion",
    )
    compilation_model_id: Optional[int] = Field(
        default=None,
        description="LLM model to use for compilation; None = KB owner's default",
    )
    max_tokens_per_article: int = Field(
        default=4000, ge=500, le=32000,
        description="Max token budget for a single compiled article",
    )
    max_chunks_per_group: int = Field(
        default=12, ge=3, le=30,
        description="Max chunks to feed into one compilation call",
    )

    # --- Health check settings ---
    health_check_enabled: bool = False
    health_check_interval_hours: int = Field(
        default=168, ge=1, le=720,
        description="Hours between scheduled health checks (default: weekly)",
    )
    last_health_check_at: Optional[datetime] = None

    # --- Incremental synthesis settings ---
    incremental_synthesis: bool = Field(
        default=True,
        description="Update existing articles when new related documents are added",
    )
    synthesis_similarity_threshold: float = Field(
        default=0.65, ge=0.0, le=1.0,
        description="Min similarity score to consider an article related to new chunks",
    )

    def has_any_enabled(self) -> bool:
        """Return True if the master compilation switch is on."""
        return self.enabled

    @classmethod
    def from_json(cls, raw: Optional[str]) -> Optional["KnowledgeCompilationConfig"]:
        """Parse from a JSON string (as stored in the DB column).

        Returns None if *raw* is empty/null or if compilation is not enabled.
        """
        if not raw:
            return None
        try:
            data = json.loads(raw)
            cfg = cls(**data)
            return cfg if cfg.has_any_enabled() else None
        except Exception:
            return None

    def to_json(self) -> str:
        return self.model_dump_json()
