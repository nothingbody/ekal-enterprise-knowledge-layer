"""Code sandbox — Docker (server) or local subprocess (desktop)."""

import asyncio
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class SandboxResult:
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    timed_out: bool = False


class LocalSubprocessSandbox:
    """本地 subprocess 沙箱 — 桌面版使用，无需 Docker，支持网络访问。
    自动安装缺失的 Python 包。"""

    _MAX_AUTO_INSTALL = 3

    # Minimal env keys — deliberately excludes PATH to prevent calling
    # external binaries (curl, wget, etc.) and network-related vars.
    _SAFE_ENV_KEYS = {
        "PYTHONHOME", "HOME", "USERPROFILE",
        "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL", "LC_CTYPE",
        "SYSTEMROOT",
    }

    def __init__(self, timeout: Optional[int] = None):
        self.timeout = timeout or getattr(settings, "SANDBOX_TIMEOUT", 60)

    def _safe_env(self) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items() if k in self._SAFE_ENV_KEYS}
        # Provide minimal PATH with only the Python executable's directory
        python_dir = os.path.dirname(sys.executable)
        env["PATH"] = python_dir
        return env

    def _extract_missing_module(self, stderr: str) -> Optional[str]:
        """从 ImportError/ModuleNotFoundError 中提取缺失的包名。"""
        import re
        m = re.search(r"No module named ['\"]([^'\"\.]+)", stderr)
        if m:
            return m.group(1)
        m = re.search(r"ModuleNotFoundError.*['\"]([^'\"\.]+)", stderr)
        if m:
            return m.group(1)
        return None

    def _install_package(self, package: str) -> bool:
        """Blocked for security — auto-install disabled."""
        logger.warning("沙箱代码请求安装包 '%s'（已禁止自动安装）", package)
        return False

    async def execute(self, code: str, language: str = "python") -> SandboxResult:
        if not getattr(settings, "SANDBOX_ENABLED", False):
            return SandboxResult(
                stderr="沙箱功能未启用。请在配置中设置 SANDBOX_ENABLED=true",
                exit_code=1,
            )

        if language != "python":
            return SandboxResult(stderr=f"不支持的语言: {language}", exit_code=1)

        python_exe = os.environ.get("SANDBOX_PYTHON_PATH") or sys.executable
        if not os.path.exists(python_exe):
            python_exe = sys.executable

        def _run_code() -> SandboxResult:
            try:
                result = subprocess.run(
                    [python_exe, "-c", code],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    encoding="utf-8",
                    errors="replace",
                    env=self._safe_env(),
                )
                return SandboxResult(
                    stdout=result.stdout or "",
                    stderr=result.stderr or "",
                    exit_code=result.returncode,
                )
            except subprocess.TimeoutExpired:
                return SandboxResult(stderr="代码执行超时", exit_code=124, timed_out=True)
            except Exception as exc:
                return SandboxResult(stderr=str(exc), exit_code=1)

        def _run_with_auto_install() -> SandboxResult:
            installed = set()
            for _ in range(self._MAX_AUTO_INSTALL):
                result = _run_code()
                if result.exit_code == 0 or result.timed_out:
                    return result
                missing = self._extract_missing_module(result.stderr)
                if not missing or missing in installed:
                    return result
                if self._install_package(missing):
                    installed.add(missing)
                    continue
                return result
            return _run_code()

        return await asyncio.to_thread(_run_with_auto_install)


class DockerSandbox:
    def __init__(
        self,
        image: Optional[str] = None,
        timeout: Optional[int] = None,
        memory_limit: Optional[str] = None,
        network_disabled: Optional[bool] = None,
    ):
        self.image = image or getattr(settings, "SANDBOX_IMAGE", "python:3.12-slim")
        self.timeout = timeout or getattr(settings, "SANDBOX_TIMEOUT", 30)
        self.memory_limit = memory_limit or getattr(settings, "SANDBOX_MEMORY_LIMIT", "256m")
        self.network_disabled = network_disabled if network_disabled is not None else getattr(settings, "SANDBOX_NETWORK_DISABLED", True)

    async def execute(self, code: str, language: str = "python") -> SandboxResult:
        if not getattr(settings, "SANDBOX_ENABLED", False):
            return SandboxResult(
                stderr="沙箱功能未启用。请在配置中设置 SANDBOX_ENABLED=true",
                exit_code=1,
            )

        try:
            import docker
        except ImportError:
            return SandboxResult(
                stderr="Docker SDK 未安装。请运行: pip install docker",
                exit_code=1,
            )

        try:
            client = docker.from_env()
            client.ping()
        except Exception as exc:
            return SandboxResult(
                stderr=f"Docker 服务不可用: {exc}",
                exit_code=1,
            )

        if language == "python":
            cmd = ["python", "-c", code]
        else:
            return SandboxResult(stderr=f"不支持的语言: {language}", exit_code=1)

        try:
            container = client.containers.run(
                self.image,
                command=["timeout", str(self.timeout)] + cmd,
                mem_limit=self.memory_limit,
                network_disabled=self.network_disabled,
                remove=True,
                stdout=True,
                stderr=True,
                detach=False,
                read_only=True,
                pids_limit=64,
                cpu_period=100000,
                cpu_quota=50000,
                stop_signal="SIGKILL",
            )
            stdout = container.decode("utf-8", errors="replace") if isinstance(container, bytes) else str(container)
            return SandboxResult(stdout=stdout, exit_code=0)
        except docker.errors.ContainerError as exc:
            return SandboxResult(
                stdout=exc.stderr.decode("utf-8", errors="replace") if exc.stderr else "",
                stderr=str(exc),
                exit_code=exc.exit_status,
            )
        except Exception as exc:
            timed_out = "timeout" in str(exc).lower() or "timed out" in str(exc).lower()
            return SandboxResult(
                stderr=str(exc),
                exit_code=124 if timed_out else 1,
                timed_out=timed_out,
            )


_sandbox_instance: Optional[object] = None


def get_sandbox() -> object:
    """返回沙箱实例。桌面版使用本地 subprocess（无需 Docker、支持网络）；服务器版使用 Docker。"""
    global _sandbox_instance
    if _sandbox_instance is None:
        use_local = getattr(settings, "SANDBOX_USE_LOCAL", None)
        if use_local is None:
            use_local = getattr(settings, "DESKTOP_MODE", False)
        if use_local:
            _sandbox_instance = LocalSubprocessSandbox()
            logger.info("使用本地 subprocess 沙箱（支持网络访问）")
        else:
            _sandbox_instance = DockerSandbox()
    return _sandbox_instance
