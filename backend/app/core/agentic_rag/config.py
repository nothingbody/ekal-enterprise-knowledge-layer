"""Agentic RAG configuration model.

Supports three-level resolution: global settings -> per-KB config -> per-request overrides.
All features default to disabled for full backward compatibility.
"""
from pydantic import BaseModel, Field


class AgenticRAGConfig(BaseModel):
    """Per-request or per-KB agentic RAG configuration."""

    # Self-RAG: decide whether retrieval is needed at all
    enable_adaptive_retrieval: bool = False
    # Corrective RAG: evaluate retrieval quality post-search
    enable_retrieval_evaluation: bool = False
    # Modular RAG: classify query complexity and adjust pipeline
    enable_dynamic_pipeline: bool = False
    # FAIR-RAG: iterative answer refinement loop
    enable_iterative_refinement: bool = False

    # CRAG: minimum relevance score for retrieved docs
    relevance_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    # Max refinement loop iterations
    max_refinement_iterations: int = Field(default=2, ge=1, le=5)
    # Complexity classification method: "rule" (0ms) or "llm" (500-1500ms)
    complexity_method: str = Field(default="rule", pattern="^(rule|llm)$")
    # Query planning: decompose very_complex queries into sub-task DAGs
    enable_query_planning: bool = False
    # Trajectory recording: capture decision trajectory for analysis
    enable_trajectory_recording: bool = False

    def has_any_enabled(self) -> bool:
        """Return True if any agentic RAG feature is turned on."""
        return (
            self.enable_adaptive_retrieval
            or self.enable_retrieval_evaluation
            or self.enable_dynamic_pipeline
            or self.enable_iterative_refinement
            or self.enable_query_planning
        )
