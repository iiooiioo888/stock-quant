"""
Redis 任務狀態存儲 — 替代進程內存 _tasks dict，支持多實例共享。

當 Redis 不可用時自動降級到進程內存（與現有行為一致）。
"""
from __future__ import annotations

import json
from typing import Optional

from src.utils.logger import logger

# Redis key 前綴
_PREFIX = "sq:task:"
_PUBSUB_CHANNEL = "sq:task-events"

_redis_client = None
_available = False
_initialized = False


def _get_redis():
    """懶初始化 Redis 連接（複用 cache.py 的連接池）。"""
    global _redis_client, _available, _initialized
    if _initialized:
        return _redis_client
    _initialized = True
    try:
        from src.config import settings
        if not getattr(settings, "redis_enabled", False):
            logger.info("📦 任務存儲: Redis 未啟用，使用進程內存")
            return None
        import redis as redis_lib
        url = getattr(settings, "redis_url", "redis://localhost:6379/0")
        pwd = getattr(settings, "redis_password", "")
        _redis_client = redis_lib.from_url(
            url,
            password=pwd or None,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        _redis_client.ping()
        _available = True
        logger.info("✅ 任務存儲: Redis 已連接")
        return _redis_client
    except Exception as e:
        logger.debug(f"任務存儲 Redis 不可用: {e}")
        _redis_client = None
        _available = False
        return None


def is_available() -> bool:
    _get_redis()
    return _available


def save_task(task_id: str, data: dict, ttl: int = 86400 * 7) -> None:
    """保存任務狀態到 Redis（Hash 結構）。"""
    r = _get_redis()
    if not r:
        return
    try:
        key = f"{_PREFIX}{task_id}"
        # 序列化：將 dict 轉為 flat hash（Redis Hash 只支持 string）
        flat = {}
        for k, v in data.items():
            if isinstance(v, (dict, list)):
                flat[k] = json.dumps(v, ensure_ascii=False, default=str)
            elif v is None:
                flat[k] = ""
            else:
                flat[k] = str(v)
        pipe = r.pipeline()
        pipe.delete(key)
        if flat:
            pipe.hset(key, mapping=flat)
        pipe.expire(key, ttl)
        pipe.execute()
    except Exception as e:
        logger.debug(f"Redis save_task 失敗: {e}")


def load_task(task_id: str) -> Optional[dict]:
    """從 Redis 讀取任務狀態。"""
    r = _get_redis()
    if not r:
        return None
    try:
        key = f"{_PREFIX}{task_id}"
        flat = r.hgetall(key)
        if not flat:
            return None
        return _unflatten(flat)
    except Exception as e:
        logger.debug(f"Redis load_task 失敗: {e}")
        return None


def update_task_fields(task_id: str, updates: dict, ttl: int = 86400 * 7) -> None:
    """增量更新任務字段（不覆蓋整個 Hash）。"""
    r = _get_redis()
    if not r:
        return
    try:
        key = f"{_PREFIX}{task_id}"
        flat = {}
        for k, v in updates.items():
            if isinstance(v, (dict, list)):
                flat[k] = json.dumps(v, ensure_ascii=False, default=str)
            elif v is None:
                flat[k] = ""
            else:
                flat[k] = str(v)
        if flat:
            pipe = r.pipeline()
            pipe.hset(key, mapping=flat)
            pipe.expire(key, ttl)
            pipe.execute()
    except Exception as e:
        logger.debug(f"Redis update_task_fields 失敗: {e}")


def delete_task(task_id: str) -> None:
    """從 Redis 刪除任務。"""
    r = _get_redis()
    if not r:
        return
    try:
        r.delete(f"{_PREFIX}{task_id}")
    except Exception as e:
        logger.debug(f"Redis delete_task 失敗: {e}")


def publish_task_event(event: dict) -> None:
    """通過 Redis Pub/Sub 發布任務事件（跨實例廣播）。"""
    r = _get_redis()
    if not r:
        return
    try:
        payload = json.dumps(event, ensure_ascii=False, default=str)
        r.publish(_PUBSUB_CHANNEL, payload)
    except Exception as e:
        logger.debug(f"Redis publish 失敗: {e}")


def subscribe_task_events(callback) -> None:
    """訂閱任務事件（在後台線程中運行）。"""
    r = _get_redis()
    if not r:
        return
    import threading

    def _listen():
        try:
            pubsub = r.pubsub()
            pubsub.subscribe(_PUBSUB_CHANNEL)
            for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        callback(data)
                    except Exception:
                        pass
        except Exception as e:
            logger.debug(f"Redis Pub/Sub 監聽退出: {e}")

    t = threading.Thread(target=_listen, daemon=True, name="task-event-subscriber")
    t.start()
    logger.info("✅ 任務事件訂閱者已啟動")


def get_active_task_ids(user_id: int | None = None) -> list[str]:
    """獲取活躍任務 ID 列表（用於並發限制等）。"""
    r = _get_redis()
    if not r:
        return []
    try:
        # SCAN 模式查找所有任務
        pattern = f"{_PREFIX}*"
        active = []
        cursor = 0
        while True:
            cursor, keys = r.scan(cursor, match=pattern, count=100)
            for key in keys:
                status = r.hget(key, "status")
                if status in ("pending", "running", "retrying"):
                    if user_id is not None:
                        uid = r.hget(key, "user_id")
                        if str(uid) != str(user_id):
                            continue
                    task_id = key.replace(_PREFIX, "")
                    active.append(task_id)
            if cursor == 0:
                break
        return active
    except Exception as e:
        logger.debug(f"Redis get_active_task_ids 失敗: {e}")
        return []


def count_active_by_user(user_id: int) -> int:
    """計算用戶的活躍任務數（跨實例）。"""
    return len(get_active_task_ids(user_id=user_id))


def cleanup_expired(max_age_days: int = 7) -> int:
    """清理過期任務（已由 TTL 自動處理，此方法供手動觸發）。"""
    r = _get_redis()
    if not r:
        return 0
    try:
        pattern = f"{_PREFIX}*"
        removed = 0
        cursor = 0
        while True:
            cursor, keys = r.scan(cursor, match=pattern, count=100)
            for key in keys:
                ttl = r.ttl(key)
                if ttl == -1:  # 無 TTL 的 key
                    r.expire(key, 86400 * max_age_days)
                    removed += 1
            if cursor == 0:
                break
        return removed
    except Exception as e:
        logger.debug(f"Redis cleanup 失敗: {e}")
        return 0


def stats() -> dict:
    """返回任務存儲統計信息。"""
    r = _get_redis()
    if not r:
        return {"backend": "memory", "available": False}
    try:
        pattern = f"{_PREFIX}*"
        total = 0
        by_status = {}
        cursor = 0
        while True:
            cursor, keys = r.scan(cursor, match=pattern, count=100)
            total += len(keys)
            for key in keys:
                status = r.hget(key, "status") or "unknown"
                by_status[status] = by_status.get(status, 0) + 1
            if cursor == 0:
                break
        return {
            "backend": "redis",
            "available": True,
            "total_tasks": total,
            "by_status": by_status,
        }
    except Exception as e:
        return {"backend": "redis", "available": False, "error": str(e)}


def _unflatten(flat: dict) -> dict:
    """將 Redis Hash 的 string 值還原為 Python 對象。"""
    out = {}
    for k, v in flat.items():
        if v == "":
            out[k] = None
        elif k in ("params", "result", "meta", "_cache_meta"):
            try:
                out[k] = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                out[k] = v
        elif k == "progress":
            try:
                out[k] = int(v)
            except (ValueError, TypeError):
                out[k] = 0
        elif k in ("user_id",):
            try:
                out[k] = int(v) if v else None
            except (ValueError, TypeError):
                out[k] = None
        else:
            out[k] = v
    return out
