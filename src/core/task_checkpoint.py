"""長任務斷點 — 寫入 task.meta.checkpoint，重跑時可跳過已完成子項。"""

from __future__ import annotations

from typing import Any, Optional


def save_checkpoint(task_id: Optional[str], payload: dict[str, Any]) -> None:
    if not task_id:
        return
    from src.core.task_manager import update_task_meta

    update_task_meta(task_id, checkpoint=payload)


def load_checkpoint(task_id: Optional[str]) -> dict[str, Any]:
    if not task_id:
        return {}
    from src.core.task_manager import get_task

    task = get_task(task_id) or {}
    cp = (task.get("meta") or {}).get("checkpoint")
    return dict(cp) if isinstance(cp, dict) else {}
