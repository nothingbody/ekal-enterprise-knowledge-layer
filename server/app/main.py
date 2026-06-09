import logging

from fastapi import FastAPI

from app.config import settings
from app._version import __version__
from app.bootstrap import app_lifespan
from app.http_setup import configure_http
from app.app_routes import register_api_routes, register_health_endpoint


logger = logging.getLogger("central_server")


app = FastAPI(
    title=settings.APP_NAME,
    version=__version__,
    lifespan=app_lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url=None,
)
configure_http(app)
register_api_routes(app)
register_health_endpoint(app)
