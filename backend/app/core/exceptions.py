"""Unified business exception hierarchy.

Service/domain layers should raise these instead of HTTPException,
keeping HTTP concerns out of business logic.
The global exception handler in main.py converts them to proper HTTP responses.
"""


class AppError(Exception):
    """Base application error."""
    status_code: int = 500
    code: str = "INTERNAL_ERROR"

    def __init__(self, detail: str = "内部服务错误", *, code: str | None = None):
        self.detail = detail
        if code:
            self.code = code
        super().__init__(detail)


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"

    def __init__(self, detail: str = "资源不存在"):
        super().__init__(detail)


class PermissionDeniedError(AppError):
    status_code = 403
    code = "PERMISSION_DENIED"

    def __init__(self, detail: str = "权限不足"):
        super().__init__(detail)


class ValidationError(AppError):
    status_code = 422
    code = "VALIDATION_ERROR"

    def __init__(self, detail: str = "请求参数无效"):
        super().__init__(detail)


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"

    def __init__(self, detail: str = "资源冲突"):
        super().__init__(detail)


class RateLimitError(AppError):
    status_code = 429
    code = "RATE_LIMIT"

    def __init__(self, detail: str = "请求过于频繁，请稍后再试"):
        super().__init__(detail)


class ExternalServiceError(AppError):
    status_code = 502
    code = "EXTERNAL_SERVICE_ERROR"

    def __init__(self, detail: str = "外部服务调用失败"):
        super().__init__(detail)
