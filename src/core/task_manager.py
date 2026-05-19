"""
任務管理器 — 防止重複執行同一任務

每個任務根據 (task_type, params_hash) 去重：
- 如果相同任務正在執行中，返回已有任務（不重複創建）
- 如果相同任務已完成，允許重新執行
- 支持任務超時自動清理
"""
import hashlib
import json
import time
import threading
from datetime import datetime
from typing import Optional
from src.utils.logger import logger

# ============================================================
# 任務狀態常量
# ============================================================
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

# 任務類型中文名稱
TASK_TYPE_NAMES = {
    "backtest": "回測",
    "backtest_advanced": "進階回測",
    "backtest_multi": "多策略對比",
    "optimize": "參數優化",
    "portfolio": "組合回測",
    "walkforward": "Walk-Forward",
    "auto_optimize": "自動優化",
    "heatmap": "熱力圖分析",
}

# ============================================================
# 內存任務存儲 + 數據庫持久化
# ============================================================
_tasks: dict[str, dict] = {}  # {task_id: task_dict}
_lock = threading.Lock()
_MAX_TASKS = 200  # 內存中最多保留 200 個任務


def _make_task_id(task_type: str, params: dict) -> str:
    """生成任務 ID（基於類型 + 參數哈希）"""
    params_str = json.dumps(params, sort_keys=True, ensure_ascii=False)
    params_hash = hashlib.md5(params_str.encode()).hexdigest()[:8]
    ts = int(time.time() * 1000) % 100000
    return f"{task_type}_{params_hash}_{ts}"


def _make_params_hash(params: dict) -> str:
    """生成參數哈希（用於去重判斷）"""
    params_str = json.dumps(params, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(params_str.encode()).hexdigest()[:12]


def create_task(task_type: str, params: dict, title: str = "") -> dict:
    """
    創建任務（自動去重）。

    如果相同 (task_type, params_hash) 的任務正在執行中，返回已有任務。
    否則創建新任務。

    Returns:
        {"task_id": "...", "status": "running", "is_duplicate": True/False, ...}
    """
    params_hash = _make_params_hash(params)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with _lock:
        # 檢查是否有相同任務正在執行中
        for tid, t in _tasks.items():
            if t["task_type"] == task_type and t["params_hash"] == params_hash:
                if t["status"] in (STATUS_PENDING, STATUS_RUNNING):
                    logger.info(f"任務去重: {task_type} 已在執行中 (task_id={tid})")
                    t["last_accessed"] = time.time()
                    return {
                        "task_id": tid,
                        "status": t["status"],
                        "is_duplicate": True,
                        "title": t.get("title", ""),
                        "created_at": t.get("created_at", ""),
                        "progress": t.get("progress", 0),
                    }

        # 創建新任務
        task_id = _make_task_id(task_type, params)
        task = {
            "task_id": task_id,
            "task_type": task_type,
            "params_hash": params_hash,
            "params": params,
            "title": title or f"{task_type}",
            "status": STATUS_RUNNING,
            "progress": 0,
            "result": None,
            "error": None,
            "created_at": now,
            "started_at": now,
            "completed_at": None,
            "last_accessed": time.time(),
        }
        _tasks[task_id] = task

        # 持久化到數據庫
        _save_task_to_db(task)

        logger.info(f"任務創建: {task_type} (task_id={task_id})")
        return {
            "task_id": task_id,
            "status": STATUS_RUNNING,
            "is_duplicate": False,
            "title": task["title"],
            "created_at": now,
            "progress": 0,
        }


def update_task(task_id: str, status: str = None, progress: int = None,
                result: any = None, error: str = None) -> Optional[dict]:
    """更新任務狀態"""
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            return None

        if status:
            task["status"] = status
        if progress is not None:
            task["progress"] = progress
        if result is not None:
            task["result"] = result
        if error is not None:
            task["error"] = error
        if status in (STATUS_COMPLETED, STATUS_FAILED, STATUS_CANCELLED):
            task["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        task["last_accessed"] = time.time()
        _save_task_to_db(task)

        # 自動清理：完成/失敗/取消後，若超過上限則淘汰最舊的已完成任務
        if status in (STATUS_COMPLETED, STATUS_FAILED, STATUS_CANCELLED):
            _evict_old_tasks()

        return task


def get_task(task_id: str) -> Optional[dict]:
    """獲取單個任務"""
    with _lock:
        task = _tasks.get(task_id)
        if task:
            task["last_accessed"] = time.time()
        return task


def get_tasks(task_type: str = None, status: str = None, limit: int = 50) -> list[dict]:
    """獲取任務列表"""
    with _lock:
        tasks = list(_tasks.values())

    if task_type:
        tasks = [t for t in tasks if t["task_type"] == task_type]
    if status:
        tasks = [t for t in tasks if t["status"] == status]

    # 按創建時間倒序
    tasks.sort(key=lambda t: t.get("created_at", ""), reverse=True)

    # 返回簡化信息（不含完整 params 和 result）
    return [_task_summary(t) for t in tasks[:limit]]


def get_running_tasks() -> list[dict]:
    """獲取所有正在執行的任務"""
    return get_tasks(status=STATUS_RUNNING)


def cancel_task(task_id: str) -> bool:
    """取消任務"""
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            return False
        if task["status"] in (STATUS_PENDING, STATUS_RUNNING):
            task["status"] = STATUS_CANCELLED
            task["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _save_task_to_db(task)
            logger.info(f"任務取消: {task_id}")
            return True
        return False


def delete_task(task_id: str) -> bool:
    """刪除任務（僅已完成/失敗/取消的任務可刪除）"""
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            return False
        if task["status"] in (STATUS_PENDING, STATUS_RUNNING):
            return False  # 運行中的任務不能刪除，需先取消
        del _tasks[task_id]
        # 同步刪除數據庫記錄
        try:
            from src.core.db import get_conn
            with get_conn() as conn:
                conn.execute("DELETE FROM task_log WHERE task_id = ?", (task_id,))
        except Exception:
            pass
        logger.info(f"任務刪除: {task_id}")
        return True


def get_task_full(task_id: str) -> Optional[dict]:
    """獲取任務完整信息（含 params 和 result），用於重試和詳情查看"""
    with _lock:
        task = _tasks.get(task_id)
        if task:
            task["last_accessed"] = time.time()
            return dict(task)  # 返回完整副本
        return None


def cleanup_stale_tasks(timeout_sec: int = 3600) -> int:
    """清理超時任務（默認 1 小時）"""
    now = time.time()
    cleaned = 0
    with _lock:
        for tid, t in list(_tasks.items()):
            if t["status"] in (STATUS_PENDING, STATUS_RUNNING):
                elapsed = now - t.get("last_accessed", t.get("started_at", now))
                if elapsed > timeout_sec:
                    t["status"] = STATUS_FAILED
                    t["error"] = f"任務超時（{timeout_sec}秒）"
                    t["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    _save_task_to_db(t)
                    cleaned += 1
                    logger.warning(f"任務超時清理: {tid}")
    return cleaned


def is_task_running(task_type: str, params: dict) -> bool:
    """檢查是否有相同任務正在執行"""
    params_hash = _make_params_hash(params)
    with _lock:
        for t in _tasks.values():
            if (t["task_type"] == task_type and
                t["params_hash"] == params_hash and
                t["status"] in (STATUS_PENDING, STATUS_RUNNING)):
                return True
    return False


def get_task_stats() -> dict:
    """獲取任務統計"""
    with _lock:
        tasks = list(_tasks.values())
    return {
        "total": len(tasks),
        "running": sum(1 for t in tasks if t["status"] == STATUS_RUNNING),
        "completed": sum(1 for t in tasks if t["status"] == STATUS_COMPLETED),
        "failed": sum(1 for t in tasks if t["status"] == STATUS_FAILED),
        "cancelled": sum(1 for t in tasks if t["status"] == STATUS_CANCELLED),
    }


# ============================================================
# 輔助函數
# ============================================================

def _task_summary(task: dict) -> dict:
    """返回任務摘要（不含完整 params/result）"""
    return {
        "task_id": task["task_id"],
        "task_type": task["task_type"],
        "task_type_name": TASK_TYPE_NAMES.get(task["task_type"], task["task_type"]),
        "title": task.get("title", ""),
        "status": task["status"],
        "progress": task.get("progress", 0),
        "error": task.get("error"),
        "created_at": task.get("created_at", ""),
        "completed_at": task.get("completed_at"),
        "has_result": task.get("result") is not None,
    }


def _save_task_to_db(task: dict):
    """持久化任務到數據庫（可選，失敗不影響內存任務）"""
    try:
        from src.core.db import get_conn
        with get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_log (
                    task_id     TEXT PRIMARY KEY,
                    task_type   TEXT NOT NULL,
                    params_hash TEXT NOT NULL,
                    title       TEXT,
                    status      TEXT NOT NULL,
                    progress    INTEGER DEFAULT 0,
                    error       TEXT,
                    created_at  TEXT,
                    completed_at TEXT
                )
            """)
            conn.execute("""
                INSERT OR REPLACE INTO task_log
                (task_id, task_type, params_hash, title, status, progress, error, created_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task["task_id"], task["task_type"], task["params_hash"],
                task.get("title", ""), task["status"], task.get("progress", 0),
                task.get("error"), task.get("created_at"), task.get("completed_at"),
            ))
    except Exception as e:
        logger.debug(f"任務持久化跳過: {e}")


def _evict_old_tasks():
    """淘汰最舊的已完成任務，保持內存任務數不超過 _MAX_TASKS"""
    with _lock:
        if len(_tasks) <= _MAX_TASKS:
            return

        # 按完成時間排序，優先淘汰最舊的已完成任務
        done_tasks = [
            (tid, t) for tid, t in _tasks.items()
            if t["status"] in (STATUS_COMPLETED, STATUS_FAILED, STATUS_CANCELLED)
        ]
        done_tasks.sort(key=lambda x: x[1].get("completed_at", ""), reverse=False)

        # 淘汰到上限以下
        to_remove = len(_tasks) - _MAX_TASKS
        for tid, _ in done_tasks[:to_remove]:
            del _tasks[tid]
            logger.debug(f"任務淘汰: {tid}")


# 啟動時清理舊任務
def _init():
    """初始化：從數據庫恢復未完成任務，清理過期任務"""
    try:
        from src.core.db import get_conn
        with get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_log (
                    task_id     TEXT PRIMARY KEY,
                    task_type   TEXT NOT NULL,
                    params_hash TEXT NOT NULL,
                    title       TEXT,
                    status      TEXT NOT NULL,
                    progress    INTEGER DEFAULT 0,
                    error       TEXT,
                    created_at  TEXT,
                    completed_at TEXT
                )
            """)
            # 將上次未完成的任務標記為失敗
            conn.execute("""
                UPDATE task_log SET status = 'failed', error = '服務重啟',
                completed_at = ? WHERE status IN ('pending', 'running')
            """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))
    except Exception as e:
        logger.debug(f"任務管理器初始化跳過: {e}")


_init()
logger.info("📋 任務管理器已初始化")
