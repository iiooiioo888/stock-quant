from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
from ...database import get_db
from ...models.task import Task
from ...schemas.task import (
    TaskCreate, TaskUpdate, TaskResponse, TaskListResponse,
    TaskStatsResponse, DailyTaskCount,
)
from ...ws.manager import manager
from ...celery_app import celery_app

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    status: str | None = Query(None),
    task_type: str | None = Query(None),
    search: str | None = Query(None, description="Search by task name"),
    sort_by: str = Query("created_at", description="Sort field: created_at, name, status"),
    sort_order: str = Query("desc", description="Sort order: asc, desc"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    query = select(Task)
    count_q = select(func.count()).select_from(Task)

    # Apply filters
    if status:
        query = query.where(Task.status == status)
        count_q = count_q.where(Task.status == status)
    if task_type:
        query = query.where(Task.task_type == task_type)
        count_q = count_q.where(Task.task_type == task_type)
    if search:
        query = query.where(Task.name.ilike(f"%{search}%"))
        count_q = count_q.where(Task.name.ilike(f"%{search}%"))

    # Sorting
    sort_col = getattr(Task, sort_by, Task.created_at)
    query = query.order_by(sort_col.desc() if sort_order == "desc" else sort_col.asc())

    total = (await db.execute(count_q)).scalar() or 0

    # Status counts (unfiltered)
    running = (await db.execute(select(func.count()).select_from(Task).where(Task.status == "running"))).scalar() or 0
    queued = (await db.execute(select(func.count()).select_from(Task).where(Task.status == "queued"))).scalar() or 0
    completed = (await db.execute(select(func.count()).select_from(Task).where(Task.status == "success"))).scalar() or 0
    failed = (await db.execute(select(func.count()).select_from(Task).where(Task.status == "failed"))).scalar() or 0

    result = await db.execute(query.offset(offset).limit(limit))
    items = [TaskResponse.model_validate(row) for row in result.scalars().all()]

    return TaskListResponse(
        items=items, total=total, running=running, queued=queued,
        completed=completed, failed=failed,
    )


@router.get("/stats", response_model=TaskStatsResponse)
async def get_task_stats(db: AsyncSession = Depends(get_db)):
    """Aggregated task statistics for the analytics panel."""
    total = (await db.execute(select(func.count()).select_from(Task))).scalar() or 0
    running = (await db.execute(select(func.count()).select_from(Task).where(Task.status == "running"))).scalar() or 0
    queued = (await db.execute(select(func.count()).select_from(Task).where(Task.status == "queued"))).scalar() or 0
    completed = (await db.execute(select(func.count()).select_from(Task).where(Task.status == "success"))).scalar() or 0
    failed = (await db.execute(select(func.count()).select_from(Task).where(Task.status == "failed"))).scalar() or 0
    cancelled = (await db.execute(select(func.count()).select_from(Task).where(Task.status == "cancelled"))).scalar() or 0

    finished = completed + failed
    success_rate = round(completed / finished * 100, 1) if finished > 0 else 0.0

    # Average execution time for completed tasks
    avg_q = await db.execute(
        select(func.avg(
            func.julianday(Task.finished_at) - func.julianday(Task.started_at)
        )).where(
            Task.status == "success",
            Task.started_at.isnot(None),
            Task.finished_at.isnot(None),
        )
    )
    avg_days = avg_q.scalar()
    avg_seconds = round(avg_days * 86400, 1) if avg_days else None

    # Tasks by type
    type_rows = (await db.execute(
        select(Task.task_type, func.count()).group_by(Task.task_type)
    )).all()
    by_type = {row[0]: row[1] for row in type_rows}

    # Daily activity (last 14 days)
    cutoff = datetime.utcnow() - timedelta(days=14)
    daily_rows = (await db.execute(
        select(
            cast(Task.created_at, Date).label("day"),
            func.count(),
        )
        .where(Task.created_at >= cutoff)
        .group_by("day")
        .order_by("day")
    )).all()
    daily_activity = [DailyTaskCount(date=str(row[0]), count=row[1]) for row in daily_rows]

    return TaskStatsResponse(
        total=total, running=running, queued=queued, completed=completed,
        failed=failed, cancelled=cancelled, success_rate=success_rate,
        avg_execution_seconds=avg_seconds, by_type=by_type,
        daily_activity=daily_activity,
    )


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str, db: AsyncSession = Depends(get_db)):
    task = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse.model_validate(task)


@router.post("", response_model=TaskResponse, status_code=201)
async def create_task(body: TaskCreate, db: AsyncSession = Depends(get_db)):
    task = Task(
        name=body.name,
        task_type=body.task_type,
        config=body.config,
        priority=body.priority,
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)

    # Dispatch to Celery
    if task.task_type == "backtest":
        celery_result = celery_app.send_task(
            "tasks.backtest.run_backtest",
            args=[task.id, task.config],
            queue="backtest",
        )
        task.celery_task_id = celery_result.id
        await db.flush()

    await manager.broadcast({"event": "task_created", "task": task.to_dict()})
    return TaskResponse.model_validate(task)


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(task_id: str, body: TaskUpdate, db: AsyncSession = Depends(get_db)):
    task = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(task, field, value)

    await db.flush()
    await db.refresh(task)
    await manager.broadcast({"event": "task_updated", "task": task.to_dict()})
    return TaskResponse.model_validate(task)


@router.post("/{task_id}/cancel", response_model=TaskResponse)
async def cancel_task(task_id: str, db: AsyncSession = Depends(get_db)):
    task = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status in ("success", "failed", "cancelled"):
        raise HTTPException(status_code=400, detail=f"Cannot cancel task in '{task.status}' state")

    if task.celery_task_id:
        celery_app.control.revoke(task.celery_task_id, terminate=True)

    task.status = "cancelled"
    from datetime import datetime
    task.finished_at = datetime.utcnow()
    await db.flush()
    await db.refresh(task)
    await manager.broadcast({"event": "task_cancelled", "task": task.to_dict()})
    return TaskResponse.model_validate(task)


@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: str, db: AsyncSession = Depends(get_db)):
    task = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status == "running":
        raise HTTPException(status_code=400, detail="Cannot delete a running task")
    await db.delete(task)
