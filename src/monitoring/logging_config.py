"""結構化日誌配置模組 - 使用 structlog"""

from __future__ import annotations
import logging
import sys
from typing import Any, Dict

import structlog
from structlog.types import Processor


def setup_structured_logging(
    log_level: str = "INFO",
    json_format: bool = False,
    include_timestamp: bool = True,
) -> None:
    """
    設置結構化日誌
    
    Args:
        log_level: 日誌級別 (DEBUG/INFO/WARNING/ERROR/CRITICAL)
        json_format: 是否使用 JSON 格式輸出
        include_timestamp: 是否在日誌中包含時間戳
    """
    
    # 配置 processors 鏈
    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    
    if include_timestamp:
        processors.append(structlog.processors.TimeStamper(fmt="iso"))
    
    if json_format:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))
    
    # 配置 structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # 配置標準 logging 與 structlog 集成
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
    )
    
    # 使用 structlog 的標準 logging 集成
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    """
    獲取結構化日誌記錄器
    
    Args:
        name: 日誌記錄器名稱（通常為模組名）
    
    Returns:
        配置好的 structlog BoundLogger
    """
    if name is None:
        return structlog.get_logger()
    return structlog.get_logger(name)


# 預設初始化
setup_structured_logging()
