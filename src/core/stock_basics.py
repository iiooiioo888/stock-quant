"""
股票基本數據 — 從本地日 K / 實時快照 / 基本面庫彙總技術與行情指標
"""
import sqlite3
from typing import Optional

import numpy as np
import pandas as pd

from src.core.db import get_conn


def _normalize_code(code: str) -> str:
    code = str(code).strip()
    upper = code.upper()
    if upper.endswith((".HK", ".US")):
        return upper
    if code.isdigit() and len(code) < 6:
        return code.zfill(6)
    return code


def _infer_market(code: str) -> str:
    """依代碼推斷 stock_universe.market。"""
    c = str(code).strip().upper()
    if c.endswith(".HK") or (c.replace(".", "").isdigit() and len(c.replace(".", "")) <= 5):
        return "hk_stock"
    if c.endswith(".US") or (not c.replace(".", "").isdigit()):
        return "us_stock"
    return "a_share"


_MARKET_LABELS = {
    "a_share": "A股",
    "hk_stock": "港股",
    "us_stock": "美股",
}


def _profile_from_universe_row(row: dict, code: str) -> dict:
    market = row.get("market") or _infer_market(code)
    intro = (row.get("intro") or "").strip()
    industry = (row.get("industry") or "").strip()
    if not intro and industry:
        intro = industry
    return {
        "code": code,
        "market": market,
        "market_label": _MARKET_LABELS.get(market, market),
        "name": row.get("name") or "",
        "exchange": row.get("exchange") or "",
        "industry": industry,
        "intro": intro,
        "list_date": row.get("list_date") or "",
        "price": row.get("price"),
        "change_pct": row.get("change_pct"),
        "total_mv": row.get("total_mv"),
        "circulating_mv": row.get("circulating_mv"),
        "pe_ttm": row.get("pe_ttm"),
        "pb": row.get("pb"),
        "universe_updated_at": row.get("updated_at"),
    }


def load_stock_profile(code: str) -> dict:
    """從 stock_universe 讀取簡介、行業、交易所等。"""
    code = _normalize_code(code)
    markets_try: list[str] = []
    for m in (_infer_market(code), "a_share", "hk_stock", "us_stock"):
        if m not in markets_try:
            markets_try.append(m)

    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        for mkt in markets_try:
            row = conn.execute(
                """SELECT code, market, name, exchange, industry, intro, list_date,
                          total_mv, circulating_mv, pe_ttm, pb, change_pct, price, updated_at
                   FROM stock_universe WHERE code = ? AND market = ?""",
                (code, mkt),
            ).fetchone()
            if row:
                return _profile_from_universe_row(dict(row), code)
        row = conn.execute(
            """SELECT code, market, name, exchange, industry, intro, list_date,
                      total_mv, circulating_mv, pe_ttm, pb, change_pct, price, updated_at
               FROM stock_universe WHERE code = ?
               ORDER BY CASE WHEN rank_mv IS NULL THEN 1 ELSE 0 END, rank_mv ASC LIMIT 1""",
            (code,),
        ).fetchone()
        if row:
            return _profile_from_universe_row(dict(row), code)

    mkt = _infer_market(code)
    return {
        "code": code,
        "market": mkt,
        "market_label": _MARKET_LABELS.get(mkt, mkt),
        "name": "",
        "exchange": "",
        "industry": "",
        "intro": "",
        "list_date": "",
    }


def load_stock_financials(
    code: str,
    allow_fetch: bool = True,
    max_age_days: int = 7,
) -> Optional[dict]:
    """合併 fundamentals 表與 stock_universe / 實時快照；A 股可觸發在線補齊。"""
    code = _normalize_code(code)
    realtime, fundamentals = _load_aux_data(code)

    if allow_fetch and code.isdigit() and len(code) == 6:
        from src.core.data_pipeline import is_stale
        from src.core.fundamental import get_fundamentals

        stale = not fundamentals or is_stale(fundamentals.get("update_date"), max_age_days)
        missing_core = not fundamentals or fundamentals.get("pe_ttm") is None
        if stale or missing_core:
            fresh = get_fundamentals(code, max_age_days=max_age_days)
            if fresh:
                fundamentals = {
                    k: fresh[k]
                    for k in (
                        "pe_ttm", "pb", "ps_ttm", "roe", "eps", "bvps", "total_mv", "circulating_mv",
                        "gross_margin", "net_margin", "debt_ratio", "dividend_yield",
                        "revenue", "net_profit", "revenue_yoy", "profit_yoy",
                        "update_date", "name",
                    )
                    if fresh.get(k) is not None
                }

    profile = load_stock_profile(code)

    fin: dict = {"code": code, "has_data": False}
    for key in (
        "pe_ttm", "pb", "ps_ttm", "roe", "eps", "bvps", "total_mv", "circulating_mv",
        "gross_margin", "net_margin", "debt_ratio", "dividend_yield",
        "revenue", "net_profit", "revenue_yoy", "profit_yoy", "update_date",
    ):
        val = fundamentals.get(key) if fundamentals else None
        if val is None and profile:
            val = profile.get(key)
        if val is not None:
            fin[key] = val

    if profile:
        for key in ("pe_ttm", "pb", "ps_ttm", "total_mv", "circulating_mv"):
            if fin.get(key) is None and profile.get(key) is not None:
                fin[key] = profile[key]

    if realtime:
        fin["realtime_price"] = realtime.get("price")
        fin["realtime_change_pct"] = realtime.get("change_pct")
        fin["realtime_updated_at"] = realtime.get("updated_at")

    if fundamentals.get("source"):
        fin["source"] = fundamentals["source"]
    elif allow_fetch:
        fin["source"] = "merged"

    fin["has_data"] = any(
        fin.get(k) is not None
        for k in fin
        if k not in ("code", "has_data", "source", "realtime_price", "realtime_change_pct", "realtime_updated_at")
    )
    return fin if fin["has_data"] else None


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
            """SELECT code, name, update_date, pe_ttm, pb, ps_ttm, roe, eps, bvps,
                      total_mv, circulating_mv, gross_margin, net_margin,
                      debt_ratio, dividend_yield, revenue, net_profit,
                      revenue_yoy, profit_yoy
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
        "ps_ttm": d.get("ps_ttm"),
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
        "revenue_yoy": d.get("revenue_yoy"),
        "profit_yoy": d.get("profit_yoy"),
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
