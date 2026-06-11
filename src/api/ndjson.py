"""NDJSON 流式響應工具（分塊序列化，降低單次 JSON 峰值）。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Iterable, Iterator
from typing import Any

from fastapi.responses import StreamingResponse

NDJSON_MEDIA = "application/x-ndjson"
NDJSON_HEADERS = {
    "Cache-Control": "no-store",
    "X-Accel-Buffering": "no",
}


def _json_line(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str) + "\n"


async def ndjson_stream(
    rows: Iterable[Any],
    *,
    chunk_size: int = 50,
) -> AsyncIterator[str]:
    """將可迭代資料按 chunk_size 分塊輸出 NDJSON 行。"""
    buf: list[Any] = []
    for row in rows:
        buf.append(row)
        if len(buf) >= chunk_size:
            yield _json_line(buf)
            buf = []
            await asyncio.sleep(0)
    if buf:
        yield _json_line(buf)


def ndjson_response(
    rows: Iterable[Any],
    *,
    chunk_size: int = 50,
) -> StreamingResponse:
    return StreamingResponse(
        ndjson_stream(rows, chunk_size=chunk_size),
        media_type=NDJSON_MEDIA,
        headers=dict(NDJSON_HEADERS),
    )


def iter_ndjson_lines(body: str) -> Iterator[Any]:
    """解析 NDJSON 文本為 Python 物件（測試用）。"""
    for line in body.splitlines():
        line = line.strip()
        if line:
            yield json.loads(line)
