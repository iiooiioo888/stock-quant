"""
Yahoo Finance 數據接口（免費，無需 API Key）

A 股代碼映射：600519 → 600519.SS，000001 → 000001.SZ
滬深300：000300.SS
"""
from __future__ import annotations

import random
import time
from datetime import datetime
from typing import Optional

import pandas as pd
import requests

from src.config import settings
from src.utils.logger import logger

YAHOO_BASE = "https://query1.finance.yahoo.com"
A_SHARE_HISTORY_CATEGORY = "a_share_history"
YAHOO_SOURCE_NAME = "Yahoo Finance"


class YahooDisabled(Exception):
    """Yahoo Finance 已透過配置關閉。"""


class YahooEmptyResult(Exception):
    """Yahoo 回傳空 K 線，應觸發降級而非視為成功。"""

    def __init__(self, symbol: str):
        self.symbol = symbol
        super().__init__(f"Yahoo chart empty: {symbol}")


class YahooRateLimited(Exception):
    """Yahoo 429 重試耗盡。"""

    def __init__(self, symbol: str):
        self.symbol = symbol
        super().__init__(f"Yahoo rate limited: {symbol}")


def _yahoo_session() -> requests.Session:
    from src.core.data_sources import get_session

    session = get_session("yahoo")
    session.headers.setdefault("Accept", "application/json")
    return session


def _get_yahoo_data_source():
    from src.core.data_sources import _find_source

    return _find_source(A_SHARE_HISTORY_CATEGORY, YAHOO_SOURCE_NAME)


def _record_yahoo_outcome(*, ok: bool, status_code: int | None = None) -> None:
    try:
        from src.core.data_sources import record_outcome

        record_outcome(A_SHARE_HISTORY_CATEGORY, YAHOO_SOURCE_NAME, ok=ok, status_code=status_code)
    except Exception:
        pass


def _sleep_on_rate_limit(resp: requests.Response, attempt: int) -> None:
    retry_after = resp.headers.get("Retry-After", "").strip()
    if retry_after.isdigit():
        delay = float(retry_after)
    else:
        base = float(settings.yahoo_request_interval)
        delay = base * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
    time.sleep(min(delay, 60.0))


def a_share_to_yahoo(code: str) -> str:
    """6 位 A 股代碼 → Yahoo symbol"""
    code = str(code).strip()
    if code.endswith((".SS", ".SZ", ".HK")):
        return code.upper()
    if not code.isdigit() or len(code) != 6:
        return code
    if code.startswith("6"):
        return f"{code}.SS"
    return f"{code}.SZ"


def yahoo_to_a_share(symbol: str) -> str:
    """Yahoo symbol → 6 位 A 股代碼（若可解析）"""
    s = symbol.upper()
    for suffix in (".SS", ".SZ"):
        if s.endswith(suffix):
            return s[: -len(suffix)]
    return symbol


def _start_to_range(start_date: Optional[str]) -> str:
    if not start_date:
        return "5y"
    sd = start_date.replace("-", "")
    try:
        dt = datetime.strptime(sd, "%Y%m%d")
        days = (datetime.now() - dt).days
        if days <= 30:
            return "1mo"
        if days <= 90:
            return "3mo"
        if days <= 365:
            return "1y"
        if days <= 730:
            return "2y"
        if days <= 1825:
            return "5y"
        return "max"
    except ValueError:
        return "5y"


def days_to_yahoo_range(days: int) -> str:
    """日數 → Yahoo range 參數。"""
    days = max(2, int(days))
    if days <= 30:
        return "1mo"
    if days <= 90:
        return "3mo"
    if days <= 180:
        return "6mo"
    if days <= 365:
        return "1y"
    if days <= 730:
        return "2y"
    return "5y"


def _parse_yahoo_chart_payload(data: dict, symbol: str) -> pd.DataFrame:
    result = data.get("chart", {}).get("result", [])
    if not result:
        raise YahooEmptyResult(symbol)

    ts = result[0].get("timestamp", [])
    indicators = result[0].get("indicators", {})
    quote = indicators.get("quote", [{}])[0]
    if not ts:
        raise YahooEmptyResult(symbol)

    records = []
    opens = quote.get("open", [])
    highs = quote.get("high", [])
    lows = quote.get("low", [])
    closes = quote.get("close", [])
    volumes = quote.get("volume", [])

    for i, t in enumerate(ts):
        c = closes[i] if i < len(closes) else None
        if c is None:
            continue
        o = opens[i] if i < len(opens) else c
        h = highs[i] if i < len(highs) else c
        low_px = lows[i] if i < len(lows) else c
        v = volumes[i] if i < len(volumes) else 0
        records.append({
            "date": datetime.fromtimestamp(t).strftime("%Y-%m-%d"),
            "open": round(float(o or c), 4),
            "high": round(float(h or c), 4),
            "low": round(float(low_px or c), 4),
            "close": round(float(c), 4),
            "volume": int(v or 0),
            "amount": 0,
            "turnover": 0,
        })

    if not records:
        raise YahooEmptyResult(symbol)

    df = pd.DataFrame(records)
    df = df.drop_duplicates(subset=["date"], keep="last")
    return df.sort_values("date").reset_index(drop=True)


def yahoo_chart(
    symbol: str,
    range_str: str = "1y",
    interval: str = "1d",
) -> pd.DataFrame:
    """從 Yahoo 獲取歷史 K 線。"""
    if not settings.yahoo_enabled:
        raise YahooDisabled()

    session = _yahoo_session()
    ds = _get_yahoo_data_source()
    if ds:
        ds.throttle()

    url = f"{YAHOO_BASE}/v8/finance/chart/{symbol}"
    params = {"range": range_str, "interval": interval}
    max_retries = int(settings.yahoo_max_retries)

    for attempt in range(1, max_retries + 1):
        t0 = time.perf_counter()
        try:
            resp = session.get(url, params=params, timeout=30)
            if resp.status_code == 404:
                logger.debug(f"Yahoo chart {symbol}: 404")
                _record_yahoo_outcome(ok=False, status_code=404)
                raise YahooEmptyResult(symbol)
            if resp.status_code == 429:
                try:
                    from src.core.pipeline_observability import record_rate_limit_429

                    record_rate_limit_429("yahoo")
                except Exception:
                    pass
                _record_yahoo_outcome(ok=False, status_code=429)
                if attempt < max_retries:
                    _sleep_on_rate_limit(resp, attempt)
                    continue
                raise YahooRateLimited(symbol)
            resp.raise_for_status()
            df = _parse_yahoo_chart_payload(resp.json(), symbol)
            _record_yahoo_outcome(ok=True)
            try:
                from src.core.pipeline_observability import record_fetch_latency

                record_fetch_latency("yahoo", (time.perf_counter() - t0) * 1000)
            except Exception:
                pass
            return df
        except (YahooEmptyResult, YahooRateLimited, YahooDisabled):
            raise
        except requests.HTTPError as e:
            sc = int(getattr(getattr(e, "response", None), "status_code", 0) or 0)
            _record_yahoo_outcome(ok=False, status_code=sc or None)
            if attempt < max_retries:
                time.sleep(settings.yahoo_request_interval * attempt)
                continue
            raise
        except Exception as e:
            _record_yahoo_outcome(ok=False)
            if attempt < max_retries:
                time.sleep(settings.yahoo_request_interval * attempt)
                continue
            logger.debug(f"Yahoo chart {symbol} 失敗: {e}")
            raise YahooEmptyResult(symbol) from e

    raise YahooRateLimited(symbol)


def yahoo_quote(symbol: str) -> dict:
    """從 Yahoo 獲取單標的報價（基於最近日 K）"""
    if not settings.yahoo_enabled:
        return {}

    session = _yahoo_session()
    ds = _get_yahoo_data_source()
    if ds:
        ds.throttle()

    url = f"{YAHOO_BASE}/v8/finance/chart/{symbol}"
    params = {"range": "5d", "interval": "1d"}
    max_retries = int(settings.yahoo_max_retries)

    for attempt in range(1, max_retries + 1):
        try:
            resp = session.get(url, params=params, timeout=15)
            if resp.status_code == 404:
                return {}
            if resp.status_code == 429:
                try:
                    from src.core.pipeline_observability import record_rate_limit_429

                    record_rate_limit_429("yahoo")
                except Exception:
                    pass
                if attempt < max_retries:
                    _sleep_on_rate_limit(resp, attempt)
                    continue
                return {}
            resp.raise_for_status()
            data = resp.json()

            result = data.get("chart", {}).get("result", [])
            if not result:
                return {}

            meta = result[0].get("meta", {})
            quote = result[0].get("indicators", {}).get("quote", [{}])[0]
            closes = [c for c in quote.get("close", []) if c is not None]
            if not closes:
                return {}

            price = closes[-1]
            prev = closes[-2] if len(closes) >= 2 else price
            change = price - prev
            change_pct = (change / prev * 100) if prev > 0 else 0

            highs = [h for h in quote.get("high", []) if h is not None]
            lows = [lv for lv in quote.get("low", []) if lv is not None]
            opens = [o for o in quote.get("open", []) if o is not None]
            volumes = [v for v in quote.get("volume", []) if v is not None]

            return {
                "symbol": symbol,
                "price": round(float(price), 4),
                "change_pct": round(float(change_pct), 2),
                "change": round(float(change), 4),
                "high": round(float(max(highs)), 4) if highs else round(float(price), 4),
                "low": round(float(min(lows)), 4) if lows else round(float(price), 4),
                "open": round(float(opens[-1]), 4) if opens else round(float(price), 4),
                "volume": int(volumes[-1]) if volumes else 0,
                "prev_close": round(float(meta.get("chartPreviousClose", prev)), 4),
                "currency": meta.get("currency", "CNY"),
                "source": "yahoo",
            }
        except Exception as e:
            if attempt < max_retries:
                time.sleep(settings.yahoo_request_interval * attempt)
            else:
                logger.debug(f"Yahoo quote {symbol} 失敗: {e}")
    return {}


def download_a_share_daily(code: str, start_date: str = None) -> pd.DataFrame:
    """下載 A 股日 K（Yahoo Finance）"""
    symbol = a_share_to_yahoo(code)
    range_str = _start_to_range(start_date)
    try:
        df = yahoo_chart(symbol, range_str=range_str, interval="1d")
    except (YahooEmptyResult, YahooRateLimited, YahooDisabled):
        return pd.DataFrame()
    if start_date:
        sd = start_date.replace("-", "")
        if len(sd) == 8:
            sd_fmt = f"{sd[:4]}-{sd[4:6]}-{sd[6:]}"
            df = df[df["date"] >= sd_fmt]
    if not df.empty:
        logger.info(f"{code} ({symbol}): {len(df)} 條記錄 (Yahoo)")
    return df


def fetch_a_share_realtime(code: str) -> dict:
    """A 股實時行情（Yahoo，映射為統一字段）"""
    symbol = a_share_to_yahoo(code)
    q = yahoo_quote(symbol)
    if not q or not q.get("price"):
        return {}
    return {
        "code": code,
        "name": q.get("name", ""),
        "price": q["price"],
        "change_pct": q.get("change_pct", 0),
        "change": q.get("change", 0),
        "volume": q.get("volume", 0),
        "amount": 0,
        "open": q.get("open", 0),
        "high": q.get("high", 0),
        "low": q.get("low", 0),
        "prev_close": q.get("prev_close", 0),
        "turnover": 0,
        "volume_ratio": 0,
        "source": "yahoo",
    }
