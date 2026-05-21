"""
MCP 共用工具 — JSON 序列化與錯誤格式（全項目 tools 復用）。
"""
import json
from typing import Any


def json_result(payload: Any) -> str:
    """成功結果：格式化 JSON 字符串。"""
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def error_result(message: str, **extra) -> str:
    """錯誤結果：統一 { error, ... } 結構。"""
    body = {"error": message}
    body.update(extra)
    return json.dumps(body, ensure_ascii=False)
