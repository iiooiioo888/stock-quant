"""組合類 API 統一走異步任務（與 /api/portfolio 一致，納入任務面板）。"""
from __future__ import annotations

from typing import Any, Callable


def _codes_from_allocations(allocations: list | None) -> list[str]:
    out: list[str] = []
    for a in allocations or []:
        if isinstance(a, dict):
            c = (a.get("code") or "").strip()
            if c:
                out.append(c)
    return out


def dispatch_portfolio_async(
    method: str,
    allocations: list | None,
    work_fn: Callable[[], Any],
    *,
    task_extra: dict | None = None,
    title: str | None = None,
    count_override: int | None = None,
) -> dict:
    """
    建立 task_type=portfolio 任務並派發至線程池。

    - params 含 method / allocations / codes / count 及 task_extra，供去重與緩存鍵。
    - title 可自訂；預設為「組合回測 · {method}」。
    """
    from src.api.dispatch import dispatch_async_task
    from src.core.task_manager import create_task

    extra = dict(task_extra or {})
    codes = _codes_from_allocations(allocations)
    n_alloc = len(allocations or [])
    n = count_override if count_override is not None else n_alloc
    base: dict[str, Any] = {
        "method": method,
        "allocations": allocations or [],
        "codes": codes,
        "count": n,
        **extra,
    }
    label = title or f"組合回測 · {method}"
    display_title = f"{label}（{n}子）" if n else label
    task = create_task("portfolio", base, title=display_title)
    if task.get("is_duplicate"):
        return {
            "success": True,
            "task_id": task["task_id"],
            "is_duplicate": True,
            "message": f"相同組合任務（{method}）正在執行中，請等待完成",
            "async": True,
        }
    tid = task["task_id"]
    code0 = codes[0] if codes else None
    return dispatch_async_task(
        tid,
        work_fn,
        cache_namespace="portfolio",
        cache_params=base,
        cache_code=code0,
    )
