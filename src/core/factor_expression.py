"""安全因子表達式 — 僅允許白名單名稱與四則運算。"""

from __future__ import annotations

import ast
import operator
from typing import Mapping

_BIN = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}


class FactorExpressionError(ValueError):
    pass


def eval_factor_expression(expr: str, factors: Mapping[str, float]) -> float:
    src = (expr or "").strip()
    if not src or len(src) > 400:
        raise FactorExpressionError("表達式為空或過長")
    try:
        tree = ast.parse(src, mode="eval")
    except SyntaxError as e:
        raise FactorExpressionError(f"語法錯誤: {e}") from e
    return float(_eval(tree.body, dict(factors)))


def _eval(node, env: dict) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id not in env:
            raise FactorExpressionError(f"未知因子: {node.id}")
        v = env[node.id]
        if v is None:
            raise FactorExpressionError(f"因子 {node.id} 無值")
        return float(v)
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        left = _eval(node.left, env)
        right = _eval(node.right, env)
        if isinstance(node.op, ast.Div) and right == 0:
            raise FactorExpressionError("除以零")
        return float(_BIN[type(node.op)](left, right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return float(_UNARY[type(node.op)](_eval(node.operand, env)))
    raise FactorExpressionError("不支援的運算（僅允許 + - * / 與因子名）")
