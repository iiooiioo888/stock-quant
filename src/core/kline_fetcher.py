"""
A 股日 K 統一降級入口 — 本地庫 → execute_with_fallback → 過期快取兜底。

供 market_fetch、auto_kline_fetch、history 共用，避免雙管線降級不一致。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd

from src.config import settings
from src.utils.logger import logger

A_SHARE_HISTORY = "a_share_history"
_HANDLERS_REGISTERED = False


def _normalize_start_date(start_date: str | None) -> str:
    if not start_date:
        return settings.history_start_date
    raw = str(start_date).replace("-", "")[:8]
    return raw if len(raw) == 8 else settings.history_start_date


def _filter_df_by_start(df: pd.DataFrame, start_date: str | None) -> pd.DataFrame:
    if df is None or df.empty or not start_date:
        return df
    sd = _normalize_start_date(start_date)
    sd_fmt = f"{sd[:4]}-{sd[4:6]}-{sd[6:]}"
    return df[df["date"] >= sd_fmt].reset_index(drop=True)


def _ak_symbol(code: str) -> str:
    return f"sh{code}" if str(code).startswith("6") else f"sz{code}"


class _YahooHistoryAdapter:
    name = "Yahoo Finance"

    def fetch_history(self, code: str, *, start_date: str | None = None, days: int = 400):
        if not settings.yahoo_enabled:
            return None
        from src.core.yahoo_finance import download_a_share_daily

        df = download_a_share_daily(code, start_date=_normalize_start_date(start_date))
        if df is None or df.empty:
            return None
        return df


class _EastmoneyAdapter:
    name = "東方財富"

    def fetch_history(self, code: str, *, start_date: str | None = None, days: int = 400):
        from src.core.market_fetch import _fetch_eastmoney_kline
        from src.core.yahoo_finance import a_share_to_yahoo

        symbol = a_share_to_yahoo(code)
        try:
            df = _fetch_eastmoney_kline(symbol, days)
            if df is not None and not df.empty:
                return _filter_df_by_start(df, start_date)
        except Exception as e:
            logger.debug(f"東財 HTTP {code} 失敗: {e}")
        if settings.akshare_enabled:
            return _fetch_akshare_eastmoney_df(code, _normalize_start_date(start_date))
        return None


class _SinaAdapter:
    name = "新浪"

    def fetch_history(self, code: str, *, start_date: str | None = None, days: int = 400):
        if not settings.akshare_enabled:
            return None
        return _fetch_sina_df(code, _normalize_start_date(start_date))


class _NeteaseAdapter:
    name = "網易"

    def fetch_history(self, code: str, *, start_date: str | None = None, days: int = 400):
        if not settings.akshare_enabled:
            return None
        return _fetch_netease_df(code, _normalize_start_date(start_date))


class _TencentAdapter:
    name = "騰訊"

    def fetch_history(self, code: str, *, start_date: str | None = None, days: int = 400):
        if not settings.akshare_enabled:
            return None
        return _fetch_tencent_df(code, _normalize_start_date(start_date))


class _HttpDirectAdapter:
    name = "HTTP直連"

    def fetch_history(self, code: str, *, start_date: str | None = None, days: int = 400):
        from src.core.history import _download_a_share_http

        df = _download_a_share_http(code, _normalize_start_date(start_date))
        if df is None or df.empty:
            return None
        return df


def _fetch_akshare_eastmoney_df(
    code: str, start_date: str, adjust: str = "qfq"
) -> pd.DataFrame | None:
    try:
        import akshare as ak
        from src.core.history import _patch_akshare_session

        _patch_akshare_session()
        df = ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start_date,
            adjust=adjust or "",
        )
        if df is None or df.empty:
            return None
        col_map = {
            "日期": "date",
            "开盘": "open",
            "最高": "high",
            "最低": "low",
            "收盘": "close",
            "成交量": "volume",
            "成交额": "amount",
            "换手率": "turnover",
        }
        return df.rename(columns=col_map)
    except Exception as e:
        logger.debug(f"AKShare 東財 {code} 失敗: {e}")
        return None


def _fetch_sina_df(code: str, start_date: str) -> pd.DataFrame | None:
    try:
        import akshare as ak
        from src.core.history import _patch_akshare_session

        _patch_akshare_session()
        df = ak.stock_zh_a_daily(symbol=_ak_symbol(code), adjust="qfq")
        if df is None or df.empty:
            return None
        col_map = {
            "date": "date",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
            "amount": "amount",
            "turnover": "turnover",
        }
        df = df.rename(columns=col_map)
        return _filter_df_by_start(df, start_date)
    except Exception as e:
        logger.debug(f"新浪 {code} 失敗: {e}")
        return None


def _fetch_netease_df(code: str, start_date: str) -> pd.DataFrame | None:
    try:
        import akshare as ak
        from src.core.history import _patch_akshare_session

        if not hasattr(ak, "stock_zh_a_hist_163"):
            return None
        _patch_akshare_session()
        df = ak.stock_zh_a_hist_163(symbol=code, start_date=start_date, adjust="qfq")
        if df is None or df.empty:
            return None
        col_map = {
            "日期": "date",
            "开盘": "open",
            "最高": "high",
            "最低": "low",
            "收盘": "close",
            "成交量": "volume",
            "成交额": "amount",
        }
        return df.rename(columns=col_map)
    except Exception as e:
        logger.debug(f"網易 {code} 失敗: {e}")
        return None


def _fetch_tencent_df(code: str, start_date: str) -> pd.DataFrame | None:
    try:
        import akshare as ak
        from src.core.history import _patch_akshare_session

        _patch_akshare_session()
        df = ak.stock_zh_a_hist_tx(symbol=_ak_symbol(code), start_date=start_date, adjust="qfq")
        if df is None or df.empty:
            return None
        col_map = {
            "date": "date",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
            "amount": "amount",
        }
        return df.rename(columns=col_map)
    except Exception as e:
        logger.debug(f"騰訊 {code} 失敗: {e}")
        return None


def register_a_share_history_handlers() -> None:
    """綁定 A 股歷史數據源適配器（冪等）。"""
    global _HANDLERS_REGISTERED
    if _HANDLERS_REGISTERED:
        return
    from src.core.data_sources import register_fetch_handler

    handlers = {
        "Yahoo Finance": _YahooHistoryAdapter(),
        "東方財富": _EastmoneyAdapter(),
        "新浪": _SinaAdapter(),
        "網易": _NeteaseAdapter(),
        "騰訊": _TencentAdapter(),
        "HTTP直連": _HttpDirectAdapter(),
    }
    for name, adapter in handlers.items():
        register_fetch_handler(A_SHARE_HISTORY, name, adapter)
    _HANDLERS_REGISTERED = True


def _get_stale_cache(code: str) -> pd.DataFrame | None:
    try:
        from src.core.cache import get_cached_kline

        cached = get_cached_kline(code)
        if cached:
            return pd.DataFrame(cached)
    except Exception as e:
        logger.debug(f"過期快取兜底跳過 {code}: {e}")
    return None


def fetch_a_share_history(
    code: str,
    start_date: str | None = None,
    *,
    skip_local: bool = False,
    days: int | None = None,
) -> tuple[pd.DataFrame, str]:
    """
    A 股日 K 統一入口：本地庫 → execute_with_fallback → 過期快取兜底。

    Returns:
        (DataFrame, source_slug)
    """
    register_a_share_history_handlers()

    from src.core.auto_kline_fetch import days_from_start_date
    from src.core.data_sources import execute_with_fallback, get_last_fetch_source
    from src.core.local_kline import normalize_kline_code
    from src.core.db import load_daily_kline

    norm = normalize_kline_code(code)
    if start_date is None:
        start_date = settings.history_start_date

    if not skip_local:
        local = load_daily_kline(norm, start_date=start_date)
        if local is not None and len(local) >= 2:
            return local, "local_db"

    if days is None:
        days = days_from_start_date(start_date)

    df = execute_with_fallback(
        A_SHARE_HISTORY,
        "fetch_history",
        norm,
        start_date=start_date,
        days=days,
    )
    src = get_last_fetch_source() or ""

    if df is not None and not df.empty and len(df) >= 2:
        from src.core.local_kline import persist_kline_df
        from src.core.pipeline_observability import record_kline_fetch

        persist_kline_df(norm, df)
        record_kline_fetch(src or "a_share_unified")
        return df, src

    cached = _get_stale_cache(norm)
    if cached is not None and len(cached) >= 2:
        logger.warning(f"使用過期緩存兜底: {norm}")
        return cached, "stale_cache"

    return pd.DataFrame(), ""


def download_a_share_kline(
    code: str,
    start_date: str | None = None,
) -> tuple[int, str]:
    """
    下載 A 股日 K 並寫入 SQLite（統一降級鏈）。

    Returns:
        (寫入/可用條數, source_slug)
    """
    from src.core.db import save_daily_kline
    from src.core.local_kline import normalize_kline_code

    norm = normalize_kline_code(code)
    df, src = fetch_a_share_history(code, start_date=start_date)
    if df is None or df.empty:
        return 0, ""

    if src == "local_db":
        return len(df), src

    count = save_daily_kline(df, norm)
    if count > 0:
        logger.info(f"{norm}: {count} 條記錄 ({src or 'unified'})")
    return count, src


# 模組載入時註冊適配器
register_a_share_history_handlers()
