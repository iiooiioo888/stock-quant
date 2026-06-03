"""
日 K 自動選源下載 — 依 data_sources 註冊表動態排序，無需手動指定來源。

流程（單標的）：
  1. 多源管線 fetch_history_df（IB/TV → 本地 → Yahoo → 東財 → 全球）
  2. 仍不足時走市場專用降級鏈（A 股：新浪/網易/騰訊/HTTP 等）
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from src.config import settings
from src.utils.logger import logger

# DataSource.name → 對外顯示/觀測用 slug
SOURCE_SLUG: dict[str, str] = {
    "Interactive Brokers": "ib",
    "TradingView": "tradingview",
    "Yahoo Finance": "yahoo",
    "Twelve Data": "twelvedata",
    "東方財富": "eastmoney",
    "新浪": "sina",
    "網易": "netease",
    "騰訊": "tencent",
    "HTTP直連": "http",
    "Binance": "binance",
    "CoinGecko": "coingecko",
    "Frankfurter": "frankfurter",
}


def source_slug(name: str) -> str:
    return SOURCE_SLUG.get(name, (name or "unknown").lower().replace(" ", "_"))


def days_from_start_date(start_date: str | None) -> int:
    if not start_date:
        return 400
    raw = str(start_date).replace("-", "")[:8]
    try:
        sd = datetime.strptime(raw, "%Y%m%d")
        return max(30, min(3650, (datetime.now() - sd).days + 30))
    except ValueError:
        return 400


def _try_pipeline_fetch(code: str, market: str, start_date: str | None) -> tuple[int, str]:
    """market_fetch 多源管線（含寫庫）。"""
    if market not in ("a_share", "global"):
        return 0, ""

    from src.core.local_kline import normalize_kline_code
    from src.core.market_fetch import fetch_history_df
    from src.core.yahoo_finance import a_share_to_yahoo

    norm = normalize_kline_code(code)
    days = days_from_start_date(start_date)
    sym = a_share_to_yahoo(norm) if market == "a_share" else norm
    if not sym:
        sym = norm

    df, src = fetch_history_df(sym, days, skip_catalog=False)
    if df is None or df.empty or len(df) < 2:
        return 0, ""
    # 僅命中本地且未寫入新數據時，交給後續市場降級鏈（避免誤判為已成功拉取）
    if src == "local_db":
        return 0, ""

    from src.core.db import load_daily_kline

    stored = load_daily_kline(norm, start_date=start_date)
    n = len(stored) if stored is not None and not stored.empty else len(df)
    return max(n, len(df)), src or "auto"


def _run_ordered_sources(
    category: str,
    handlers: dict[str, Callable[[], int]],
) -> tuple[int, str]:
    from src.core.data_sources import get_sources, record_outcome

    for src in get_sources(category):
        handler = handlers.get(src.name)
        if not handler:
            continue
        try:
            count = int(handler() or 0)
            if count > 0:
                record_outcome(category, src.name, ok=True)
                return count, source_slug(src.name)
            record_outcome(category, src.name, ok=False, status_code=404)
        except Exception as e:
            logger.debug(f"{src.name} 下載失敗: {e}")
            record_outcome(category, src.name, ok=False)
    return 0, ""


def download_one_auto(
    code: str,
    start_date: str | None = None,
    market: str | None = None,
) -> tuple[int, str]:
    """
    自動選源下載單標的日 K 並寫入 SQLite。

    Returns:
        (寫入/可用條數, source_slug)
    """
    from src.core.history import detect_market

    if start_date is None:
        start_date = settings.history_start_date
    if market is None:
        market = detect_market(code)

    n, src = _try_pipeline_fetch(code, market, start_date)
    if n > 0:
        return n, src or "auto"

    if market == "global":
        from src.core.history import download_global_auto

        n, src = download_global_auto(code, start_date)
    elif market == "a_share":
        from src.core.history import _download_a_share

        n = _download_a_share(code, start_date)
        src = "a_share_chain" if n else ""
    elif market == "crypto":
        from src.core.history import _download_crypto

        n = _download_crypto(code, start_date)
        src = "binance" if n else ""
    elif market == "forex":
        from src.core.history import _download_forex

        n = _download_forex(code, start_date)
        src = "frankfurter" if n else ""
    else:
        from src.core.history import _download_a_share

        n = _download_a_share(code, start_date)
        src = "a_share_chain" if n else ""

    if n > 0:
        try:
            from src.core.cache import invalidate_by_rule

            invalidate_by_rule("data_update", code=code)
        except Exception:
            pass
    return n, src
