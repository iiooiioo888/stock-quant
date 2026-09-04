"""
行情抓取緩衝 — 多客戶端共用本地庫，避免同一標的重複爬取。

- 進程內按代碼合併進行中的抓取
- 緩衝時間內視為新鮮，跳過外網
- API 缺資料時可經任務中心排隊補齊（worker 內直接抓，避免嵌套佔槽）
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.utils.logger import logger

_lock = threading.Lock()
_inflight: dict[str, threading.Event] = {}
_last_ok: dict[str, float] = {}
_loaded = False


def _buffer_path() -> Path:
    try:
        from src.config import DATA_DIR

        return Path(DATA_DIR) / "kline_fetch_buffer.json"
    except Exception:
        return Path("data") / "kline_fetch_buffer.json"


def _ensure_loaded() -> None:
    global _loaded
    if _loaded:
        return
    path = _buffer_path()
    try:
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for k, v in raw.items():
                    try:
                        _last_ok[str(k)] = float(v)
                    except (TypeError, ValueError):
                        continue
    except Exception as e:
        logger.debug(f"讀取抓取緩衝失敗: {e}")
    _loaded = True


def _persist_last_ok() -> None:
    try:
        path = _buffer_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        snapshot = dict(_last_ok)
        path.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=0),
            encoding="utf-8",
        )
    except Exception as e:
        logger.debug(f"寫入抓取緩衝失敗: {e}")


def _buffer_hours() -> float:
    try:
        from src.core.task_manager import _resolve_buffer_hours

        return _resolve_buffer_hours()
    except Exception:
        try:
            from src.config import settings

            return float(getattr(settings, "data_fetch_buffer_hours", 12) or 0)
        except Exception:
            return 12.0


def is_fresh(code: str, *, min_bars: int = 2, force: bool = False) -> bool:
    if force:
        return False
    from src.core.local_kline import has_local_kline, normalize_kline_code

    code = normalize_kline_code(code)
    if not has_local_kline(code, min_bars=min_bars):
        return False
    hours = _buffer_hours()
    now = time.time()
    with _lock:
        _ensure_loaded()
        ts = _last_ok.get(code)
    if ts and hours > 0 and (now - ts) < hours * 3600:
        return True
    try:
        from src.core.db import get_latest_date

        latest = get_latest_date(code)
        if not latest:
            return False
        dt = datetime.strptime(str(latest)[:10], "%Y-%m-%d")
        if dt.date() >= datetime.now().date():
            return True
        if hours <= 0:
            return False
        age_h = (datetime.now() - dt).total_seconds() / 3600.0
        return age_h <= hours
    except Exception:
        return False


def mark_fetched(code: str) -> None:
    from src.core.local_kline import normalize_kline_code

    code = normalize_kline_code(code)
    with _lock:
        _ensure_loaded()
        _last_ok[code] = time.time()
        _persist_last_ok()


def is_inflight(code: str) -> bool:
    from src.core.local_kline import normalize_kline_code

    code = normalize_kline_code(code)
    with _lock:
        return code in _inflight


def download_one_buffered(
    code: str,
    start_date: str | None = None,
    market: str | None = None,
    *,
    force: bool = False,
) -> tuple[int, str]:
    """合併同代碼抓取；緩衝命中則不碰外網。"""
    from src.core.local_kline import normalize_kline_code

    code = normalize_kline_code(code)
    if not force and is_fresh(code):
        logger.info(f"資料緩衝命中，跳過爬取: {code}")
        return 0, "buffer"

    ev: threading.Event | None = None
    wait_ev: threading.Event | None = None
    with _lock:
        wait_ev = _inflight.get(code)
        if wait_ev is None:
            ev = threading.Event()
            _inflight[code] = ev
    if wait_ev is not None:
        wait_ev.wait(timeout=180)
        return (0, "coalesced") if is_fresh(code) else (0, "coalesced_empty")

    try:
        if not force and is_fresh(code):
            return 0, "buffer"
        from src.core.auto_kline_fetch import download_one_auto

        count, src = download_one_auto(code, start_date=start_date, market=market)
        if count > 0:
            mark_fetched(code)
        return count, src or "fetched"
    finally:
        with _lock:
            _inflight.pop(code, None)
        if ev is not None:
            ev.set()


def ensure_fetched(
    code: str,
    *,
    start_date: str | None = None,
    market: str | None = None,
    min_bars: int = 2,
) -> str:
    """
    補齊本地 K 線。API 線程可排隊進任務中心；任務 worker 內直接抓取。
    返回 source slug。
    """
    from src.config import settings
    from src.core.local_kline import has_local_kline, normalize_kline_code
    from src.core.task_manager import is_inside_task_worker

    code = normalize_kline_code(code)
    if has_local_kline(code, min_bars=min_bars) and is_fresh(code, min_bars=min_bars):
        return "local_db"

    via_tasks = bool(getattr(settings, "kline_prefetch_via_tasks", True))
    if via_tasks and not is_inside_task_worker():
        src = _prefetch_via_task_center(code, start_date=start_date, market=market)
        if has_local_kline(code, min_bars=min_bars):
            return src or "fetched"
        # 任務超時或失敗時仍嘗試本進程合併抓取一次
    count, src = download_one_buffered(code, start_date=start_date, market=market)
    if count > 0:
        return src
    return src or "empty"


def _prefetch_via_task_center(
    code: str,
    *,
    start_date: str | None = None,
    market: str | None = None,
) -> Optional[str]:
    from src.config import settings
    from src.core.download_tasks import run_incremental
    from src.core.task_manager import (
        create_task,
        submit_task,
        wait_for_task,
    )

    params = {
        "codes": [code],
        "force": False,
        "prefetch": True,
        "market": market or "a_share",
        "start_date": start_date,
    }
    task = create_task("data_incremental", params, title=f"補齊 K 線 {code}")
    if task.get("from_cache") or task.get("status") == "completed":
        return "buffer"
    task_id = task["task_id"]
    if not task.get("is_duplicate"):
        submit_task(
            task_id,
            lambda: run_incremental(codes=[code], force=False, task_id=task_id),
        )
    wait_sec = float(getattr(settings, "kline_prefetch_wait_sec", 90) or 90)
    done = wait_for_task(task_id, timeout_sec=wait_sec)
    if done and done.get("status") == "completed":
        mark_fetched(code)
        return "task_center"
    return None
