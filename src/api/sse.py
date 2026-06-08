"""SSE (Server-Sent Events) event hub.

提供：
- subscribe() / unsubscribe()：每個連線一個 asyncio.Queue
- sync_publish(payload)：可從任意執行緒呼叫（任務線程池）安全推送到主 event loop
"""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

from src.utils.logger import logger

_loop: asyncio.AbstractEventLoop | None = None
_subs: set[asyncio.Queue] = set()
_lock = threading.RLock()


def set_event_loop(loop: asyncio.AbstractEventLoop):
    global _loop
    _loop = loop


def subscribe(*, maxsize: int = 200) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
    with _lock:
        _subs.add(q)
    return q


def unsubscribe(q: asyncio.Queue):
    with _lock:
        _subs.discard(q)


async def _publish(payload: dict[str, Any]):
    text = json.dumps(payload, ensure_ascii=False)
    with _lock:
        subs = list(_subs)
    for q in subs:
        try:
            q.put_nowait(text)
        except asyncio.QueueFull:
            # 丟掉舊的，保新事件（避免慢客戶端拖垮）
            try:
                _ = q.get_nowait()
            except Exception:
                pass
            try:
                q.put_nowait(text)
            except Exception:
                pass


def sync_publish(payload: dict[str, Any]):
    """跨執行緒推送。"""
    if _loop is None:
        return
    try:
        asyncio.run_coroutine_threadsafe(_publish(payload), _loop)
    except Exception as e:
        logger.debug(f"SSE 同步推送失敗: {e}")


def sse_format(data_text: str, *, event: str | None = None) -> str:
    # SSE 規範：每行以 data: 開頭；空行表示一個 event 結束
    out = []
    if event:
        out.append(f"event: {event}")
    for line in str(data_text).splitlines() or [""]:
        out.append(f"data: {line}")
    out.append("")
    return "\n".join(out)
