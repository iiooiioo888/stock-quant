"""
Celery 應用 — 使用 Redis Broker（與緩存分庫）
"""
from __future__ import annotations

from src.config import settings
from src.utils.logger import logger

_celery_app = None


def _broker_url() -> str:
    explicit = (getattr(settings, "celery_broker_url", None) or "").strip()
    if explicit:
        return explicit
    base = (settings.redis_url or "redis://localhost:6379/0").strip()
    if "/0" in base:
        return base.replace("/0", "/1", 1)
    if base.endswith("/"):
        return base + "1"
    return base + "/1"


def _result_backend() -> str:
    explicit = (getattr(settings, "celery_result_backend", None) or "").strip()
    if explicit:
        return explicit
    return _broker_url()


def get_celery_app():
    global _celery_app
    if _celery_app is not None:
        return _celery_app
    from celery import Celery

    app = Celery("stock_quant")
    app.conf.update(
        broker_url=_broker_url(),
        result_backend=_result_backend(),
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="Asia/Shanghai",
        enable_utc=True,
        task_track_started=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        task_time_limit=int(getattr(settings, "task_timeout_sec", 1800)),
        task_soft_time_limit=int(getattr(settings, "task_timeout_sec", 1800)) - 60,
    )
    app.autodiscover_tasks(["src.core"])
    _celery_app = app
    logger.info(f"Celery 已配置 broker={_broker_url()}")
    return _celery_app


def celery_available() -> bool:
    if not getattr(settings, "celery_enabled", False):
        return False
    if not settings.redis_enabled:
        return False
    try:
        import redis
        client = redis.from_url(_broker_url(), socket_connect_timeout=2)
        client.ping()
        return True
    except Exception as e:
        logger.debug(f"Celery broker 不可用: {e}")
        return False
