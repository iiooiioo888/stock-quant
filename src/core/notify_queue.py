"""
通知異步隊列 — 失敗重試 + SQLite 歷史。

send_notification 主流程只入列，不阻塞預警檢查。
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Callable

from src.config import settings
from src.utils.logger import logger

_lock = threading.Lock()
_executor: ThreadPoolExecutor | None = None
_MAX_WORKERS = 2


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    with _lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=_MAX_WORKERS, thread_name_prefix="notify"
            )
        return _executor


def log_notification(
    channel: str,
    message: str,
    *,
    status: str,
    msg_type: str = "alert",
    error: str | None = None,
    attempts: int = 1,
) -> None:
    """寫入 notification_history（失敗不影響主流程）。"""
    try:
        from src.core.db import get_conn

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with get_conn() as conn:
            conn.execute(
                """INSERT INTO notification_history
                   (channel, msg_type, message, status, error, attempts, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    channel,
                    msg_type,
                    (message or "")[:4000],
                    status,
                    (error or "")[:1000] if error else None,
                    int(attempts),
                    now,
                ),
            )
            keep = int(getattr(settings, "notify_history_limit", 500) or 500)
            conn.execute(
                """DELETE FROM notification_history WHERE id NOT IN (
                    SELECT id FROM notification_history ORDER BY id DESC LIMIT ?
                )""",
                (keep,),
            )
    except Exception as e:
        logger.debug(f"通知歷史寫入跳過: {e}")


def get_notification_history(
    limit: int = 50, offset: int = 0, channel: str | None = None
) -> tuple[list[dict], int]:
    from src.core.db import get_conn
    import sqlite3

    where = "1=1"
    params: list = []
    if channel:
        where += " AND channel = ?"
        params.append(channel)
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        total = conn.execute(
            f"SELECT COUNT(*) AS c FROM notification_history WHERE {where}",
            params,
        ).fetchone()["c"]
        rows = conn.execute(
            f"""SELECT * FROM notification_history WHERE {where}
                ORDER BY id DESC LIMIT ? OFFSET ?""",
            params + [int(limit), max(0, int(offset))],
        ).fetchall()
    return [dict(r) for r in rows], int(total)


def enqueue_notify(send_fn: Callable[[], None]) -> None:
    """非阻塞提交；notify_async=false 時同步執行。"""
    if not getattr(settings, "notify_async", True):
        try:
            send_fn()
        except Exception as e:
            logger.error(f"同步通知失敗: {e}")
        return
    try:
        _get_executor().submit(send_fn)
    except Exception as e:
        logger.debug(f"通知入隊失敗，改同步: {e}")
        try:
            send_fn()
        except Exception as e2:
            logger.error(f"通知發送失敗: {e2}")


def send_with_retry(
    channel: str,
    send_once: Callable[[], bool],
    message: str,
    *,
    msg_type: str = "alert",
) -> bool:
    """指數退避重試，並寫入歷史。"""
    max_n = int(getattr(settings, "notify_max_retries", 3) or 0)
    attempts = 0
    last_err = ""
    ok = False
    for i in range(max_n + 1):
        attempts = i + 1
        try:
            ok = bool(send_once())
            if ok:
                break
            last_err = "channel returned false"
        except Exception as e:
            last_err = str(e)
            ok = False
        if i < max_n:
            time.sleep(min(8.0, 0.5 * (2**i)))
    log_notification(
        channel,
        message,
        status="ok" if ok else "failed",
        msg_type=msg_type,
        error=None if ok else last_err,
        attempts=attempts,
    )
    return ok
