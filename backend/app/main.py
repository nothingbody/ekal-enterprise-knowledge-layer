import asyncio
import logging

from fastapi import FastAPI

from app.config import settings
from app._version import __version__
from app.bootstrap import app_lifespan, setup_metrics
from app.http_setup import configure_http
from app.app_routes import API_V1, register_api_routes, register_desktop_frontend, register_system_endpoints


logger = logging.getLogger("rag_platform")


app = FastAPI(
    title=settings.APP_NAME,
    version=__version__,
    lifespan=app_lifespan,
    docs_url="/api/docs" if settings.DEBUG else None,
    redoc_url="/api/redoc" if settings.DEBUG else None,
    openapi_url="/api/openapi.json" if settings.DEBUG else None,
)
setup_metrics(app)
configure_http(app)
limiter = app.state.limiter
register_api_routes(app)
register_system_endpoints(app)
register_desktop_frontend(app)
