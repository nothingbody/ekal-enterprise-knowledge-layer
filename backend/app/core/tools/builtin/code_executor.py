"""Code executor tool — runs Python code in sandbox (Docker or local subprocess)."""

from __future__ import annotations

from app.core.tools.base import BaseTool, ToolResult


class CodeExecutorTool(BaseTool):
    name = "code_executor"
    description = (
        "在沙箱环境中执行 Python 代码。"
        "适用于数据计算、文本处理、格式转换、调用外部 API 等任务。"
        "桌面版使用本地 subprocess（支持网络）；服务器版使用 Docker 容器。"
    )
    sandboxed = True
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "要执行的 Python 代码",
            },
        },
        "required": ["code"],
    }

    # Modules that should never be imported in sandboxed code
    _BLOCKED_MODULES = frozenset({
        "os", "subprocess", "shutil", "sys", "importlib",
        "ctypes", "socket", "http", "urllib", "requests",
        "pathlib", "glob", "tempfile", "signal", "multiprocessing",
        "threading", "asyncio", "builtins", "code", "codeop",
        "compileall", "compile", "eval", "exec",
        # Additional sandbox escape vectors
        "pickle", "marshal", "shelve", "types", "inspect",
        "runpy", "pkgutil", "zipimport", "io", "webbrowser",
    })

    @classmethod
    def _check_code_safety(cls, code: str) -> str | None:
        """Use AST to detect dangerous imports/calls. Returns error message or None."""
        import ast
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return f"代码语法错误: {e}"

        for node in ast.walk(tree):
            # Block: import os / import subprocess / from os import ...
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = None
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        module = alias.name.split(".")[0]
                        if module in cls._BLOCKED_MODULES:
                            return f"不允许导入模块: {alias.name}"
                elif isinstance(node, ast.ImportFrom) and node.module:
                    module = node.module.split(".")[0]
                    if module in cls._BLOCKED_MODULES:
                        return f"不允许导入模块: {node.module}"

            # Block: __import__("os"), eval(), exec(), compile(), globals(), getattr()
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id in (
                    "__import__", "eval", "exec", "compile", "open",
                    "globals", "locals", "vars", "dir", "getattr", "setattr", "delattr",
                    "breakpoint", "exit", "quit",
                ):
                    return f"不允许调用: {func.id}()"
                if isinstance(func, ast.Attribute) and func.attr in ("system", "popen", "exec", "spawn"):
                    return f"不允许调用: .{func.attr}()"

            # Block access to dunder attributes that enable sandbox escapes
            if isinstance(node, ast.Attribute) and node.attr in (
                "__subclasses__", "__bases__", "__class__", "__globals__",
                "__builtins__", "__import__", "__loader__", "__spec__",
            ):
                return f"不允许访问: .{node.attr}"

        return None

    async def execute(self, **kwargs) -> ToolResult:
        code = kwargs.get("code", "")
        if not code.strip():
            return ToolResult(success=False, error="代码不能为空")

        from app.config import settings
        if not getattr(settings, "DESKTOP_MODE", False):
            safety_error = self._check_code_safety(code)
            if safety_error:
                return ToolResult(success=False, error=safety_error)

        from app.core.sandbox import get_sandbox
        sandbox = get_sandbox()
        result = await sandbox.execute(code)

        if result.exit_code != 0:
            error_msg = result.stderr or "代码执行失败"
            if result.timed_out:
                error_msg = "代码执行超时"
            return ToolResult(success=False, error=error_msg)

        return ToolResult(
            success=True,
            data=result.stdout or "(无输出)",
            display_type="text",
        )
