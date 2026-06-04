"""
統一行情拉取 — 多數據源自動降級

優先級（依標的類型略有不同）：
  目錄 IB → TradingView → 本地庫 → Yahoo → 東方財富 → Twelve Data（全球標的）
實時報價：A 股走 realtime.fetch_one_realtime；全球走 global_market.get_global_realtime

寫入本地 K 線：persist_kline_df → defer_data_cache_clear；批量任務結束後 flush（見 data_pipeline）。
財報：fundamental.get_fundamentals / data_pipeline.resolve_financials（非僅讀空表）。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

from src.core.circuit_breaker import CircuitBreakerOpenError, circuit_breaker
from src.core.data_sources import get_session
from src.core.yahoo_finance import (
    a_share_to_yahoo,
    yahoo_chart,
    yahoo_quote,
    yahoo_to_a_share,
)
from src.utils.logger import logger

_HTTP = get_session("market_fetch")


def _record_kline_fetch(source: str) -> None:
    try:
        from src.core.pipeline_observability import record_kline_fetch

        record_kline_fetch(source)
    except Exception:
        pass


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


@circuit_breaker("eastmoney", failure_threshold=3, recovery_timeout=120)
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


# ── 外部調用熔斷封裝 ─────────────────────────────────────────

@circuit_breaker("yahoo_chart", failure_threshold=5, recovery_timeout=180)
def _fetch_yahoo_chart(symbol: str, range_str: str, interval: str) -> pd.DataFrame:
    return yahoo_chart(symbol, range_str=range_str, interval=interval)


@circuit_breaker("yahoo_quote", failure_threshold=5, recovery_timeout=180)
def _fetch_yahoo_quote(symbol: str) -> dict:
    return yahoo_quote(symbol) or {}


@circuit_breaker("global_download", failure_threshold=3, recovery_timeout=120)
def _fetch_global_download(symbol: str, start_date: str) -> pd.DataFrame:
    from src.core.global_market import download_global_symbol
    return download_global_symbol(symbol, start_date=start_date)


@circuit_breaker("global_realtime", failure_threshold=3, recovery_timeout=120)
def _fetch_global_realtime(symbols: list[str]) -> list[dict]:
    from src.core.global_market import get_global_realtime
    return get_global_realtime(symbols)


@circuit_breaker("ib_bundle", failure_threshold=3, recovery_timeout=300)
def _fetch_ib_bundle(ib_symbol: str, days: int) -> tuple:
    from src.core.ib_data import fetch_ib_bundle
    return fetch_ib_bundle(ib_symbol, days)


@circuit_breaker("tv_bundle", failure_threshold=3, recovery_timeout=180)
def _fetch_tv_bundle(tv_symbol: str, scanner: str, days: int, symbol: str) -> tuple:
    from src.core.tradingview_data import fetch_tv_bundle
    return fetch_tv_bundle(tv_symbol, scanner, days, symbol)


def fetch_history_df(
    symbol: str,
    days: int = 90,
    *,
    skip_catalog: bool = False,
) -> tuple[pd.DataFrame, str]:
    """
    拉取日 K 線（多源降級）。
    順序：目錄 IB → TV → 本地庫 → Yahoo → 東財 → global（與 data-fetch-pipeline 一致）。
    返回 (DataFrame, source_name)；失敗時為空 DataFrame 與空字串。

    skip_catalog: 為 True 時跳過目錄 IB/TV（避免 build_index_chart_item 重複請求）。
    """
    symbol = symbol.strip()
    days = max(2, int(days))

    def _return_online(df: pd.DataFrame, source: str) -> tuple[pd.DataFrame, str]:
        if df.empty or len(df) < 2:
            return pd.DataFrame(), ""
        from src.core.local_kline import persist_kline_df

        persist_kline_df(symbol, df)
        _record_kline_fetch(source)
        return df, source

    # 0. 目錄 IB → TradingView（需 SQ_IB_ENABLED / TV 配置）
    if not skip_catalog:
        df_cat, _, src_cat = _fetch_catalog_primary(symbol, days)
        if not df_cat.empty and len(df_cat) >= 2:
            out, src = _return_online(df_cat, src_cat or "catalog")
            if not out.empty:
                return out, src

    # 1. 本地庫（有則不再請求外網）
    df = _fetch_local_kline(symbol, days)
    if not df.empty:
        _record_kline_fetch("local_db")
        return df, "local_db"

    code = symbol_to_a_share_code(symbol)

    # 2. Yahoo Finance
    yahoo_sym = a_share_to_yahoo(symbol) if code else symbol
    try:
        df = _fetch_yahoo_chart(yahoo_sym, range_str=days_to_yahoo_range(days), interval="1d")
    except CircuitBreakerOpenError:
        df = pd.DataFrame()
    except Exception:
        df = pd.DataFrame()
    if not df.empty:
        df = df.tail(days).reset_index(drop=True)
        out, src = _return_online(df, "yahoo")
        if not out.empty:
            return out, src

    # 3. 東方財富
    try:
        df = _fetch_eastmoney_kline(symbol, days)
    except CircuitBreakerOpenError:
        df = pd.DataFrame()
    except Exception:
        df = pd.DataFrame()
    if not df.empty and len(df) >= 2:
        out, src = _return_online(df, "eastmoney")
        if not out.empty:
            return out, src

    # 4. 全球模塊（Yahoo + Twelve Data）
    try:
        start = (datetime.now() - timedelta(days=days + 60)).strftime("%Y%m%d")
        df = _fetch_global_download(yahoo_sym, start_date=start)
        if not df.empty:
            df = df.tail(days).reset_index(drop=True)
            out, src = _return_online(df, "global")
            if not out.empty:
                return out, src
    except CircuitBreakerOpenError:
        pass
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

    try:
        q = _fetch_yahoo_quote(yahoo_sym)
    except CircuitBreakerOpenError:
        q = {}
    except Exception:
        q = {}
    if q.get("price"):
        q.setdefault("source", "yahoo")
        return q, "yahoo"

    try:
        rows = _fetch_global_realtime([yahoo_sym])
        if rows:
            return rows[0], rows[0].get("source", "global")
    except CircuitBreakerOpenError:
        pass
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


def _source_label(raw: str) -> str:
    """統一來源顯示名。"""
    m = {
        "tradingview": "TradingView",
        "ib": "IB",
        "yahoo": "Yahoo",
        "eastmoney": "東財",
        "local_db": "本地",
        "global": "Global",
        "twelvedata": "Twelve Data",
        "a_share_realtime": "A股實時",
    }
    if not raw:
        return ""
    parts = str(raw).split("+")
    return "+".join(m.get(p, p) for p in parts)


def _fetch_catalog_primary(symbol: str, days: int) -> tuple[pd.DataFrame, dict, str]:
    """
    按目錄優先拉 IB → TradingView；無目錄或未命中則返回空。
    """
    from src.core.market_catalog import lookup_instrument

    inst = lookup_instrument(symbol)
    if not inst:
        return pd.DataFrame(), {}, ""

    try:
        from src.config import settings
    except Exception:
        settings = None

    # 1. Interactive Brokers
    if inst.ib and settings and getattr(settings, "ib_enabled", False):
        try:
            df, quote, src = _fetch_ib_bundle(inst.ib, days)
            if not df.empty or quote.get("price"):
                return df, quote, src
        except CircuitBreakerOpenError:
            pass
        except Exception as e:
            logger.debug(f"IB 目錄 {symbol} 失敗: {e}")

    # 2. TradingView
    if inst.tv and (not settings or getattr(settings, "tradingview_enabled", True)):
        try:
            df, quote, src = _fetch_tv_bundle(inst.tv, inst.scanner, days, inst.symbol)
            if not df.empty or quote.get("price"):
                return df, quote, src
        except CircuitBreakerOpenError:
            pass
        except Exception as e:
            logger.debug(f"TradingView 目錄 {symbol} 失敗: {e}")

    return pd.DataFrame(), {}, ""


def build_index_chart_item(symbol: str, name: str, days: int) -> Optional[dict]:
    """首頁指數卡片：K 線 + 報價（本地優先 → 外部降級）"""
    from src.core.market_catalog import lookup_instrument

    inst = lookup_instrument(symbol)
    group = inst.group if inst else ""
    tv_symbol = inst.tv if inst else ""
    topbar = inst.topbar if inst else True

    quote = {}
    quote_source = ""

    # 1. 先查本地數據庫（最快）
    df, hist_source = fetch_history_df(symbol, days, skip_catalog=True)
    
    # 2. 本地無數據時才打外部 API
    if df.empty or len(df) < 2:
        df_ext, quote_ext, primary_source = _fetch_catalog_primary(symbol, days)
        if not df_ext.empty and len(df_ext) >= 2:
            df = df_ext
            hist_source = primary_source
            quote = quote_ext or {}
            quote_source = primary_source
        if df.empty or len(df) < 2:
            return None

    # 3. 只在沒有報價時才單獨請求
    if not quote or not quote.get("price"):
        quote, quote_source = fetch_quote(symbol)

    latest, change, change_pct = _metrics_from_df(df)

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
        "source": _source_label(source),
        "source_raw": source,
        "tv_symbol": tv_symbol,
        "group": group,
        "topbar": topbar,
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
