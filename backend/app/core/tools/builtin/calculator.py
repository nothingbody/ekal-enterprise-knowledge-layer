"""Safe calculator tool — evaluates mathematical expressions."""

from __future__ import annotations

import ast
import math
import operator

from app.core.tools.base import BaseTool, ToolResult

# Allowed operators for safe evaluation
_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

_SAFE_FUNCS = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "sqrt": math.sqrt,
    "log": math.log,
    "log10": math.log10,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "pi": math.pi,
    "e": math.e,
    "ceil": math.ceil,
    "floor": math.floor,
}


def _safe_eval(expr: str):
    """Evaluate a math expression safely using AST parsing."""
    tree = ast.parse(expr, mode="eval")

    def _eval_node(node):
        if isinstance(node, ast.Expression):
            return _eval_node(node.body)
        elif isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError(f"不允许的常量类型: {type(node.value)}")
        elif isinstance(node, ast.BinOp):
            op_func = _SAFE_OPS.get(type(node.op))
            if not op_func:
                raise ValueError(f"不允许的运算符: {type(node.op).__name__}")
            left = _eval_node(node.left)
            right = _eval_node(node.right)
            # Guard against absurdly large exponentiation
            if isinstance(node.op, ast.Pow):
                if isinstance(right, (int, float)) and abs(right) > 100:
                    raise ValueError(f"指数过大 ({right})，最大允许 ±100")
                if isinstance(left, (int, float)) and abs(left) > 1e6:
                    raise ValueError(f"底数过大 ({left})，最大允许 ±1000000")
            return op_func(left, right)
        elif isinstance(node, ast.UnaryOp):
            op_func = _SAFE_OPS.get(type(node.op))
            if not op_func:
                raise ValueError(f"不允许的一元运算符: {type(node.op).__name__}")
            return op_func(_eval_node(node.operand))
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in _SAFE_FUNCS:
                func = _SAFE_FUNCS[node.func.id]
                args = [_eval_node(a) for a in node.args]
                return func(*args)
            raise ValueError(f"不允许的函数调用: {ast.dump(node.func)}")
        elif isinstance(node, ast.Name):
            if node.id in _SAFE_FUNCS:
                val = _SAFE_FUNCS[node.id]
                if isinstance(val, (int, float)):
                    return val
            raise ValueError(f"不允许的变量: {node.id}")
        else:
            raise ValueError(f"不支持的表达式类型: {type(node).__name__}")

    return _eval_node(tree)


class CalculatorTool(BaseTool):
    name = "calculator"
    description = (
        "安全计算器，用于执行数学运算。"
        "支持加减乘除、幂运算、取余，以及 sqrt、log、sin、cos 等数学函数。"
        "输入数学表达式字符串，返回计算结果。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "数学表达式，例如 '(3.14 * 5**2) + sqrt(144)'",
            },
        },
        "required": ["expression"],
    }

    async def execute(self, **kwargs) -> ToolResult:
        expression = kwargs.get("expression", "")
        if not expression.strip():
            return ToolResult(success=False, error="表达式不能为空")
        try:
            result = _safe_eval(expression)
            return ToolResult(
                success=True,
                data=f"{expression} = {result}",
                display_type="text",
            )
        except Exception as exc:
            return ToolResult(success=False, error=f"计算失败: {str(exc)}")
