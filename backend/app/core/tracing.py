"""
请求追踪中间件。

为每个请求生成或传递 Request-ID，用于分布式追踪和日志关联。
"""
import uuid
import logging
from contextvars import ContextVar
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# Context variable to store request ID across async boundaries
_request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)

# Header names for request ID propagation
REQUEST_ID_HEADER = "X-Request-ID"
TRACE_ID_HEADER = "X-Trace-ID"


def get_request_id() -> Optional[str]:
    """获取当前请求的 Request-ID。"""
    return _request_id_ctx.get()


def set_request_id(request_id: str) -> None:
    """设置当前请求的 Request-ID。"""
    _request_id_ctx.set(request_id)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Request-ID 中间件。

    - 从请求头 X-Request-ID 或 X-Trace-ID 读取现有 ID
    - 若无则生成新的 UUID
    - 将 ID 存入 ContextVar 供日志使用
    - 在响应头中返回 X-Request-ID
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Try to get existing request ID from headers
        request_id = (
            request.headers.get(REQUEST_ID_HEADER)
            or request.headers.get(TRACE_ID_HEADER)
            or uuid.uuid4().hex
        )

        # Store in context var
        token = _request_id_ctx.set(request_id)

        # Store in request state for easy access
        request.state.request_id = request_id

        try:
            response = await call_next(request)
            # Add request ID to response headers
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            # Reset context var
            _request_id_ctx.reset(token)


class RequestIDLogFilter(logging.Filter):
    """
    日志过滤器，自动添加 request_id 字段到日志记录。

    使用方式：
        handler.addFilter(RequestIDLogFilter())
        formatter = logging.Formatter(
            "%(asctime)s [%(request_id)s] %(levelname)s %(name)s: %(message)s"
        )
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        return True


def setup_request_id_logging() -> None:
    """
    配置根日志器使用 Request-ID。

    在应用启动时调用一次即可。
    """
    root_logger = logging.getLogger()

    # Add filter to all handlers
    filter_instance = RequestIDLogFilter()
    for handler in root_logger.handlers:
        handler.addFilter(filter_instance)

    logger.info("Request-ID logging configured")
