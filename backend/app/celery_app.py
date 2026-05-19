from celery import Celery
from ..config import get_settings

settings = get_settings()

celery_app = Celery(
    "stock_quant",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "tasks.backtest.*": {"queue": "backtest"},
    },
)

celery_app.autodiscover_tasks(["tasks"])
