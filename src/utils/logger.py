"""
日誌系統 — 控制台 + 文件輪轉；支援 SQ_LOG_FORMAT=json 結構化輸出
"""
from __future__ import annotations

import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

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


class JsonLogFormatter(logging.Formatter):
    """單行 JSON，便於 Loki / ELK 收集。"""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        for key in ("task_id", "user_id", "path", "status_code"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload, ensure_ascii=False)


def setup_logger(name: str = "stock_quant") -> logging.Logger:
    """
    配置日誌器

    - 控制台: 人類可讀（text）
    - 文件: text 或 json（由 SQ_LOG_FORMAT 控制）
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    if logger.handlers:
        return logger

    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    text_fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    use_json_files = settings.log_format.lower() == "json"
    file_fmt: logging.Formatter = JsonLogFormatter() if use_json_files else text_fmt

    console = logging.StreamHandler(_make_console_stream_safe())
    console.setLevel(logging.INFO)
    console.setFormatter(text_fmt)
    logger.addHandler(console)

    file_handler = RotatingFileHandler(
        log_dir / ("app.jsonl" if use_json_files else "app.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_fmt)
    logger.addHandler(file_handler)

    error_handler = RotatingFileHandler(
        log_dir / ("error.jsonl" if use_json_files else "error.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(file_fmt)
    logger.addHandler(error_handler)

    return logger


# 全局 logger
logger = setup_logger()
