"""
定時任務調度器 — 基於 APScheduler

支持的任務:
  - daily_report:        每日策略報告（15:30）
  - degradation_check:   策略衰減檢測（每日 16:00）
  - correlation_monitor: 策略相關性監控（每週一 16:30）
  - data_quality_check:  數據質量巡檢（每日 09:00）
  - paper_trading_tick:  模擬交易信號輪詢（交易時段每 N 秒）

每次觸發會經 task_manager 登記，出現在任務中心列表。
"""
import threading
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from src.utils.logger import logger

# 定時任務 ID → 任務中心 task_type（其餘用 scheduled_job）
SCHEDULER_TASK_TYPES: dict[str, str] = {
    "incremental_update": "data_incremental",
}

_scheduler = None
_lock = threading.Lock()


def _get_scheduler():
    """獲取或創建調度器實例"""
    global _scheduler
    if _scheduler is None:
        with _lock:
            if _scheduler is None:
                from apscheduler.schedulers.background import BackgroundScheduler
                _scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    return _scheduler


def _job_runtime_maintenance():
    """週期性釋放內存、清理過期 asyncio 任務。"""
    from src.core.runtime_maintenance import run_memory_gc

    run_memory_gc()


def start_scheduler(*, auto_register: bool | None = None):
    """啟動後台調度器，可選按配置註冊默認任務"""
    from src.config import settings

    if not settings.scheduler_enabled:
        logger.info("定時任務已關閉 (SQ_SCHEDULER_ENABLED=false)")
        return

    scheduler = _get_scheduler()
    if not scheduler.running:
        if getattr(settings, "runtime_gc_interval_sec", 3600) > 0:
            scheduler.add_job(
                _job_runtime_maintenance,
                "interval",
                seconds=int(settings.runtime_gc_interval_sec),
                id="runtime_maintenance",
                replace_existing=True,
            )
        scheduler.start()
        logger.info("調度器已啟動 (Asia/Shanghai)")

    if auto_register is None:
        auto_register = settings.scheduler_auto_register
    if auto_register:
        setup_from_settings()


def stop_scheduler():
    """停止調度器"""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("調度器已停止")


def list_jobs() -> list[dict]:
    """列出所有調度任務"""
    scheduler = _get_scheduler()
    jobs = []
    for job in scheduler.get_jobs():
        next_run = job.next_run_time
        jobs.append({
            "id": job.id,
            "name": job.name or job.id,
            "next_run": next_run.strftime("%Y-%m-%d %H:%M:%S") if next_run else None,
            "trigger": str(job.trigger),
        })
    return jobs


def _remove_job_safe(job_id: str):
    """安全移除任務"""
    scheduler = _get_scheduler()
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass


def _run_scheduled_as_task(
    job_id: str,
    display_name: str,
    fn: Callable[..., Any],
    *,
    task_type: str | None = None,
    extra_params: dict | None = None,
    pass_task_id: bool = False,
) -> str | None:
    """
    將一次定時觸發登記到 task_manager 並在背景執行。
    返回 task_id；若去重略過則返回 None。
    """
    from src.core.task_manager import (
        create_task,
        is_task_cancelled,
        submit_task,
        update_task_meta,
    )

    ttype = task_type or SCHEDULER_TASK_TYPES.get(job_id) or "scheduled_job"
    params: dict = {
        "scheduler_job_id": job_id,
        "source": "scheduler",
        "scheduler_run_id": uuid.uuid4().hex[:12],
        "triggered_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    if extra_params:
        params.update(extra_params)

    title = f"定時·{display_name}"
    created = create_task(ttype, params, title=title)
    task_id = created["task_id"]

    from src.core.task_manager import _lock as tm_lock
    from src.core.task_manager import _tasks

    with tm_lock:
        t = _tasks.get(task_id)
        if t is not None:
            meta = t.setdefault("meta", {})
            meta["source"] = "scheduler"
            meta["scheduler_job_id"] = job_id

    from src.core.task_manager import _save_task_to_db

    with tm_lock:
        t = _tasks.get(task_id)
        if t is not None:
            _save_task_to_db(t, force=True)

    if created.get("is_duplicate"):
        logger.warning(
            f"定時任務 {job_id} 意外去重 (task_id={task_id}, status={created.get('status')})"
        )

    def work():
        if is_task_cancelled(task_id):
            return {"cancelled": True, "job_id": job_id}
        update_task_meta(task_id, message=f"執行：{display_name}")
        try:
            if pass_task_id:
                result = fn(task_id)
            else:
                result = fn()
            if isinstance(result, dict):
                return result
            return {"ok": True, "job_id": job_id}
        except Exception as e:
            logger.error(f"定時任務 {job_id} 失敗: {e}")
            raise

    submit_task(task_id, work)
    return task_id


def _wrap_scheduled_job(job_id: str, display_name: str, fn: Callable[..., Any], **kwargs):
    """包裝 APScheduler 回調：觸發時登記至任務列表。"""
    def tracked():
        return _run_scheduled_as_task(job_id, display_name, fn, **kwargs)
    tracked.__name__ = f"tracked_{job_id}"
    return tracked


# ============================================================
# 每日策略報告
# ============================================================

def enable_daily_report(codes: list[str] = None):
    """啟用每日報告任務（15:30 觸發）"""
    scheduler = _get_scheduler()
    _remove_job_safe("daily_report")

    def _job_impl():
        logger.info("執行每日報告任務...")
        from src.core.report import generate_daily_report
        report = generate_daily_report(codes)
        logger.info(f"每日報告:\n{report}")
        try:
            from src.core.alerts import send_notification
            send_notification(report, msg_type="daily_report")
        except Exception as e:
            logger.debug(f"通知發送跳過: {e}")
        return {"ok": True, "job_id": "daily_report"}

    scheduler.add_job(
        _wrap_scheduled_job("daily_report", "每日策略報告", _job_impl),
        "cron", hour=15, minute=30,
        id="daily_report", replace_existing=True, name="每日策略報告",
    )
    logger.info("已啟用每日報告任務 (15:30)")


def disable_daily_report():
    """禁用每日報告任務"""
    _remove_job_safe("daily_report")
    logger.info("已禁用每日報告任務")


# ============================================================
# 策略衰減檢測
# ============================================================

def enable_degradation_check(codes: list[str] = None, lookback_days: int = 30):
    """
    啟用策略衰減檢測（每日 16:00 觸發）。

    檢測每個策略在近 N 天的回測表現是否顯著低於歷史平均，
    如果連續多日跑輸基準，標記為衰減。
    """
    scheduler = _get_scheduler()
    _remove_job_safe("degradation_check")

    def _job_impl():
        logger.info("執行策略衰減檢測...")
        import numpy as np

        from src.core.backtest import STRATEGIES, run_backtest
        from src.core.db import load_daily_kline

        target_codes = codes or ["600519", "000001", "000858"]
        degraded = []

        for strategy_name in STRATEGIES:
            try:
                returns_list = []
                for code in target_codes:
                    df = load_daily_kline(code)
                    if df.empty or len(df) < lookback_days + 60:
                        continue
                    try:
                        result = run_backtest(code, strategy_name=strategy_name)
                        ret = result.get("total_return_pct", 0)
                        returns_list.append(ret)
                    except Exception:
                        pass

                if not returns_list:
                    continue

                avg_return = np.mean(returns_list)
                if avg_return < -5 and all(r < 0 for r in returns_list):
                    degraded.append({
                        "strategy": strategy_name,
                        "avg_return_pct": round(float(avg_return), 2),
                        "stocks_checked": len(returns_list),
                    })
            except Exception as e:
                logger.debug(f"衰減檢測 {strategy_name} 失敗: {e}")

        if degraded:
            msg = "⚠️ 策略衰減警告:\n"
            for d in degraded:
                msg += f"  • {d['strategy']}: 近期平均收益 {d['avg_return_pct']}%\n"
            logger.warning(msg)
            try:
                from src.core.alerts import send_notification
                send_notification(msg, msg_type="degradation_alert")
            except Exception:
                pass
        else:
            logger.info("策略衰減檢測: 所有策略正常")
        return {"degraded_count": len(degraded), "job_id": "degradation_check"}

    scheduler.add_job(
        _wrap_scheduled_job("degradation_check", "策略衰減檢測", _job_impl),
        "cron", hour=16, minute=0,
        id="degradation_check", replace_existing=True, name="策略衰減檢測",
    )
    logger.info("已啟用策略衰減檢測 (16:00)")


def disable_degradation_check():
    """禁用策略衰減檢測"""
    _remove_job_safe("degradation_check")
    logger.info("已禁用策略衰減檢測")


# ============================================================
# 策略相關性監控
# ============================================================

def enable_correlation_monitor(codes: list[str] = None):
    """
    啟用策略相關性監控（每週一 16:30 觸發）。

    計算各策略之間的收益相關性矩陣，
    高相關（>0.8）的策略對會被標記為冗餘。
    """
    scheduler = _get_scheduler()
    _remove_job_safe("correlation_monitor")

    def _job_impl():
        logger.info("執行策略相關性監控...")
        import pandas as pd

        from src.core.backtest import STRATEGIES, run_backtest

        target_codes = codes or ["600519", "000001"]
        nav_series = {}
        for strategy_name in STRATEGIES:
            for code in target_codes:
                try:
                    result = run_backtest(code, strategy_name=strategy_name)
                    nav = result.get("nav", [])
                    if nav and len(nav) > 30:
                        nav_series[f"{strategy_name}_{code}"] = nav
                except Exception:
                    pass

        if len(nav_series) < 2:
            logger.info("相關性監控: 數據不足，跳過")
            return {"skipped": True, "reason": "insufficient_data"}

        min_len = min(len(v) for v in nav_series.values())
        df = pd.DataFrame({k: v[:min_len] for k, v in nav_series.items()})
        corr = df.corr()
        high_corr_pairs = []
        cols = corr.columns
        for i in range(len(cols)):
            for j in range(i + 1, len(cols)):
                c = corr.iloc[i, j]
                if abs(c) > 0.8:
                    high_corr_pairs.append({
                        "strategy_1": cols[i],
                        "strategy_2": cols[j],
                        "correlation": round(float(c), 4),
                    })

        if high_corr_pairs:
            msg = "📊 策略相關性報告:\n"
            for p in high_corr_pairs:
                msg += f"  ⚠️ {p['strategy_1']} ↔ {p['strategy_2']}: {p['correlation']}\n"
            logger.warning(msg)
        else:
            logger.info("策略相關性監控: 無高相關策略對")
        return {"high_corr_pairs": len(high_corr_pairs), "job_id": "correlation_monitor"}

    scheduler.add_job(
        _wrap_scheduled_job("correlation_monitor", "策略相關性監控", _job_impl),
        "cron", day_of_week="mon", hour=16, minute=30,
        id="correlation_monitor", replace_existing=True, name="策略相關性監控",
    )
    logger.info("已啟用策略相關性監控 (每週一 16:30)")


def disable_correlation_monitor():
    """禁用策略相關性監控"""
    _remove_job_safe("correlation_monitor")
    logger.info("已禁用策略相關性監控")


# ============================================================
# 數據質量巡檢
# ============================================================

def enable_data_quality_check():
    """
    啟用數據質量巡檢（每日 09:00 觸發）。

    在開盤前檢查所有股票數據的完整性，
    發現問題自動記錄並通知。
    """
    scheduler = _get_scheduler()
    _remove_job_safe("data_quality_check")

    def _job_impl():
        logger.info("執行數據質量巡檢...")
        from src.core.data_quality import validate_all
        report = validate_all(severity_filter="warning")
        logger.info(f"數據質量:\n{report['summary']}")

        if report.get("total_issues", 0) > 0:
            critical = [i for i in report.get("issues", []) if i.get("severity") == "critical"]
            if critical:
                msg = f"🔴 數據質量告警: {len(critical)} 個嚴重問題\n"
                for i in critical[:5]:
                    msg += f"  • {i['code']}: {i['description']}\n"
                try:
                    from src.core.alerts import send_notification
                    send_notification(msg, msg_type="data_quality_alert")
                except Exception:
                    pass
        return {
            "total_issues": report.get("total_issues", 0),
            "job_id": "data_quality_check",
        }

    scheduler.add_job(
        _wrap_scheduled_job("data_quality_check", "數據質量巡檢", _job_impl),
        "cron", hour=9, minute=0,
        id="data_quality_check", replace_existing=True, name="數據質量巡檢",
    )
    logger.info("已啟用數據質量巡檢 (09:00)")


def disable_data_quality_check():
    """禁用數據質量巡檢"""
    _remove_job_safe("data_quality_check")
    logger.info("已禁用數據質量巡檢")


# ============================================================
# 增量數據更新
# ============================================================

def enable_incremental_update(codes: list[str] = None):
    """啟用增量數據更新（工作日 08:05，可配置）"""
    from src.config import settings

    scheduler = _get_scheduler()
    _remove_job_safe("incremental_update")

    watch_codes = codes or settings.watchlist

    def _job_impl(task_id: str):
        logger.info("執行定時增量數據更新...")
        from src.core.download_tasks import run_incremental
        result = run_incremental(codes=watch_codes, task_id=task_id)
        logger.info(
            f"增量更新完成: 更新 {result.get('updated', 0)} 只, "
            f"跳過 {result.get('skipped', 0)} 只, "
            f"共 {result.get('total_records', 0)} 條"
        )
        return result

    scheduler.add_job(
        _wrap_scheduled_job(
            "incremental_update",
            "增量數據更新",
            _job_impl,
            task_type="data_incremental",
            extra_params={"codes": watch_codes},
            pass_task_id=True,
        ),
        "cron",
        day_of_week="mon-fri",
        hour=settings.scheduler_incremental_hour,
        minute=settings.scheduler_incremental_minute,
        id="incremental_update",
        replace_existing=True,
        name="增量數據更新",
    )
    logger.info(
        f"已啟用增量數據更新 "
        f"({settings.scheduler_incremental_hour:02d}:{settings.scheduler_incremental_minute:02d} 工作日)"
    )


def disable_incremental_update():
    _remove_job_safe("incremental_update")
    logger.info("已禁用增量數據更新")


# ============================================================
# 策略排行榜刷新
# ============================================================

def enable_leaderboard_refresh(codes: list[str] = None):
    """啟用策略排行榜刷新（每週日 17:00）"""
    scheduler = _get_scheduler()
    _remove_job_safe("leaderboard_refresh")

    def _job_impl():
        logger.info("執行策略排行榜刷新...")
        from src.core.leaderboard import update_leaderboard
        rows = update_leaderboard(codes)
        logger.info(f"排行榜已更新: {len(rows)} 條記錄")
        return {"rows": len(rows), "job_id": "leaderboard_refresh"}

    scheduler.add_job(
        _wrap_scheduled_job("leaderboard_refresh", "策略排行榜刷新", _job_impl),
        "cron",
        day_of_week="sun",
        hour=17,
        minute=0,
        id="leaderboard_refresh",
        replace_existing=True,
        name="策略排行榜刷新",
    )
    logger.info("已啟用策略排行榜刷新 (每週日 17:00)")


def disable_leaderboard_refresh():
    _remove_job_safe("leaderboard_refresh")
    logger.info("已禁用策略排行榜刷新")


# ============================================================
# 任務註冊表與統一管理
# ============================================================

JOB_CATALOG = [
    {
        "id": "incremental_update",
        "name": "增量數據更新",
        "schedule": "工作日 08:05（可配置）",
        "description": "更新監控列表股票的日 K 線",
    },
    {
        "id": "data_quality_check",
        "name": "數據質量巡檢",
        "schedule": "每日 09:00",
        "description": "開盤前檢查數據完整性",
    },
    {
        "id": "daily_report",
        "name": "每日策略報告",
        "schedule": "每日 15:30",
        "description": "生成策略表現報告並可推送通知",
    },
    {
        "id": "degradation_check",
        "name": "策略衰減檢測",
        "schedule": "每日 16:00",
        "description": "檢測策略近期表現是否衰退",
    },
    {
        "id": "correlation_monitor",
        "name": "策略相關性監控",
        "schedule": "每週一 16:30",
        "description": "標記高相關冗餘策略對",
    },
    {
        "id": "leaderboard_refresh",
        "name": "策略排行榜刷新",
        "schedule": "每週日 17:00",
        "description": "全策略回測並更新排行榜",
    },
]

_ENABLE_BY_ID = {
    "incremental_update": enable_incremental_update,
    "data_quality_check": enable_data_quality_check,
    "daily_report": enable_daily_report,
    "degradation_check": enable_degradation_check,
    "correlation_monitor": enable_correlation_monitor,
    "leaderboard_refresh": enable_leaderboard_refresh,
}

_DISABLE_BY_ID = {
    "incremental_update": disable_incremental_update,
    "data_quality_check": disable_data_quality_check,
    "daily_report": disable_daily_report,
    "degradation_check": disable_degradation_check,
    "correlation_monitor": disable_correlation_monitor,
    "leaderboard_refresh": disable_leaderboard_refresh,
}


def get_catalog() -> list[dict]:
    """返回任務目錄及當前是否已註冊"""
    active_ids = {j["id"] for j in list_jobs()}
    out = []
    for item in JOB_CATALOG:
        row = dict(item)
        row["enabled"] = row["id"] in active_ids
        out.append(row)
    return out


def enable_job(job_id: str, **kwargs):
    """按 ID 啟用單個定時任務"""
    fn = _ENABLE_BY_ID.get(job_id)
    if not fn:
        raise ValueError(f"未知任務 ID: {job_id}")
    start_scheduler(auto_register=False)
    fn(**kwargs)


def disable_job(job_id: str):
    """按 ID 禁用單個定時任務"""
    fn = _DISABLE_BY_ID.get(job_id)
    if not fn:
        raise ValueError(f"未知任務 ID: {job_id}")
    fn()


def run_job_now(job_id: str):
    """立即執行一次（若未註冊則先註冊再執行）"""
    if job_id not in _ENABLE_BY_ID:
        raise ValueError(f"未知任務 ID: {job_id}")

    start_scheduler(auto_register=False)
    scheduler = _get_scheduler()
    job = scheduler.get_job(job_id)
    if not job:
        _ENABLE_BY_ID[job_id]()
        job = scheduler.get_job(job_id)
    if not job:
        raise RuntimeError(f"無法註冊任務: {job_id}")
    logger.info(f"手動觸發定時任務: {job_id}")
    return job.func()


def setup_from_settings():
    """按 config 註冊默認定時任務（已存在的任務會 replace_existing）"""
    from src.config import settings

    if not settings.scheduler_enabled:
        logger.info("跳過定時任務註冊：scheduler_enabled=false")
        return list_jobs()

    start_scheduler(auto_register=False)

    if settings.scheduler_job_incremental:
        enable_incremental_update()
    else:
        disable_incremental_update()

    if settings.scheduler_job_data_quality:
        enable_data_quality_check()
    else:
        disable_data_quality_check()

    if settings.scheduler_job_daily_report:
        enable_daily_report()
    else:
        disable_daily_report()

    if settings.scheduler_job_degradation:
        enable_degradation_check()
    else:
        disable_degradation_check()

    if settings.scheduler_job_correlation:
        enable_correlation_monitor()
    else:
        disable_correlation_monitor()

    if settings.scheduler_job_leaderboard:
        enable_leaderboard_refresh()
    else:
        disable_leaderboard_refresh()

    if settings.scheduler_job_daily_download:
        enable_daily_full_download()
    else:
        disable_daily_full_download()

    jobs = list_jobs()
    logger.info(f"定時任務已按配置註冊: {len(jobs)} 個 — {[j['id'] for j in jobs]}")
    return jobs


def enable_daily_full_download(codes: list[str] = None):
    """啟用每日完整數據爬取（每天 09:00）"""
    from src.config import settings

    scheduler = _get_scheduler()
    _remove_job_safe("daily_full_download")

    watch_codes = codes or settings.watchlist

    def _job_impl(task_id: str):
        logger.info("執行每日完整數據爬取...")
        from src.core.download_tasks import run_incremental
        # 強制模式：重新下載最近的數據，確保完整性
        result = run_incremental(codes=watch_codes, force=False, task_id=task_id)
        updated = result.get("updated", 0)
        total = result.get("total_records", 0)
        logger.info(f"每日數據爬取完成: 更新 {updated} 只, 共 {total} 條記錄")
        return result

    scheduler.add_job(
        _wrap_scheduled_job(
            "daily_full_download",
            "每日數據爬取",
            _job_impl,
            task_type="data_incremental",
            extra_params={"codes": watch_codes},
            pass_task_id=True,
        ),
        "cron",
        hour=9,
        minute=0,
        id="daily_full_download",
        replace_existing=True,
        name="每日數據爬取",
    )
    logger.info("已啟用每日數據爬取 (09:00)")


def disable_daily_full_download():
    _remove_job_safe("daily_full_download")
    logger.info("已禁用每日數據爬取")
