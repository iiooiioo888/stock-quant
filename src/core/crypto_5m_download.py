"""
加密貨幣 5 分鐘 K 線數據下載 — 直接調用 Binance API
"""
import time
import requests
import pandas as pd
from datetime import datetime, timedelta

from src.utils.logger import logger

CRYPTO_SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]
BINANCE_BASE = "https://api.binance.com"
MAX_RETRIES = 3
RETRY_DELAY = 2


def download_crypto_5m(symbol: str, days: int = 7) -> pd.DataFrame:
    """
    從 Binance 下載 5 分鐘 K 線數據。
    
    Args:
        symbol: 交易對（如 BTCUSDT）
        days: 下載最近幾天的數據
    
    Returns:
        DataFrame: datetime, open, high, low, close, volume, amount
    """
    symbol = symbol.upper().replace("-", "").replace("/", "")
    start_dt = datetime.now() - timedelta(days=days)
    
    all_data = []
    current_start = int(start_dt.timestamp() * 1000)
    end_ts = int(datetime.now().timestamp() * 1000)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            while current_start < end_ts:
                params = {
                    "symbol": symbol,
                    "interval": "5m",
                    "startTime": current_start,
                    "limit": 1000,
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
                        "datetime": datetime.fromtimestamp(k[0] / 1000).strftime("%Y-%m-%d %H:%M:%S"),
                        "open": float(k[1]),
                        "high": float(k[2]),
                        "low": float(k[3]),
                        "close": float(k[4]),
                        "volume": float(k[5]),
                        "amount": float(k[7]),  # quote asset volume
                    })

                last_close_time = data[-1][6]
                current_start = last_close_time + 1

                if len(data) < 1000:
                    break
                time.sleep(0.2)

            break
        except Exception as e:
            if attempt < MAX_RETRIES:
                logger.warning(f"{symbol} 5m 下載失敗(第{attempt}次)，重試... ({e})")
                time.sleep(RETRY_DELAY * attempt)
            else:
                logger.error(f"{symbol} 5m 下載失敗: {e}")
                return pd.DataFrame()

    if not all_data:
        return pd.DataFrame()
    
    df = pd.DataFrame(all_data)
    df = df.sort_values("datetime").reset_index(drop=True)
    return df


def download_crypto_5m_all(symbols: list[str] = None, days: int = 7) -> dict:
    """
    下載所有加密貨幣的 5 分鐘 K 線數據。
    
    Args:
        symbols: 交易對列表，默認 5 大幣種
        days: 下載最近幾天的數據
    
    Returns:
        {"total": int, "updated": int, "failed": int, "details": [...]}
    """
    from src.core.db import save_minute_kline

    symbols = symbols or CRYPTO_SYMBOLS
    
    total = 0
    updated = 0
    failed = 0
    details = []

    for sym in symbols:
        try:
            logger.info(f"下載 {sym} 5 分鐘 K 線...")
            df = download_crypto_5m(symbol=sym, days=days)
            if df.empty:
                logger.warning(f"{sym}: 無數據")
                details.append({"symbol": sym, "status": "no_data"})
                failed += 1
                continue

            count = save_minute_kline(df, sym, "5m")
            total += count
            updated += 1
            details.append({"symbol": sym, "status": "ok", "records": count})
            logger.info(f"{sym}: {count} 條 5 分鐘 K 線")
            
            time.sleep(1)
            
        except Exception as e:
            logger.error(f"{sym} 5 分鐘 K 線下載失敗: {e}")
            details.append({"symbol": sym, "status": "error", "error": str(e)})
            failed += 1

    result = {
        "total": total,
        "updated": updated,
        "failed": failed,
        "details": details,
    }
    logger.info(f"加密貨幣 5 分鐘 K 線下載完成: {updated} 只成功, {total} 條記錄")
    return result


if __name__ == "__main__":
    from src.core.database.bootstrap import init_database
    init_database()
    result = download_crypto_5m_all()
    print(f"結果: {result}")
