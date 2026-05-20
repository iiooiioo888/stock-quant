"""任務管理 API 路由"""
from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["tasks"])

@router.get("/api/tasks")
async def list_tasks_api(task_type: str = None, status: str = None, limit: int = 50):
    """獲取任務列表"""
    from src.core.task_manager import get_tasks, get_task_stats, get_queue_snapshot
    tasks = get_tasks(task_type=task_type, status=status, limit=limit)
    stats = get_task_stats()
    return {"tasks": tasks, "stats": stats, "queue": get_queue_snapshot()}


@router.get("/api/tasks/queue")
async def get_task_queue_api():
    """獲取執行佇列快照（目前 / 下一個 / 剛完成）"""
    from src.core.task_manager import get_queue_snapshot
    return get_queue_snapshot()


@router.get("/api/tasks/types")
async def list_task_types_api():
    """獲取異步任務類型清單（供篩選器與顯示名稱）"""
    from src.core.task_manager import get_task_types
    return {"types": get_task_types(async_only=True)}


@router.get("/api/tasks/{task_id}")
async def get_task_api(task_id: str):
    """獲取單個任務詳情"""
    from src.core.task_manager import get_task
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "任務不存在")
    return {"task": task}


@router.post("/api/tasks/{task_id}/cancel")
async def cancel_task_api(task_id: str):
    """取消任務"""
    from src.core.task_manager import cancel_task
    success = cancel_task(task_id)
    if not success:
        raise HTTPException(400, "任務無法取消（可能已完成或不存在）")
    return {"success": True, "message": "任務已取消"}


@router.post("/api/tasks/cleanup")
async def cleanup_tasks_api(timeout_sec: int = 3600):
    """清理超時任務"""
    from src.core.task_manager import cleanup_stale_tasks
    cleaned = cleanup_stale_tasks(timeout_sec)
    return {"success": True, "cleaned": cleaned}


@router.delete("/api/tasks/{task_id}")
async def delete_task_api(task_id: str):
    """刪除已完成/失敗/取消的任務"""
    from src.core.task_manager import delete_task
    ok = delete_task(task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="任務不存在或仍在運行中，請先取消")
    return {"success": True}


@router.get("/api/tasks/{task_id}/params")
async def get_task_params_api(task_id: str):
    """獲取任務參數（輕量，不含大型 result）"""
    from src.core.task_manager import get_task_params
    task = get_task_params(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任務不存在")
    return {"task": task}


@router.get("/api/tasks/{task_id}/full")
async def get_task_full_api(task_id: str):
    """獲取任務完整信息（含 params 和 result）"""
    from src.core.task_manager import get_task_full
    task = get_task_full(task_id, include_result=True)
    if not task:
        raise HTTPException(status_code=404, detail="任務不存在")
    if isinstance(task, dict):
        task.pop("last_accessed", None)
        task.pop("_worker_fn", None)
    return {"task": task}
