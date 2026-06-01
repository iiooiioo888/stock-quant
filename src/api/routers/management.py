"""management 路由（P5 從 app.py 拆分）。"""
import json
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from src.config import settings
from src.core.auth import require_auth, require_admin, get_current_user
from src.models.user import User
from src.utils.logger import logger

router = APIRouter()


@router.get("/api/data-sources")
async def get_data_sources():
    """獲取所有數據源狀態"""
    from src.core.data_sources import health_check
    return {"sources": health_check()}




@router.get("/api/data-sources/health")
async def data_sources_health_check():
    """
    數據源健康檢查端點（Phase 1 P1-5）
    
    提供詳細的數據源健康狀態，包括：
    - 各類別數據源可用性
    - 熔斷狀態
    - 今日請求次數
    - 動態評分
    """
    from src.core.data_sources import health_check, get_all_sources
    
    health = health_check()
    all_sources = get_all_sources()
    
    # 計算整體健康分數
    total_available = 0
    total_sources = 0
    degraded_categories = []
    
    for cat, info in health.items():
        total_available += info.get("available", 0)
        total_sources += info.get("total", 0)
        if info.get("status") != "ok":
            degraded_categories.append(cat)
    
    health_score = (total_available / total_sources * 100) if total_sources > 0 else 0
    
    return {
        "status": "ok" if health_score >= 80 else "degraded" if health_score >= 50 else "critical",
        "health_score": round(health_score, 2),
        "total_available": total_available,
        "total_sources": total_sources,
        "degraded_categories": degraded_categories,
        "categories": health,
        "detailed_sources": all_sources,
        "timestamp": time.time(),
    }




@router.get("/api/status")
async def system_status():
    """系統狀態"""
    from src.core.db import get_db_stats
    from src.api import state
    stats = get_db_stats()
    uptime_sec = int(time.time() - state.start_time)

    return {
        "version": settings.app_version,
        "uptime_seconds": uptime_sec,
        "watchlist": settings.watchlist,
        "poll_interval": settings.poll_interval_sec,
        **stats,
    }



# ====== 任務調度輔助 ======


# ====== 回測 ======



# ====== 回測歷史 ======
# ====== 緩存管理 ======



@router.get("/api/cache/stats")
async def cache_stats_api():
    """緩存統計（LRU / Redis）"""
    from src.core.result_cache import cache_stats
    return {"success": True, **cache_stats()}




@router.post("/api/cache/clear")
async def cache_clear_api(code: str = None):
    """清除計算結果緩存；可選按股票代碼"""
    from src.core.result_cache import invalidate_compute
    from src.core.db import clear_data_cache
    if code:
        removed = invalidate_compute(code=code)
    else:
        clear_data_cache()
        removed = invalidate_compute()
    return {"success": True, "removed": removed, "code": code}


# ====== 調度器 ======



@router.get("/api/scheduler/jobs")
async def list_scheduler_jobs():
    """列出已註冊的調度任務"""
    from src.core.scheduler import list_jobs
    return {"jobs": list_jobs()}




@router.get("/api/scheduler/catalog")
async def scheduler_catalog():
    """定時任務目錄（含是否已啟用）"""
    from src.core.scheduler import get_catalog, list_jobs
    return {"catalog": get_catalog(), "jobs": list_jobs()}




@router.post("/api/scheduler/setup")
async def scheduler_setup():
    """按 config 重新註冊默認定時任務"""
    from src.core.scheduler import setup_from_settings
    jobs = setup_from_settings()
    return {
        "success": True,
        "message": f"已註冊 {len(jobs)} 個定時任務",
        "jobs": jobs,
    }




@router.post("/api/scheduler/enable")
async def enable_scheduler():
    """啟用默認定時任務套件（同 /api/scheduler/setup）"""
    from src.core.scheduler import setup_from_settings
    jobs = setup_from_settings()
    return {
        "success": True,
        "message": f"已啟用 {len(jobs)} 個定時任務",
        "jobs": jobs,
    }




@router.post("/api/scheduler/disable")
async def disable_scheduler():
    """禁用全部定時任務"""
    from src.core.scheduler import _DISABLE_BY_ID
    for fn in _DISABLE_BY_ID.values():
        fn()
    return {"success": True, "message": "已禁用全部定時任務"}




@router.post("/api/scheduler/jobs/{job_id}/enable")
async def enable_scheduler_job(job_id: str):
    """啟用單個定時任務"""
    from src.core.scheduler import enable_job
    try:
        enable_job(job_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"success": True, "message": f"任務 {job_id} 已啟用"}




@router.post("/api/scheduler/jobs/{job_id}/disable")
async def disable_scheduler_job(job_id: str):
    """禁用單個定時任務"""
    from src.core.scheduler import disable_job
    try:
        disable_job(job_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"success": True, "message": f"任務 {job_id} 已禁用"}




@router.post("/api/scheduler/jobs/{job_id}/run")
async def run_scheduler_job_now(job_id: str):
    """立即執行一次定時任務"""
    from src.core.scheduler import run_job_now
    try:
        task_id = run_job_now(job_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    out = {"success": True, "message": f"任務 {job_id} 已觸發執行", "async": True}
    if task_id:
        out["task_id"] = task_id
    return out


# ====== 通知渠道 ======



@router.get("/api/notify/channels")
async def list_notify_channels():
    """列出通知渠道狀態"""
    from src.core.alerts import get_notification_channels
    return {"channels": get_notification_channels()}




@router.post("/api/notify/test")
async def test_notify():
    """測試所有通知渠道"""
    from src.core.alerts import test_all_channels
    results = test_all_channels()
    return {"success": True, "results": results}


# ====== 配置 ======



@router.get("/api/config")
async def get_config():
    """獲取當前配置"""
    from src.core.api_cache import cached_response
    from src.core.optimize import PARAM_GRIDS, PARAM_RANGES

    def _build():
        from src.core.admin_controls import get_controls
        return {
            "watchlist": settings.watchlist,
            "crypto_watchlist": settings.crypto_watchlist,
            "forex_watchlist": settings.forex_watchlist,
            "poll_interval": settings.poll_interval_sec,
            "alert_cooldown": settings.alert_cooldown_sec,
            "history_start_date": settings.history_start_date,
            "backtest_cash": settings.backtest_cash,
            "backtest_commission": settings.backtest_commission,
            "backtest_stamp_tax": settings.backtest_stamp_tax,
            "task_max_workers": settings.task_max_workers,
            "task_heavy_max_concurrent": settings.task_heavy_max_concurrent,
            "task_timeout_sec": settings.task_timeout_sec,
            "task_parallel_grid": settings.task_parallel_grid,
            "strategy_params": settings.strategy_params,
            "param_grids": PARAM_GRIDS,
            "param_ranges": {k: {pk: list(pv) for pk, pv in v.items()} for k, v in PARAM_RANGES.items()},
            "alert_rules": settings.alert_rules,
            "portfolio_presets": settings.portfolio_presets,
            "tradingview_enabled": settings.tradingview_enabled,
            "ib_enabled": settings.ib_enabled,
            "local_first_auto_fetch": settings.local_first_auto_fetch,
            "stock_logo_api_enabled": settings.stock_logo_api_enabled,
            "admin_controls": get_controls(),
            "billing": {
                "dev_upgrade": bool(getattr(settings, "billing_dev_upgrade", True)),
                "checkout_enabled": bool(getattr(settings, "billing_checkout_enabled", False)),
                "pricing_url": "/app#/pricing",
            },
        }

    return cached_response("api:config", ttl=60, builder=_build)




@router.post("/api/scheduler/degradation/enable")
async def enable_degradation_api(codes: list[str] = None):
    """啟用策略衰減檢測"""
    from src.core.scheduler import enable_degradation_check
    enable_degradation_check(codes)
    return {"success": True, "message": "策略衰減檢測已啟用 (每日 16:00)"}




@router.post("/api/scheduler/degradation/disable")
async def disable_degradation_api():
    """禁用策略衰減檢測"""
    from src.core.scheduler import disable_degradation_check
    disable_degradation_check()
    return {"success": True, "message": "策略衰減檢測已禁用"}




@router.post("/api/scheduler/correlation/enable")
async def enable_correlation_api(codes: list[str] = None):
    """啟用策略相關性監控"""
    from src.core.scheduler import enable_correlation_monitor
    enable_correlation_monitor(codes)
    return {"success": True, "message": "策略相關性監控已啟用 (每週一 16:30)"}




@router.post("/api/scheduler/correlation/disable")
async def disable_correlation_api():
    """禁用策略相關性監控"""
    from src.core.scheduler import disable_correlation_monitor
    disable_correlation_monitor()
    return {"success": True, "message": "策略相關性監控已禁用"}




@router.post("/api/scheduler/data-quality/enable")
async def enable_data_quality_api():
    """啟用數據質量巡檢"""
    from src.core.scheduler import enable_data_quality_check
    enable_data_quality_check()
    return {"success": True, "message": "數據質量巡檢已啟用 (每日 09:00)"}




@router.post("/api/scheduler/data-quality/disable")
async def disable_data_quality_api():
    """禁用數據質量巡檢"""
    from src.core.scheduler import disable_data_quality_check
    disable_data_quality_check()
    return {"success": True, "message": "數據質量巡檢已禁用"}


# ====== 業務監控指標 ======


@router.get("/api/metrics/business")
async def business_metrics_api():
    """業務監控指標（回測成功率、策略勝率、數據源健康度）"""
    from src.monitoring.business_metrics import get_all_business_metrics
    return {"success": True, "metrics": get_all_business_metrics()}


@router.get("/api/metrics/business/prometheus")
async def business_metrics_prometheus():
    """Prometheus 格式業務指標"""
    from src.monitoring.business_metrics import export_prometheus
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(
        content=export_prometheus(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


# ====== 靜態文件（前端） ======

static_dir = Path(__file__).parent.parent.parent / "static"




