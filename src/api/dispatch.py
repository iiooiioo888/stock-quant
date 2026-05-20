"""異步任務提交輔助（供各 API router 共用）"""
from src.utils.logger import logger


def dispatch_async_task(
    task_id: str,
    work_fn,
    *,
    cache_namespace: str = None,
    cache_params: dict = None,
    cache_code: str = None,
) -> dict:
    """將任務提交到線程池；支持結果緩存讀寫"""
    from src.core.task_manager import get_task, submit_task, STATUS_COMPLETED

    task = get_task(task_id)
    if task and task.get("status") == STATUS_COMPLETED:
        return {
            "success": True,
            "task_id": task_id,
            "async": False,
            "from_cache": bool(task.get("from_cache")),
            "result": task.get("result"),
        }

    def _work():
        result = work_fn()
        if cache_namespace and cache_params is not None:
            try:
                from src.core.result_cache import set_cached_compute
                set_cached_compute(
                    cache_namespace, cache_params, result, code=cache_code,
                )
            except Exception as e:
                logger.debug(f"緩存寫入跳過: {e}")
        return result

    submit_task(task_id, _work)
    return {"success": True, "task_id": task_id, "async": True}
