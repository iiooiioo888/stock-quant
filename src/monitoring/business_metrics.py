"""
業務監控指標 — 回測成功率、策略勝率、數據源健康度

指標分類：
1. 回測相關：成功率、平均執行時間、失敗原因分佈
2. 策略相關：勝率、平均收益、夏普比率分佈
3. 數據源相關：健康度、降級次數、延遲
4. 用戶相關：活躍用戶、任務提交量
"""
from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Optional

from src.utils.logger import logger

# ============================================================
# 內存計數器（進程生命週期內）
# ============================================================

_counters: dict[str, int] = defaultdict(int)
_histograms: dict[str, list[float]] = defaultdict(list)
_last_reset = time.time()

# 指標名稱常量
METRIC_BACKTEST_SUCCESS = "backtest_success"
METRIC_BACKTEST_FAILURE = "backtest_failure"
METRIC_BACKTEST_DURATION = "backtest_duration_sec"
METRIC_STRATEGY_WIN = "strategy_win"
METRIC_STRATEGY_LOSS = "strategy_loss"
METRIC_DATA_SOURCE_OK = "data_source_ok"
METRIC_DATA_SOURCE_FAIL = "data_source_fail"
METRIC_DATA_SOURCE_DEGRADE = "data_source_degrade"
METRIC_ACTIVE_USERS = "active_users"
METRIC_TASK_SUBMITTED = "task_submitted"
METRIC_TASK_COMPLETED = "task_completed"
METRIC_TASK_FAILED = "task_failed"


def inc(metric: str, n: int = 1) -> None:
    """遞增計數器。"""
    _counters[metric] += n


def record_duration(metric: str, seconds: float) -> None:
    """記錄持續時間（用於計算平均值/分位數）。"""
    _histograms[metric].append(seconds)
    # 保留最近 1000 條
    if len(_histograms[metric]) > 1000:
        _histograms[metric] = _histograms[metric][-1000:]


def record_backtest_result(success: bool, duration_sec: float = 0, error_type: str = "") -> None:
    """記錄回測結果。"""
    if success:
        inc(METRIC_BACKTEST_SUCCESS)
    else:
        inc(METRIC_BACKTEST_FAILURE)
    if duration_sec > 0:
        record_duration(METRIC_BACKTEST_DURATION, duration_sec)


def record_strategy_trade(win: bool) -> None:
    """記錄策略交易結果。"""
    inc(METRIC_STRATEGY_WIN if win else METRIC_STRATEGY_LOSS)


def record_data_source_event(ok: bool, degraded: bool = False) -> None:
    """記錄數據源事件。"""
    if ok:
        inc(METRIC_DATA_SOURCE_OK)
    elif degraded:
        inc(METRIC_DATA_SOURCE_DEGRADE)
    else:
        inc(METRIC_DATA_SOURCE_FAIL)


# ============================================================
# 指標查詢
# ============================================================

def get_backtest_metrics() -> dict[str, Any]:
    """回測相關指標。"""
    success = _counters[METRIC_BACKTEST_SUCCESS]
    failure = _counters[METRIC_BACKTEST_FAILURE]
    total = success + failure
    rate = round(success / total * 100, 2) if total > 0 else 0.0

    durations = _histograms[METRIC_BACKTEST_DURATION]
    avg_duration = round(sum(durations) / len(durations), 2) if durations else 0.0

    return {
        "total": total,
        "success": success,
        "failure": failure,
        "success_rate_pct": rate,
        "avg_duration_sec": avg_duration,
    }


def get_strategy_metrics() -> dict[str, Any]:
    """策略相關指標。"""
    wins = _counters[METRIC_STRATEGY_WIN]
    losses = _counters[METRIC_STRATEGY_LOSS]
    total = wins + losses
    win_rate = round(wins / total * 100, 2) if total > 0 else 0.0

    return {
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": win_rate,
    }


def get_data_source_metrics() -> dict[str, Any]:
    """數據源相關指標。"""
    ok = _counters[METRIC_DATA_SOURCE_OK]
    fail = _counters[METRIC_DATA_SOURCE_FAIL]
    degrade = _counters[METRIC_DATA_SOURCE_DEGRADE]
    total = ok + fail + degrade
    health = round(ok / total * 100, 2) if total > 0 else 100.0

    return {
        "total_requests": total,
        "ok": ok,
        "failures": fail,
        "degradations": degrade,
        "health_score_pct": health,
    }


def get_all_business_metrics() -> dict[str, Any]:
    """所有業務指標匯總。"""
    uptime_sec = int(time.time() - _last_reset)
    return {
        "uptime_seconds": uptime_sec,
        "backtest": get_backtest_metrics(),
        "strategy": get_strategy_metrics(),
        "data_source": get_data_source_metrics(),
        "tasks": {
            "submitted": _counters[METRIC_TASK_SUBMITTED],
            "completed": _counters[METRIC_TASK_COMPLETED],
            "failed": _counters[METRIC_TASK_FAILED],
        },
        "timestamp": datetime.now().isoformat(),
    }


def reset_metrics() -> None:
    """重置所有計數器（測試用）。"""
    _counters.clear()
    _histograms.clear()
    global _last_reset
    _last_reset = time.time()


# ============================================================
# Prometheus 格式導出（可選）
# ============================================================

def export_prometheus() -> str:
    """導出 Prometheus 文本格式指標。"""
    lines = []
    gauges = {
        "backtest_success_total": _counters[METRIC_BACKTEST_SUCCESS],
        "backtest_failure_total": _counters[METRIC_BACKTEST_FAILURE],
        "strategy_win_total": _counters[METRIC_STRATEGY_WIN],
        "strategy_loss_total": _counters[METRIC_STRATEGY_LOSS],
        "data_source_ok_total": _counters[METRIC_DATA_SOURCE_OK],
        "data_source_fail_total": _counters[METRIC_DATA_SOURCE_FAIL],
        "data_source_degrade_total": _counters[METRIC_DATA_SOURCE_DEGRADE],
        "task_submitted_total": _counters[METRIC_TASK_SUBMITTED],
        "task_completed_total": _counters[METRIC_TASK_COMPLETED],
        "task_failed_total": _counters[METRIC_TASK_FAILED],
    }
    for name, value in gauges.items():
        lines.append(f"# TYPE stock_quant_{name} gauge")
        lines.append(f"stock_quant_{name} {value}")

    # Histograms
    durations = _histograms[METRIC_BACKTEST_DURATION]
    if durations:
        avg = sum(durations) / len(durations)
        lines.append("# TYPE stock_quant_backtest_duration_seconds gauge")
        lines.append(f"stock_quant_backtest_duration_seconds {avg:.2f}")

    return "\n".join(lines) + "\n"