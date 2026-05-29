"""
Patch task_manager.py to integrate Redis task store.
Three precise insertions:
1. _save_task_to_db: add Redis sync at top
2. ensure_task_in_memory: try Redis before DB
3. _notify_task_update: add Redis Pub/Sub broadcast
"""
import re

filepath = "src/core/task_manager.py"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Patch _save_task_to_db: add Redis sync right after function signature
old_save = '''def _save_task_to_db(task: dict, force: bool = False):
    if not force and task.get("status") in (STATUS_RUNNING, STATUS_RETRYING):'''
new_save = '''def _save_task_to_db(task: dict, force: bool = False):
    # === Redis 同步（非阻塞，失敗不影響主流程）===
    try:
        from src.core import task_store
        if task_store.is_available():
            task_store.save_task(task.get("task_id", ""), task)
    except Exception:
        pass
    if not force and task.get("status") in (STATUS_RUNNING, STATUS_RETRYING):'''

assert old_save in content, "Cannot find _save_task_to_db signature"
content = content.replace(old_save, new_save, 1)
print("[OK] Patched _save_task_to_db with Redis sync")

# 2. Patch ensure_task_in_memory: try Redis before DB
old_ensure = '''def ensure_task_in_memory(task_id: str) -> bool:
    """跨進程（Celery Worker）從 DB 還原任務至本進程記憶體。"""
    with _lock:
        if task_id in _tasks:
            return True
        row = _load_task_from_db(task_id)
        if not row:
            return False
        _tasks[task_id] = row
        return True'''
new_ensure = '''def ensure_task_in_memory(task_id: str) -> bool:
    """跨進程（Celery Worker）從 DB 或 Redis 還原任務至本進程記憶體。"""
    with _lock:
        if task_id in _tasks:
            return True
        # 先嘗試 Redis（更快）
        try:
            from src.core import task_store
            if task_store.is_available():
                cached = task_store.load_task(task_id)
                if cached:
                    _tasks[task_id] = cached
                    return True
        except Exception:
            pass
        row = _load_task_from_db(task_id)
        if not row:
            return False
        _tasks[task_id] = row
        return True'''

assert old_ensure in content, "Cannot find ensure_task_in_memory"
content = content.replace(old_ensure, new_ensure, 1)
print("[OK] Patched ensure_task_in_memory with Redis fallback")

# 3. Patch _notify_task_update: add Redis Pub/Sub
old_notify = '''def _notify_task_update(task_id: str, event: str = "task_update"):
    """推送任務狀態更新（非阻塞）。"""
    with _lock:
        if not _broadcasters:
            return
    try:
        task = _tasks.get(task_id)'''
new_notify = '''def _notify_task_update(task_id: str, event: str = "task_update"):
    """推送任務狀態更新（非阻塞），同步到 Redis Pub/Sub。"""
    # === Redis Pub/Sub 跨實例廣播 ===
    try:
        from src.core import task_store
        if task_store.is_available():
            task = _tasks.get(task_id)
            if task:
                task_store.publish_task_event({
                    "type": event,
                    "task_id": task_id,
                    "status": task.get("status"),
                    "progress": task.get("progress", 0),
                })
    except Exception:
        pass

    with _lock:
        if not _broadcasters:
            return
    try:
        task = _tasks.get(task_id)'''

assert old_notify in content, "Cannot find _notify_task_update"
content = content.replace(old_notify, new_notify, 1)
print("[OK] Patched _notify_task_update with Redis Pub/Sub")

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("\n=== All patches applied successfully ===")