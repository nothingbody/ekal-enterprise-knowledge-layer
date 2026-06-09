import logging
import os
import secrets
from pathlib import Path

from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).parent.parent
_ENV_FILE = BASE_DIR / ".env"

_logger = logging.getLogger(__name__)

_KEY_FILE = BASE_DIR / "data" / ".secret_key"


def _write_key_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _ensure_secret_key() -> None:
    """Auto-generate SECRET_KEY if not set, with keyfile persistence."""
    explicit = os.environ.get("SECRET_KEY", "").strip()
    if explicit:
        return

    if _KEY_FILE.exists():
        os.environ["SECRET_KEY"] = _KEY_FILE.read_text(encoding="utf-8").strip()
        return

    key = secrets.token_urlsafe(64)
    try:
        _write_key_file(_KEY_FILE, key)
    except OSError as exc:
        _logger.warning("Could not persist generated SECRET_KEY to %s: %s", _KEY_FILE, exc)
    os.environ["SECRET_KEY"] = key


_ensure_secret_key()


class Settings(BaseSettings):
    APP_NAME: str = "知枢中心服务"
    DEBUG: bool = False

    POSTGRES_PASSWORD: str = ""
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/rag_central.db"
    REDIS_URL: str = "redis://localhost:6379/0"
    TOKEN_BLACKLIST_STRICT: bool = True

    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24h
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    CORS_ORIGINS: str = "http://localhost:5173"

    ALLOW_REGISTRATION: bool = True
    INVITE_CODE: str = ""

    ADMIN_EMAIL: str = "admin@example.com"
    ADMIN_PASSWORD: str = ""
    ADMIN_PORT: int = 80
    WEB_WORKERS: int = 2
    REMOTE_RELAY_ENABLED: bool = True
    RELAY_MAX_CONCURRENT_PER_HOST: int = 4

    UPLOAD_DIR: str = str(BASE_DIR / "uploads")
    MAX_SKILL_PACKAGE_MB: int = 50

    class Config:
        env_file = str(_ENV_FILE)
        env_file_encoding = "utf-8"


settings = Settings()
