from pydantic import BaseModel, Field
from datetime import datetime


class TaskCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    task_type: str = Field(default="backtest")
    config: dict | None = None
    priority: int = Field(default=0, ge=0, le=10)


class TaskUpdate(BaseModel):
    name: str | None = None
    status: str | None = None
    progress: float | None = None
    config: dict | None = None
    result: dict | None = None
    error_message: str | None = None
    celery_task_id: str | None = None


class TaskResponse(BaseModel):
    id: str
    name: str
    task_type: str
    status: str
    progress: float
    config: dict | None
    result: dict | None
    error_message: str | None
    celery_task_id: str | None
    priority: int
    retry_count: int
    created_at: str | None
    started_at: str | None
    finished_at: str | None

    class Config:
        from_attributes = True


class TaskListResponse(BaseModel):
    items: list[TaskResponse]
    total: int
    running: int
    queued: int
    completed: int
    failed: int


class DailyTaskCount(BaseModel):
    date: str
    count: int


class TaskStatsResponse(BaseModel):
    total: int
    running: int
    queued: int
    completed: int
    failed: int
    cancelled: int
    success_rate: float
    avg_execution_seconds: float | None
    by_type: dict[str, int]
    daily_activity: list[DailyTaskCount]
