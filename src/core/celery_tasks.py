"""
Celery 任務定義 — Worker 進程執行已註冊的 task_type。
"""
from __future__ import annotations

from src.core.celery_app import get_celery_app
from src.utils.logger import logger

celery_app = get_celery_app()


@celery_app.task(name="sq.execute_task", bind=True, max_retries=1)
def execute_task_celery(self, task_id: str):
    """在 Celery Worker 中執行任務（與線程池共用執行器）。"""
    from src.core.database.bootstrap import init_database
    from src.core.task_worker import run_registered_task

    init_database()
    try:
        from src.core.task_manager import ensure_task_in_memory, load_recent_tasks_from_db

        load_recent_tasks_from_db(limit=50)
        ensure_task_in_memory(task_id)
        return run_registered_task(task_id)
    except Exception as exc:
        logger.error(f"Celery 任務失敗 {task_id}: {exc}")
        raise self.retry(exc=exc, countdown=5) from exc


def enqueue_celery_task(task_id: str) -> bool:
    from src.core.celery_app import celery_available

    if not celery_available():
        return False
    execute_task_celery.delay(task_id)
    logger.info(f"任務已送入 Celery: {task_id}")
    return True
