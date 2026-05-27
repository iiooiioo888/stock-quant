"""Patch task_manager for scheduled task visibility."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TM = ROOT / "src/core/task_manager.py"
TASKS_JS = ROOT / "static/js/pro/modules/tasks-pro.js"


def patch_task_manager():
    t = TM.read_text(encoding="utf-8")
    if "_merge_tasks_for_list" in t:
        print("task_manager already patched")
        return

    old = """def get_tasks(task_type: str = None, status: str = None, limit: int = 50) -> list[dict]:
    with _lock:
        tasks = list(_tasks.values())
    if task_type:
        tasks = [t for t in tasks if t["task_type"] == task_type]
    if status:
        tasks = [t for t in tasks if t["status"] == status]
    tasks.sort(key=lambda t: t.get("created_at", ""), reverse=True)
    return [_task_summary(t) for t in tasks[:limit]]"""

    new = (Path(__file__).parent / "_patch_scheduler_tasks_snippet.py").read_text(encoding="utf-8")
    if old not in t:
        raise SystemExit("get_tasks anchor missing")
    t = t.replace(old, new.rstrip() + "\n", 1)

    old_stats = """def get_task_stats() -> dict:
    with _lock:
        tasks = list(_tasks.values())"""
    new_stats = """def get_task_stats() -> dict:
    tasks = _merge_tasks_for_list(limit=_MAX_TASKS)"""
    t = t.replace(old_stats, new_stats, 1)

    old_sum = """    preview = _extract_result_preview(task)
    if preview:
        summary["result_preview"] = preview
    return summary


def _extract_result_preview(task: dict) -> Optional[dict]:"""

    new_sum = """    preview = _extract_result_preview(task)
    if preview:
        summary["result_preview"] = preview
    params = task.get("params") or {}
    if meta.get("source") == "scheduler" or params.get("source") == "scheduler":
        summary["source"] = "scheduler"
        summary["scheduler_job_id"] = meta.get("scheduler_job_id") or params.get("scheduler_job_id")
        summary["is_scheduled"] = True
    elif (task.get("title") or "").startswith("定時·"):
        summary["is_scheduled"] = True
    return summary


def _extract_result_preview(task: dict) -> Optional[dict]:"""
    t = t.replace(old_sum, new_sum, 1)

    TM.write_text(t, encoding="utf-8")
    print("task_manager patched")


def patch_tasks_js():
    t = TASKS_JS.read_text(encoding="utf-8")
    if "tk-scheduled-badge" in t:
        print("tasks-pro already patched")
        return
    old = """      const typeName = TC.typeName(t.task_type);
      const statusCls = t.status || 'pending';"""
    new = """      const typeName = TC.typeName(t.task_type);
      const schedBadge = t.is_scheduled
        ? '<span class="badge b-am tk-scheduled-badge" title="定時任務">定時</span>'
        : '';
      const statusCls = t.status || 'pending';"""
    if old not in t:
        raise SystemExit("tasks-pro card anchor missing")
    t = t.replace(old, new, 1)
    old2 = """          <div class="tk-card-title-row">
            <span class="tk-card-title">${TC.escapeHtml(t.title || typeName)}</span>"""
    new2 = """          <div class="tk-card-title-row">
            ${schedBadge}
            <span class="tk-card-title">${TC.escapeHtml(t.title || typeName)}</span>"""
    if old2 not in t:
        raise SystemExit("tasks-pro title row missing")
    t = t.replace(old2, new2, 1)
    TASKS_JS.write_text(t, encoding="utf-8")
    print("tasks-pro patched")


if __name__ == "__main__":
    patch_task_manager()
    patch_tasks_js()
