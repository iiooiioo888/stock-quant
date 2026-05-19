"""
基準對比 — 滬深300 基準比較
"""
import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime
from src.core.db import load_daily_kline, get_conn
from src.utils.logger import logger

BENCHMARK_CODE = "000300"


def get_benchmark_returns(start_date: str = None, end_date: str = None) -> dict:
    """
    獲取滬深300 日收益率數據。
    
    Args:
        start_date: 起始日期 (YYYY-MM-DD 或 YYYYMMDD)
        end_date: 結束日期
    
    Returns:
        {"dates": [...], "prices": [...], "returns": [...], "nav": [...]}
    """
    # 嘗試從數據庫讀取
    df = load_daily_kline(BENCHMARK_CODE, start_date=start_date, end_date=end_date)

    if df.empty:
        # 從 AKShare 下載
        try:
            sd = start_date.replace("-", "") if start_date else "20200101"
            ed = end_date.replace("-", "") if end_date else datetime.now().strftime("%Y%m%d")
            raw = ak.stock_zh_index_daily(symbol="sh000300")
            if raw.empty:
                return {"dates": [], "prices": [], "returns": [], "nav": []}
            raw = raw.rename(columns={"date": "date", "open": "open", "high": "high",
                                       "low": "low", "close": "close", "volume": "volume"})
            raw["date"] = pd.to_datetime(raw["date"]).dt.strftime("%Y-%m-%d")
            if start_date:
                sd_fmt = f"{sd[:4]}-{sd[4:6]}-{sd[6:]}" if len(sd) == 8 else sd
                raw = raw[raw["date"] >= sd_fmt]
            if end_date:
                ed_fmt = f"{ed[:4]}-{ed[4:6]}-{ed[6:]}" if len(ed) == 8 else ed
                raw = raw[raw["date"] <= ed_fmt]
            raw = raw.sort_values("date").reset_index(drop=True)
            df = raw
        except Exception as e:
            logger.error(f"獲取滬深300 數據失敗: {e}")
            return {"dates": [], "prices": [], "returns": [], "nav": []}

    if df.empty:
        return {"dates": [], "prices": [], "returns": [], "nav": []}

    dates = df["date"].astype(str).tolist()
    prices = df["close"].astype(float).tolist()

    # 計算日收益率
    returns = [0.0]
    for i in range(1, len(prices)):
        if prices[i - 1] > 0:
            returns.append((prices[i] - prices[i - 1]) / prices[i - 1])
        else:
            returns.append(0.0)

    # 計算淨值
    nav = [1.0]
    for r in returns[1:]:
        nav.append(nav[-1] * (1 + r))

    return {
        "dates": dates,
        "prices": [round(p, 2) for p in prices],
        "returns": [round(r, 6) for r in returns],
        "nav": [round(n, 6) for n in nav],
    }


def compare_with_benchmark(backtest_result: dict) -> dict:
    """
    將回測結果與滬深300 基準進行比較。
    
    Args:
        backtest_result: run_backtest() 返回的結果字典
    
    Returns:
        {"alpha": ..., "beta": ..., "information_ratio": ..., "tracking_error": ...,
         "benchmark_return": ..., "excess_return": ...}
    """
    bt_dates = backtest_result.get("dates", [])
    bt_returns = backtest_result.get("daily_returns", [])

    if not bt_dates or not bt_returns:
        return {"error": "回測結果缺少日期或收益率數據"}

    start = bt_dates[0]
    end = bt_dates[-1]

    benchmark = get_benchmark_returns(start_date=start, end_date=end)
    bm_dates = benchmark.get("dates", [])
    bm_returns = benchmark.get("returns", [])

    if not bm_dates or not bm_returns:
        return {"error": "無法獲取基準數據"}

    # 對齊日期
    bm_map = dict(zip(bm_dates, bm_returns))
    aligned_bt = []
    aligned_bm = []

    for i, d in enumerate(bt_dates):
        if d in bm_map:
            aligned_bt.append(bt_returns[i])
            aligned_bm.append(bm_map[d])

    if len(aligned_bt) < 20:
        return {"error": f"對齊數據不足: {len(aligned_bt)} 天"}

    bt_arr = np.array(aligned_bt)
    bm_arr = np.array(aligned_bm)

    # Alpha, Beta (CAPM)
    cov_matrix = np.cov(bt_arr, bm_arr)
    beta = cov_matrix[0, 1] / cov_matrix[1, 1] if cov_matrix[1, 1] > 0 else 0
    alpha_daily = np.mean(bt_arr) - beta * np.mean(bm_arr)
    alpha_annual = alpha_daily * 252

    # Tracking error
    excess = bt_arr - bm_arr
    tracking_error = float(np.std(excess) * np.sqrt(252))

    # Information ratio
    information_ratio = float(np.mean(excess) / np.std(excess) * np.sqrt(252)) if np.std(excess) > 0 else 0

    # 總收益對比
    bt_total = backtest_result.get("total_return_pct", 0)
    bm_total = float((benchmark["nav"][-1] / benchmark["nav"][0] - 1) * 100) if benchmark["nav"] else 0

    result = {
        "alpha": round(float(alpha_annual), 4),
        "beta": round(float(beta), 4),
        "information_ratio": round(information_ratio, 4),
        "tracking_error": round(tracking_error, 4),
        "benchmark_return_pct": round(bm_total, 4),
        "strategy_return_pct": round(bt_total, 4),
        "excess_return_pct": round(bt_total - bm_total, 4),
        "benchmark_dates": benchmark["dates"],
        "benchmark_nav": benchmark["nav"],
    }

    logger.info(
        f"基準對比: alpha={alpha_annual:.4f} beta={beta:.4f} "
        f"IR={information_ratio:.4f} TE={tracking_error:.4f}"
    )

    return result
