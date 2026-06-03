"""
Yahoo Finance 數據接口（免費，無需 API Key）

A 股代碼映射：600519 → 600519.SS，000001 → 000001.SZ
滬深300：000300.SS
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Optional

import pandas as pd
import requests

from src.utils.logger import logger

YAHOO_BASE = "https://query1.finance.yahoo.com"
MAX_RETRIES = 3
RETRY_DELAY = 2

_yahoo_session = requests.Session()
_yahoo_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
})


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


def yahoo_chart(
    symbol: str,
    range_str: str = "1y",
    interval: str = "1d",
) -> pd.DataFrame:
    """從 Yahoo 獲取歷史 K 線"""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            url = f"{YAHOO_BASE}/v8/finance/chart/{symbol}"
            params = {"range": range_str, "interval": interval}
            resp = _yahoo_session.get(url, params=params, timeout=30)
            if resp.status_code == 404:
                logger.debug(f"Yahoo chart {symbol}: 404")
                return pd.DataFrame()
            if resp.status_code == 429:
                time.sleep(RETRY_DELAY * attempt)
                continue
            resp.raise_for_status()
            data = resp.json()

            result = data.get("chart", {}).get("result", [])
            if not result:
                return pd.DataFrame()

            ts = result[0].get("timestamp", [])
            indicators = result[0].get("indicators", {})
            quote = indicators.get("quote", [{}])[0]
            if not ts:
                return pd.DataFrame()

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
                return pd.DataFrame()

            df = pd.DataFrame(records)
            df = df.drop_duplicates(subset=["date"], keep="last")
            return df.sort_values("date").reset_index(drop=True)

        except Exception as e:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
            else:
                logger.debug(f"Yahoo chart {symbol} 失敗: {e}")
    return pd.DataFrame()


def yahoo_quote(symbol: str) -> dict:
    """從 Yahoo 獲取單標的報價（基於最近日 K）"""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            url = f"{YAHOO_BASE}/v8/finance/chart/{symbol}"
            params = {"range": "5d", "interval": "1d"}
            resp = _yahoo_session.get(url, params=params, timeout=15)
            if resp.status_code in (404, 429):
                if resp.status_code == 429:
                    time.sleep(RETRY_DELAY * attempt)
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
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
            else:
                logger.debug(f"Yahoo quote {symbol} 失敗: {e}")
    return {}


def download_a_share_daily(code: str, start_date: str = None) -> pd.DataFrame:
    """下載 A 股日 K（Yahoo Finance）"""
    symbol = a_share_to_yahoo(code)
    range_str = _start_to_range(start_date)
    df = yahoo_chart(symbol, range_str=range_str, interval="1d")
    if df.empty:
        return df
    if start_date:
        sd = start_date.replace("-", "")
        if len(sd) == 8:
            sd_fmt = f"{sd[:4]}-{sd[4:6]}-{sd[6:]}"
            df = df[df["date"] >= sd_fmt]
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
