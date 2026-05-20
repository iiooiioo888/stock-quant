"""
統一行情拉取 — 多數據源自動降級

優先級（依標的類型略有不同）：
  本地庫 → Yahoo Finance → 東方財富 → Twelve Data（全球標的）
實時報價：A 股走 realtime.fetch_one_realtime；全球走 global_market.get_global_realtime
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

from src.core.data_sources import get_session
from src.core.yahoo_finance import (
    a_share_to_yahoo,
    yahoo_chart,
    yahoo_quote,
    yahoo_to_a_share,
)
from src.utils.logger import logger

_HTTP = get_session("market_fetch")


def days_to_yahoo_range(days: int) -> str:
    if days <= 30:
        return "1mo"
    if days <= 90:
        return "3mo"
    if days <= 180:
        return "6mo"
    if days <= 365:
        return "1y"
    return "2y"


def symbol_to_a_share_code(symbol: str) -> Optional[str]:
    """Yahoo / 純數字 → 6 位 A 股代碼（非 A 股返回 None）"""
    s = str(symbol).strip().upper()
    if s.endswith((".SS", ".SZ")):
        code = yahoo_to_a_share(s)
        return code if code.isdigit() and len(code) == 6 else None
    if s.isdigit() and len(s) == 6:
        return s
    return None


def _em_secid_for_kline(symbol: str) -> str:
    """東財歷史 K 線 secid"""
    s = symbol.upper().strip()
    if s.endswith(".SS"):
        return f"1.{s[:-3]}"
    if s.endswith(".SZ"):
        return f"0.{s[:-3]}"
    from src.core.global_market import _to_em_secid

    return _to_em_secid(s)


def _fetch_local_kline(symbol: str, days: int) -> pd.DataFrame:
    try:
        from src.core.db import load_daily_kline
        from src.core.local_kline import normalize_kline_code

        keys = []
        a_code = symbol_to_a_share_code(symbol)
        if a_code:
            keys.append(a_code)
        norm = normalize_kline_code(symbol)
        if norm not in keys:
            keys.append(norm)
        raw = symbol.strip()
        if raw not in keys:
            keys.append(raw)

        need = min(10, max(2, days // 5))
        for key in keys:
            df = load_daily_kline(key)
            if df.empty or len(df) < need:
                continue
            return df.tail(days).reset_index(drop=True)
        return pd.DataFrame()
    except Exception as e:
        logger.debug(f"本地庫 {symbol} K 線失敗: {e}")
        return pd.DataFrame()


def _fetch_eastmoney_kline(symbol: str, days: int) -> pd.DataFrame:
    secid = _em_secid_for_kline(symbol)
    if not secid:
        return pd.DataFrame()

    beg = (datetime.now() - timedelta(days=days + 45)).strftime("%Y%m%d")
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": secid,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101",
        "fqt": "1",
        "beg": beg,
        "end": "20500101",
        "lmt": str(max(days + 30, 120)),
    }
    try:
        resp = _HTTP.get(url, params=params, timeout=15)
        resp.raise_for_status()
        klines = resp.json().get("data", {}).get("klines", [])
        if not klines:
            return pd.DataFrame()

        rows = []
        for line in klines:
            parts = line.split(",")
            if len(parts) < 7:
                continue
            rows.append({
                "date": parts[0],
                "open": float(parts[1]),
                "close": float(parts[2]),
                "high": float(parts[3]),
                "low": float(parts[4]),
                "volume": float(parts[5]),
                "amount": float(parts[6]) if len(parts) > 6 else 0,
                "turnover": float(parts[10]) if len(parts) > 10 else 0,
            })
        df = pd.DataFrame(rows)
        return df.tail(days).reset_index(drop=True)
    except Exception as e:
        logger.debug(f"東財 K 線 {symbol} 失敗: {e}")
        return pd.DataFrame()


def fetch_history_df(symbol: str, days: int = 90) -> tuple[pd.DataFrame, str]:
    """
    拉取日 K 線（多源降級）。
    返回 (DataFrame, source_name)；失敗時為空 DataFrame 與空字串。
    """
    symbol = symbol.strip()
    days = max(2, int(days))

    # 1. 本地庫（有則不再請求外網）
    df = _fetch_local_kline(symbol, days)
    if not df.empty:
        return df, "local_db"

    code = symbol_to_a_share_code(symbol)

    def _return_online(df: pd.DataFrame, source: str) -> tuple[pd.DataFrame, str]:
        if df.empty or len(df) < 2:
            return pd.DataFrame(), ""
        from src.core.local_kline import persist_kline_df

        persist_kline_df(symbol, df)
        return df, source

    # 2. Yahoo Finance
    yahoo_sym = a_share_to_yahoo(symbol) if code else symbol
    df = yahoo_chart(yahoo_sym, range_str=days_to_yahoo_range(days), interval="1d")
    if not df.empty:
        df = df.tail(days).reset_index(drop=True)
        out, src = _return_online(df, "yahoo")
        if not out.empty:
            return out, src

    # 3. 東方財富
    df = _fetch_eastmoney_kline(symbol, days)
    if not df.empty and len(df) >= 2:
        out, src = _return_online(df, "eastmoney")
        if not out.empty:
            return out, src

    # 4. 全球模塊（Yahoo + Twelve Data）
    try:
        from src.core.global_market import download_global_symbol

        start = (datetime.now() - timedelta(days=days + 60)).strftime("%Y%m%d")
        df = download_global_symbol(yahoo_sym, start_date=start)
        if not df.empty:
            df = df.tail(days).reset_index(drop=True)
            out, src = _return_online(df, "global")
            if not out.empty:
                return out, src
    except Exception as e:
        logger.debug(f"全球下載 {symbol} 失敗: {e}")

    return pd.DataFrame(), ""


def fetch_quote(symbol: str) -> tuple[dict, str]:
    """多源實時報價，返回 (quote_dict, source)"""
    symbol = symbol.strip()
    code = symbol_to_a_share_code(symbol)
    yahoo_sym = a_share_to_yahoo(symbol) if code else symbol

    if code:
        try:
            from src.core.realtime import fetch_one_realtime

            q = fetch_one_realtime(code)
            if q and q.get("price", 0) > 0:
                return q, q.get("source", "a_share_realtime")
        except Exception as e:
            logger.debug(f"A 股實時 {code} 失敗: {e}")

    q = yahoo_quote(yahoo_sym) or {}
    if q.get("price"):
        q.setdefault("source", "yahoo")
        return q, "yahoo"

    try:
        from src.core.global_market import get_global_realtime

        rows = get_global_realtime([yahoo_sym])
        if rows:
            return rows[0], rows[0].get("source", "global")
    except Exception as e:
        logger.debug(f"全球報價 {symbol} 失敗: {e}")

    return {}, ""


def _metrics_from_df(df: pd.DataFrame) -> tuple[float, float, float]:
    closes = df["close"].astype(float).tolist()
    latest = float(closes[-1])
    prev = float(closes[-2]) if len(closes) >= 2 else latest
    change = latest - prev
    change_pct = (change / prev * 100) if prev else 0.0
    return latest, change, change_pct


def df_to_kline_records(df: pd.DataFrame) -> list[dict]:
    return [
        {
            "date": row["date"],
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": int(row.get("volume") or 0),
        }
        for _, row in df.iterrows()
    ]


def build_index_chart_item(symbol: str, name: str, days: int) -> Optional[dict]:
    """首頁指數卡片：K 線 + 報價（多源）"""
    df, hist_source = fetch_history_df(symbol, days)
    if df.empty or len(df) < 2:
        return None

    latest, change, change_pct = _metrics_from_df(df)
    quote, quote_source = fetch_quote(symbol)

    if quote.get("price"):
        latest = float(quote["price"])
    if quote.get("change_pct") is not None:
        change_pct = float(quote["change_pct"])
        if quote.get("change") is not None:
            change = float(quote["change"])

    source = quote_source or hist_source or "unknown"
    if quote_source and hist_source and quote_source != hist_source:
        source = f"{hist_source}+{quote_source}"

    return {
        "symbol": symbol,
        "name": name,
        "latest": round(latest, 4),
        "change": round(change, 4),
        "change_pct": round(change_pct, 2),
        "currency": quote.get("currency", ""),
        "source": source,
        "kline": df_to_kline_records(df),
    }


def build_sparkline_item(code: str, days: int = 30) -> dict:
    """儀表盤迷你走勢（多源）"""
    code = str(code).strip()
    yahoo_sym = a_share_to_yahoo(code)
    df, source = fetch_history_df(yahoo_sym, days)

    if df.empty:
        return {"prices": [], "dates": [], "change_pct": 0, "latest": 0, "source": ""}

    df = df.tail(days)
    prices = df["close"].astype(float).tolist()
    dates = df["date"].tolist()

    if len(prices) >= 2:
        change = (prices[-1] - prices[0]) / prices[0] * 100
    else:
        change = 0

    return {
        "prices": [round(p, 4) for p in prices],
        "dates": dates,
        "change_pct": round(change, 2),
        "latest": round(prices[-1], 4) if prices else 0,
        "source": source,
    }
