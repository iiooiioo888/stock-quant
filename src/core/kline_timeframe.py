"""
回測 K 線週期 — 日線 / 60 分鐘（1 小時）/ 1 分鐘。

對外 API 使用 1d / 1h / 1m；內部分鐘庫週期為 60m / 1m。
"""

from __future__ import annotations

import pandas as pd

from src.core.local_kline import ensure_daily_kline, normalize_kline_code
from src.utils.logger import logger

# 用戶可選週期 → 元數據
TIMEFRAME_META: dict[str, dict] = {
    "1d": {
        "label": "日線 (1天)",
        "type": "daily",
        "minute_period": None,
        "bars_per_year": 252,
        "min_bars": 60,
    },
    "1h": {
        "label": "1 小時",
        "type": "minute",
        "minute_period": "60m",
        "bars_per_year": 252 * 4,
        "min_bars": 40,
    },
    "1m": {
        "label": "1 分鐘",
        "type": "minute",
        "minute_period": "1m",
        "bars_per_year": 252 * 240,
        "min_bars": 120,
    },
}

_ALIASES = {
    "1day": "1d",
    "day": "1d",
    "daily": "1d",
    "d": "1d",
    "1hour": "1h",
    "hour": "1h",
    "h": "1h",
    "60m": "1h",
    "60min": "1h",
    "1min": "1m",
    "minute": "1m",
    "min": "1m",
    "m1": "1m",
}


def normalize_timeframe(timeframe: str | None) -> str:
    """標準化為 1d / 1h / 1m。"""
    raw = (timeframe or "1d").strip().lower()
    key = _ALIASES.get(raw, raw)
    if key not in TIMEFRAME_META:
        raise ValueError(
            f"不支持的 K 線週期: {timeframe}，可選: {', '.join(TIMEFRAME_META.keys())}"
        )
    return key


def timeframe_label(timeframe: str | None) -> str:
    return TIMEFRAME_META[normalize_timeframe(timeframe)]["label"]


def bars_per_year(timeframe: str | None) -> int:
    return int(TIMEFRAME_META[normalize_timeframe(timeframe)]["bars_per_year"])


def list_timeframes() -> list[dict]:
    return [
        {
            "id": tf,
            "label": meta["label"],
            "type": meta["type"],
            "minute_period": meta["minute_period"],
        }
        for tf, meta in TIMEFRAME_META.items()
    ]


def cache_key(code: str, timeframe: str | None) -> str:
    return f"{normalize_kline_code(code)}|{normalize_timeframe(timeframe)}"


def _df_to_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "date" in out.columns and "datetime" not in out.columns:
        out["datetime"] = out["date"]
    out["datetime"] = pd.to_datetime(out["datetime"])
    out = out.set_index("datetime")
    out = out[["open", "high", "low", "close", "volume"]]
    out.columns = ["Open", "High", "Low", "Close", "Volume"]
    return out.sort_index()


def ensure_kline_for_backtest(
    code: str,
    timeframe: str | None = "1d",
) -> tuple[pd.DataFrame, str, str]:
    """
    讀取回測用 OHLCV（本地優先，不足時自動拉取）。

    Returns:
        (DataFrame indexed by datetime, source, normalized_timeframe)
    """
    code = normalize_kline_code(code)
    tf = normalize_timeframe(timeframe)
    meta = TIMEFRAME_META[tf]
    min_bars = meta["min_bars"]

    if meta["type"] == "daily":
        df, src = ensure_daily_kline(code, min_bars=min_bars)
        if df.empty:
            raise ValueError(f"股票 {code} 無日線數據（請檢查代碼或網路）")
        return _df_to_ohlcv(df), src, tf

    period = meta["minute_period"]
    from src.core.db import load_minute_kline
    from src.core.history import download_minute_data

    df = load_minute_kline(code, period)
    src = "local_db"
    if len(df) < min_bars:
        logger.info(f"本地 {code} {period} 不足（{len(df)} 條），從外網拉取…")
        download_minute_data(code, period)
        from src.core.db import _load_minute_kline_cached

        _load_minute_kline_cached.cache_clear()
        df = load_minute_kline(code, period)
        src = "fetched" if len(df) >= min_bars else "partial"

    if df.empty:
        raise ValueError(
            f"股票 {code} 無 {timeframe_label(tf)} 數據；"
            f"分鐘線通常僅保留近期交易日，請稍後重試或換用日線。"
        )
    if len(df) < min_bars:
        logger.warning(
            f"{code} {period} 僅 {len(df)} 條，低於建議 {min_bars} 條，回測結果可能不穩定"
        )

    return _df_to_ohlcv(df), src, tf
