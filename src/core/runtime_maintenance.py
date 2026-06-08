"""
運行時維護 — asyncio 懸掛任務清理、記憶體 GC。
"""

from __future__ import annotations

import asyncio
import gc

from src.utils.logger import logger


async def cleanup_orphaned_asyncio_tasks() -> int:
    """取消已完成/已取消以外的長時間懸掛 Task（僅開發診斷用）。"""
    current = asyncio.current_task()
    cancelled = 0
    for task in asyncio.all_tasks():
        if task is current or task.done():
            continue
        name = task.get_name()
        if name.startswith("ws_") or name.startswith("Task-"):
            continue
        try:
            task.cancel()
            cancelled += 1
        except Exception:
            pass
    if cancelled:
        logger.debug(f"已取消 {cancelled} 個懸掛 asyncio 任務")
    return cancelled


def run_memory_gc() -> dict:
    collected = gc.collect()
    return {"gc_collected": collected}
