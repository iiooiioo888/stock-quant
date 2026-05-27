"""
任務執行封裝 — Celery / 線程池共用，含緩存寫回與狀態更新。
"""
from __future__ import annotations

from src.utils.logger import logger


def run_registered_task(task_id: str):
    from src.core.task_executors import execute_task
    from src.core.task_log_stream import capture_exception, task_log_context
    from src.core.task_manager import (
        append_task_log,
        get_task,
        is_task_cancelled,
        update_task,
        STATUS_CANCELLED,
        STATUS_COMPLETED,
        STATUS_FAILED,
    )

    from src.core.task_manager import _mark_running, ensure_task_in_memory

    if is_task_cancelled(task_id):
        update_task(task_id, status=STATUS_CANCELLED, error="用戶取消")
        return None

    if not ensure_task_in_memory(task_id):
        update_task(task_id, status=STATUS_FAILED, error="任務不存在或已過期")
        return None

    if not _mark_running(task_id):
        if is_task_cancelled(task_id):
            update_task(task_id, status=STATUS_CANCELLED, error="用戶取消")
        else:
            update_task(
                task_id,
                status=STATUS_FAILED,
                error="無法啟動任務（狀態異常，請取消後重試）",
            )
        return None

    append_task_log(task_id, f"Celery/Worker 開始執行 ({task_id})")
    try:
        with task_log_context(task_id):
            result = execute_task(task_id)
        if is_task_cancelled(task_id):
            update_task(task_id, status=STATUS_CANCELLED, error="用戶取消")
            return None
        _maybe_write_cache(task_id, result)
        append_task_log(task_id, "任務執行完成")
        update_task(task_id, status=STATUS_COMPLETED, progress=100, result=result)
        return result
    except Exception as e:
        capture_exception(task_id, e)
        if is_task_cancelled(task_id):
            update_task(task_id, status=STATUS_CANCELLED, error="用戶取消")
        else:
            logger.error(f"任務失敗 {task_id}: {e}")
            update_task(task_id, status=STATUS_FAILED, error=str(e))
        raise


def _maybe_write_cache(task_id: str, result) -> None:
    task = get_task(task_id)
    if not task:
        return
    meta = task.get("_cache_meta") or {}
    ns = meta.get("namespace")
    if not ns:
        return
    try:
        from src.core.result_cache import set_cached_compute
        set_cached_compute(
            ns,
            meta.get("params") or {},
            result,
            code=meta.get("code"),
        )
    except Exception as e:
        logger.debug(f"任務緩存寫入跳過: {e}")
