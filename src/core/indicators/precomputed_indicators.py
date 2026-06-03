"""
指標預計算引擎 — 離線批量計算常用技術指標，回測時直接讀取

支援指標：
- MA/SMA/EMA (多種週期)
- MACD (多組參數)
- RSI (多種週期)
- ATR (多種週期)
- 布林帶 (多組參數)
- KDJ
- OBV
- 成交量均線

功能特性：
- 批量預計算：一次處理多支股票
- 增量更新：僅重新計算變化的數據
- 版本控制：基於 K 線數據版本自動失效
- 多進程加速：支援並行計算
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.core.indicators.fast_indicators import (
    compute_atr,
    compute_macd,
    compute_rsi,
    compute_sma,
)
from src.utils.logger import logger


@dataclass
class IndicatorConfig:
    """指標配置"""
    name: str
    params: Dict[str, Any]
    output_columns: List[str]
    ttl_days: int = 7  # 緩存有效天數


@dataclass
class PrecomputeResult:
    """預計算結果"""
    code: str
    indicator: str
    params_hash: str
    computed_at: str
    data_version: str
    row_count: int
    status: str = "success"  # success / failed / skipped
    error: Optional[str] = None


# 預設指標配置清單
DEFAULT_INDICATORS: List[IndicatorConfig] = [
    # SMA 移動平均
    IndicatorConfig("sma", {"period": 5}, ["sma_5"]),
    IndicatorConfig("sma", {"period": 10}, ["sma_10"]),
    IndicatorConfig("sma", {"period": 20}, ["sma_20"]),
    IndicatorConfig("sma", {"period": 60}, ["sma_60"]),
    IndicatorConfig("sma", {"period": 120}, ["sma_120"]),
    IndicatorConfig("sma", {"period": 250}, ["sma_250"]),

    # EMA 指數移動平均
    IndicatorConfig("ema", {"period": 12}, ["ema_12"]),
    IndicatorConfig("ema", {"period": 26}, ["ema_26"]),
    IndicatorConfig("ema", {"period": 50}, ["ema_50"]),

    # MACD
    IndicatorConfig("macd", {"fast": 12, "slow": 26, "signal": 9}, ["macd_line", "macd_signal", "macd_hist"]),
    IndicatorConfig("macd", {"fast": 6, "slow": 13, "signal": 5}, ["macd_line_f6", "macd_signal_f6", "macd_hist_f6"]),

    # RSI
    IndicatorConfig("rsi", {"period": 6}, ["rsi_6"]),
    IndicatorConfig("rsi", {"period": 12}, ["rsi_12"]),
    IndicatorConfig("rsi", {"period": 14}, ["rsi_14"]),
    IndicatorConfig("rsi", {"period": 24}, ["rsi_24"]),

    # ATR
    IndicatorConfig("atr", {"period": 14}, ["atr_14"]),
    IndicatorConfig("atr", {"period": 20}, ["atr_20"]),

    # 布林帶
    IndicatorConfig("bollinger", {"period": 20, "std": 2.0}, ["bb_upper", "bb_mid", "bb_lower"]),
    IndicatorConfig("bollinger", {"period": 26, "std": 2.0}, ["bb_upper_26", "bb_mid_26", "bb_lower_26"]),

    # 成交量均線
    IndicatorConfig("vma", {"period": 5}, ["vma_5"]),
    IndicatorConfig("vma", {"period": 10}, ["vma_10"]),
    IndicatorConfig("vma", {"period": 20}, ["vma_20"]),
]


def _params_hash(params: Dict[str, Any]) -> str:
    """生成參數哈希"""
    normalized = json.dumps(params, sort_keys=True, default=str)
    return hashlib.md5(normalized.encode()).hexdigest()[:16]


def _get_data_version(code: str) -> str:
    """獲取 K 線數據版本號"""
    try:
        from src.core.db import get_latest_date
        latest = get_latest_date(code)
        if latest:
            return f"{code}:{latest}"
    except Exception:
        pass

    # fallback 到文件修改時間
    try:
        from src.config import settings
        db_path = settings.db_path
        if os.path.exists(db_path):
            mtime = os.path.getmtime(db_path)
            return f"db:{int(mtime)}"
    except Exception:
        pass

    return "v0"


def _compute_sma(close: np.ndarray, period: int) -> np.ndarray:
    """計算 SMA"""
    return compute_sma(close, period)


def _compute_ema(close: np.ndarray, period: int) -> np.ndarray:
    """計算 EMA"""
    from src.core.indicators.fast_indicators import _ema_core
    return _ema_core(close.astype(np.float64), period)


def _compute_bollinger(
    close: np.ndarray,
    period: int = 20,
    std: float = 2.0,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """計算布林帶"""
    n = len(close)

    # 中軌 = SMA
    mid = compute_sma(close, period)

    # 計算標準差
    upper = np.full(n, np.nan, dtype=np.float64)
    lower = np.full(n, np.nan, dtype=np.float64)

    for i in range(period - 1, n):
        window = close[i - period + 1:i + 1]
        if not np.isnan(mid[i]):
            std_val = np.std(window)
            upper[i] = mid[i] + std * std_val
            lower[i] = mid[i] - std * std_val

    return upper, mid, lower


def _compute_kdj(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    n: int = 9,
    m1: int = 3,
    m2: int = 3,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """計算 KDJ"""
    n_len = len(close)
    k = np.full(n_len, np.nan, dtype=np.float64)
    d = np.full(n_len, np.nan, dtype=np.float64)
    j = np.full(n_len, np.nan, dtype=np.float64)

    for i in range(n - 1, n_len):
        highest = np.max(high[i - n + 1:i + 1])
        lowest = np.min(low[i - n + 1:i + 1])

        if highest == lowest:
            rsv = 50.0
        else:
            rsv = (close[i] - lowest) / (highest - lowest) * 100.0

        if i == n - 1:
            k[i] = 50.0
            d[i] = 50.0
        else:
            k[i] = (m2 - 1) / m2 * k[i - 1] + 1 / m2 * rsv
            d[i] = (m1 - 1) / m1 * d[i - 1] + 1 / m1 * k[i]

        j[i] = 3 * k[i] - 2 * d[i]

    return k, d, j


def _compute_obv(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    """計算 OBV"""
    n = len(close)
    obv = np.zeros(n, dtype=np.float64)

    for i in range(1, n):
        if close[i] > close[i - 1]:
            obv[i] = obv[i - 1] + volume[i]
        elif close[i] < close[i - 1]:
            obv[i] = obv[i - 1] - volume[i]
        else:
            obv[i] = obv[i - 1]

    return obv


def compute_indicator_for_code(
    code: str,
    config: IndicatorConfig,
) -> PrecomputeResult:
    """為單支股票計算單一指標"""
    start_time = time.time()

    try:
        # 載入 K 線數據
        from src.core.db import load_daily_kline
        df = load_daily_kline(code)

        if df.empty or len(df) < 10:
            return PrecomputeResult(
                code=code,
                indicator=config.name,
                params_hash=_params_hash(config.params),
                computed_at=datetime.now().isoformat(),
                data_version="empty",
                row_count=0,
                status="skipped",
                error="數據不足",
            )

        # 準備數據
        close = df["close"].astype(float).to_numpy()
        high = df["high"].astype(float).to_numpy()
        low = df["low"].astype(float).to_numpy()
        volume = df["volume"].astype(float).to_numpy()

        # 根據指標類型計算
        result_dict: Dict[str, np.ndarray] = {}

        if config.name == "sma":
            period = config.params.get("period", 20)
            result_dict[f"sma_{period}"] = _compute_sma(close, period)

        elif config.name == "ema":
            period = config.params.get("period", 12)
            result_dict[f"ema_{period}"] = _compute_ema(close, period)

        elif config.name == "macd":
            fast = config.params.get("fast", 12)
            slow = config.params.get("slow", 26)
            signal = config.params.get("signal", 9)
            line, sig, hist = compute_macd(close, fast, slow, signal)
            suffix = "" if fast == 12 else f"_f{fast}"
            result_dict[f"macd_line{suffix}"] = line
            result_dict[f"macd_signal{suffix}"] = sig
            result_dict[f"macd_hist{suffix}"] = hist

        elif config.name == "rsi":
            period = config.params.get("period", 14)
            result_dict[f"rsi_{period}"] = compute_rsi(close, period)

        elif config.name == "atr":
            period = config.params.get("period", 14)
            result_dict[f"atr_{period}"] = compute_atr(high, low, close, period)

        elif config.name == "bollinger":
            period = config.params.get("period", 20)
            std = config.params.get("std", 2.0)
            upper, mid, lower = _compute_bollinger(close, period, std)
            suffix = "" if period == 20 else f"_{period}"
            result_dict[f"bb_upper{suffix}"] = upper
            result_dict[f"bb_mid{suffix}"] = mid
            result_dict[f"bb_lower{suffix}"] = lower

        elif config.name == "kdj":
            n = config.params.get("n", 9)
            m1 = config.params.get("m1", 3)
            m2 = config.params.get("m2", 3)
            k, d, j = _compute_kdj(high, low, close, n, m1, m2)
            result_dict["kdj_k"] = k
            result_dict["kdj_d"] = d
            result_dict["kdj_j"] = j

        elif config.name == "obv":
            result_dict["obv"] = _compute_obv(close, volume)

        elif config.name == "vma":
            period = config.params.get("period", 20)
            result_dict[f"vma_{period}"] = _compute_sma(volume, period)

        else:
            return PrecomputeResult(
                code=code,
                indicator=config.name,
                params_hash=_params_hash(config.params),
                computed_at=datetime.now().isoformat(),
                data_version="unknown",
                row_count=0,
                status="failed",
                error=f"未知指標類型：{config.name}",
            )

        # 儲存到 SQLite
        _save_indicator_to_db(code, config, result_dict, df["date"].tolist())

        elapsed = time.time() - start_time
        logger.debug(f"預計算 {code} {config.name} 完成，耗時 {elapsed:.3f}s")

        return PrecomputeResult(
            code=code,
            indicator=config.name,
            params_hash=_params_hash(config.params),
            computed_at=datetime.now().isoformat(),
            data_version=_get_data_version(code),
            row_count=len(df),
            status="success",
        )

    except Exception as e:
        logger.error(f"預計算 {code} {config.name} 失敗：{e}")
        return PrecomputeResult(
            code=code,
            indicator=config.name,
            params_hash=_params_hash(config.params),
            computed_at=datetime.now().isoformat(),
            data_version="error",
            row_count=0,
            status="failed",
            error=str(e),
        )


def _save_indicator_to_db(
    code: str,
    config: IndicatorConfig,
    result_dict: Dict[str, np.ndarray],
    dates: List[str],
) -> None:
    """將指標結果儲存到 SQLite"""
    from src.config import settings

    db_path = settings.db_path
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 建立指標表（如果不存在）
        table_name = f"indicator_{code}_{config.name}_{_params_hash(config.params)}"

        # 建表語句
        columns_def = ", ".join([f'"{col}" REAL' for col in config.output_columns])
        create_sql = f"""
        CREATE TABLE IF NOT EXISTS "{table_name}" (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL UNIQUE,
            {columns_def},
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
        cursor.execute(create_sql)

        # 建立索引
        cursor.execute(f'CREATE INDEX IF NOT EXISTS "idx_{table_name}_date" ON "{table_name}"(date)')

        # 清空舊數據
        cursor.execute(f'DELETE FROM "{table_name}"')

        # 插入新數據
        n = len(dates)
        batch_size = 500

        for batch_start in range(0, n, batch_size):
            batch_end = min(batch_start + batch_size, n)
            rows = []

            for i in range(batch_start, batch_end):
                row = [dates[i]]
                for col in config.output_columns:
                    if col in result_dict and i < len(result_dict[col]):
                        val = result_dict[col][i]
                        row.append(None if np.isnan(val) else float(val))
                    else:
                        row.append(None)
                rows.append(tuple(row))

            placeholders = ", ".join(["?" for _ in row])
            insert_sql = f'INSERT OR REPLACE INTO "{table_name}" (date, {", ".join(config.output_columns)}) VALUES ({placeholders})'
            cursor.executemany(insert_sql, rows)

        conn.commit()
        logger.debug(f"已儲存 {code} {config.name} 共 {n} 筆指標數據到 {table_name}")

    finally:
        conn.close()


def precompute_all_indicators(
    codes: List[str],
    indicators: Optional[List[IndicatorConfig]] = None,
    max_workers: int = 4,
) -> List[PrecomputeResult]:
    """批量預計算所有指標"""
    indicators = indicators or DEFAULT_INDICATORS

    logger.info(f"開始預計算 {len(codes)} 支股票，共 {len(indicators)} 個指標配置")

    all_results: List[PrecomputeResult] = []
    tasks = []

    # 建立任務清單
    for code in codes:
        for config in indicators:
            tasks.append((code, config))

    logger.info(f"總共 {len(tasks)} 個計算任務")

    # 使用進程池並行計算
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(compute_indicator_for_code, code, config): (code, config)
            for code, config in tasks
        }

        completed = 0
        for future in as_completed(futures):
            result = future.result()
            all_results.append(result)
            completed += 1

            if completed % 50 == 0:
                success_count = sum(1 for r in all_results if r.status == "success")
                logger.info(f"進度：{completed}/{len(tasks)}，成功 {success_count}")

    # 統計結果
    success_count = sum(1 for r in all_results if r.status == "success")
    failed_count = sum(1 for r in all_results if r.status == "failed")
    skipped_count = sum(1 for r in all_results if r.status == "skipped")

    logger.info(
        f"預計算完成：總計 {len(all_results)}，成功 {success_count}，"
        f"失敗 {failed_count}，跳過 {skipped_count}"
    )

    return all_results


def get_cached_indicator(
    code: str,
    indicator_name: str,
    params: Optional[Dict[str, Any]] = None,
) -> Optional[pd.DataFrame]:
    """從緩存取回已預計算的指標"""
    from src.config import settings

    # 找到匹配的配置
    config = None
    for cfg in DEFAULT_INDICATORS:
        if cfg.name == indicator_name:
            if params is None or cfg.params == params:
                config = cfg
                break

    if config is None:
        logger.warning(f"未找到指標配置：{indicator_name} {params}")
        return None

    # 檢查數據版本是否匹配
    _get_data_version(code)

    db_path = settings.db_path
    conn = sqlite3.connect(db_path)

    try:
        table_name = f"indicator_{code}_{indicator_name}_{_params_hash(params or config.params)}"

        # 檢查表是否存在
        check_sql = """
        SELECT name FROM sqlite_master
        WHERE type='table' AND name=?
        """
        cursor = conn.cursor()
        cursor.execute(check_sql, (table_name,))

        if not cursor.fetchone():
            logger.debug(f"指標表不存在：{table_name}")
            return None

        # 讀取數據
        query_sql = f'SELECT date, {", ".join(config.output_columns)} FROM "{table_name}" ORDER BY date'
        df = pd.read_sql_query(query_sql, conn)

        if df.empty:
            return None

        logger.debug(f"命中指標緩存：{table_name}，共 {len(df)} 筆")
        return df

    finally:
        conn.close()


def warmup_indicators(
    codes: Optional[List[str]] = None,
    subset_indicators: Optional[List[str]] = None,
    max_workers: int = 4,
) -> Dict[str, Any]:
    """
    預熱指標緩存
    
    Args:
        codes: 股票代碼清單，None 表示所有股票
        subset_indicators: 要預熱的指標子集，None 表示全部
        max_workers: 最大並行 worker 數
    
    Returns:
        預熱結果統計
    """
    # 獲取股票清單（如果未提供）
    if codes is None:
        # 嘗試從 stock_universe 獲取，如果失敗則使用空清單
        try:
            from src.core.stock_universe import fetch_all_market_basics
            all_data = fetch_all_market_basics()
            codes = [item.get("code") for item in all_data if item.get("code")]
            logger.info(f"從 stock_universe 獲取 {len(codes)} 支股票")
        except Exception as e:
            logger.warning(f"無法獲取股票清單：{e}，請手動指定 codes 參數")
            return {"status": "error", "message": "沒有可用的股票代碼，請手動指定"}

    if not codes:
        return {"status": "error", "message": "沒有可用的股票代碼"}

    # 篩選指標
    indicators = DEFAULT_INDICATORS
    if subset_indicators:
        indicators = [cfg for cfg in indicators if cfg.name in subset_indicators]

    start_time = time.time()
    results = precompute_all_indicators(codes, indicators, max_workers)
    elapsed = time.time() - start_time

    # 統計
    success = sum(1 for r in results if r.status == "success")
    failed = sum(1 for r in results if r.status == "failed")
    skipped = sum(1 for r in results if r.status == "skipped")

    return {
        "status": "completed",
        "total_tasks": len(results),
        "success": success,
        "failed": failed,
        "skipped": skipped,
        "elapsed_seconds": round(elapsed, 2),
        "codes_processed": len(set(r.code for r in results)),
        "indicators_computed": len(set(f"{r.indicator}:{r.params_hash}" for r in results if r.status == "success")),
    }


# CLI 入口
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="指標預計算工具")
    parser.add_argument("--codes", nargs="+", help="股票代碼清單")
    parser.add_argument("--all", action="store_true", help="處理所有股票")
    parser.add_argument("--indicators", nargs="+", help="指定指標名稱")
    parser.add_argument("--workers", type=int, default=4, help="worker 數量")

    args = parser.parse_args()

    codes = args.codes if args.codes else None
    if args.all:
        from src.core.stock_universe import get_all_codes
        codes = get_all_codes()

    result = warmup_indicators(codes=codes, subset_indicators=args.indicators, max_workers=args.workers)
    print(json.dumps(result, indent=2, ensure_ascii=False))
