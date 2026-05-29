"""健康檢查 API 路由"""
import time
import shutil

from fastapi import APIRouter, Response

from src.config import settings
from src.core.db import get_db_stats
from src.api import state
from src.core.data_sources import health_check as data_sources_health_check
from src.utils.logger import logger

router = APIRouter(tags=["health"])

@router.get("/api/health")
async def health_check():
    """健康檢查"""
    from src.core.api_cache import cached_response

    def _build():
        uptime_sec = int(time.time() - state.start_time)
        hours, remainder = divmod(uptime_sec, 3600)
        minutes, seconds = divmod(remainder, 60)

        try:
            stats = get_db_stats()
            db_status = "ok"
        except Exception:
            stats = {"db_size_mb": 0, "total_stocks": 0, "total_alerts": 0}
            db_status = "error"

        data_ready = stats.get("total_stocks", 0) > 0
        return {
            "status": "ok",
            "version": settings.app_version,
            "database": db_status,
            "data_ready": data_ready,
            "ws_auth_required": settings.effective_ws_auth_required,
            "billing_dev_upgrade": bool(getattr(settings, "billing_dev_upgrade", True)),
            "uptime": f"{hours}h {minutes}m {seconds}s",
            **stats,
        }

    return cached_response("api:health", ttl=3, builder=_build)


@router.get("/api/health/detailed")
async def health_detailed():
    """
    詳細健康檢查 — 包含 Redis、DB、磁盤、內存狀態
    """
    import shutil

    uptime_sec = int(time.time() - state.start_time)
    hours, remainder = divmod(uptime_sec, 3600)
    minutes, seconds = divmod(remainder, 60)

    result = {
        "status": "ok",
        "version": settings.app_version,
        "uptime": f"{hours}h {minutes}m {seconds}s",
        "uptime_seconds": uptime_sec,
    }

    # ---- 數據庫狀態 ----
    try:
        stats = get_db_stats()
        result["database"] = {"status": "ok", **stats}
    except Exception as e:
        result["database"] = {"status": "error", "error": str(e)}
        result["status"] = "degraded"

    # ---- 數據管線 / 索引 ----
    try:
        from src.core.pipeline_observability import get_pipeline_metrics
        from src.core.database.index_audit import audit_indexes

        result["pipeline_metrics"] = get_pipeline_metrics()
        result["index_audit"] = audit_indexes()
        if not result["index_audit"].get("ok"):
            result["status"] = "degraded"
    except Exception as e:
        result["pipeline_metrics"] = {"error": str(e)}

    # ---- Redis 狀態 ----
    try:
        from src.core.cache import get_cache
        cache = get_cache()
        cache_stats = cache.stats()
        result["redis"] = {
            "available": cache.is_redis_available,
            "backend": cache_stats.get("backend", "unknown"),
            **cache_stats,
        }
    except Exception as e:
        result["redis"] = {"available": False, "error": str(e)}

    # ---- 磁盤空間 ----
    try:
        disk = shutil.disk_usage("/")
        result["disk"] = {
            "total_gb": round(disk.total / (1024**3), 2),
            "used_gb": round(disk.used / (1024**3), 2),
            "free_gb": round(disk.free / (1024**3), 2),
            "usage_pct": round(disk.used / disk.total * 100, 1),
        }
    except Exception:
        result["disk"] = {"status": "unavailable"}

    # ---- 內存使用 ----
    try:
        import resource
        usage = resource.getrusage(resource.RUSAGE_SELF)
        # maxrss 單位：Linux 是 KB，macOS 是 bytes
        import sys
        maxrss_kb = usage.ru_maxrss if sys.platform == "linux" else usage.ru_maxrss / 1024
        result["memory"] = {
            "max_rss_mb": round(maxrss_kb / 1024, 2),
        }
        # 嘗試 psutil 獲取更詳細信息
        try:
            import psutil
            proc = psutil.Process()
            mem_info = proc.memory_info()
            result["memory"]["rss_mb"] = round(mem_info.rss / (1024**2), 2)
            result["memory"]["vms_mb"] = round(mem_info.vms / (1024**2), 2)
            sys_mem = psutil.virtual_memory()
            result["memory"]["system_total_gb"] = round(sys_mem.total / (1024**3), 2)
            result["memory"]["system_available_gb"] = round(sys_mem.available / (1024**3), 2)
            result["memory"]["system_usage_pct"] = sys_mem.percent
        except ImportError:
            pass
    except Exception:
        result["memory"] = {"status": "unavailable"}

    return result


@router.get("/api/data-sources/health")
async def data_sources_health():
    """
    數據源健康檢查端點（Phase 1 穩定性優化）
    
    返回所有已註冊數據源的狀態，包括：
    - 可用性（是否熔斷/超限）
    - 失敗次數
    - 今日調用次數
    - 動態評分（用於智能排隊）
    - IB/TWS 連接狀態（如適用）
    
    用途：
    - 監控數據源穩定性
    - 觸發告警（當某類別所有源均不可用）
    - 前端顯示數據源狀態儀表板
    """
    try:
        health = data_sources_health_check()
        overall_status = "ok"
        degraded_categories = []
        
        for category, info in health.items():
            if info.get("status") == "degraded":
                degraded_categories.append(category)
                overall_status = "degraded"
        
        return {
            "status": overall_status,
            "timestamp": time.time(),
            "categories": health,
            "degraded_categories": degraded_categories,
            "total_categories": len(health),
            "healthy_categories": len(health) - len(degraded_categories),
        }
    except Exception as e:
        logger.error(f"數據源健康檢查失敗：{e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "timestamp": time.time(),
        }


@router.get("/metrics")
async def prometheus_metrics():
    """Prometheus 指標（需安裝 prometheus-client）。"""
    from src.utils.metrics import metrics_payload

    body, content_type = metrics_payload()
    return Response(content=body, media_type=content_type)
