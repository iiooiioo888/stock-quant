from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def patch_config():
    p = ROOT / "src/config.py"
    t = p.read_text(encoding="utf-8")
    if "celery_enabled" in t:
        print("config celery ok")
        return
    anchor = "    heatmap_max_workers: int = Field(default=4, ge=1, le=16)"
    ins = """

    # ====== Celery 任務佇列 ======
    celery_enabled: bool = False
    celery_broker_url: str = ""
    celery_result_backend: str = ""
    db_read_replica_path: str = ""
    prometheus_enabled: bool = True
    runtime_gc_interval_sec: float = Field(default=3600.0, ge=300.0, le=86400.0)
"""
    p.write_text(t.replace(anchor, anchor + ins, 1), encoding="utf-8")
    print("config patched")


def patch_submit_task():
    p = ROOT / "src/core/task_manager.py"
    t = p.read_text(encoding="utf-8")
    old = """def submit_task(task_id: str, work_fn: Callable) -> None:
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            raise ValueError(f"任務不存在: {task_id}")
        task["_worker_fn"] = work_fn
        task["last_accessed"] = time.time()
    _drain_queue()"""
    new = """def submit_task(task_id: str, work_fn: Callable) -> None:
    from src.config import settings
    from src.core.task_executors import has_executor

    with _lock:
        task = _tasks.get(task_id)
        if not task:
            raise ValueError(f"任務不存在: {task_id}")
        task_type = task.get("task_type") or ""
        if work_fn is not None:
            task["_worker_fn"] = work_fn
        task["last_accessed"] = time.time()

    if getattr(settings, "celery_enabled", False) and has_executor(task_type):
        try:
            from src.core.celery_tasks import enqueue_celery_task
            if enqueue_celery_task(task_id):
                with _lock:
                    t = _tasks.get(task_id)
                    if t:
                        t.pop("_worker_fn", None)
                return
        except Exception as e:
            logger.debug(f"Celery 提交失敗，回退線程池: {e}")

    if work_fn is None and has_executor(task_type):
        def _registry_work():
            from src.core.task_worker import run_registered_task
            return run_registered_task(task_id)
        with _lock:
            task = _tasks.get(task_id)
            if task:
                task["_worker_fn"] = _registry_work
    _drain_queue()"""
    if old not in t:
        raise SystemExit("submit_task anchor missing")
    p.write_text(t.replace(old, new, 1), encoding="utf-8")
    print("submit_task patched")


def patch_dispatch():
    p = ROOT / "src/api/dispatch.py"
    t = p.read_text(encoding="utf-8")
    if "_cache_meta" in t:
        print("dispatch ok")
        return
    old = """    submit_task(task_id, _work)
    return {"success": True, "task_id": task_id, "async": True}"""
    new = """    if cache_namespace and cache_params is not None:
        from src.core.task_manager import get_task
        import src.core.task_manager as tm
        with tm._lock:
            t = tm._tasks.get(task_id)
            if t is not None:
                t["_cache_meta"] = {
                    "namespace": cache_namespace,
                    "params": cache_params,
                    "code": cache_code,
                }

    submit_task(task_id, _work)
    return {"success": True, "task_id": task_id, "async": True}"""
    p.write_text(t.replace(old, new, 1), encoding="utf-8")
    print("dispatch patched")


def patch_cache():
    p = ROOT / "src/core/cache.py"
    t = p.read_text(encoding="utf-8")
    if "CACHE_INVALIDATION_RULES" in t:
        print("cache rules ok")
        return
    ins = '''
CACHE_INVALIDATION_RULES = {
    "kline:*": {"trigger": "data_update", "scope": "code_specific"},
    "backtest:*": {"trigger": "strategy_change", "scope": "param_hash"},
    "optimize:*": {"trigger": "market_regime_change", "scope": "global"},
    "sq:compute:*": {"trigger": "data_update", "scope": "code_specific"},
}


def invalidate_by_rule(trigger: str, code: str | None = None) -> int:
    """按規則觸發失效（L1 + Redis 前綴）。"""
    removed = 0
    cache = get_cache()
    prefixes = [
        k.replace("*", "")
        for k, rule in CACHE_INVALIDATION_RULES.items()
        if rule.get("trigger") == trigger
    ]
    for prefix in prefixes:
        if code and rule_scope_is_code_specific(prefix):
            pattern = f"{prefix}*{code}*"
        else:
            pattern = f"{prefix}*"
        if cache.is_redis_available:
            try:
                cursor = 0
                while True:
                    cursor, keys = cache._redis_client.scan(cursor, match=pattern, count=200)
                    if keys:
                        cache._redis_client.delete(*keys)
                        removed += len(keys)
                    if cursor == 0:
                        break
            except Exception:
                pass
        for k in list(cache._lru._cache.keys()):
            if k.startswith(prefix.rstrip(":")) and (code is None or code in k):
                cache._lru.delete(k)
                removed += 1
    return removed


def rule_scope_is_code_specific(prefix: str) -> bool:
    for k, rule in CACHE_INVALIDATION_RULES.items():
        if k.startswith(prefix):
            return rule.get("scope") == "code_specific"
    return False

'''
    anchor = "PREFIX_KLINE = \"sq:kline:\""
    t = t.replace(anchor, ins + anchor, 1)

    old_get = """        l1 = self._lru.get(key)
        if l1 is not None:
            self._hits_l1 += 1
            return l1"""
    new_get = """        l1 = self._lru.get(key)
        if l1 is not None:
            self._hits_l1 += 1
            try:
                from src.utils.metrics import record_cache_hit
                record_cache_hit("l1")
            except Exception:
                pass
            return l1"""
    t = t.replace(old_get, new_get, 1)

    old_miss = """        self._misses += 1
        return None"""
    new_miss = """        self._misses += 1
        try:
            from src.utils.metrics import record_cache_miss
            record_cache_miss("l1")
        except Exception:
            pass
        return None"""
    t = t.replace(old_miss, new_miss, 1)

    old_hit2 = """                    self._hits_l2 += 1
                    self._lru.set(key, value, ttl=0)
                    return value"""
    new_hit2 = """                    self._hits_l2 += 1
                    self._lru.set(key, value, ttl=0)
                    try:
                        from src.utils.metrics import record_cache_hit
                        record_cache_hit("l2")
                    except Exception:
                        pass
                    return value"""
    t = t.replace(old_hit2, new_hit2, 1)

    p.write_text(t, encoding="utf-8")
    print("cache patched")


def patch_app_timing():
    p = ROOT / "src/api/app.py"
    t = p.read_text(encoding="utf-8")
    old = """@app.middleware("http")
async def api_timing_middleware(request: Request, call_next):
    \"\"\"Add X-Response-Time-Ms header for /api routes.\"\"\"
    if not (request.url.path or "").startswith("/api/"):
        return await call_next(request)
    t0 = time.perf_counter()
    response = await call_next(request)
    ms = int((time.perf_counter() - t0) * 1000)
    response.headers["X-Response-Time-Ms"] = str(ms)
    return response"""
    new = """@app.middleware("http")
async def api_timing_middleware(request: Request, call_next):
    \"\"\"Add X-Response-Time-Ms header for /api routes.\"\"\"
    path = request.url.path or ""
    if not path.startswith("/api/"):
        return await call_next(request)
    t0 = time.perf_counter()
    response = await call_next(request)
    ms = int((time.perf_counter() - t0) * 1000)
    response.headers["X-Response-Time-Ms"] = str(ms)
    try:
        from src.utils.metrics import observe_request
        observe_request(request.method, path, response.status_code, (time.perf_counter() - t0))
    except Exception:
        pass
    return response"""
    if old in t:
        p.write_text(t.replace(old, new, 1), encoding="utf-8")
        print("app timing patched")
    else:
        print("app timing skip")


def patch_scheduler():
    p = ROOT / "src/core/scheduler.py"
    t = p.read_text(encoding="utf-8")
    if "runtime_maintenance" in t:
        print("scheduler ok")
        return
    old = """def start_scheduler():"""
    hook = '''

def _job_runtime_maintenance():
    from src.core.runtime_maintenance import run_memory_gc
    run_memory_gc()


'''
    if hook.strip() not in t:
        t = t.replace("def start_scheduler():", hook + "def start_scheduler():", 1)
    if "_job_runtime_maintenance" not in t or "runtime_maintenance" in t:
        pass
    # register job inside start_scheduler after scheduler created
    marker = "        scheduler.start()"
    reg = """        if getattr(settings, "runtime_gc_interval_sec", 3600) > 0:
            scheduler.add_job(
                _job_runtime_maintenance,
                "interval",
                seconds=int(settings.runtime_gc_interval_sec),
                id="runtime_maintenance",
                replace_existing=True,
            )
"""
    if marker in t and reg.strip() not in t:
        t = t.replace(marker, reg + marker, 1)
    p.write_text(t, encoding="utf-8")
    print("scheduler patched")


def patch_requirements():
    p = ROOT / "requirements.txt"
    t = p.read_text(encoding="utf-8")
    for pkg in ("celery>=5.3.0", "prometheus-client>=0.19.0"):
        if pkg.split(">")[0] not in t:
            t = t.rstrip() + f"\n{pkg}\n"
    p.write_text(t, encoding="utf-8")
    print("requirements patched")


def patch_docker():
    p = ROOT / "docker-compose.yml"
    t = p.read_text(encoding="utf-8")
    if "celery-worker" in t:
        print("docker celery ok")
        return
    svc = """
  celery-worker:
    build: .
    container_name: stock-quant-celery
    command: celery -A celery_worker worker --loglevel=info --concurrency=4
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    env_file:
      - .env
    environment:
      TZ: Asia/Shanghai
      SQ_DB_PATH: /app/data/stock.db
      SQ_LOG_DIR: /app/logs
      SQ_REDIS_ENABLED: ${SQ_REDIS_ENABLED:-true}
      SQ_REDIS_URL: redis://:${SQ_REDIS_PASSWORD:-stockquant_redis_2024}@redis:6379/0
      SQ_CELERY_ENABLED: ${SQ_CELERY_ENABLED:-true}
      SQ_CELERY_BROKER_URL: redis://:${SQ_REDIS_PASSWORD:-stockquant_redis_2024}@redis:6379/1
    depends_on:
      redis:
        condition: service_healthy
      app:
        condition: service_healthy
    restart: unless-stopped
    profiles:
      - celery

"""
    t = t.replace("  # ====== Nginx", svc + "  # ====== Nginx", 1)
    if "SQ_CELERY_ENABLED" not in t:
        t = t.replace(
            "SQ_HEATMAP_MAX_WORKERS: ${SQ_HEATMAP_MAX_WORKERS:-4}",
            "SQ_HEATMAP_MAX_WORKERS: ${SQ_HEATMAP_MAX_WORKERS:-4}\n      SQ_CELERY_ENABLED: ${SQ_CELERY_ENABLED:-false}",
            1,
        )
    p.write_text(t, encoding="utf-8")
    print("docker patched")


def patch_tasks_js():
    p = ROOT / "static/js/pro/modules/tasks-pro.js"
    t = p.read_text(encoding="utf-8")
    if "_patchTaskFromWs" in t:
        print("tasks-pro ok")
        return
    patch_fn = '''
    _patchTaskFromWs(data) {
      if (!data?.task_id || !this._lastData?.tasks) return false;
      const idx = this._lastData.tasks.findIndex((t) => t.task_id === data.task_id);
      if (idx < 0) return false;
      const cur = this._lastData.tasks[idx];
      const next = {
        ...cur,
        status: data.status ?? cur.status,
        progress: data.progress ?? cur.progress,
        error: data.error ?? cur.error,
      };
      this._lastData.tasks[idx] = next;
      const card = document.querySelector(`[data-task-id="${data.task_id}"]`);
      if (card) {
        const fill = card.querySelector('.tk-card-progress-fill');
        const pct = card.querySelector('.tk-pct');
        if (fill) fill.style.width = `${next.progress || 0}%`;
        if (pct) pct.textContent = `${next.progress || 0}%`;
      }
      if (this._detailId === data.task_id) this._renderDetail(next);
      return true;
    },
'''
    t = t.replace("    _getFilters() {", patch_fn + "\n    _getFilters() {", 1)
    old = """          if (!data.type.startsWith('task_')) return;
          this._pollCount = 0;
          this.refresh(true);"""
    new = """          if (!data.type.startsWith('task_')) return;
          if (data.type === 'task_progress' && this._patchTaskFromWs(data)) return;
          this._pollCount = 0;
          this.refresh(true);"""
    t = t.replace(old, new, 1)
    # ensure cards have data-task-id
  # check render card - add data-task-id attribute
    if 'data-task-id' not in t:
        old_card = 'class="tk-card'
        if old_card in t:
            t = t.replace(
                '<article class="tk-card',
                '<article class="tk-card" data-task-id="${t.task_id}"',
                1,
            )
    p.write_text(t, encoding="utf-8")
    print("tasks-pro patched")


def patch_history():
    p = ROOT / "src/core/history.py"
    t = p.read_text(encoding="utf-8")
    if "async def preload_kline_range" in t:
        print("history ok")
        return
    fn = '''

async def preload_kline_range(code: str, start_date: str = None, end_date: str = None) -> int:
    """異步預載 K 線至 LRU（不阻塞事件循環）。"""
    import asyncio
    from src.core.db import preload_kline_range as _sync_preload
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _sync_preload, code, start_date, end_date)

'''
    t = t.rstrip() + fn
    p.write_text(t, encoding="utf-8")
    print("history patched")


def patch_env():
    p = ROOT / ".env.example"
    t = p.read_text(encoding="utf-8")
    if "SQ_CELERY_ENABLED" in t:
        print("env ok")
        return
    t = t.replace(
        "SQ_HEATMAP_MAX_WORKERS=4",
        "SQ_HEATMAP_MAX_WORKERS=4\n# SQ_CELERY_ENABLED=false\n# SQ_CELERY_BROKER_URL=redis://:password@localhost:6379/1",
        1,
    )
    p.write_text(t, encoding="utf-8")
    print("env patched")


def main():
    patch_config()
    patch_submit_task()
    patch_dispatch()
    patch_cache()
    patch_app_timing()
    patch_scheduler()
    patch_requirements()
    patch_docker()
    patch_tasks_js()
    patch_history()
    patch_env()


if __name__ == "__main__":
    main()
