"""
Desktop entry point for the RAG Platform backend.
Starts the FastAPI server on an auto-detected free port and prints the port for Electron
only AFTER the server is actually listening (avoids ECONNREFUSED when app load fails).

Environment defaults are set BEFORE importing the app so that .env PostgreSQL
settings are overridden for the standalone desktop scenario.
"""
import socket
import sys
import os
import threading
import time
from pathlib import Path

# Safety guard: in frozen Windows builds, stdout/stderr may be None
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

# Ensure the backend directory is on the path
_BACKEND_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(_BACKEND_DIR))

# ── Desktop-mode environment defaults (set before app import) ──
_DATA_DIR = Path(os.environ.get("DESKTOP_DATA_DIR", str(_BACKEND_DIR / "data")))
_UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", str(_DATA_DIR.parent / "uploads")))
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

_defaults = {
    "DESKTOP_MODE": "true",
    "DESKTOP_SEED_DEMO_DATA": "true",
    "DATABASE_URL": f"sqlite+aiosqlite:///{(_DATA_DIR / 'rag.db').as_posix()}",
    "CHROMA_MODE": "embedded",
    "CHROMA_DATA_DIR": str(_DATA_DIR / "chroma"),
    "UPLOAD_DIR": str(_UPLOAD_DIR),
    "CORS_ORIGINS": "*",
    "DEBUG": "false",
    # 桌面版不使用 Redis；必须显式置空，避免 settings 默认 redis://localhost:6379/0
    # 触发 token_blacklist 的 fail-closed（Redis 不可达时拒绝所有 token → 登录后 401）。
    "REDIS_URL": "",
    # 公网统一部署：Nginx 将 /api/v1/ 指到「节点后端」，中心服仅在 /api/central/v1/（见 deploy/nginx.conf）。
    # 中心根地址不设默认域名：通过 CENTRAL_SERVER_URL 或 SERVER_PUBLIC_IP（见下方）配置，避免写死域名。
    "CENTRAL_SERVER_URL": "",
    "CLOUD_REQUIRE_HTTPS": "false",
    "CLOUD_DATA_SYNC_ENABLED": "true",
}
for key, value in _defaults.items():
    os.environ.setdefault(key, value)

# 中心服务 URL：优先完整 CENTRAL_SERVER_URL；否则用 SERVER_PUBLIC_IP 拼成 https://IP（或 CENTRAL_SERVER_SCHEME）
if not (os.environ.get("CENTRAL_SERVER_URL") or "").strip():
    _ip = (os.environ.get("SERVER_PUBLIC_IP") or "").strip()
    if _ip:
        _scheme = (os.environ.get("CENTRAL_SERVER_SCHEME") or "https").strip().rstrip(":")
        if not _scheme:
            _scheme = "https"
        os.environ["CENTRAL_SERVER_URL"] = f"{_scheme}://{_ip}"

if not os.environ.get("CENTRAL_API_PREFIX"):
    _u = (os.environ.get("CENTRAL_SERVER_URL") or "").lower()
    if "127.0.0.1" in _u or "localhost" in _u:
        os.environ["CENTRAL_API_PREFIX"] = "/api/v1"
    else:
        os.environ["CENTRAL_API_PREFIX"] = "/api/central/v1"

# 公网 HTTP 部署：中心地址为 http:// 时必须关闭「强制 HTTPS」，否则 app.cloud.client 会把 URL 升级为 https:// 导致连接失败
_central_url = (os.environ.get("CENTRAL_SERVER_URL") or "").strip().lower()
if _central_url.startswith("http://"):
    os.environ["CLOUD_REQUIRE_HTTPS"] = "false"


def find_free_port() -> int:
    """Find an available TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def is_port_listening(port: int, timeout: float = 1.0) -> bool:
    """Check if something is accepting TCP connections on the given port."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(("127.0.0.1", port))
            return True
    except (OSError, socket.error):
        return False


def main():
    import uvicorn

    try:
        port = int(os.environ.get("BACKEND_PORT", "0"))
    except (ValueError, TypeError):
        port = 0
    if port < 0 or port > 65535:
        port = 0
    if port == 0:
        port = find_free_port()
    os.environ["BACKEND_PORT"] = str(port)

    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    server_error = [None]

    lan_enabled = os.environ.get("LAN_SHARING_ENABLED", "").lower() in {"1", "true", "yes", "on"}
    bind_host = "0.0.0.0" if lan_enabled else "127.0.0.1"

    def run_server():
        try:
            uvicorn.run(
                "app.main:app",
                host=bind_host,
                port=port,
                log_level="info",
                access_log=False,
            )
        except Exception as e:
            server_error[0] = e

    server_thread = threading.Thread(target=run_server, daemon=False)
    server_thread.start()

    for i in range(180):
        if server_error[0]:
            err_msg = str(server_error[0]).replace("@", "(at)")
            print(f"@@ERROR@@{err_msg}@@ERROR@@", flush=True)
            sys.exit(1)
        if is_port_listening(port):
            break
        if not server_thread.is_alive():
            server_error[0] = server_error[0] or RuntimeError("Server thread exited unexpectedly")
            continue
        time.sleep(0.5)
    else:
        print("@@ERROR@@Server failed to bind within 90 seconds@@ERROR@@", flush=True)
        sys.exit(1)

    print(f"@@PORT@@{port}@@PORT@@", flush=True)

    server_thread.join()


if __name__ == "__main__":
    main()
