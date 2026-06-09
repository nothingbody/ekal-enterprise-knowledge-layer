import logging
import time

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import settings
from app.core.exceptions import AppError
from app.core.tracing import RequestIDMiddleware, get_request_id, setup_request_id_logging


logger = logging.getLogger("rag_platform")


def _detect_limiter_storage() -> str:
    if settings.DESKTOP_MODE:
        return "memory://"
    try:
        import redis as redis_lib
        r = redis_lib.from_url(settings.REDIS_URL, socket_connect_timeout=0.5)
        r.ping()
        r.close()
        return settings.REDIS_URL
    except Exception:
        logger.warning("Redis 不可用，限流器回退到内存模式")
        return "memory://"


def register_rate_limiter(app: FastAPI) -> None:
    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"],
        storage_uri=_detect_limiter_storage(),
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


def register_cors(app: FastAPI) -> None:
    cors_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
    if settings.DESKTOP_MODE:
        cors_origins = ["*"]  # Allow LAN access for sharing
    elif "*" in cors_origins:
        if not settings.DEBUG:
            raise RuntimeError(
                "CORS_ORIGINS 不允许在生产环境使用通配符 '*'！"
                "请在 .env 中设置具体域名，例如: CORS_ORIGINS=https://your-domain.com"
            )
        logger.warning("⚠ CORS 配置为通配符 '*'，生产环境建议设置具体域名")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins if "*" not in cors_origins else ["*"],
        allow_origin_regex=r"^https?://(127\.0\.0\.1|localhost)(:\d+)?$" if settings.DESKTOP_MODE else None,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Requested-With", "Accept", "X-Request-ID"],
    )


def register_middlewares(app: FastAPI) -> None:
    # Add RequestID middleware (uses ContextVar for cross-async access)
    app.add_middleware(RequestIDMiddleware)

    @app.middleware("http")
    async def security_headers_middleware(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "img-src 'self' data: blob:; "
            "font-src 'self' data: https://fonts.gstatic.com; "
            "connect-src 'self'; "
            "frame-ancestors 'none'"
        )
        response.headers["Permissions-Policy"] = "camera=(), microphone=(self), geolocation=()"
        return response

    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        request_id = get_request_id() or "-"
        start = time.time()
        response = await call_next(request)
        duration = (time.time() - start) * 1000
        path = request.url.path
        if path.startswith("/api/health"):
            return response
        client_ip = request.client.host if request.client else "-"
        if response.status_code >= 400:
            logger.warning("[%s] %s %s %s → %s (%.0fms) ip=%s",
                           request_id, request.method, path,
                           request.query_params or "", response.status_code, duration, client_ip)
        elif request.method in ("POST", "PUT", "DELETE", "PATCH"):
            logger.info("[%s] %s %s → %s (%.0fms) ip=%s",
                        request_id, request.method, path, response.status_code, duration, client_ip)
        else:
            logger.debug("[%s] %s %s → %s (%.0fms)", request_id, request.method, path, response.status_code, duration)
        return response


def register_exception_handlers(app: FastAPI) -> None:
    async def app_error_handler(request: Request, exc: AppError):
        request_id = getattr(request.state, "request_id", None) or "-"
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "status": "error",
                "code": exc.code,
                "detail": exc.detail,
                "request_id": request_id,
            },
        )

    async def http_exception_handler(request: Request, exc: HTTPException):
        request_id = getattr(request.state, "request_id", None) or "-"
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "status": "error",
                "code": f"HTTP_{exc.status_code}",
                "detail": exc.detail,
                "request_id": request_id,
            },
        )

    async def global_exception_handler(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", None) or "-"
        logger.error("[%s] Unhandled error on %s %s: %s", request_id, request.method, request.url.path, exc, exc_info=True)
        if settings.DESKTOP_MODE:
            try:
                from app.database import async_session as _err_session
                from app.models.operation_log import add_log_and_sync
                async with _err_session() as db:
                    error_detail = f"{type(exc).__name__}: {str(exc)[:300]}"
                    add_log_and_sync(
                        db,
                        action="error",
                        resource_type="api",
                        detail=f"[{request.method} {request.url.path}] {error_detail}",
                    )
                    await db.commit()
            except Exception:
                pass
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "code": "INTERNAL_ERROR",
                "detail": "服务器内部错误，请稍后重试",
                "request_id": request_id,
            },
        )

    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, global_exception_handler)


def configure_http(app: FastAPI) -> None:
    register_rate_limiter(app)
    register_cors(app)
    register_middlewares(app)
    register_exception_handlers(app)
