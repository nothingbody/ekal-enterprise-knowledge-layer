import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.database import async_session
from app.models.user import User


logger = logging.getLogger("central_server")


def _error_response(status_code: int, detail: str, error_code: str = "ERROR") -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"status": "error", "code": error_code, "detail": detail},
    )


def register_rate_limiter(app: FastAPI) -> None:
    limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])
    app.state.limiter = limiter

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
        return _error_response(429, "请求过于频繁，请稍后再试", "RATE_LIMITED")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        detail = exc.detail
        if isinstance(detail, list):
            parts = []
            for d in detail:
                if isinstance(d, dict) and ("msg" in d or "message" in d):
                    parts.append(d.get("msg") or d.get("message", ""))
                else:
                    parts.append(str(d))
            detail = "；".join(parts) if parts else "请求参数错误"
        return _error_response(exc.status_code, str(detail), "HTTP_ERROR")

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        parts = []
        for err in exc.errors():
            loc = ".".join(str(x) for x in err.get("loc", []))
            msg = err.get("msg", str(err))
            parts.append(f"{loc}: {msg}" if loc else msg)
        detail = "；".join(parts) if parts else "请求参数校验失败"
        return _error_response(422, detail, "VALIDATION_ERROR")

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled error: %s %s", request.method, request.url.path)
        return _error_response(500, "服务器内部错误", "INTERNAL_ERROR")


def register_cors(app: FastAPI) -> None:
    origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept"],
    )


def register_audit_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def audit_middleware(request: Request, call_next):
        """Auto-log all write operations and login attempts to audit_logs."""
        response = await call_next(request)
        method = request.method
        path = request.url.path

        is_login = path.endswith("/auth/login") and method == "POST"
        is_write = method in ("POST", "PUT", "PATCH", "DELETE")
        if not is_write:
            return response
        skip_paths = ("/api/v1/health", "/docs", "/api/v1/devices/heartbeat", "/api/v1/stats/")
        if any(path.startswith(p) for p in skip_paths) or "/auth/refresh" in path:
            return response

        try:
            import jwt as pyjwt
            from app.core.audit import record_audit, parse_action_from_request

            user_id, username = None, None
            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                try:
                    payload = pyjwt.decode(
                        auth_header[7:], settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
                    )
                    user_id = int(payload.get("sub", 0)) or None
                except Exception:
                    pass
            if user_id:
                try:
                    async with async_session() as db:
                        from sqlalchemy import select as sa_select
                        row = (await db.execute(
                            sa_select(User.username).where(User.id == user_id)
                        )).scalar_one_or_none()
                        username = row
                except Exception:
                    pass

            action, resource_type, resource_id = parse_action_from_request(method, path)
            if is_login:
                action = "login_success" if response.status_code < 400 else "login_failed"
                resource_type = "auth"
            ip = request.headers.get("x-real-ip") or (request.client.host if request.client else None)
            ua = request.headers.get("user-agent", "")[:300]

            async with async_session() as db:
                await record_audit(
                    db,
                    user_id=user_id,
                    username=username,
                    action=action,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    ip_address=ip,
                    user_agent=ua,
                    status_code=response.status_code,
                )
        except Exception:
            logger.debug("Audit log write failed", exc_info=True)
        return response


def configure_http(app: FastAPI) -> None:
    register_rate_limiter(app)
    register_exception_handlers(app)
    register_cors(app)
    register_audit_middleware(app)
