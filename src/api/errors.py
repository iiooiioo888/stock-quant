"""統一 API 錯誤 JSON：{"code", "msg", "trace_id"}"""
from __future__ import annotations

import uuid

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def api_error_body(code: int, msg: str, trace_id: str | None = None) -> dict:
    return {
        "code": code,
        "msg": msg,
        "trace_id": trace_id or uuid.uuid4().hex[:12],
    }


def get_trace_id(request: Request) -> str:
    existing = request.headers.get("X-Request-Id") or request.headers.get("X-Trace-Id")
    return (existing or uuid.uuid4().hex[:12])[:32]


def api_error_response(request: Request, code: int, msg: str) -> JSONResponse:
    """
    統一由 middleware / router 直接返回的錯誤格式。
    例：429 限流、401 未登錄、403 功能關閉等。
    """
    tid = get_trace_id(request)
    return JSONResponse(
        status_code=code,
        content=api_error_body(code, msg, tid),
        headers={"X-Trace-Id": tid},
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    tid = get_trace_id(request)
    detail = exc.detail
    if isinstance(detail, dict):
        msg = detail.get("msg") or detail.get("message") or str(detail)
    else:
        msg = str(detail) if detail is not None else "請求失敗"
    return JSONResponse(
        status_code=exc.status_code,
        content=api_error_body(exc.status_code, msg, tid),
        headers={"X-Trace-Id": tid},
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    tid = get_trace_id(request)
    errs = exc.errors()
    first = errs[0] if errs else {}
    loc = ".".join(str(x) for x in first.get("loc", []) if x != "body")
    msg = first.get("msg", "參數校驗失敗")
    if loc:
        msg = f"{loc}: {msg}"
    return JSONResponse(
        status_code=422,
        content=api_error_body(422, msg, tid),
        headers={"X-Trace-Id": tid},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    tid = get_trace_id(request)
    from src.utils.logger import logger

    logger.exception("未處理異常 [%s] %s", tid, request.url.path)
    return JSONResponse(
        status_code=500,
        content=api_error_body(500, "伺服器內部錯誤", tid),
        headers={"X-Trace-Id": tid},
    )


def register_exception_handlers(app) -> None:
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
