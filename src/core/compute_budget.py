"""
全局計算資源預算 — 避免多任務嵌套並行導致 CPU/進程爆炸
"""

import os

HEAVY_TASK_TYPES = frozenset(
    {
        "backtest",
        "backtest_advanced",
        "backtest_multi",
        "optimize",
        "auto_optimize",
        "walkforward",
        "portfolio",
    }
)


def cpu_count() -> int:
    return os.cpu_count() or 4


def count_running_tasks(exclude_task_id: str = None) -> int:
    from src.core.task_manager import count_in_flight_tasks

    return count_in_flight_tasks(exclude_task_id)


def count_running_heavy_tasks(exclude_task_id: str = None) -> int:
    from src.core.task_manager import count_in_flight_heavy

    return count_in_flight_heavy(exclude_task_id)


def get_process_workers(
    per_job_cap: int = 8,
    task_id: str = None,
    min_workers: int = 1,
) -> int:
    try:
        from src.config import settings

        configured = getattr(settings, "task_grid_workers", 0)
        if configured and configured > 0:
            per_job_cap = min(per_job_cap, configured)
    except Exception:
        pass

    cpu = cpu_count()
    budget = max(1, cpu - 1)
    heavy = count_running_heavy_tasks(exclude_task_id=task_id)
    heavy = max(heavy, 1)
    workers = max(min_workers, budget // heavy)
    return min(per_job_cap, workers)


def get_thread_workers(
    configured: int,
    task_id: str = None,
    min_workers: int = 1,
) -> int:
    cpu = cpu_count()
    running = count_running_tasks(exclude_task_id=task_id)
    running = max(running, 1)
    budget = max(1, cpu - 1)
    return max(min_workers, min(configured, budget // running))


def should_parallelize_optimize_all(task_id: str = None) -> bool:
    try:
        from src.config import settings

        if not getattr(settings, "optimize_all_parallel", False):
            return False
    except Exception:
        return False
    return count_running_heavy_tasks(exclude_task_id=task_id) <= 1
