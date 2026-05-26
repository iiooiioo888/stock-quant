"""
TradingView 行情數據 — Scanner 報價 + TVC History K 線

非官方接口，需 Referer；失敗時由 market_fetch 降級至 Yahoo 等。
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

from src.core.data_sources import get_session
from src.utils.logger import logger

_TV_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Origin": "https://www.tradingview.com",
    "Referer": "https://www.tradingview.com/",
    "Accept": "application/json",
}

_SESSION = get_session("tradingview")
_SESSION.headers.update(_TV_HEADERS)

_SCANNER_BASE = "https://scanner.tradingview.com"
_HISTORY_BASE = "https://tvc4.tradingview.com/history"

# scanner 路由別名
_SCANNER_ALIASES = {
    "hongkong": "hong_kong",
    "uk": "uk",
    "germany": "germany",
    "japan": "japan",
    "korea": "korea",
}


def _scanner_market(scanner: str) -> str:
    s = (scanner or "america").strip().lower()
    return _SCANNER_ALIASES.get(s, s)


def fetch_tv_quote(tv_symbol: str, scanner: str = "america") -> dict:
    """
    單標的報價（TradingView Scanner）。
    返回 quote dict 或空 dict。
    """
    tv_symbol = str(tv_symbol).strip()
    if not tv_symbol:
        return {}

    market = _scanner_market(scanner)
    url = f"{_SCANNER_BASE}/{market}/scan"
    payload = {
        "symbols": {"tickers": [tv_symbol], "query": {"types": []}},
        "columns": [
            "close", "change", "change_abs", "volume",
            "description", "currency", "market",
        ],
    }
    try:
        resp = _SESSION.post(url, json=payload, timeout=12)
        resp.raise_for_status()
        data = resp.json()
        rows = data.get("data") or []
        if not rows:
            return {}

        row = rows[0]
        vals = row.get("d") or []
        if len(vals) < 3:
            return {}

        close = float(vals[0] or 0)
        change_pct = float(vals[1] or 0)
        change_abs = float(vals[2] or 0)
        if close <= 0:
            return {}

        name = str(vals[4] or tv_symbol) if len(vals) > 4 else tv_symbol
        currency = str(vals[5] or "") if len(vals) > 5 else ""

        return {
            "symbol": tv_symbol,
            "name": name,
            "price": round(close, 6),
            "change_pct": round(change_pct, 4),
            "change": round(change_abs, 6),
            "currency": currency,
            "source": "tradingview",
        }
    except Exception as e:
        logger.debug(f"TradingView quote {tv_symbol} 失敗: {e}")
        return {}


def fetch_tv_history(tv_symbol: str, days: int = 90) -> pd.DataFrame:
    """
    TradingView TVC History 日 K。
    返回 columns: date, open, high, low, close, volume
    """
    tv_symbol = str(tv_symbol).strip()
    if not tv_symbol:
        return pd.DataFrame()

    days = max(2, int(days))
    now = int(time.time())
    start = int((datetime.now() - timedelta(days=days + 30)).timestamp())

    params = {
        "symbol": tv_symbol,
        "resolution": "D",
        "from": start,
        "to": now,
        "countback": days + 10,
    }
    try:
        resp = _SESSION.get(_HISTORY_BASE, params=params, timeout=15)
        resp.raise_for_status()
        body = resp.json()
        if body.get("s") != "ok":
            return pd.DataFrame()

        ts = body.get("t") or []
        opens = body.get("o") or []
        highs = body.get("h") or []
        lows = body.get("l") or []
        closes = body.get("c") or []
        volumes = body.get("v") or []
        if len(ts) < 2:
            return pd.DataFrame()

        rows = []
        for i, t in enumerate(ts):
            try:
                dt = datetime.utcfromtimestamp(int(t)).strftime("%Y-%m-%d")
                rows.append({
                    "date": dt,
                    "open": float(opens[i]),
                    "high": float(highs[i]),
                    "low": float(lows[i]),
                    "close": float(closes[i]),
                    "volume": float(volumes[i]) if i < len(volumes) else 0,
                })
            except (IndexError, TypeError, ValueError):
                continue

        if len(rows) < 2:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        return df.tail(days).reset_index(drop=True)
    except Exception as e:
        logger.debug(f"TradingView history {tv_symbol} 失敗: {e}")
        return pd.DataFrame()


def fetch_tv_bundle(
    tv_symbol: str,
    scanner: str,
    days: int,
    fallback_symbol: str = "",
) -> tuple[pd.DataFrame, dict, str]:
    """
    同時拉 K 線 + 報價。
    返回 (df, quote, source_tag)；失敗時 df 為空。
    """
    df = fetch_tv_history(tv_symbol, days)
    quote = fetch_tv_quote(tv_symbol, scanner)
    if df.empty and not quote:
        return pd.DataFrame(), {}, ""

    tag = "tradingview"
    if quote:
        quote.setdefault("source", tag)
    return df, quote, tag


def tv_health_probe() -> dict:
    """探活：用 EURUSD 測 scanner。"""
    q = fetch_tv_quote("FX:EURUSD", "forex")
    return {
        "ok": bool(q.get("price")),
        "sample": "FX:EURUSD",
        "price": q.get("price"),
    }
