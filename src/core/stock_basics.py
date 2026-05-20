"""
股票基本數據 — 從本地日 K / 實時快照 / 基本面庫彙總技術與行情指標
"""
import sqlite3
from typing import Optional

import numpy as np
import pandas as pd

from src.core.db import get_conn, load_daily_kline
from src.utils.logger import logger


def _normalize_code(code: str) -> str:
    code = str(code).strip()
    if code.isdigit() and len(code) < 6:
        return code.zfill(6)
    return code


def _pct_change(cur: float, prev: float) -> Optional[float]:
    if prev is None or prev == 0:
        return None
    return round((cur / prev - 1) * 100, 2)


def _load_aux_data(code: str) -> tuple[dict, dict]:
    """一次連接讀取實時快照 + 基本面摘要"""
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rt = conn.execute(
            """SELECT code, name, price, change_pct, updated_at
               FROM realtime_snapshot WHERE code = ?""",
            (code,),
        ).fetchone()
        fund = conn.execute(
            """SELECT code, name, update_date, pe_ttm, pb, roe, eps, bvps,
                      total_mv, circulating_mv, gross_margin, net_margin,
                      debt_ratio, dividend_yield, revenue, net_profit
               FROM fundamentals WHERE code = ?
               ORDER BY update_date DESC LIMIT 1""",
            (code,),
        ).fetchone()
    realtime = dict(rt) if rt else {}
    if not fund:
        return realtime, {}
    d = dict(fund)
    fundamentals = {
        "pe_ttm": d.get("pe_ttm"),
        "pb": d.get("pb"),
        "roe": d.get("roe"),
        "eps": d.get("eps"),
        "bvps": d.get("bvps"),
        "total_mv": d.get("total_mv"),
        "circulating_mv": d.get("circulating_mv"),
        "gross_margin": d.get("gross_margin"),
        "net_margin": d.get("net_margin"),
        "debt_ratio": d.get("debt_ratio"),
        "dividend_yield": d.get("dividend_yield"),
        "revenue": d.get("revenue"),
        "net_profit": d.get("net_profit"),
        "update_date": d.get("update_date"),
        "name": d.get("name"),
    }
    return realtime, fundamentals


def _np_tail_mean(arr: np.ndarray, n: int) -> Optional[float]:
    if len(arr) < n:
        return None
    return round(float(arr[-n:].mean()), 4)


def build_stock_overview(code: str, lookback: int = 250) -> dict:
    """
    彙總單股基本數據：最新價、漲跌、均線、量能、波動、區間高低等。
    """
    from src.core.local_kline import ensure_daily_kline

    code = _normalize_code(code)
    df, kline_source = ensure_daily_kline(code, min_bars=20)
    if df.empty:
        return {
            "code": code,
            "has_kline": False,
            "message": "無法取得日 K（外網拉取失敗），請稍後重試或手動下載",
        }

    if len(df) > lookback:
        df = df.iloc[-lookback:]

    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else last
    close = float(last["close"])
    prev_close = float(prev["close"])
    high = float(last.get("high", close) or close)
    low = float(last.get("low", close) or close)
    open_p = float(last.get("open", close) or close)
    volume = float(last.get("volume", 0) or 0)
    amount = float(last.get("amount", 0) or 0)
    turnover = last.get("turnover")

    c = df["close"].to_numpy(dtype=float, copy=False)
    v = df["volume"].to_numpy(dtype=float, copy=False) if "volume" in df.columns else np.zeros(len(df))

    ma5 = _np_tail_mean(c, 5)
    ma10 = _np_tail_mean(c, 10)
    ma20 = _np_tail_mean(c, 20)
    ma60 = _np_tail_mean(c, 60)

    vol_ma20 = _np_tail_mean(v, 20)
    vol_ratio = round(volume / vol_ma20, 2) if vol_ma20 and vol_ma20 > 0 else None

    h_arr = df["high"].to_numpy(dtype=float, copy=False) if "high" in df.columns else c
    l_arr = df["low"].to_numpy(dtype=float, copy=False) if "low" in df.columns else c
    window_high = round(float(h_arr.max()), 2)
    window_low = round(float(l_arr.min()), 2)

    amplitude = round((high - low) / prev_close * 100, 2) if prev_close else None

    volatility_20d = None
    if len(c) >= 21:
        ret = np.diff(c[-21:]) / c[-21:-1]
        volatility_20d = round(float(ret.std() * (252 ** 0.5) * 100), 2)

    change_5d = _pct_change(close, float(c[-6])) if len(c) >= 6 else None
    change_20d = _pct_change(close, float(c[-21])) if len(c) >= 21 else None
    change_60d = _pct_change(close, float(c[-61])) if len(c) >= 61 else None

    def _vs_ma(ma_val):
        if ma_val is None or ma_val == 0:
            return None
        return round((close / ma_val - 1) * 100, 2)

    realtime, fundamentals = _load_aux_data(code)
    name = fundamentals.get("name") or realtime.get("name") or ""

    technical = {
        "date": str(last["date"]),
        "open": round(open_p, 2),
        "high": round(high, 2),
        "low": round(low, 2),
        "close": round(close, 2),
        "prev_close": round(prev_close, 2),
        "change_pct": _pct_change(close, prev_close),
        "amplitude_pct": amplitude,
        "volume": volume,
        "amount": amount,
        "turnover": float(turnover) if turnover is not None and pd.notna(turnover) else None,
        "ma5": ma5,
        "ma10": ma10,
        "ma20": ma20,
        "ma60": ma60,
        "vs_ma5_pct": _vs_ma(ma5),
        "vs_ma10_pct": _vs_ma(ma10),
        "vs_ma20_pct": _vs_ma(ma20),
        "vs_ma60_pct": _vs_ma(ma60),
        "vol_ma20": vol_ma20,
        "volume_ratio": vol_ratio,
        "high_lookback": window_high,
        "low_lookback": window_low,
        "pct_from_high": round((close / window_high - 1) * 100, 2) if window_high else None,
        "pct_from_low": round((close / window_low - 1) * 100, 2) if window_low and window_low > 0 else None,
        "volatility_annual_pct": volatility_20d,
        "change_5d_pct": change_5d,
        "change_20d_pct": change_20d,
        "change_60d_pct": change_60d,
    }

    if realtime:
        technical["realtime"] = {
            "price": realtime.get("price"),
            "change_pct": realtime.get("change_pct"),
            "updated_at": realtime.get("updated_at"),
        }

    return {
        "code": code,
        "name": name,
        "has_kline": True,
        "kline_source": kline_source,
        "bars": len(df),
        "date_from": str(df["date"].iloc[0]),
        "date_to": str(df["date"].iloc[-1]),
        "lookback_days": lookback,
        "technical": technical,
        "fundamentals": fundamentals if fundamentals else None,
    }
