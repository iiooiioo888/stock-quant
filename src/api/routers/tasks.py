"""任務管理 API 路由"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

from src.core.auth import get_current_user

router = APIRouter(tags=["tasks"])


class BatchIdsRequest(BaseModel):
    task_ids: list[str]


class PipelineStepRequest(BaseModel):
    task_type: str
    params: dict = {}
    title: str = ""
    pass_result: bool = False


class PipelineCreateRequest(BaseModel):
    title: str = "任務管道"
    steps: list[PipelineStepRequest]
    auto_dispatch: bool = True


@router.get("/api/tasks")
async def list_tasks_api(
    task_type: str = None,
    status: str = None,
    limit: int = 50,
    user=Depends(get_current_user),
):
    """獲取任務列表"""
    from src.core.task_manager import get_tasks, get_task_stats, get_queue_snapshot

    tasks = get_tasks(task_type=task_type, status=status, limit=limit)
    stats = get_task_stats()
    return {"tasks": tasks, "stats": stats, "queue": get_queue_snapshot()}


@router.get("/api/tasks/queue")
async def get_task_queue_api(
    user=Depends(get_current_user),
):
    """獲取執行佇列快照（目前 / 下一個 / 剛完成）"""
    from src.core.task_manager import get_queue_snapshot
    return get_queue_snapshot()


@router.get("/api/tasks/types")
async def list_task_types_api(
    user=Depends(get_current_user),
):
    """獲取異步任務類型清單（供篩選器與顯示名稱）"""
    from src.core.task_manager import get_task_types
    return {"types": get_task_types(async_only=True)}


@router.get("/api/tasks/stats")
async def get_task_stats_api():
    """獲取任務統計（含佇列深度、運行時長等）"""
    from src.core.task_manager import get_task_stats, get_queue_snapshot
    stats = get_task_stats()
    queue = get_queue_snapshot()
    return {"stats": stats, "queue": queue}


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


@router.post("/api/tasks/batch/cancel")
async def batch_cancel_tasks_api(body: BatchIdsRequest):
    """批量取消任務"""
    from src.core.task_manager import cancel_task
    cancelled = []
    failed = []
    for tid in body.task_ids:
        if cancel_task(tid):
            cancelled.append(tid)
        else:
            failed.append(tid)
    return {"success": True, "cancelled": cancelled, "failed": failed}


@router.post("/api/tasks/batch/delete")
async def batch_delete_tasks_api(body: BatchIdsRequest):
    """批量刪除任務（僅已完成/失敗/取消的任務）"""
    from src.core.task_manager import delete_task
    deleted = []
    failed = []
    for tid in body.task_ids:
        if delete_task(tid):
            deleted.append(tid)
        else:
            failed.append(tid)
    return {"success": True, "deleted": deleted, "failed": failed}


@router.post("/api/tasks/{task_id}/retry")
async def retry_task_api(task_id: str):
    """重試失敗/取消的任務（基於原參數重新提交並派發 worker）"""
    from src.core.task_manager import get_task_full, create_task
    from src.core.task_retry import RetryWorkerError, build_retry_worker
    from src.api.dispatch import dispatch_async_task

    original = get_task_full(task_id, include_result=False)
    if not original:
        raise HTTPException(404, "任務不存在")
    if original.get("status") not in ("failed", "cancelled"):
        raise HTTPException(400, "只能重試失敗或取消的任務")
    task_type = original.get("task_type")
    params = original.get("params") or {}
    title = original.get("title", "")
    try:
        work_fn = build_retry_worker(task_type, params, "")
    except RetryWorkerError as e:
        raise HTTPException(400, str(e)) from e

    new_task = create_task(task_type, params, title=f"[重試] {title}")
    if new_task.get("is_duplicate"):
        return {
            "success": True,
            "task_id": new_task["task_id"],
            "is_duplicate": True,
            "message": "相同任務正在執行中",
            "async": True,
        }
    if new_task.get("status") == "completed" and new_task.get("result") is not None:
        return {
            "success": True,
            "task_id": new_task["task_id"],
            "async": False,
            "from_cache": new_task.get("from_cache"),
            "result": new_task.get("result"),
        }

    new_id = new_task["task_id"]
    from src.core.task_manager import STATUS_RETRYING, update_task
    update_task(new_id, status=STATUS_RETRYING, progress=0)
    retry_work = build_retry_worker(task_type, params, new_id)
    out = dispatch_async_task(new_id, retry_work)
    out["message"] = "已提交重試任務"
    return out


@router.post("/api/tasks/cancel-pending")
async def cancel_all_pending_api():
    """一鍵取消所有排隊任務"""
    from src.core.task_manager import cancel_all_pending
    n = cancel_all_pending()
    return {"success": True, "cancelled": n}


@router.post("/api/tasks/clear-completed")
async def clear_completed_tasks_api(
    include_failed: bool = True,
    include_cancelled: bool = True,
):
    """清空已結束的歷史任務"""
    from src.core.task_manager import delete_all_completed
    n = delete_all_completed(
        include_failed=include_failed,
        include_cancelled=include_cancelled,
    )
    return {"success": True, "deleted": n}


@router.get("/api/tasks/{task_id}/logs")
async def get_task_logs_api(task_id: str, tail: int = 200):
    """獲取任務執行日誌（最近 N 行）"""
    from src.core.task_manager import get_task, get_task_logs
    if not get_task(task_id):
        raise HTTPException(404, "任務不存在")
    return {"task_id": task_id, "logs": get_task_logs(task_id, tail=tail)}


@router.post("/api/tasks/pipeline")
async def create_pipeline_api(body: PipelineCreateRequest):
    """建立任務管道並派發第一步"""
    from src.core.task_manager import STATUS_COMPLETED, create_pipeline, submit_task
    from src.core.task_retry import RetryWorkerError, build_retry_worker
    from src.api.dispatch import dispatch_async_task

    if not body.steps:
        raise HTTPException(400, "管道至少需要一個步驟")
    steps = [s.model_dump() for s in body.steps]
    pipe = create_pipeline(steps, title=body.title)
    task_id = pipe["task_id"]
    if not body.auto_dispatch:
        return {"success": True, **pipe, "async": False}

    first = steps[0]
    if pipe.get("status") == STATUS_COMPLETED:
        return {"success": True, **pipe, "async": False, "from_cache": True}

    try:
        work_fn = build_retry_worker(first["task_type"], first.get("params") or {}, task_id)
    except RetryWorkerError as e:
        raise HTTPException(400, str(e)) from e

    out = dispatch_async_task(task_id, work_fn)
    return {"success": True, **pipe, **out}


@router.post("/api/tasks/cleanup")
async def cleanup_tasks_api(timeout_sec: int = 0):
    """清理超時任務"""
    from src.core.task_manager import cleanup_stale_tasks
    cleaned = cleanup_stale_tasks(timeout_sec or None)
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
