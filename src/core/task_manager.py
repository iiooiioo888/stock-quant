"""
任務管理器 — 防止重複執行 + 線程池並行調度

每個任務根據 (task_type, params_hash) 去重：
- 如果相同任務正在 pending/running，返回已有任務
- 支持 ThreadPool 並行執行與 pending 佇列
- 支持協作式取消
- 全局槽位控制，避免線程池無限排隊
"""
import hashlib
import json
import math
import os
import time
import threading
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Callable, Optional
from src.utils.logger import logger

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_SUCCESS = STATUS_COMPLETED  # API 別名
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"
STATUS_RETRYING = "retrying"

TERMINAL_STATUSES = frozenset({
    STATUS_COMPLETED, STATUS_FAILED, STATUS_CANCELLED,
})
ACTIVE_STATUSES = frozenset({
    STATUS_PENDING, STATUS_RUNNING, STATUS_RETRYING,
})

_VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    STATUS_PENDING: frozenset({STATUS_RUNNING, STATUS_COMPLETED, STATUS_CANCELLED, STATUS_RETRYING}),
    STATUS_RUNNING: frozenset({
        STATUS_COMPLETED, STATUS_FAILED, STATUS_CANCELLED, STATUS_RETRYING,
    }),
    STATUS_RETRYING: frozenset({STATUS_RUNNING, STATUS_FAILED, STATUS_CANCELLED}),
    STATUS_COMPLETED: frozenset(),
    STATUS_FAILED: frozenset(),
    STATUS_CANCELLED: frozenset(),
}

# 單一任務類型註冊表（async=True 的會出現在任務列表與篩選器）
TASK_REGISTRY: dict[str, dict] = {
    "backtest": {
        "label": "回測",
        "icon": "📊",
        "tab": "backtest",
        "async": True,
    },
    "backtest_advanced": {
        "label": "進階回測",
        "icon": "📊",
        "tab": "backtest",
        "async": True,
    },
    "backtest_multi": {
        "label": "多策略對比",
        "icon": "📊",
        "tab": "backtest",
        "async": True,
    },
    "optimize": {
        "label": "參數優化",
        "icon": "⚡",
        "tab": "optimize",
        "async": True,
    },
    "portfolio": {
        "label": "組合回測",
        "icon": "📈",
        "tab": "portfolio",
        "async": True,
    },
    "walkforward": {
        "label": "Walk-Forward",
        "icon": "🔄",
        "tab": "walkforward",
        "async": True,
    },
    "auto_optimize": {
        "label": "自動優化",
        "icon": "🤖",
        "tab": "optimize",
        "async": True,
    },
    "stock_universe_sync": {
        "label": "股票庫同步",
        "icon": "📚",
        "tab": "data",
        "async": True,
    },
    "stock_universe_intro": {
        "label": "股票簡介補充",
        "icon": "📝",
        "tab": "data",
        "async": True,
    },
    "data_download": {
        "label": "市場數據下載",
        "icon": "📥",
        "tab": "data",
        "async": True,
    },
    "data_download_all": {
        "label": "全市場下載",
        "icon": "📥",
        "tab": "data",
        "async": True,
    },
    "data_incremental": {
        "label": "增量更新",
        "icon": "🔄",
        "tab": "data",
        "async": True,
    },
    "polymarket_sync": {
        "label": "Polymarket 快照同步",
        "icon": "🔮",
        "tab": "markets",
        "async": True,
    },
    # 同步計算，不經 create_task，僅供緩存命名參考
    "heatmap": {
        "label": "熱力圖分析",
        "icon": "🌡️",
        "tab": "heatmap",
        "async": False,
    },
}

TASK_TYPE_NAMES = {
    k: v["label"] for k, v in TASK_REGISTRY.items()
}


def get_task_types(*, async_only: bool = True) -> list[dict]:
    """返回任務類型清單，供 API / 前端篩選器使用。"""
    out = []
    for tid, meta in TASK_REGISTRY.items():
        if async_only and not meta.get("async", True):
            continue
        out.append({
            "id": tid,
            "label": meta["label"],
            "icon": meta.get("icon", ""),
            "tab": meta.get("tab", "tasks"),
        })
    return out


def task_type_label(task_type: str) -> str:
    meta = TASK_REGISTRY.get(task_type)
    if meta:
        icon = meta.get("icon", "")
        label = meta["label"]
        return f"{icon} {label}".strip() if icon else label
    return task_type

_tasks: dict[str, dict] = {}
_lock = threading.RLock()
_MAX_TASKS = 200
_cancel_flags: dict[str, bool] = {}
_dispatched: set[str] = set()  # 已提交線程池、尚未結束
_executor: Optional[ThreadPoolExecutor] = None
_executor_lock = threading.Lock()
_progress_throttle: dict[str, tuple] = {}  # task_id -> (last_ts, last_saved_progress)
_task_logs: dict[str, deque] = {}  # task_id -> 最近 N 行日誌
_pipelines: dict[str, dict] = {}  # pipeline_id -> 編排狀態
_watchdog_stop = threading.Event()
_watchdog_thread: Optional[threading.Thread] = None
_MAX_LOG_LINES = 500

# ── WebSocket 任務推送 ──────────────────────────────────────────
_ws_broadcast: Optional[Callable] = None


def register_ws_broadcaster(broadcast_fn: Callable):
    """註冊 WebSocket 廣播函數，任務狀態變更時自動推送。"""
    global _ws_broadcast
    _ws_broadcast = broadcast_fn


def append_task_log(task_id: str, line: str, *, level: str = "info") -> None:
    """追加任務日誌行並推送 WebSocket。"""
    if not line:
        return
    entry = {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "level": level,
        "message": line.rstrip()[:2000],
    }
    with _lock:
        buf = _task_logs.setdefault(task_id, deque(maxlen=_MAX_LOG_LINES))
        buf.append(entry)
    if _ws_broadcast is None:
        return
    try:
        _ws_broadcast(_to_json_safe({
            "type": "task_log",
            "task_id": task_id,
            "log": entry,
        }))
    except Exception as e:
        logger.debug(f"WS 任務日誌推送失敗: {e}")


def get_task_logs(task_id: str, *, tail: int = 200) -> list[dict]:
    with _lock:
        buf = _task_logs.get(task_id)
        if not buf:
            return []
        items = list(buf)
    if tail > 0:
        items = items[-tail:]
    return [_to_json_safe(x) for x in items]


def _notify_task_update(task_id: str, event: str = "task_update"):
    """通過 WebSocket 推送任務狀態更新（非阻塞）。"""
    if _ws_broadcast is None:
        return
    try:
        task = _tasks.get(task_id)
        if not task:
            return
        payload = _to_json_safe({
            "type": event,
            "task_id": task_id,
            "task_type": task.get("task_type"),
            "title": task.get("title"),
            "status": task.get("status"),
            "progress": task.get("progress", 0),
            "error": task.get("error"),
            "elapsed_sec": _calc_elapsed(task),
            "eta_sec": _calc_eta(task),
            "created_at": task.get("created_at"),
            "completed_at": task.get("completed_at"),
            "result_preview": _extract_result_preview(task),
        })
        _ws_broadcast(payload)
    except Exception as e:
        logger.debug(f"WS 任務推送失敗: {e}")


def _resolve_max_workers() -> int:
    try:
        from src.config import settings
        configured = getattr(settings, "task_max_workers", 0)
    except Exception:
        configured = 0
    if configured and configured > 0:
        return configured
    cpu = os.cpu_count() or 4
    return max(1, min(4, max(1, cpu - 1)))


def _resolve_heavy_max_concurrent() -> int:
    try:
        from src.config import settings
        configured = int(getattr(settings, "task_heavy_max_concurrent", 2) or 2)
    except Exception:
        configured = 2
    return max(1, min(configured, _resolve_max_workers()))


def _resolve_task_timeout() -> int:
    try:
        from src.config import settings
        return int(getattr(settings, "task_timeout_sec", 1800) or 1800)
    except Exception:
        return 1800


def _resolve_watchdog_interval() -> float:
    try:
        from src.config import settings
        return float(getattr(settings, "task_watchdog_interval_sec", 60.0) or 60.0)
    except Exception:
        return 60.0


def normalize_status(status: str) -> str:
    """統一狀態字串（success → completed）。"""
    if not status:
        return status
    s = status.lower().strip()
    if s == "success":
        return STATUS_COMPLETED
    return s


def can_transition(from_status: str, to_status: str) -> bool:
    from_s = normalize_status(from_status)
    to_s = normalize_status(to_status)
    if from_s == to_s:
        return True
    allowed = _VALID_TRANSITIONS.get(from_s)
    if allowed is None:
        return False
    return to_s in allowed


def transition_task(task_id: str, to_status: str, **kwargs) -> Optional[dict]:
    """依狀態機校驗後更新任務。"""
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            return None
        from_s = task.get("status", STATUS_PENDING)
        to_s = normalize_status(to_status)
        if not can_transition(from_s, to_s):
            logger.warning(f"任務狀態轉換拒絕: {task_id} {from_s} → {to_s}")
            return task
    return update_task(task_id, status=to_s, **kwargs)


def _to_json_safe(obj):
    """將 numpy 等類型轉為 JSON 可序列化結構，避免 API 返回失敗"""
    if obj is None:
        return None
    try:
        import numpy as np

        def _default(o):
            if isinstance(o, (np.integer,)):
                return int(o)
            if isinstance(o, (np.floating,)):
                v = float(o)
                if math.isnan(v) or math.isinf(v):
                    return None
                return v
            if isinstance(o, np.ndarray):
                return o.tolist()
            if isinstance(o, (datetime,)):
                return o.strftime("%Y-%m-%d %H:%M:%S")
            return str(o)

        def _sanitize_floats(x):
            if isinstance(x, float):
                if math.isnan(x) or math.isinf(x):
                    return None
                return x
            if isinstance(x, dict):
                return {k: _sanitize_floats(v) for k, v in x.items()}
            if isinstance(x, (list, tuple)):
                return [_sanitize_floats(v) for v in x]
            return x

        raw = json.loads(json.dumps(obj, default=_default, ensure_ascii=False))
        return _sanitize_floats(raw)
    except Exception:
        return obj


def _parse_dt(dt_str: str) -> Optional[float]:
    """將 'YYYY-MM-DD HH:MM:SS' 解析為 timestamp，失敗返回 None。"""
    if not dt_str:
        return None
    try:
        return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S").timestamp()
    except Exception:
        return None


def _calc_elapsed(task: dict) -> float:
    """計算任務已運行秒數。"""
    started = _parse_dt(task.get("started_at"))
    if not started:
        return 0.0
    if task.get("status") in (STATUS_COMPLETED, STATUS_FAILED, STATUS_CANCELLED):
        ended = _parse_dt(task.get("completed_at")) or time.time()
        return round(ended - started, 1)
    return round(time.time() - started, 1)


def _calc_eta(task: dict) -> Optional[float]:
    """根據進度速率預估剩餘秒數，返回 None 表示無法預估。"""
    progress = task.get("progress", 0)
    if progress < 5 or progress >= 100:
        return None
    started = _parse_dt(task.get("started_at"))
    if not started:
        return None
    elapsed = time.time() - started
    if elapsed < 3:
        return None
    rate = progress / elapsed  # 每秒進度
    if rate <= 0:
        return None
    remaining = (100 - progress) / rate
    return round(remaining, 0)


def _resolve_progress_interval() -> float:
    try:
        from src.config import settings
        return float(getattr(settings, "task_progress_save_interval_sec", 2.0))
    except Exception:
        return 2.0


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            workers = _resolve_max_workers()
            _executor = ThreadPoolExecutor(
                max_workers=workers,
                thread_name_prefix="task-worker",
            )
            logger.info(f"任務執行器已啟動: max_workers={workers}")
        return _executor


def is_task_cancelled(task_id: str) -> bool:
    return _cancel_flags.get(task_id, False)


def _count_active() -> int:
    return sum(1 for t in _tasks.values() if t["status"] == STATUS_RUNNING)


def _count_in_flight() -> int:
    """運行中 + 已派發未結束"""
    with _lock:
        return sum(
            1 for tid, t in _tasks.items()
            if t["status"] in (STATUS_RUNNING, STATUS_RETRYING) or tid in _dispatched
        )


def _make_task_id(task_type: str, params: dict) -> str:
    params_str = json.dumps(params, sort_keys=True, ensure_ascii=False)
    params_hash = hashlib.md5(params_str.encode()).hexdigest()[:8]
    ts = int(time.time() * 1000) % 100000
    return f"{task_type}_{params_hash}_{ts}"


def _make_params_hash(params: dict) -> str:
    params_str = json.dumps(params, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.md5(params_str.encode()).hexdigest()[:12]


def _task_data_version(params: dict) -> str:
    """K 線最新日期等版本號；數據更新後應與舊任務結果脫鉤。"""
    try:
        from src.core.result_cache import get_data_version, _code_from_params
        return get_data_version(_code_from_params(params or {}))
    except Exception:
        return "v0"


def create_task(task_type: str, params: dict, title: str = "", *, force_refresh: bool = False) -> dict:
    params_hash = _make_params_hash(params)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data_ver = _task_data_version(params)

    with _lock:
        if force_refresh:
            drop_ids = [
                tid for tid, t in _tasks.items()
                if t["task_type"] == task_type and t["params_hash"] == params_hash
                and t["status"] == STATUS_COMPLETED
            ]
            for tid in drop_ids:
                _tasks.pop(tid, None)

        for tid, t in _tasks.items():
            if t["task_type"] == task_type and t["params_hash"] == params_hash:
                if t["status"] in ACTIVE_STATUSES or tid in _dispatched:
                    logger.info(f"任務去重: {task_type} 已在佇列中 (task_id={tid})")
                    t["last_accessed"] = time.time()
                    return {
                        "task_id": tid,
                        "status": t["status"],
                        "is_duplicate": True,
                        "title": t.get("title", ""),
                        "created_at": t.get("created_at", ""),
                        "progress": t.get("progress", 0),
                    }
                if (
                    not force_refresh
                    and t["status"] == STATUS_COMPLETED
                    and t.get("result") is not None
                    and t.get("data_version") == data_ver
                ):
                    logger.info(f"任務內存命中: {task_type} (task_id={tid})")
                    t["last_accessed"] = time.time()
                    return {
                        "task_id": tid,
                        "status": STATUS_COMPLETED,
                        "is_duplicate": False,
                        "from_cache": True,
                        "title": t.get("title", ""),
                        "created_at": t.get("created_at", ""),
                        "progress": 100,
                        "result": t.get("result"),
                    }

        # 全局結果緩存命中 → 直接建立已完成任務
        try:
            from src.core.result_cache import get_cached_compute, _code_from_params
            cached = None
            if not force_refresh:
                cached = get_cached_compute(task_type, params, code=_code_from_params(params))
            if cached is not None:
                task_id = _make_task_id(task_type, params)
                task = {
                    "task_id": task_id,
                    "task_type": task_type,
                    "params_hash": params_hash,
                    "params": params,
                    "title": title or f"{task_type}",
                    "status": STATUS_COMPLETED,
                    "progress": 100,
                    "result": _to_json_safe(cached),
                    "error": None,
                    "created_at": now,
                    "started_at": now,
                    "completed_at": now,
                    "last_accessed": time.time(),
                    "from_cache": True,
                    "data_version": data_ver,
                }
                _tasks[task_id] = task
                _save_task_to_db(task, force=True)
                logger.info(f"緩存命中任務: {task_type} (task_id={task_id})")
                return {
                    "task_id": task_id,
                    "status": STATUS_COMPLETED,
                    "is_duplicate": False,
                    "from_cache": True,
                    "title": task["title"],
                    "created_at": now,
                    "progress": 100,
                    "result": task["result"],
                }
        except Exception as e:
            logger.debug(f"緩存查詢跳過: {e}")

        task_id = _make_task_id(task_type, params)
        task = {
            "task_id": task_id,
            "task_type": task_type,
            "params_hash": params_hash,
            "params": params,
            "title": title or f"{task_type}",
            "status": STATUS_PENDING,
            "progress": 0,
            "result": None,
            "error": None,
            "created_at": now,
            "started_at": None,
            "completed_at": None,
            "last_accessed": time.time(),
            "data_version": data_ver,
        }
        _tasks[task_id] = task
        _cancel_flags.pop(task_id, None)
        _progress_throttle.pop(task_id, None)
        _save_task_to_db(task)

        logger.info(f"任務創建: {task_type} (task_id={task_id}, pending)")
        return {
            "task_id": task_id,
            "status": STATUS_PENDING,
            "is_duplicate": False,
            "title": task["title"],
            "created_at": now,
            "progress": 0,
        }


def _mark_running(task_id: str) -> bool:
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            return False
        if _cancel_flags.get(task_id) or task["status"] == STATUS_CANCELLED:
            return False
        if task["status"] not in (STATUS_PENDING, STATUS_RETRYING):
            return task["status"] == STATUS_RUNNING
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        task["status"] = STATUS_RUNNING
        task["started_at"] = now
        task["progress"] = max(task.get("progress", 0), 1)
        task["last_accessed"] = time.time()
        _save_task_to_db(task, force=True)
    _notify_task_update(task_id, "task_started")
    return True


def _on_task_finished(task_id: str):
    with _lock:
        _dispatched.discard(task_id)
        _progress_throttle.pop(task_id, None)
    _drain_queue()


def _drain_queue():
    max_workers = _resolve_max_workers()
    heavy_max = _resolve_heavy_max_concurrent()
    to_start: list[tuple[str, Callable]] = []

    try:
        from src.core.compute_budget import HEAVY_TASK_TYPES
    except Exception:
        HEAVY_TASK_TYPES = frozenset()

    with _lock:
        pending = [
            t for t in _tasks.values()
            if t["status"] in (STATUS_PENDING, STATUS_RETRYING)
            and t["task_id"] not in _dispatched
            and not _cancel_flags.get(t["task_id"])
        ]
        pending.sort(key=lambda t: t.get("created_at", ""))
        in_flight = _count_in_flight()
        heavy_in_flight = count_in_flight_heavy()

        for t in pending:
            if in_flight >= max_workers:
                break
            if t["task_type"] in HEAVY_TASK_TYPES and heavy_in_flight >= heavy_max:
                continue
            fn = t.get("_worker_fn")
            if fn is None:
                continue
            tid = t["task_id"]
            _dispatched.add(tid)
            to_start.append((tid, fn))
            in_flight += 1
            if t["task_type"] in HEAVY_TASK_TYPES:
                heavy_in_flight += 1

    for task_id, fn in to_start:
        _start_worker(task_id, fn)


def _start_worker(task_id: str, work_fn: Callable):
    def _run():
        from src.core.task_log_stream import capture_exception, task_log_context

        try:
            if not _mark_running(task_id):
                if is_task_cancelled(task_id):
                    update_task(task_id, status=STATUS_CANCELLED, error="用戶取消")
                return
            if is_task_cancelled(task_id):
                update_task(task_id, status=STATUS_CANCELLED, error="用戶取消")
                return
            append_task_log(task_id, f"任務開始執行 ({task_id})")
            with task_log_context(task_id):
                result = work_fn()
            if is_task_cancelled(task_id):
                update_task(task_id, status=STATUS_CANCELLED, error="用戶取消")
            else:
                append_task_log(task_id, "任務執行完成")
                update_task(task_id, status=STATUS_COMPLETED, progress=100, result=result)
        except Exception as e:
            capture_exception(task_id, e)
            if is_task_cancelled(task_id):
                update_task(task_id, status=STATUS_CANCELLED, error="用戶取消")
            else:
                logger.error(f"任務失敗 {task_id}: {e}")
                update_task(task_id, status=STATUS_FAILED, error=str(e))
        finally:
            with _lock:
                t = _tasks.get(task_id)
                if t:
                    t.pop("_worker_fn", None)
            _cancel_flags.pop(task_id, None)
            _on_task_finished(task_id)

    _get_executor().submit(_run)


def submit_task(task_id: str, work_fn: Callable) -> None:
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            raise ValueError(f"任務不存在: {task_id}")
        task["_worker_fn"] = work_fn
        task["last_accessed"] = time.time()
    _drain_queue()


def update_task_meta(task_id: str, message: str = None, download: dict = None, **extra) -> None:
    """更新任務運行中的展示信息（下載進度等）"""
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            return
        meta = task.setdefault("meta", {})
        if message is not None:
            meta["message"] = message
        if download is not None:
            meta["download"] = {**meta.get("download", {}), **download}
        meta.update(extra)


def update_task(task_id: str, status: str = None, progress: int = None,
                result: any = None, error: str = None) -> Optional[dict]:
    force_db = status is not None or result is not None or error is not None
    if progress is not None and not force_db:
        now = time.time()
        interval = _resolve_progress_interval()
        with _lock:
            task = _tasks.get(task_id)
            if not task:
                return None
            last_ts, last_prog = _progress_throttle.get(task_id, (0, -1))
            if progress < 100 and (now - last_ts) < interval and abs(progress - last_prog) < 5:
                task["progress"] = progress
                task["last_accessed"] = now
                return task
            _progress_throttle[task_id] = (now, progress)
            task["progress"] = progress
            task["last_accessed"] = now
        if not force_db and progress < 100:
            return _tasks.get(task_id)

    with _lock:
        task = _tasks.get(task_id)
        if not task:
            return None

        if status:
            new_status = normalize_status(status)
            old_status = task.get("status")
            if old_status != new_status and not can_transition(old_status, new_status):
                logger.warning(
                    f"任務狀態跳轉: {task_id} {old_status} → {new_status}（未在狀態機中定義）"
                )
            task["status"] = new_status
            status = new_status
        if progress is not None:
            task["progress"] = progress
        if result is not None:
            task["result"] = _to_json_safe(result)
            task["data_version"] = _task_data_version(task.get("params") or {})
        if error is not None:
            task["error"] = error
        if status in (STATUS_COMPLETED, STATUS_FAILED, STATUS_CANCELLED):
            task["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        task["last_accessed"] = time.time()
        _save_task_to_db(task, force=force_db)

        if status in (STATUS_COMPLETED, STATUS_FAILED, STATUS_CANCELLED):
            _evict_old_tasks_inner()

    # WebSocket 推送（鎖外執行，避免死鎖）
    if status in (STATUS_COMPLETED, STATUS_FAILED, STATUS_CANCELLED):
        _notify_task_update(task_id, f"task_{status}")
        if status == STATUS_COMPLETED:
            _on_task_completed_pipeline(task_id)
    elif status == STATUS_RUNNING:
        _notify_task_update(task_id, "task_started")
    elif status == STATUS_RETRYING:
        _notify_task_update(task_id, "task_retrying")
    elif progress is not None and progress >= 0:
        _notify_task_update(task_id, "task_progress")

    return task


def get_task(task_id: str) -> Optional[dict]:
    with _lock:
        task = _tasks.get(task_id)
        if task:
            task["last_accessed"] = time.time()
            out = dict(task)
            out.pop("_worker_fn", None)
            return _to_json_safe(out)
        return _load_task_from_db(task_id, include_result=True)


def get_tasks(task_type: str = None, status: str = None, limit: int = 50) -> list[dict]:
    with _lock:
        tasks = list(_tasks.values())
    if task_type:
        tasks = [t for t in tasks if t["task_type"] == task_type]
    if status:
        tasks = [t for t in tasks if t["status"] == status]
    tasks.sort(key=lambda t: t.get("created_at", ""), reverse=True)
    return [_task_summary(t) for t in tasks[:limit]]


def get_running_tasks() -> list[dict]:
    return get_tasks(status=STATUS_RUNNING)


def get_task_stats() -> dict:
    with _lock:
        tasks = list(_tasks.values())
    in_flight = len(_dispatched) + sum(
        1 for t in tasks
        if t["status"] == STATUS_RUNNING and t["task_id"] not in _dispatched
    )
    return {
        "total": len(tasks),
        "pending": sum(1 for t in tasks if t["status"] == STATUS_PENDING),
        "running": sum(1 for t in tasks if t["status"] == STATUS_RUNNING),
        "retrying": sum(1 for t in tasks if t["status"] == STATUS_RETRYING),
        "dispatched": len(_dispatched),
        "in_flight": in_flight,
        "max_workers": _resolve_max_workers(),
        "heavy_max_concurrent": _resolve_heavy_max_concurrent(),
        "heavy_in_flight": count_in_flight_heavy(),
        "task_timeout_sec": _resolve_task_timeout(),
        "completed": sum(1 for t in tasks if t["status"] == STATUS_COMPLETED),
        "failed": sum(1 for t in tasks if t["status"] == STATUS_FAILED),
        "cancelled": sum(1 for t in tasks if t["status"] == STATUS_CANCELLED),
    }


def get_queue_snapshot() -> dict:
    with _lock:
        tasks = list(_tasks.values())

    running = sorted(
        [t for t in tasks if t["status"] == STATUS_RUNNING],
        key=lambda t: t.get("started_at") or t.get("created_at", ""),
    )
    pending = sorted(
        [t for t in tasks if t["status"] == STATUS_PENDING and t["task_id"] not in _dispatched],
        key=lambda t: t.get("created_at", ""),
    )
    completed = sorted(
        [t for t in tasks if t["status"] == STATUS_COMPLETED and t.get("result") is not None],
        key=lambda t: t.get("completed_at", ""),
        reverse=True,
    )

    current = _task_summary(running[0]) if running else None
    next_task = None
    if len(running) > 1:
        next_task = _task_summary(running[1])
    elif pending:
        next_task = _task_summary(pending[0])

    stats = get_task_stats()
    return {
        "current": current,
        "next": next_task,
        "running": [_task_summary(t) for t in running],
        "pending": [_task_summary(t) for t in pending],
        "recent_completed": _task_summary(completed[0]) if completed else None,
        "stats": stats,
    }


def cancel_task(task_id: str) -> bool:
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            return False
        if task["status"] not in ACTIVE_STATUSES and task_id not in _dispatched:
            return False
        _cancel_flags[task_id] = True
        if task["status"] == STATUS_PENDING:
            task["status"] = STATUS_CANCELLED
            task["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            task.pop("_worker_fn", None)
            _dispatched.discard(task_id)
            _save_task_to_db(task, force=True)
            logger.info(f"任務取消(pending): {task_id}")
            _notify_task_update(task_id, "task_cancelled")
            return True
        logger.info(f"任務取消請求(running): {task_id}")
        return True


def delete_task(task_id: str) -> bool:
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            return False
        if task["status"] in ACTIVE_STATUSES or task_id in _dispatched:
            return False
        del _tasks[task_id]
        _cancel_flags.pop(task_id, None)
        _progress_throttle.pop(task_id, None)
        try:
            from src.core.db import get_conn
            with get_conn() as conn:
                conn.execute("DELETE FROM task_log WHERE task_id = ?", (task_id,))
        except Exception:
            pass
        logger.info(f"任務刪除: {task_id}")
        return True


def get_task_full(task_id: str, *, include_result: bool = True) -> Optional[dict]:
    with _lock:
        task = _tasks.get(task_id)
        if task:
            task["last_accessed"] = time.time()
            out = dict(task)
            out.pop("_worker_fn", None)
            if not include_result:
                out.pop("result", None)
            return _to_json_safe(out)
        return _load_task_from_db(task_id, include_result=include_result)


def get_task_params(task_id: str) -> Optional[dict]:
    """僅返回任務參數（輕量，供任務面板展開）"""
    full = get_task_full(task_id, include_result=False)
    if not full:
        return None
    params = dict(full.get("params") or {})
    if not params and full.get("from_db"):
        import re
        title = full.get("title") or ""
        if full.get("task_type") == "portfolio":
            m = re.search(r"\((\d+)\s*隻\)", title)
            if m:
                params = {
                    "_legacy": True,
                    "count": int(m.group(1)),
                    "note": "此任務完成於參數持久化功能上線前，僅保留標題摘要。請重新執行組合回測以查看完整配置。",
                }
    return {
        "task_id": full.get("task_id"),
        "task_type": full.get("task_type"),
        "title": full.get("title"),
        "params": params,
        "meta": full.get("meta") or {},
    }


def cleanup_stale_tasks(timeout_sec: int = None) -> int:
    if timeout_sec is None:
        timeout_sec = _resolve_task_timeout()
    now = time.time()
    cleaned = 0
    with _lock:
        for tid, t in list(_tasks.items()):
            if t["status"] in ACTIVE_STATUSES or tid in _dispatched:
                last = t.get("last_accessed", time.time())
                if isinstance(last, str):
                    try:
                        last = datetime.strptime(last, "%Y-%m-%d %H:%M:%S").timestamp()
                    except Exception:
                        last = now
                elapsed = now - float(last)
                if elapsed > timeout_sec:
                    t["status"] = STATUS_FAILED
                    t["error"] = f"任務超時（{timeout_sec}秒）"
                    t["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    t.pop("_worker_fn", None)
                    _cancel_flags.pop(tid, None)
                    _dispatched.discard(tid)
                    _save_task_to_db(t, force=True)
                    cleaned += 1
                    logger.warning(f"任務超時清理: {tid}")
    if cleaned:
        _drain_queue()
    return cleaned


def count_in_flight_tasks(exclude_task_id: str = None) -> int:
    """已派發或運行中的任務數（不含僅 pending）"""
    with _lock:
        return sum(
            1 for tid, t in _tasks.items()
            if tid != exclude_task_id
            and (t["status"] == STATUS_RUNNING or tid in _dispatched)
        )


def count_in_flight_heavy(exclude_task_id: str = None) -> int:
    from src.core.compute_budget import HEAVY_TASK_TYPES
    with _lock:
        return sum(
            1 for tid, t in _tasks.items()
            if tid != exclude_task_id
            and t["task_type"] in HEAVY_TASK_TYPES
            and (t["status"] == STATUS_RUNNING or tid in _dispatched)
        )


def is_task_running(task_type: str, params: dict) -> bool:
    params_hash = _make_params_hash(params)
    with _lock:
        for t in _tasks.values():
            if (t["task_type"] == task_type and
                t["params_hash"] == params_hash and
                (t["status"] in ACTIVE_STATUSES or t["task_id"] in _dispatched)):
                return True
    return False


def _task_summary(task: dict) -> dict:
    meta = task.get("meta") or {}
    dl = meta.get("download") or {}
    elapsed = _calc_elapsed(task)
    eta = _calc_eta(task)
    summary = {
        "task_id": task["task_id"],
        "task_type": task["task_type"],
        "task_type_name": TASK_TYPE_NAMES.get(task["task_type"], task["task_type"]),
        "title": task.get("title", ""),
        "status": task["status"],
        "progress": task.get("progress", 0),
        "error": task.get("error"),
        "created_at": task.get("created_at", ""),
        "started_at": task.get("started_at"),
        "completed_at": task.get("completed_at"),
        "elapsed_sec": elapsed,
        "eta_sec": eta,
        "has_result": task.get("result") is not None,
        "status_message": meta.get("message", ""),
        "download": dl if dl else None,
    }
    if task.get("result") and isinstance(task["result"], dict):
        r = task["result"]
        if "total_records" in r:
            summary["download_summary"] = {
                "total_records": r.get("total_records"),
                "success_symbols": r.get("success_symbols"),
                "total_symbols": r.get("total_symbols"),
                "market_name": r.get("market_name") or dl.get("market_name"),
            }
    preview = _extract_result_preview(task)
    if preview:
        summary["result_preview"] = preview
    return summary


def _extract_result_preview(task: dict) -> Optional[dict]:
    """從回測/優化結果提取列表欄位可展示的指標。"""
    result = task.get("result")
    if not isinstance(result, dict):
        return None
    task_type = task.get("task_type", "")
    if task_type in ("backtest", "backtest_advanced", "backtest_multi", "portfolio", "walkforward"):
        return {
            "annual_return_pct": result.get("annual_return_pct"),
            "max_drawdown_pct": result.get("max_drawdown_pct"),
            "sharpe_ratio": result.get("sharpe_ratio"),
            "total_return_pct": result.get("total_return_pct"),
            "win_rate_pct": result.get("win_rate_pct"),
        }
    if task_type == "optimize" and isinstance(result.get("best"), dict):
        best = result["best"]
        return {
            "annual_return_pct": best.get("annual_return_pct"),
            "max_drawdown_pct": best.get("max_drawdown_pct"),
            "sharpe_ratio": best.get("sharpe_ratio"),
            "objective": result.get("objective"),
        }
    return None


def _load_task_from_db(task_id: str, *, include_result: bool = False) -> Optional[dict]:
    """內存淘汰後從 task_log 恢復任務元數據（不含 result）"""
    try:
        from src.core.db import get_conn
        with get_conn() as conn:
            row = conn.execute(
                """SELECT task_id, task_type, params_hash, title, status, progress, error,
                          created_at, completed_at, params_json
                   FROM task_log WHERE task_id = ?""",
                (task_id,),
            ).fetchone()
        if not row:
            return None
        params = {}
        if row[9]:
            try:
                params = json.loads(row[9])
            except Exception:
                params = {}
        return _to_json_safe({
            "task_id": row[0],
            "task_type": row[1],
            "params_hash": row[2],
            "title": row[3] or "",
            "status": row[4],
            "progress": row[5] or 0,
            "error": row[6],
            "created_at": row[7] or "",
            "completed_at": row[8],
            "params": params,
            "result": None if not include_result else None,
            "from_db": True,
        })
    except Exception as e:
        logger.debug(f"從 DB 載入任務失敗 {task_id}: {e}")
        return None


def _save_task_to_db(task: dict, force: bool = False):
    if not force and task.get("status") in (STATUS_RUNNING, STATUS_RETRYING):
        prog = task.get("progress", 0)
        if 0 < prog < 100:
            return
    try:
        from src.core.db import get_conn
        meta = dict(task.get("meta") or {})
        if force and task.get("task_id") in _task_logs:
            logs = list(_task_logs.get(task["task_id"], []))[-50:]
            if logs:
                meta["log_tail"] = logs
        meta_json = json.dumps(meta, ensure_ascii=False, default=str) if meta else None
        pipeline_id = meta.get("pipeline_id")
        parent_task_id = meta.get("parent_task_id")
        with get_conn() as conn:
            params_json = json.dumps(task.get("params") or {}, ensure_ascii=False, default=str)
            cols = [
                "task_id", "task_type", "params_hash", "title", "status", "progress", "error",
                "created_at", "completed_at", "params_json",
            ]
            vals = [
                task["task_id"], task["task_type"], task["params_hash"],
                task.get("title", ""), task["status"], task.get("progress", 0),
                task.get("error"), task.get("created_at"), task.get("completed_at"),
                params_json,
            ]
            if _column_exists_conn(conn, "task_log", "parent_task_id"):
                cols.extend(["parent_task_id", "pipeline_id", "meta_json"])
                vals.extend([parent_task_id, pipeline_id, meta_json])
            placeholders = ", ".join("?" for _ in vals)
            conn.execute(
                f"INSERT OR REPLACE INTO task_log ({', '.join(cols)}) VALUES ({placeholders})",
                tuple(vals),
            )
    except Exception as e:
        logger.debug(f"任務持久化跳過: {e}")


def _column_exists_conn(conn, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def _evict_old_tasks_inner():
    if len(_tasks) <= _MAX_TASKS:
        return
    done_tasks = [
        (tid, t) for tid, t in _tasks.items()
        if t["status"] in (STATUS_COMPLETED, STATUS_FAILED, STATUS_CANCELLED)
    ]
    done_tasks.sort(key=lambda x: x[1].get("completed_at", ""), reverse=False)
    to_remove = len(_tasks) - _MAX_TASKS
    for tid, _ in done_tasks[:to_remove]:
        del _tasks[tid]
        logger.debug(f"任務淘汰: {tid}")


def recover_stale_tasks_on_startup() -> int:
    """啟動自癒：記憶體中殘留的活躍任務標記失敗（DB 由遷移 003 處理）。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    recovered = 0
    with _lock:
        for tid, t in list(_tasks.items()):
            if t["status"] not in ACTIVE_STATUSES and tid not in _dispatched:
                continue
            t["status"] = STATUS_FAILED
            t["error"] = "服務重啟導致任務中斷"
            t["completed_at"] = now
            t.pop("_worker_fn", None)
            _dispatched.discard(tid)
            _cancel_flags.pop(tid, None)
            _save_task_to_db(t, force=True)
            recovered += 1
    if recovered:
        logger.warning(f"啟動自癒：已標記 {recovered} 個殘留任務為失敗")
    return recovered


def start_task_watchdog() -> None:
    """背景看門狗：週期性熔斷超時任務。"""
    global _watchdog_thread
    if _watchdog_thread and _watchdog_thread.is_alive():
        return
    _watchdog_stop.clear()

    def _loop():
        while not _watchdog_stop.wait(_resolve_watchdog_interval()):
            try:
                n = cleanup_stale_tasks()
                if n:
                    logger.info(f"看門狗：已熔斷 {n} 個超時任務")
            except Exception as e:
                logger.debug(f"任務看門狗異常: {e}")

    _watchdog_thread = threading.Thread(target=_loop, name="task-watchdog", daemon=True)
    _watchdog_thread.start()
    logger.info(
        f"任務看門狗已啟動: interval={_resolve_watchdog_interval()}s, "
        f"timeout={_resolve_task_timeout()}s"
    )


def stop_task_watchdog() -> None:
    _watchdog_stop.set()


def cancel_all_pending() -> int:
    """取消所有排隊中的任務。"""
    cancelled = 0
    with _lock:
        pending_ids = [
            tid for tid, t in _tasks.items()
            if t["status"] == STATUS_PENDING
        ]
    for tid in pending_ids:
        if cancel_task(tid):
            cancelled += 1
    return cancelled


def delete_all_completed(*, include_failed: bool = True, include_cancelled: bool = True) -> int:
    """清空已結束的歷史任務（內存）。"""
    removable = {STATUS_COMPLETED}
    if include_failed:
        removable.add(STATUS_FAILED)
    if include_cancelled:
        removable.add(STATUS_CANCELLED)
    deleted = 0
    with _lock:
        ids = [tid for tid, t in _tasks.items() if t["status"] in removable]
    for tid in ids:
        if delete_task(tid):
            deleted += 1
    return deleted


def create_pipeline(steps: list[dict], title: str = "任務管道") -> dict:
    """
    建立任務管道：前一步 SUCCESS 後自動派發下一步。

    steps: [{"task_type", "params", "title?", "pass_result?"}, ...]
    """
    if not steps:
        raise ValueError("管道至少需要一個步驟")
    pipeline_id = f"pipeline_{uuid.uuid4().hex[:12]}"
    with _lock:
        _pipelines[pipeline_id] = {
            "pipeline_id": pipeline_id,
            "title": title,
            "steps": steps,
            "current_index": 0,
            "task_ids": [],
            "status": "running",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    first = steps[0]
    created = create_task(
        first["task_type"],
        first.get("params") or {},
        title=first.get("title") or f"{title} (1/{len(steps)})",
    )
    task_id = created["task_id"]
    with _lock:
        t = _tasks.get(task_id)
        if t:
            meta = t.setdefault("meta", {})
            meta["pipeline_id"] = pipeline_id
            meta["pipeline_step"] = 0
            meta["pipeline_total"] = len(steps)
        _pipelines[pipeline_id]["task_ids"].append(task_id)
    return {
        "pipeline_id": pipeline_id,
        "task_id": task_id,
        "status": created.get("status"),
        "steps": len(steps),
        "title": title,
    }


def submit_pipeline_step(pipeline_id: str, step_index: int, work_fn: Callable) -> str:
    """為管道某一步註冊 worker 並排隊（由 API 在 create 後調用）。"""
    with _lock:
        pipe = _pipelines.get(pipeline_id)
        if not pipe:
            raise ValueError(f"管道不存在: {pipeline_id}")
        task_ids = pipe.get("task_ids") or []
        if step_index >= len(task_ids):
            raise ValueError("管道步驟與任務 ID 不一致")
        task_id = task_ids[step_index]
    submit_task(task_id, work_fn)
    return task_id


def get_pipeline(pipeline_id: str) -> Optional[dict]:
    with _lock:
        pipe = _pipelines.get(pipeline_id)
        return _to_json_safe(dict(pipe)) if pipe else None


def _on_task_completed_pipeline(task_id: str) -> None:
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            return
        meta = task.get("meta") or {}
        pipeline_id = meta.get("pipeline_id")
        if not pipeline_id:
            return
        pipe = _pipelines.get(pipeline_id)
        if not pipe or pipe.get("status") != "running":
            return
        step_idx = int(meta.get("pipeline_step", 0))
        steps = pipe.get("steps") or []
        prev_result = task.get("result")
        if step_idx + 1 >= len(steps):
            pipe["status"] = "completed"
            pipe["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger.info(f"管道完成: {pipeline_id}")
            return
        next_idx = step_idx + 1
        pipe["current_index"] = next_idx

    _dispatch_pipeline_step(pipeline_id, next_idx, prev_result)


def _dispatch_pipeline_step(pipeline_id: str, step_index: int, prev_result) -> None:
    from src.core.task_retry import RetryWorkerError, build_retry_worker

    with _lock:
        pipe = _pipelines.get(pipeline_id)
        if not pipe:
            return
        steps = pipe["steps"]
        step = steps[step_index]
        parent_id = (pipe.get("task_ids") or [])[-1] if pipe.get("task_ids") else None

    params = dict(step.get("params") or {})
    if step.get("pass_result") and prev_result is not None:
        params["_pipeline_prev_result"] = prev_result

    title = step.get("title") or f"{pipe['title']} ({step_index + 1}/{len(steps)})"
    created = create_task(step["task_type"], params, title=title)
    task_id = created["task_id"]

    with _lock:
        t = _tasks.get(task_id)
        if t:
            meta = t.setdefault("meta", {})
            meta["pipeline_id"] = pipeline_id
            meta["pipeline_step"] = step_index
            meta["pipeline_total"] = len(steps)
            if parent_id:
                meta["parent_task_id"] = parent_id
        pipe["task_ids"].append(task_id)

    if created.get("status") == STATUS_COMPLETED:
        _on_task_completed_pipeline(task_id)
        return
    if created.get("is_duplicate"):
        return

    try:
        work_fn = build_retry_worker(step["task_type"], params, task_id)
    except RetryWorkerError as e:
        update_task(task_id, status=STATUS_FAILED, error=str(e))
        with _lock:
            if pipeline_id in _pipelines:
                _pipelines[pipeline_id]["status"] = "failed"
        return

    submit_task(task_id, work_fn)
    append_task_log(
        task_id,
        f"管道 {pipeline_id} 步驟 {step_index + 1}/{len(steps)} 已派發",
    )


logger.info("任務管理器已初始化")
