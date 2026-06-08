"""可選 Sentry 整合（SQ_SENTRY_DSN）。"""

from __future__ import annotations

from src.config import settings
from src.utils.logger import logger


def init_sentry() -> bool:
    """初始化 Sentry；未配置 DSN 或缺少套件時靜默跳過。"""
    dsn = (settings.sentry_dsn or "").strip()
    if not dsn:
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
    except ImportError:
        logger.warning(
            "SQ_SENTRY_DSN 已設置但未安裝 sentry-sdk（pip install sentry-sdk）"
        )
        return False

    sentry_sdk.init(
        dsn=dsn,
        release=f"{settings.app_name}@{settings.app_version}",
        environment="production" if not settings.debug else "development",
        traces_sample_rate=0.05 if settings.debug else 0.1,
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            LoggingIntegration(level=None, event_level="ERROR"),
        ],
        send_default_pii=False,
    )
    logger.info("Sentry 已啟用")
    return True
