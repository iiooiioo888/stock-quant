def _fetch_recent_task_rows(limit: int = 150) -> list[dict]:
    """從 task_log 讀取最近任務（不含 result，供列表合併）。"""
    try:
        from src.core.db import get_conn
        with get_conn() as conn:
            rows = conn.execute(
                """SELECT task_id, task_type, params_hash, title, status, progress, error,
                          created_at, completed_at, params_json
                   FROM task_log
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
        out = []
        for row in rows:
            params = {}
            if row[9]:
                try:
                    params = json.loads(row[9])
                except Exception:
                    params = {}
            meta = {}
            if params.get("source") == "scheduler" or params.get("scheduler_job_id"):
                meta["source"] = "scheduler"
                meta["scheduler_job_id"] = params.get("scheduler_job_id")
            out.append({
                "task_id": row[0],
                "task_type": row[1],
                "params_hash": row[2],
                "title": row[3] or "",
                "status": row[4],
                "progress": row[5] or 0,
                "error": row[6],
                "created_at": row[7] or "",
                "completed_at": row[8],
                "params": params,
                "meta": meta,
                "result": None,
                "from_db": True,
            })
        return out
    except Exception as e:
        logger.debug(f"讀取 task_log 列表跳過: {e}")
        return []


def load_recent_tasks_from_db(limit: int = 200) -> int:
    """啟動時將持久化任務灌入內存，避免重啟後任務中心為空。"""
    loaded = 0
    with _lock:
        for row in _fetch_recent_task_rows(limit=limit):
            tid = row["task_id"]
            if tid in _tasks:
                continue
            _tasks[tid] = row
            loaded += 1
    if loaded:
        logger.info(f"已從 task_log 載入 {loaded} 條歷史任務至任務中心")
    return loaded


def _merge_tasks_for_list(limit: int = 50) -> list[dict]:
    """合併內存與 task_log（內存狀態優先）。"""
    with _lock:
        merged: dict[str, dict] = {t["task_id"]: dict(t) for t in _tasks.values()}
    for row in _fetch_recent_task_rows(limit=max(limit * 3, 150)):
        tid = row.get("task_id")
        if tid and tid not in merged:
            merged[tid] = row
    tasks = list(merged.values())
    tasks.sort(key=lambda t: t.get("created_at", ""), reverse=True)
    return tasks[:limit]


def get_tasks(task_type: str = None, status: str = None, limit: int = 50) -> list[dict]:
    tasks = _merge_tasks_for_list(limit=limit)
    if task_type:
        tasks = [t for t in tasks if t["task_type"] == task_type]
    if status:
        tasks = [t for t in tasks if t["status"] == status]
    return [_task_summary(t) for t in tasks[:limit]]
