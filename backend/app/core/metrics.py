"""Prometheus metrics for the RAG platform.

Exposes:
- Default HTTP request metrics via prometheus-fastapi-instrumentator
- Custom metrics for LLM calls, token consumption, and retrieval quality
"""
import logging

logger = logging.getLogger(__name__)

try:
    from prometheus_client import Counter, Histogram, Gauge

    llm_call_latency = Histogram(
        "rag_llm_call_latency_seconds",
        "LLM call latency in seconds",
        ["model_name", "chat_mode"],
        buckets=(0.5, 1, 2, 5, 10, 30, 60, 120, 300),
    )

    llm_input_tokens_total = Counter(
        "rag_llm_input_tokens_total",
        "Total input tokens sent to LLM",
        ["model_name"],
    )

    llm_output_tokens_total = Counter(
        "rag_llm_output_tokens_total",
        "Total output tokens received from LLM",
        ["model_name"],
    )

    retrieval_hit_count = Counter(
        "rag_retrieval_hit_total",
        "Total retrieval calls that returned results",
        ["search_mode"],
    )

    retrieval_miss_count = Counter(
        "rag_retrieval_miss_total",
        "Total retrieval calls that returned no results",
        ["search_mode"],
    )

    retrieval_top_score = Histogram(
        "rag_retrieval_top_score",
        "Top retrieval result score",
        buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
    )

    active_conversations = Gauge(
        "rag_active_conversations",
        "Number of active streaming conversations",
    )

    METRICS_AVAILABLE = True

except ImportError:
    METRICS_AVAILABLE = False
    logger.info("prometheus_client not installed — metrics disabled")

    # Provide no-op stubs so callers don't need to check METRICS_AVAILABLE
    class _NoOp:
        def labels(self, *a, **kw):
            return self
        def observe(self, *a, **kw): pass
        def inc(self, *a, **kw): pass
        def dec(self, *a, **kw): pass

    llm_call_latency = _NoOp()
    llm_input_tokens_total = _NoOp()
    llm_output_tokens_total = _NoOp()
    retrieval_hit_count = _NoOp()
    retrieval_miss_count = _NoOp()
    retrieval_top_score = _NoOp()
    active_conversations = _NoOp()


def setup_instrumentator(app):
    """Attach prometheus-fastapi-instrumentator to the FastAPI app."""
    if not METRICS_AVAILABLE:
        return
    try:
        from prometheus_fastapi_instrumentator import Instrumentator
        Instrumentator(
            should_group_status_codes=True,
            should_ignore_untemplated=True,
            excluded_handlers=["/api/health", "/api/metrics"],
        ).instrument(app).expose(app, endpoint="/api/metrics", include_in_schema=False)
        logger.info("Prometheus metrics endpoint: /api/metrics")
    except ImportError:
        logger.info("prometheus-fastapi-instrumentator not installed — HTTP metrics disabled")
