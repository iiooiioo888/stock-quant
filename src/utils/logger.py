"""
日誌系統 — 結構化日誌 + 控制台 + 文件輪轉
"""
import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from src.config import settings


def _make_console_stream_safe():
    """避免 Windows 非 UTF-8 控制台遇到 emoji 日誌時拋 UnicodeEncodeError。"""
    stream = getattr(sys, "__stdout__", None) or sys.stdout
    if hasattr(stream, "reconfigure"):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass
    return stream


def setup_logger(name: str = "stock_quant") -> logging.Logger:
    """
    配置日誌器

    - 控制台: 彩色輸出，INFO 級別
    - 文件: JSON 格式，DEBUG 級別，10MB 輪轉，保留 5 個
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    if logger.handlers:
        return logger

    # 日誌目錄
    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    # 格式
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 控制台 handler
    console = logging.StreamHandler(_make_console_stream_safe())
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    logger.addHandler(console)

    # 文件 handler（輪轉）
    file_handler = RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    # 錯誤單獨記錄
    error_handler = RotatingFileHandler(
        log_dir / "error.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(fmt)
    logger.addHandler(error_handler)

    return logger


# 全局 logger
logger = setup_logger()
