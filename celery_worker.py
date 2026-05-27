#!/usr/bin/env python
"""Celery Worker 入口: celery -A celery_worker worker --loglevel=info --concurrency=4"""
from src.core.celery_app import get_celery_app

app = get_celery_app()

# 確保任務模塊載入
from src.core import celery_tasks  # noqa: F401
