"""
加密貨幣數據模塊 — Binance 公開 API（無需 API Key）
支持：BTC/USDT, ETH/USDT, SOL/USDT 等主流交易對
"""
import time
from datetime import datetime

import pandas as pd
import requests

from src.utils.logger import logger

BINANCE_BASE = "https://api.binance.com"
MAX_RETRIES = 3
RETRY_DELAY = 2

_http = requests.Session()
_http.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})

# 常用交易對（顯示名）
CRYPTO_SYMBOLS = {
    "BTCUSDT": "比特幣",
    "ETHUSDT": "以太坊",
    "BNBUSDT": "幣安幣",
    "SOLUSDT": "Solana",
    "XRPUSDT": "瑞波幣",
    "ADAUSDT": "卡爾達諾",
    "DOGEUSDT": "狗狗幣",
    "DOTUSDT": "波卡",
    "AVAXUSDT": "雪崩",
    "MATICUSDT": "Polygon",
    "LINKUSDT": "Chainlink",
    "UNIUSDT": "Uniswap",
    "LTCUSDT": "萊特幣",
    "ATOMUSDT": "Cosmos",
    "NEARUSDT": "NEAR",
}


def get_crypto_symbols() -> dict:
    """返回支持的加密貨幣交易對 {symbol: 中文名}"""
    return CRYPTO_SYMBOLS.copy()


# ============================================================
# CoinGecko 符號映射（Binance → CoinGecko ID）
# ============================================================
_COINGECKO_IDS = {
    "BTCUSDT": "bitcoin", "ETHUSDT": "ethereum", "BNBUSDT": "binancecoin",
    "SOLUSDT": "solana", "XRPUSDT": "ripple", "ADAUSDT": "cardano",
    "DOGEUSDT": "dogecoin", "DOTUSDT": "polkadot", "AVAXUSDT": "avalanche-2",
    "MATICUSDT": "matic-network", "LINKUSDT": "chainlink", "UNIUSDT": "uniswap",
    "LTCUSDT": "litecoin", "ATOMUSDT": "cosmos", "NEARUSDT": "near",
    "SHIBUSDT": "shiba-inu", "TRXUSDT": "tron", "EOSUSDT": "eos",
    "XLMUSDT": "stellar", "AAVEUSDT": "aave", "FILUSDT": "filecoin",
}

# CoinCap 符號映射
_COINCAP_IDS = {
    "BTCUSDT": "bitcoin", "ETHUSDT": "ethereum", "BNBUSDT": "binancecoin",
    "SOLUSDT": "solana", "XRPUSDT": "xrp", "ADAUSDT": "cardano",
    "DOGEUSDT": "dogecoin", "DOTUSDT": "polkadot", "AVAXUSDT": "avalanche",
    "LINKUSDT": "chainlink", "LTCUSDT": "litecoin", "ATOMUSDT": "cosmos",
}


def _coingecko_quote(symbol: str) -> dict:
    """CoinGecko 實時行情（免費，無需 API Key，10-30 次/分鐘）"""
    cg_id = _COINGECKO_IDS.get(symbol.upper())
    if not cg_id:
        return {}
    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {
            "ids": cg_id,
            "vs_currencies": "usd",
            "include_24hr_change": "true",
            "include_24hr_vol": "true",
            "include_market_cap": "true",
        }
        resp = _http.get(url, params=params, timeout=10)
        data = resp.json()

        if cg_id not in data:
            return {}

        d = data[cg_id]
        price = float(d.get("usd", 0))
        change_pct = float(d.get("usd_24h_change", 0) or 0)
        volume = float(d.get("usd_24h_vol", 0) or 0)
        market_cap = float(d.get("usd_market_cap", 0) or 0)

        return {
            "symbol": symbol,
            "name": CRYPTO_SYMBOLS.get(symbol, symbol),
            "price": price,
            "change_pct": round(change_pct, 2),
            "high": 0,
            "low": 0,
            "volume": volume,
            "quote_volume": volume,
            "market_cap": market_cap,
            "market": "crypto",
            "source": "coingecko",
        }
    except Exception as e:
        logger.debug(f"CoinGecko {symbol} 失敗: {e}")
        return {}


def _coincap_quote(symbol: str) -> dict:
    """CoinCap 實時行情（免費，無需 API Key，200 次/分鐘）"""
    cap_id = _COINCAP_IDS.get(symbol.upper())
    if not cap_id:
        return {}
    try:
        url = f"https://api.coincap.io/v2/assets/{cap_id}"
        resp = _http.get(url, timeout=10)
        data = resp.json().get("data", {})

        if not data:
            return {}

        price = float(data.get("priceUsd", 0) or 0)
        change_pct = float(data.get("changePercent24Hr", 0) or 0)
        volume = float(data.get("volumeUsd24Hr", 0) or 0)
        market_cap = float(data.get("marketCapUsd", 0) or 0)

        return {
            "symbol": symbol,
            "name": data.get("name", CRYPTO_SYMBOLS.get(symbol, symbol)),
            "price": price,
            "change_pct": round(change_pct, 2),
            "high": 0,
            "low": 0,
            "volume": 0,
            "quote_volume": volume,
            "market_cap": market_cap,
            "market": "crypto",
            "source": "coincap",
        }
    except Exception as e:
        logger.debug(f"CoinCap {symbol} 失敗: {e}")
        return {}


def _twelve_crypto_quote(symbol: str) -> dict:
    """Twelve Data 加密貨幣行情（免費 800 次/天）"""
    # Twelve Data 格式：BTC/USDT
    base = symbol.replace("USDT", "").replace("BUSD", "").replace("BTC", "")
    if not base:
        base = "BTC"
    pair = f"{base}/USDT"
    try:
        url = "https://api.twelvedata.com/quote"
        params = {"symbol": pair}
        resp = _http.get(url, params=params, timeout=10)
        data = resp.json()

        if data.get("status") == "error":
            return {}

        price = float(data.get("close", 0) or 0)
        if price <= 0:
            return {}

        return {
            "symbol": symbol,
            "name": data.get("name", CRYPTO_SYMBOLS.get(symbol, symbol)),
            "price": price,
            "change_pct": round(float(data.get("percent_change", 0) or 0), 2),
            "change": round(float(data.get("change", 0) or 0), 4),
            "high": round(float(data.get("high", 0) or 0), 4),
            "low": round(float(data.get("low", 0) or 0), 4),
            "volume": int(float(data.get("volume", 0) or 0)),
            "market": "crypto",
            "source": "twelvedata",
        }
    except Exception as e:
        logger.debug(f"Twelve Data crypto {symbol} 失敗: {e}")
        return {}


def _coingecko_history(symbol: str, start_date: str = None) -> pd.DataFrame:
    """CoinGecko 歷史 K 線（免費，使用 OHLC 端點獲取真實開高低收）"""
    cg_id = _COINGECKO_IDS.get(symbol.upper())
    if not cg_id:
        return pd.DataFrame()

    days = 365
    if start_date:
        try:
            sd = datetime.strptime(start_date.replace("-", ""), "%Y%m%d")
            days = min((datetime.now() - sd).days, 365)
        except ValueError:
            pass

    # CoinGecko OHLC 端點：返回 [timestamp, open, high, low, close]
    # days=1→30min, 7→4h, 14→4h, 30→4h, 90→4d, 180→4d, 365→4d
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{cg_id}/ohlc"
        params = {"vs_currency": "usd", "days": min(days, 365)}
        resp = _http.get(url, params=params, timeout=30)
        data = resp.json()

        if not isinstance(data, list) or len(data) < 5:
            # OHLC 端點失敗，回退到 market_chart（僅 close）
            logger.debug(f"CoinGecko OHLC {symbol} 數據不足，回退 market_chart")
            return _coingecko_history_fallback(symbol, start_date)

        records = []
        for row in data:
            if len(row) < 5:
                continue
            ts, o, h, low_px, c = row[0], float(row[1]), float(row[2]), float(row[3]), float(row[4])
            dt = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")
            records.append({
                "date": dt,
                "open": o,
                "high": h,
                "low": low_px,
                "close": c,
                "volume": 0.0,
                "amount": 0.0,
            })

        if not records:
            return _coingecko_history_fallback(symbol, start_date)

        df = pd.DataFrame(records)
        df = df.drop_duplicates(subset=["date"], keep="last")
        df = df.sort_values("date").reset_index(drop=True)

        if start_date:
            sd_str = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}" if len(start_date) == 8 else start_date
            df = df[df["date"] >= sd_str]

        logger.info(f"CoinGecko OHLC {symbol}: {len(df)} 條記錄")
        return df

    except Exception as e:
        logger.debug(f"CoinGecko OHLC {symbol} 失敗: {e}")
        return _coingecko_history_fallback(symbol, start_date)


def _coingecko_history_fallback(symbol: str, start_date: str = None) -> pd.DataFrame:
    """CoinGecko market_chart 回退（僅 close，OHLC 用 close 填充）"""
    cg_id = _COINGECKO_IDS.get(symbol.upper())
    if not cg_id:
        return pd.DataFrame()

    days = 365
    if start_date:
        try:
            sd = datetime.strptime(start_date.replace("-", ""), "%Y%m%d")
            days = min((datetime.now() - sd).days, 365)
        except ValueError:
            pass

    try:
        url = f"https://api.coingecko.com/api/v3/coins/{cg_id}/market_chart"
        params = {"vs_currency": "usd", "days": days, "interval": "daily"}
        resp = _http.get(url, params=params, timeout=30)
        data = resp.json()

        prices = data.get("prices", [])
        volumes = data.get("total_volumes", [])

        if not prices:
            return pd.DataFrame()

        records = []
        for i, (ts, price) in enumerate(prices):
            vol = volumes[i][1] if i < len(volumes) else 0
            dt = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")
            records.append({
                "date": dt,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": float(vol),
                "amount": 0.0,
            })

        df = pd.DataFrame(records)
        df = df.drop_duplicates(subset=["date"], keep="last")
        df = df.sort_values("date").reset_index(drop=True)

        if start_date:
            sd_str = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}" if len(start_date) == 8 else start_date
            df = df[df["date"] >= sd_str]

        logger.info(f"CoinGecko market_chart {symbol}: {len(df)} 條記錄（僅 close）")
        return df

    except Exception as e:
        logger.debug(f"CoinGecko market_chart {symbol} 失敗: {e}")
        return pd.DataFrame()


def download_crypto_kline(
    symbol: str = "BTCUSDT",
    interval: str = "1d",
    start_date: str = None,
    limit: int = 1000,
) -> pd.DataFrame:
    """
    從 Binance 下載加密貨幣 K 線數據。

    參數：
        symbol: 交易對（如 BTCUSDT）
        interval: K 線週期（1m, 5m, 15m, 1h, 4h, 1d, 1w）
        start_date: 起始日期 YYYY-MM-DD 或 YYYYMMDD
        limit: 每次請求最大數量（最大 1000）

    返回：
        DataFrame: date, open, high, low, close, volume, amount
    """
    symbol = symbol.upper().replace("-", "").replace("/", "")

    if start_date:
        start_date = start_date.replace("-", "")
        start_dt = datetime.strptime(start_date, "%Y%m%d")
    else:
        start_dt = datetime(2020, 1, 1)

    all_data = []
    current_start = int(start_dt.timestamp() * 1000)
    end_ts = int(datetime.now().timestamp() * 1000)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            while current_start < end_ts:
                params = {
                    "symbol": symbol,
                    "interval": interval,
                    "startTime": current_start,
                    "limit": limit,
                }
                resp = requests.get(
                    f"{BINANCE_BASE}/api/v3/klines",
                    params=params,
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()

                if not data:
                    break

                for k in data:
                    all_data.append({
                        "date": datetime.fromtimestamp(k[0] / 1000).strftime("%Y-%m-%d"),
                        "open": float(k[1]),
                        "high": float(k[2]),
                        "low": float(k[3]),
                        "close": float(k[4]),
                        "volume": float(k[5]),
                        "amount": float(k[7]),  # quote asset volume
                    })

                # 移動到下一批
                last_close_time = data[-1][6]
                current_start = last_close_time + 1

                if len(data) < limit:
                    break

                time.sleep(0.2)  # 避免限流

            break  # 成功則跳出重試循環

        except Exception as e:
            if attempt < MAX_RETRIES:
                logger.warning(f"加密貨幣 {symbol} 下載失敗(第{attempt}次)，重試... ({e})")
                time.sleep(RETRY_DELAY * attempt)
            else:
                logger.error(f"加密貨幣 {symbol} 下載失敗: {e}")
                return pd.DataFrame()

    if not all_data:
        # Binance 失敗，嘗試 CoinGecko 備選
        logger.warning(f"Binance {symbol} 無數據，嘗試 CoinGecko...")
        df = _coingecko_history(symbol, start_date)
        if not df.empty:
            return df

        logger.error(f"加密貨幣 {symbol}: 所有數據源均失敗")
        return pd.DataFrame()

    df = pd.DataFrame(all_data)
    # 去重（按日期）
    df = df.drop_duplicates(subset=["date"], keep="last")
    df = df.sort_values("date").reset_index(drop=True)

    logger.info(f"加密貨幣 {symbol}: {len(df)} 條記錄")
    return df


def get_crypto_realtime(symbol: str = "BTCUSDT") -> dict:
    """
    獲取加密貨幣實時行情。

    返回：
        {symbol, price, change_pct, high, low, volume, quote_volume}
    """
    symbol = symbol.upper().replace("-", "").replace("/", "")

    # 源 1：Binance
    try:
        resp = requests.get(
            f"{BINANCE_BASE}/api/v3/ticker/24hr",
            params={"symbol": symbol},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "symbol": symbol,
            "name": CRYPTO_SYMBOLS.get(symbol, symbol),
            "price": float(data["lastPrice"]),
            "change_pct": float(data["priceChangePercent"]),
            "high": float(data["highPrice"]),
            "low": float(data["lowPrice"]),
            "volume": float(data["volume"]),
            "quote_volume": float(data["quoteVolume"]),
            "open": float(data["openPrice"]),
            "prev_close": float(data["prevClosePrice"]),
            "market": "crypto",
            "source": "binance",
        }
    except Exception as e:
        logger.debug(f"Binance {symbol} 失敗: {e}")

    # 源 2：CoinGecko
    result = _coingecko_quote(symbol)
    if result and result.get("price", 0) > 0:
        return result

    # 源 3：CoinCap
    result = _coincap_quote(symbol)
    if result and result.get("price", 0) > 0:
        return result

    # 源 4：Twelve Data
    result = _twelve_crypto_quote(symbol)
    if result and result.get("price", 0) > 0:
        return result

    logger.error(f"加密貨幣實時行情失敗 {symbol}: 所有源均失敗")
    return {}


def get_crypto_multi_realtime(symbols: list[str] = None) -> list[dict]:
    """批量獲取加密貨幣實時行情"""
    if symbols is None:
        symbols = list(CRYPTO_SYMBOLS.keys())[:5]

    results = []
    try:
        resp = requests.get(
            f"{BINANCE_BASE}/api/v3/ticker/24hr",
            timeout=15,
        )
        resp.raise_for_status()
        all_tickers = {t["symbol"]: t for t in resp.json()}

        for sym in symbols:
            sym = sym.upper().replace("-", "").replace("/", "")
            if sym in all_tickers:
                t = all_tickers[sym]
                results.append({
                    "symbol": sym,
                    "name": CRYPTO_SYMBOLS.get(sym, sym),
                    "price": float(t["lastPrice"]),
                    "change_pct": float(t["priceChangePercent"]),
                    "high": float(t["highPrice"]),
                    "low": float(t["lowPrice"]),
                    "volume": float(t["volume"]),
                    "market": "crypto",
                })
    except Exception as e:
        logger.error(f"加密貨幣批量行情失敗: {e}")

    return results
