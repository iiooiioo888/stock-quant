"""
MCP 共用工具 — JSON 序列化與統一錯誤/成功封裝（全項目 tools 復用）。

成功：{ "ok": true, ...payload }
失敗：{ "ok": false, "error": "...", "error_code": "...", "tool": "..." }
"""

from __future__ import annotations

import json
from typing import Any, Callable

from src.utils.logger import logger

# 穩定錯誤碼（供 Agent / 自動化分支）
ERR_VALIDATION = "VALIDATION_ERROR"
ERR_NOT_FOUND = "NOT_FOUND"
ERR_INTERNAL = "INTERNAL_ERROR"
ERR_UNKNOWN_TOOL = "UNKNOWN_TOOL"


def json_result(payload: Any) -> str:
    """成功結果：格式化 JSON，自動附加 ok=true。"""
    if isinstance(payload, dict):
        body = dict(payload)
        body.setdefault("ok", True)
    else:
        body = {"ok": True, "data": payload}
    return json.dumps(body, ensure_ascii=False, indent=2, default=str)


def error_result(
    message: str,
    *,
    code: str = ERR_INTERNAL,
    tool: str | None = None,
    **extra: Any,
) -> str:
    """錯誤結果：統一 { ok, error, error_code, tool?, ... } 結構。"""
    body: dict[str, Any] = {
        "ok": False,
        "error": message,
        "error_code": code,
    }
    if tool:
        body["tool"] = tool
    body.update(extra)
    return json.dumps(body, ensure_ascii=False, indent=2)


def safe_handler(
    tool_name: str, handler: Callable[[dict], str]
) -> Callable[[dict], str]:
    """包裝 tool handler：捕獲未處理異常並返回統一錯誤 JSON。"""

    def wrapped(args: dict | None) -> str:
        try:
            return handler(args or {})
        except (ValueError, TypeError, KeyError) as e:
            return error_result(str(e), code=ERR_VALIDATION, tool=tool_name)
        except Exception as e:
            logger.debug(f"MCP tool {tool_name} 失敗: {e}", exc_info=True)
            return error_result(str(e), code=ERR_INTERNAL, tool=tool_name)

    return wrapped
