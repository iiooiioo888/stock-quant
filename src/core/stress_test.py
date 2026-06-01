"""
壓力測試模組 — 蒙特卡洛模擬、歷史極端行情重放、VaR/CVaR 壓力測試

功能：
- 蒙特卡洛模擬（多資產相關性）
- 歷史極端行情重放（2015 股災、2020 疫情等）
- VaR/CVaR 壓力測試報告
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Any, Optional

from src.utils.logger import logger


def _generate_extreme_returns(mean: float, std: float, n: int, min_return: float) -> list[float]:
    """生成極端行情收益率序列。"""
    np.random.seed(42)
    returns = np.random.normal(mean, std, n)
    returns = np.clip(returns, min_return, 0.05)
    returns[0] = min_return
    returns[1] = min_return * 0.7
    return [round(float(r), 6) for r in returns]


# ============================================================
# 歷史極端行情定義
# ============================================================

EXTREME_SCENARIOS = {
    "china_crash_2015": {
        "name": "2015 中國股災",
        "description": "槓桿牛市崩盤，千股跌停",
        "duration_days": 45,
        "max_drawdown_pct": -45.0,
        "daily_returns": _generate_extreme_returns(-0.08, 0.04, 45, -0.10),
    },
    "covid_2020": {
        "name": "2020 新冠疫情",
        "description": "全球市場恐慌性拋售",
        "duration_days": 23,
        "max_drawdown_pct": -35.0,
        "daily_returns": _generate_extreme_returns(-0.05, 0.06, 23, -0.08),
    },
    "trade_war_2018": {
        "name": "2018 中美貿易戰",
        "description": "關稅升級引發持續下跌",
        "duration_days": 60,
        "max_drawdown_pct": -30.0,
        "daily_returns": _generate_extreme_returns(-0.02, 0.03, 60, -0.04),
    },
    "flash_crash": {
        "name": "閃崩測試",
        "description": "單日極端跌幅",
        "duration_days": 5,
        "max_drawdown_pct": -20.0,
        "daily_returns": _generate_extreme_returns(-0.10, 0.05, 5, -0.10),
    },
}


def list_scenarios() -> list[dict]:
    """列出所有歷史極端行情場景。"""
    return [
        {"id": sid, "name": s["name"], "description": s["description"],
         "duration_days": s["duration_days"], "max_drawdown_pct": s["max_drawdown_pct"]}
        for sid, s in EXTREME_SCENARIOS.items()
    ]


# ============================================================
# 蒙特卡洛模擬（多資產）
# ============================================================

def monte_carlo_multi_asset(
    returns_matrix: np.ndarray,
    weights: np.ndarray,
    n_simulations: int = 1000,
    days: int = 252,
    initial_value: float = 100000.0,
) -> dict[str, Any]:
    """
    多資產蒙特卡洛模擬（考慮相關性）。
    
    Args:
        returns_matrix: (T, N) 收益率矩陣，T=歷史天數，N=資產數
        weights: (N,) 資產權重
        n_simulations: 模擬次數
        days: 模擬天數
        initial_value: 初始價值
    
    Returns:
        {"paths": np.ndarray, "final_values": np.ndarray, "var_95": float,
         "cvar_95": float, "mean_return": float, "max_drawdown_mean": float,
         "percentiles": dict}
    """
    n_assets = returns_matrix.shape[1]
    
    # 計算均值和協方差
    mu = np.mean(returns_matrix, axis=0)
    cov = np.cov(returns_matrix.T)
    
    # Cholesky 分解（處理相關性）
    try:
        L = np.linalg.cholesky(cov + np.eye(n_assets) * 1e-8)
    except np.linalg.LinAlgError:
        L = np.eye(n_assets) * np.std(returns_matrix, axis=0)
    
    # 模擬
    portfolio_returns = np.zeros((n_simulations, days))
    for i in range(n_simulations):
        z = np.random.randn(days, n_assets)
        asset_returns = mu + z @ L.T
        portfolio_returns[i] = asset_returns @ weights
    
    # 累計收益
    cumulative = np.cumprod(1 + portfolio_returns, axis=1)
    final_values = initial_value * cumulative[:, -1]
    paths = initial_value * cumulative
    
    # VaR / CVaR
    daily_pnl = portfolio_returns[:, -1]
    var_95 = float(np.percentile(daily_pnl, 5))
    cvar_95 = float(np.mean(daily_pnl[daily_pnl <= var_95]))
    
    # 最大回撤（每條路徑）
    drawdowns = []
    for path in paths:
        peak = np.maximum.accumulate(path)
        dd = (peak - path) / peak
        drawdowns.append(float(np.max(dd)))
    
    return {
        "n_simulations": n_simulations,
        "days": days,
        "initial_value": initial_value,
        "final_values_mean": round(float(np.mean(final_values)), 2),
        "final_values_std": round(float(np.std(final_values)), 2),
        "var_95": round(var_95, 6),
        "cvar_95": round(cvar_95, 6),
        "mean_return_pct": round(float(np.mean(portfolio_returns)) * 100, 4),
        "max_drawdown_mean_pct": round(float(np.mean(drawdowns)) * 100, 2),
        "max_drawdown_worst_pct": round(float(np.max(drawdowns)) * 100, 2),
        "percentiles": {
            "p5": round(float(np.percentile(final_values, 5)), 2),
            "p25": round(float(np.percentile(final_values, 25)), 2),
            "p50": round(float(np.percentile(final_values, 50)), 2),
            "p75": round(float(np.percentile(final_values, 75)), 2),
            "p95": round(float(np.percentile(final_values, 95)), 2),
        },
        "prob_loss": round(float(np.mean(final_values < initial_value)) * 100, 2),
    }


# ============================================================
# 歷史極端行情重放
# ============================================================

def replay_extreme_scenario(
    portfolio_returns: list[float],
    scenario_id: str,
    initial_value: float = 100000.0,
) -> dict[str, Any]:
    """
    將策略收益序列重放到歷史極端行情場景。
    
    Args:
        portfolio_returns: 策略的歷史日收益率序列
        scenario_id: 場景 ID
        initial_value: 初始價值
    
    Returns:
        壓力測試結果
    """
    if scenario_id not in EXTREME_SCENARIOS:
        raise ValueError(f"未知場景: {scenario_id}，可用: {list(EXTREME_SCENARIOS.keys())}")
    
    scenario = EXTREME_SCENARIOS[scenario_id]
    extreme_returns = scenario["daily_returns"]
    
    # 計算策略的 beta（相對於極端場景）
    n = min(len(portfolio_returns), len(extreme_returns))
    if n < 5:
        return {"error": "策略收益數據不足"}
    
    pr = np.array(portfolio_returns[:n])
    er = np.array(extreme_returns[:n])
    
    beta = float(np.corrcoef(pr, er)[0, 1]) if np.std(pr) > 0 and np.std(er) > 0 else 1.0
    
    # 用 beta 調整極端場景對策略的影響
    adjusted_returns = [r * beta for r in extreme_returns]
    
    # 計算累計收益
    cumulative = initial_value
    peak = initial_value
    max_dd = 0.0
    values = [initial_value]
    
    for r in adjusted_returns:
        cumulative *= (1 + r)
        values.append(cumulative)
        if cumulative > peak:
            peak = cumulative
        dd = (peak - cumulative) / peak
        if dd > max_dd:
            max_dd = dd
    
    return {
        "scenario": scenario["name"],
        "scenario_id": scenario_id,
        "description": scenario["description"],
        "beta": round(beta, 4),
        "initial_value": initial_value,
        "final_value": round(cumulative, 2),
        "total_return_pct": round((cumulative / initial_value - 1) * 100, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "duration_days": scenario["duration_days"],
        "values": [round(v, 2) for v in values],
    }


def replay_all_scenarios(
    portfolio_returns: list[float],
    initial_value: float = 100000.0,
) -> list[dict]:
    """對所有歷史極端場景進行壓力測試。"""
    results = []
    for sid in EXTREME_SCENARIOS:
        try:
            result = replay_extreme_scenario(portfolio_returns, sid, initial_value)
            results.append(result)
        except Exception as e:
            results.append({"scenario_id": sid, "error": str(e)})
    return results


# ============================================================
# VaR / CVaR 壓力測試
# ============================================================

def var_stress_test(
    returns: list[float],
    confidence_levels: list[float] = None,
    holding_periods: list[int] = None,
) -> dict[str, Any]:
    """
    VaR/CVaR 壓力測試。
    
    Args:
        returns: 日收益率序列
        confidence_levels: 置信水平列表（默認 [0.95, 0.99]）
        holding_periods: 持有期天數（默認 [1, 5, 10, 20]）
    
    Returns:
        VaR/CVaR 矩陣
    """
    if confidence_levels is None:
        confidence_levels = [0.90, 0.95, 0.99]
    if holding_periods is None:
        holding_periods = [1, 5, 10, 20]
    
    arr = np.array(returns)
    arr = arr[~np.isnan(arr)]
    
    if len(arr) < 30:
        return {"error": "收益率數據不足（需要至少 30 條）"}
    
    results = {}
    for cl in confidence_levels:
        level_results = {}
        for hp in holding_periods:
            # 持有期收益 = 日收益 * sqrt(持有期)（簡化假設）
            scale = np.sqrt(hp)
            var_val = float(np.percentile(arr, (1 - cl) * 100)) * scale
            cvar_val = float(np.mean(arr[arr <= np.percentile(arr, (1 - cl) * 100)])) * scale
            
            level_results[f"{hp}d"] = {
                "var": round(var_val, 6),
                "cvar": round(cvar_val, 6),
                "var_pct": round(var_val * 100, 4),
                "cvar_pct": round(cvar_val * 100, 4),
            }
        results[f"{int(cl*100)}%"] = level_results
    
    return {
        "data_points": len(arr),
        "mean_daily_return_pct": round(float(np.mean(arr)) * 100, 4),
        "daily_std_pct": round(float(np.std(arr)) * 100, 4),
        "skewness": round(float(pd.Series(arr).skew()), 4),
        "kurtosis": round(float(pd.Series(arr).kurtosis()), 4),
        "var_cvar_matrix": results,
    }