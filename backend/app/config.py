import secrets

import os

from pydantic_settings import BaseSettings
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
_ENV_FILE = BASE_DIR / ".env"

_DESKTOP_DATA_DIR = os.environ.get("DESKTOP_DATA_DIR")
_IS_DESKTOP_RUNTIME = os.environ.get("DESKTOP_MODE", "").lower() in {"1", "true", "yes"} or bool(_DESKTOP_DATA_DIR)
_RUNTIME_DATA_DIR = Path(_DESKTOP_DATA_DIR) if _DESKTOP_DATA_DIR else BASE_DIR / "data"
_RUNTIME_UPLOAD_DIR = Path(
    os.environ.get(
        "UPLOAD_DIR",
        str((_RUNTIME_DATA_DIR.parent if _DESKTOP_DATA_DIR else BASE_DIR) / "uploads"),
    )
)


def _write_key_file(path: Path, content: str) -> None:
    """Write content to a key file with restrictive permissions (owner-only)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # Windows may not support Unix-style chmod


def _ensure_secret_key() -> None:
    """If .env has no SECRET_KEY, generate a strong random one and persist it.

    Also writes the key to a dedicated keyfile so it survives .env rewrites.
    If .env loses SECRET_KEY but the keyfile exists, restore from keyfile.
    """
    _KEY_FILE = _RUNTIME_DATA_DIR / ".secret_key"
    marker = "SECRET_KEY="

    _WEAK_KEYS = {
        "change-" + "this-to-a-random-secret-key-in-production",
        "your-secret-key-change-in-production",
        "secret", "password", "123456",
    }

    explicit_env_key = os.environ.get("SECRET_KEY", "").strip()
    if explicit_env_key:
        if explicit_env_key.lower() in _WEAK_KEYS or len(explicit_env_key) < 16:
            import logging as _log
            _logger = _log.getLogger(__name__)
            key = secrets.token_urlsafe(64)
            _write_key_file(_KEY_FILE, key)
            os.environ["SECRET_KEY"] = key
            _logger.warning(
                "检测到不安全的 SECRET_KEY，已自动替换为随机密钥。"
                "建议通过环境变量设置强密钥: "
                "python -c \"import secrets; print(secrets.token_urlsafe(64))\""
            )
            return
        if not _KEY_FILE.exists() or _KEY_FILE.read_text(encoding="utf-8").strip() != explicit_env_key:
            _write_key_file(_KEY_FILE, explicit_env_key)
        return

    if _IS_DESKTOP_RUNTIME:
        if _KEY_FILE.exists():
            os.environ["SECRET_KEY"] = _KEY_FILE.read_text(encoding="utf-8").strip()
            return
        key = secrets.token_urlsafe(64)
        _write_key_file(_KEY_FILE, key)
        os.environ["SECRET_KEY"] = key
        return

    # 1. Try reading existing key from .env
    env_key = None
    env_text = ""
    if _ENV_FILE.exists():
        env_text = _ENV_FILE.read_text(encoding="utf-8")
        for line in env_text.splitlines():
            if line.startswith(marker):
                env_key = line[len(marker):].strip()
                break

    # 2. Try reading backup keyfile
    backup_key = None
    if _KEY_FILE.exists():
        backup_key = _KEY_FILE.read_text(encoding="utf-8").strip()

    if env_key and backup_key and env_key != backup_key:
        # .env was changed — trust .env, update backup
        _write_key_file(_KEY_FILE, env_key)
        return

    if env_key:
        # .env has key, ensure backup exists
        if not backup_key:
            _write_key_file(_KEY_FILE, env_key)
        return

    if backup_key:
        # .env lost the key, restore from backup
        line = f"{marker}{backup_key}\n"
        with open(_ENV_FILE, "a", encoding="utf-8") as f:
            if env_text and not env_text.endswith("\n"):
                f.write("\n")
            f.write(line)
        return

    # 3. No key anywhere — generate a new one and save to both locations
    key = secrets.token_urlsafe(64)
    line = f"{marker}{key}\n"
    with open(_ENV_FILE, "a", encoding="utf-8") as f:
        if env_text and not env_text.endswith("\n"):
            f.write("\n")
        f.write(line)
    _write_key_file(_KEY_FILE, key)


_ensure_secret_key()


class Settings(BaseSettings):
    APP_NAME: str = "RAG应用平台"
    DEBUG: bool = False
    DESKTOP_MODE: bool = False
    DESKTOP_SEED_DEMO_DATA: bool = _IS_DESKTOP_RUNTIME
    DESKTOP_DEMO_TARGET_USERS: str = "15996983380"

    DATABASE_URL: str = f"sqlite+aiosqlite:///{(_RUNTIME_DATA_DIR / 'rag.db').as_posix()}"

    REDIS_URL: str = "redis://localhost:6379/0"
    TOKEN_BLACKLIST_STRICT: bool = not _IS_DESKTOP_RUNTIME
    BACKEND_PORT: int = 0

    VECTOR_STORE_TYPE: str = "chroma"  # "chroma" or "pgvector"

    CHROMA_MODE: str = "embedded"
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8100
    CHROMA_DATA_DIR: str = str(_RUNTIME_DATA_DIR / "chroma")

    SECRET_KEY: str = "REPLACE_WITH_RANDOM_SECRET_KEY"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440 if os.environ.get("DESKTOP_MODE", "").lower() == "true" else 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    UPLOAD_DIR: str = str(_RUNTIME_UPLOAD_DIR)
    MAX_UPLOAD_SIZE_MB: int = 100

    DEFAULT_CHUNK_SIZE: int = 500
    DEFAULT_CHUNK_OVERLAP: int = 50
    DEFAULT_TOP_K: int = 5

    MAX_HISTORY_TOKENS: int = 4000

    DB_STARTUP_MAX_RETRIES: int = 10
    DB_STARTUP_RETRY_SECONDS: float = 2.0

    CORS_ORIGINS: str = "http://localhost:3000"
    RATE_LIMIT_PER_MINUTE: int = 60
    LOG_LEVEL: str = "INFO"

    ALLOW_REGISTRATION: bool = True
    INVITE_CODE: str = ""

    CONTEXT_ENGINE: str = "sliding_window"  # sliding_window | semantic_summary | full_context

    VECTOR_SEARCH_WEIGHT: float = 0.7

    WEB_SEARCH_PROVIDER: str = "duckduckgo"  # duckduckgo (default, no key)
    TAVILY_API_KEY: str = ""  # optional: Tavily search API key for better results

    # ── OCR (LLM 多模态视觉识别) ──
    OCR_MODEL_ID: int = 0        # 指定 OCR 用的 LLM model_config.id；0 = 自动查找用户默认 LLM
    OCR_MAX_PAGES: int = 50      # 扫描 PDF 最大 OCR 页数

    # ── Sandbox (代码执行沙箱) ──
    SANDBOX_ENABLED: bool = _IS_DESKTOP_RUNTIME  # 桌面版自动启用
    SANDBOX_USE_LOCAL: bool = _IS_DESKTOP_RUNTIME  # 桌面版自动使用本地 subprocess
    SANDBOX_IMAGE: str = "python:3.12-slim"
    SANDBOX_TIMEOUT: int = 30
    SANDBOX_MEMORY_LIMIT: str = "256m"
    SANDBOX_NETWORK_DISABLED: bool = False  # False=允许网络(技能脚本调用外部 API)

    # ── Platform Built-in Model (平台内置模型) ──
    PLATFORM_LLM_API_BASE: str = ""
    PLATFORM_LLM_API_KEY: str = ""
    PLATFORM_LLM_MODEL_NAME: str = ""
    PLATFORM_LLM_DISPLAY_NAME: str = "知枢官方模型"
    PLATFORM_EMBEDDING_API_BASE: str = ""
    PLATFORM_EMBEDDING_API_KEY: str = ""
    PLATFORM_EMBEDDING_MODEL_NAME: str = ""
    PLATFORM_EMBEDDING_DISPLAY_NAME: str = "知枢官方 Embedding"

    # ── Agentic RAG (智能管线编排) ──
    AGENTIC_RAG_ADAPTIVE_RETRIEVAL: bool = False    # Self-RAG: skip retrieval for simple queries
    AGENTIC_RAG_RETRIEVAL_EVALUATION: bool = False  # CRAG: evaluate retrieval quality
    AGENTIC_RAG_DYNAMIC_PIPELINE: bool = False      # Modular: adjust pipeline by complexity
    AGENTIC_RAG_ITERATIVE_REFINEMENT: bool = False  # FAIR-RAG: answer refinement loop
    AGENTIC_RAG_MAX_ITERATIONS: int = 2             # Max refinement iterations
    AGENTIC_RAG_RELEVANCE_THRESHOLD: float = 0.6   # CRAG: minimum relevance score
    AGENTIC_RAG_QUERY_PLANNING: bool = False        # Planning: decompose complex queries into sub-tasks
    GRAPH_RAG_ENABLED: bool = False                   # Graph RAG: extract entities and build knowledge graph
    AGENTIC_RAG_TRAJECTORY_RECORDING: bool = False # Trajectory: record decision trajectories
    MEMORY_RETRIEVAL_BLEND_WEIGHT: float = 0.1    # Memory-enhanced retrieval: user interest blend (0.0-1.0)

    # ── Central Server (云连接) ──
    CENTRAL_SERVER_URL: str = ""
    # 直连中心进程用默认 /api/v1；经统一 Nginx（域名）访问中心时必须与 nginx 一致，一般为 /api/central/v1
    CENTRAL_API_PREFIX: str = "/api/v1"
    CLOUD_HEARTBEAT_INTERVAL: int = 300
    CLOUD_USAGE_REPORT_INTERVAL: int = 300
    CLOUD_DATA_SYNC_ENABLED: bool = False
    CLOUD_USAGE_REPORT_ENABLED: bool = True
    CLOUD_REQUIRE_HTTPS: bool = True
    REMOTE_RELAY_ENABLED: bool = True
    RELAY_MAX_CONCURRENT_PER_HOST: int = 4
    LAN_SHARING_DEFAULT: bool = False

    class Config:
        env_file = str(_ENV_FILE)
        env_file_encoding = "utf-8"


settings = Settings()
