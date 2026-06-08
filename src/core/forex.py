"""
外匯數據模塊 — 使用 frankfurter.app（免費，無需 API Key）
支持：USD/CNY, EUR/USD, GBP/USD 等主要貨幣對
"""

import time
from datetime import datetime

import pandas as pd
import requests

from src.utils.logger import logger

FRANKFURTER_BASE = "https://api.frankfurter.dev"
MAX_RETRIES = 3
RETRY_DELAY = 2

# 常用貨幣對（顯示名）
FOREX_PAIRS = {
    "USDCNY": "美元/人民幣",
    "EURUSD": "歐元/美元",
    "GBPUSD": "英鎊/美元",
    "USDJPY": "美元/日元",
    "USDCHF": "美元/瑞郎",
    "AUDUSD": "澳元/美元",
    "USDCAD": "美元/加元",
    "EURCNY": "歐元/人民幣",
    "GBPCNY": "英鎊/人民幣",
    "JPYCNY": "日元/人民幣",
    "HKDCNY": "港幣/人民幣",
    "EURGBP": "歐元/英鎊",
    "EURJPY": "歐元/日元",
    "GBPJPY": "英鎊/日元",
    "AUDJPY": "澳元/日元",
}

# 支持的基礎貨幣（frankfurter 支持的）
_BASE_CURRENCIES = {
    "USD",
    "EUR",
    "GBP",
    "JPY",
    "CHF",
    "AUD",
    "CAD",
    "CNY",
    "HKD",
    "SGD",
    "NZD",
    "SEK",
    "NOK",
    "DKK",
    "ZAR",
    "INR",
    "BRL",
    "KRW",
}


def _split_pair(pair: str) -> tuple[str, str]:
    """將 USDCNY 拆分為 (USD, CNY)"""
    pair = pair.upper().replace("/", "").replace("-", "")
    # 嘗試 3+3 拆分
    for i in range(3, len(pair) - 2):
        base = pair[:i]
        quote = pair[i:]
        if base in _BASE_CURRENCIES and quote in _BASE_CURRENCIES:
            return base, quote
    # 默認前3後3
    return pair[:3], pair[3:]


def get_forex_pairs() -> dict:
    """返回支持的外匯貨幣對 {pair: 中文名}"""
    return FOREX_PAIRS.copy()


def download_forex_kline(
    pair: str = "USDCNY",
    start_date: str = None,
    end_date: str = None,
) -> pd.DataFrame:
    """
    從 frankfurter.dev 下載外匯歷史數據。

    參數：
        pair: 貨幣對（如 USDCNY, EUR/USD）
        start_date: 起始日期 YYYY-MM-DD 或 YYYYMMDD
        end_date: 結束日期

    返回：
        DataFrame: date, open, high, low, close, volume(=0), amount(=0)
    """
    base, quote = _split_pair(pair)

    if start_date:
        start_date = start_date.replace("-", "")
        if len(start_date) == 8:
            start_dt = datetime.strptime(start_date, "%Y%m%d")
        else:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    else:
        start_dt = datetime(2020, 1, 1)

    if end_date:
        end_date = end_date.replace("-", "")
        if len(end_date) == 8:
            end_dt = datetime.strptime(end_date, "%Y%m%d")
        else:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        end_dt = datetime.now()

    start_str = start_dt.strftime("%Y-%m-%d")
    end_str = end_dt.strftime("%Y-%m-%d")

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            # frankfurter.dev: GET /v1/{start}..{end}?from={base}&to={quote}
            url = f"{FRANKFURTER_BASE}/v1/{start_str}..{end_str}"
            params = {"base": base, "symbols": quote}
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            rates = data.get("rates", {})
            if not rates:
                logger.warning(f"外匯 {pair}: 無數據")
                return pd.DataFrame()

            records = []
            for date_str, rate_dict in sorted(rates.items()):
                rate = rate_dict.get(quote, 0)
                if rate <= 0:
                    continue
                # frankfurter 只給收盤價，我們用它構造 OHLCV
                records.append(
                    {
                        "date": date_str,
                        "open": rate,
                        "high": rate,
                        "low": rate,
                        "close": rate,
                        "volume": 0,
                        "amount": 0,
                    }
                )

            if not records:
                return pd.DataFrame()

            df = pd.DataFrame(records)
            # 嘗試填充更真實的 OHLC（用相鄰數據估算波動）
            df = _estimate_forex_ohlc(df)

            logger.info(f"外匯 {pair} ({base}/{quote}): {len(df)} 條記錄")
            return df

        except Exception as e:
            if attempt < MAX_RETRIES:
                logger.warning(f"外匯 {pair} 下載失敗(第{attempt}次)，重試... ({e})")
                time.sleep(RETRY_DELAY * attempt)
            else:
                logger.error(f"外匯 {pair} 下載失敗: {e}")
                return pd.DataFrame()

    return pd.DataFrame()


def _estimate_forex_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    """
    外匯只有收盤價，用日內波動率估算 OHLC。
    使用前後日的收盤價差估算日內高低點。
    """
    if len(df) < 2:
        return df

    closes = df["close"].values
    # 用前後日收盤價的平均絕對偏差估算日內幅度
    daily_range = (
        pd.Series(closes).diff().abs().rolling(5, min_periods=1).mean().fillna(0.001)
    )

    for i in range(len(df)):
        c = closes[i]
        r = daily_range.iloc[i] if i < len(daily_range) else 0.001
        if r <= 0:
            r = abs(c * 0.001)  # 默認 0.1% 波動

        # 估算 open：前一天收盤
        o = closes[i - 1] if i > 0 else c
        # 估算 high/low
        h = max(o, c) + r * 0.5
        low_px = min(o, c) - r * 0.5

        df.at[i, "open"] = round(o, 6)
        df.at[i, "high"] = round(h, 6)
        df.at[i, "low"] = round(low_px, 6)
        df.at[i, "close"] = round(c, 6)

    return df


def _sina_forex_quote(pair: str) -> dict:
    """新浪外匯行情（備選源）"""
    base, quote = _split_pair(pair)
    sina_pair = f"fx_s{base.lower()}{quote.lower()}"
    try:
        url = f"https://hq.sinajs.cn/list={sina_pair}"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://finance.sina.com.cn",
        }
        resp = requests.get(url, headers=headers, timeout=8)
        resp.encoding = "gbk"
        text = resp.text.strip()
        if "=" not in text or '""' in text:
            return {}
        data_str = text.split('="')[1].rstrip('";')
        parts = data_str.split(",")
        if len(parts) < 7:
            return {}
        price = float(parts[1] or 0)
        prev_close = float(parts[3] or 0)
        change_pct = float(parts[2] or 0)
        return {
            "symbol": pair.upper(),
            "name": FOREX_PAIRS.get(pair.upper(), f"{base}/{quote}"),
            "price": round(price, 6),
            "change_pct": round(change_pct, 2),
            "change": round(price - prev_close, 6) if prev_close else 0,
            "base": base,
            "quote": quote,
            "date": "",
            "market": "forex",
            "source": "sina",
        }
    except Exception as e:
        logger.debug(f"新浪外匯 {pair} 失敗: {e}")
        return {}


def _eastmoney_forex_quote(pair: str) -> dict:
    """東方財富外匯行情（備選源）"""
    # 東財外匯 secid: 119.USDCNY, 119.EURUSD 等
    base, quote = _split_pair(pair)
    secid = f"119.{base}{quote}"
    try:
        url = "https://push2.eastmoney.com/api/qt/stock/get"
        params = {
            "secid": secid,
            "fields": "f43,f44,f45,f46,f58,f60,f169,f170",
            "ut": "fa5fd1943c7b386f172d6893dbbd1",
        }
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, params=params, headers=headers, timeout=8)
        data = resp.json().get("data", {})
        if not data:
            return {}
        price = data.get("f43", 0)
        prev_close = data.get("f60", 0)
        # 外匯價格需要 /10000
        price_f = price / 10000 if price else 0
        prev_f = prev_close / 10000 if prev_close else 0
        change_pct = data.get("f170", 0)
        return {
            "symbol": pair.upper(),
            "name": data.get("f58", FOREX_PAIRS.get(pair.upper(), f"{base}/{quote}")),
            "price": round(price_f, 6),
            "change_pct": round(change_pct / 100, 2) if change_pct else 0,
            "change": round(price_f - prev_f, 6) if prev_f else 0,
            "base": base,
            "quote": quote,
            "date": "",
            "market": "forex",
            "source": "eastmoney",
        }
    except Exception as e:
        logger.debug(f"東財外匯 {pair} 失敗: {e}")
        return {}


def get_forex_realtime(pair: str = "USDCNY") -> dict:
    """
    獲取外匯實時匯率（多源自動降級）。

    優先級：Frankfurter → 新浪 → 東財

    返回：
        {pair, rate, change_pct, base, quote}
    """
    base, quote = _split_pair(pair)

    # 源 1：Frankfurter（準確但無漲跌幅）
    try:
        url = f"{FRANKFURTER_BASE}/v1/latest"
        params = {"base": base, "symbols": quote}
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        rate = data.get("rates", {}).get(quote, 0)
        if rate > 0:
            return {
                "symbol": pair.upper(),
                "name": FOREX_PAIRS.get(pair.upper(), f"{base}/{quote}"),
                "price": rate,
                "change_pct": 0,
                "base": base,
                "quote": quote,
                "date": data.get("date", ""),
                "market": "forex",
                "source": "frankfurter",
            }
    except Exception as e:
        logger.debug(f"Frankfurter 外匯 {pair} 失敗: {e}")

    # 源 2：新浪
    result = _sina_forex_quote(pair)
    if result and result.get("price", 0) > 0:
        return result

    # 源 3：東財
    result = _eastmoney_forex_quote(pair)
    if result and result.get("price", 0) > 0:
        return result

    logger.error(f"外匯實時行情失敗 {pair}: 所有源均失敗")
    return {}


def get_forex_multi_realtime(pairs: list[str] = None) -> list[dict]:
    """批量獲取外匯實時匯率"""
    if pairs is None:
        pairs = ["USDCNY", "EURUSD", "GBPUSD", "USDJPY"]

    results = []
    for pair in pairs:
        r = get_forex_realtime(pair)
        if r:
            results.append(r)
        time.sleep(0.1)
    return results


# ============================================================
# 貴金屬 & 商品（使用 frankfurter 的 ECB 匯率 + 黃金 API）
# ============================================================

COMMODITY_SYMBOLS = {
    "XAUUSD": "現貨黃金",
    "XAGUSD": "現貨白銀",
    "CL": "WTI 原油",
    "BRENT": "布倫特原油",
}


def get_commodity_symbols() -> dict:
    return COMMODITY_SYMBOLS.copy()
