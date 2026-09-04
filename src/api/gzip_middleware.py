"""選擇性 GZip — 跳過 SSE / WebSocket / NDJSON 串流。"""

from __future__ import annotations

from starlette.middleware.gzip import GZipMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

_SKIP_PREFIXES = (
    "/ws",
    "/api/stream",
    "/api/backtest/equity",
)


class SelectiveGZipMiddleware:
    def __init__(self, app: ASGIApp, minimum_size: int = 1000, compresslevel: int = 5):
        self._plain = app
        self._gzip = GZipMiddleware(app, minimum_size=minimum_size, compresslevel=compresslevel)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._plain(scope, receive, send)
            return
        path = scope.get("path") or ""
        if any(path.startswith(p) for p in _SKIP_PREFIXES) or "ndjson" in path:
            await self._plain(scope, receive, send)
            return
        await self._gzip(scope, receive, send)
