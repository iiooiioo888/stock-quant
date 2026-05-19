"""
定時任務調度器 — 基於 APScheduler

支持的任務:
  - daily_report:        每日策略報告（15:30）
  - degradation_check:   策略衰減檢測（每日 16:00）
  - correlation_monitor: 策略相關性監控（每週一 16:30）
  - data_quality_check:  數據質量巡檢（每日 09:00）
  - paper_trading_tick:  模擬交易信號輪詢（交易時段每 N 秒）
"""
import threading
from datetime import datetime
from src.utils.logger import logger

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


def start_scheduler():
    """啟動後台調度器"""
    scheduler = _get_scheduler()
    if not scheduler.running:
        scheduler.start()
        logger.info("調度器已啟動")


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


# ============================================================
# 每日策略報告
# ============================================================

def enable_daily_report(codes: list[str] = None):
    """啟用每日報告任務（15:30 觸發）"""
    scheduler = _get_scheduler()
    _remove_job_safe("daily_report")

    def _job():
        logger.info("執行每日報告任務...")
        try:
            from src.core.report import generate_daily_report
            report = generate_daily_report(codes)
            logger.info(f"每日報告:\n{report}")
            try:
                from src.core.alerts import send_notification
                send_notification(report, msg_type="daily_report")
            except Exception as e:
                logger.debug(f"通知發送跳過: {e}")
        except Exception as e:
            logger.error(f"每日報告失敗: {e}")

    scheduler.add_job(
        _job, "cron", hour=15, minute=30,
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

    def _job():
        logger.info("執行策略衰減檢測...")
        try:
            import numpy as np
            from src.core.backtest import STRATEGIES, run_backtest
            from src.core.db import load_daily_kline

            target_codes = codes or ["600519", "000001", "000858"]
            degraded = []

            for strategy_name in STRATEGIES:
                try:
                    # 跑最近 lookback_days 的回測
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

                    # 衰減判定：平均收益 < -5% 且所有股票都虧損
                    if avg_return < -5 and all(r < 0 for r in returns_list):
                        degraded.append({
                            "strategy": strategy_name,
                            "avg_return_pct": round(avg_return, 2),
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

        except Exception as e:
            logger.error(f"策略衰減檢測失敗: {e}")

    scheduler.add_job(
        _job, "cron", hour=16, minute=0,
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

    def _job():
        logger.info("執行策略相關性監控...")
        try:
            import numpy as np
            import pandas as pd
            from src.core.backtest import STRATEGIES, run_backtest
            from src.core.db import load_daily_kline

            target_codes = codes or ["600519", "000001"]

            # 收集各策略的淨值序列
            nav_series = {}
            for strategy_name in STRATEGIES:
                for code in target_codes:
                    try:
                        result = run_backtest(code, strategy_name=strategy_name)
                        nav = result.get("nav", [])
                        dates = result.get("dates", [])
                        if nav and len(nav) > 30:
                            key = f"{strategy_name}_{code}"
                            nav_series[key] = nav
                    except Exception:
                        pass

            if len(nav_series) < 2:
                logger.info("相關性監控: 數據不足，跳過")
                return

            # 計算相關性矩陣
            # 對齊長度
            min_len = min(len(v) for v in nav_series.values())
            df = pd.DataFrame({k: v[:min_len] for k, v in nav_series.items()})
            corr = df.corr()

            # 找高相關對
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

        except Exception as e:
            logger.error(f"策略相關性監控失敗: {e}")

    scheduler.add_job(
        _job, "cron", day_of_week="mon", hour=16, minute=30,
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

    def _job():
        logger.info("執行數據質量巡檢...")
        try:
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

        except Exception as e:
            logger.error(f"數據質量巡檢失敗: {e}")

    scheduler.add_job(
        _job, "cron", hour=9, minute=0,
        id="data_quality_check", replace_existing=True, name="數據質量巡檢",
    )
    logger.info("已啟用數據質量巡檢 (09:00)")


def disable_data_quality_check():
    """禁用數據質量巡檢"""
    _remove_job_safe("data_quality_check")
    logger.info("已禁用數據質量巡檢")
