"""
歷史數據下載模塊（支持增量更新，多市場：A股/加密貨幣/外匯）
"""
import akshare as ak
import pandas as pd
import requests
import time
import random
from datetime import datetime, timedelta
from src.core.db import save_daily_kline, init_db, get_latest_date, clear_data_cache, get_market_for_code
from src.config import settings
from src.utils.logger import logger

MAX_RETRIES = 3
RETRY_DELAY = 5  # 基礎重試間隔（秒），配合指數退避

_REQ_SESSION = requests.Session()
_REQ_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
})


def _patch_akshare_session():
    """修復 akshare 的 requests Session，避免東方財富 API 斷開連接"""
    try:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        })
        # 替換 akshare 內部的 requests 模塊 session
        import akshare.core.stock_zh_a_hist as _mod
        if hasattr(_mod, 'requests'):
            _mod.requests = session
        # 也嘗試 patch 全局 requests
        import requests as _req
        _req.Session = lambda: session
    except Exception:
        pass  # patch 失敗不影響正常功能

# 啟動時 patch 一次
_patch_akshare_session()


def detect_market(code: str) -> str:
    """根據代碼格式自動判斷市場類型"""
    code = code.upper().strip()
    # 加密貨幣：以 USDT/BTC/ETH 結尾
    if code.endswith("USDT") or code.endswith("BTC") or code.endswith("ETH") or code.endswith("BNB"):
        return "crypto"
    # 外匯：6 字符，前 3 後 3 都是貨幣代碼
    if len(code) == 6 and code[:3] in ("USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "CNY", "HKD", "SGD", "NZD", "SEK", "NOK"):
        return "forex"
    # Yahoo 全球標的
    if code.endswith(".HK") or code.endswith(".SS") or code.endswith(".SZ"):
        return "global"
    if code.startswith("^"):
        return "global"
    if code.endswith("=F") or code.endswith("=X"):
        return "global"
    # A 股：6 位數字
    if code.isdigit() and len(code) == 6:
        return "a_share"
    # 美股/ETF：字母代碼
    if code.isalpha() or ("-" in code and not code[0].isdigit()):
        return "global"
    # 默認 A 股
    return "a_share"


def download_one(code: str, start_date: str = None, market: str = None) -> int:
    """
    下載單個標的歷史日K（自動判斷市場）。

    參數：
        code: 標的代碼（如 600519, BTCUSDT, USDCNY）
        start_date: 起始日期
        market: 市場類型（自動判斷）
    """
    if start_date is None:
        start_date = settings.history_start_date

    if market is None:
        market = detect_market(code)

    if market == "crypto":
        return _download_crypto(code, start_date)
    elif market == "forex":
        return _download_forex(code, start_date)
    elif market == "global":
        return _download_global(code, start_date)
    else:
        return _download_a_share(code, start_date)


def _download_crypto(code: str, start_date: str = None) -> int:
    """下載加密貨幣歷史數據"""
    from src.core.crypto import download_crypto_kline
    try:
        df = download_crypto_kline(symbol=code, start_date=start_date)
        if df.empty:
            return 0
        count = save_daily_kline(df, code, market="crypto")
        logger.info(f"加密貨幣 {code}: {count} 條記錄")
        return count
    except Exception as e:
        logger.error(f"加密貨幣 {code} 下載失敗: {e}")
        return 0


def _download_forex(code: str, start_date: str = None) -> int:
    """下載外匯歷史數據"""
    from src.core.forex import download_forex_kline
    try:
        df = download_forex_kline(pair=code, start_date=start_date)
        if df.empty:
            return 0
        count = save_daily_kline(df, code, market="forex")
        logger.info(f"外匯 {code}: {count} 條記錄")
        return count
    except Exception as e:
        logger.error(f"外匯 {code} 下載失敗: {e}")
        return 0


def _download_global(code: str, start_date: str = None) -> int:
    """下載全球標的歷史數據（Yahoo Finance）"""
    from src.core.global_market import download_global_symbol
    try:
        df = download_global_symbol(symbol=code, start_date=start_date)
        if df.empty:
            return 0
        market = "global"
        # 細分市場
        if code.endswith(".HK"):
            market = "hk_stock"
        elif code.endswith("=F"):
            market = "commodity"
        elif code.endswith("=X"):
            market = "forex_yahoo"
        elif code.startswith("^"):
            market = "index"
        elif code.isalpha():
            market = "us_stock"
        count = save_daily_kline(df, code, market=market)
        logger.info(f"全球標的 {code}: {count} 條記錄 (market={market})")
        return count
    except Exception as e:
        logger.error(f"全球標的 {code} 下載失敗: {e}")
        return 0


def _download_a_share(code: str, start_date: str = None) -> int:
    """下載 A 股歷史數據（Yahoo 主源 + AKShare/HTTP 備選）"""
    if start_date is None:
        start_date = settings.history_start_date

    if code.startswith("6"):
        symbol = f"sh{code}"
    else:
        symbol = f"sz{code}"

    # 主接口：Yahoo Finance
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            from src.core.yahoo_finance import download_a_share_daily
            df = download_a_share_daily(code, start_date=start_date)
            if not df.empty:
                count = save_daily_kline(df, code)
                logger.info(f"{code}: {count} 條記錄 (Yahoo)")
                return count
            logger.warning(f"{code}: Yahoo 無數據")
            break
        except Exception as e:
            if attempt < MAX_RETRIES:
                delay = RETRY_DELAY * (2 ** (attempt - 1)) + random.uniform(0.5, 2.0)
                logger.warning(f"{code}: Yahoo 失敗(第{attempt}次)，{delay:.1f}秒後重試... ({e})")
                time.sleep(delay)
            else:
                logger.warning(f"{code}: Yahoo 全部失敗，嘗試 AKShare 備選... ({e})")
                time.sleep(random.uniform(1.0, 2.0))

    # 備選：東方財富 (ak.stock_zh_a_hist)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            # 每次重試前重新 patch session
            _patch_akshare_session()
            df = ak.stock_zh_a_hist(
                symbol=code, period="daily",
                start_date=start_date, adjust="qfq",
            )
            if df.empty:
                logger.warning(f"{code}: 無數據")
                return 0

            col_map = {
                "日期": "date", "开盘": "open", "最高": "high",
                "最低": "low", "收盘": "close", "成交量": "volume",
                "成交额": "amount", "换手率": "turnover",
            }
            df = df.rename(columns=col_map)
            count = save_daily_kline(df, code)
            logger.info(f"{code}: {count} 條記錄 (東財 AKShare)")
            return count

        except Exception as e:
            if attempt < MAX_RETRIES:
                delay = RETRY_DELAY * (2 ** (attempt - 1)) + random.uniform(0.5, 2.0)
                logger.warning(f"{code}: 東財失敗(第{attempt}次)，{delay:.1f}秒後重試... ({e})")
                time.sleep(delay)
            else:
                logger.warning(f"{code}: 東財全部失敗，嘗試其他備選...")
                time.sleep(random.uniform(3.0, 6.0))

    # 備選接口 1：新浪 (ak.stock_zh_a_daily)
    try:
        logger.info(f"{code}: 嘗試新浪備選接口...")
        _patch_akshare_session()
        df = ak.stock_zh_a_daily(symbol=symbol, adjust="qfq")
        if df.empty:
            logger.warning(f"{code}: 新浪備選接口無數據")
        else:
            col_map = {"date": "date", "open": "open", "high": "high",
                        "low": "low", "close": "close", "volume": "volume",
                        "amount": "amount", "turnover": "turnover"}
            df = df.rename(columns=col_map)

            if start_date:
                df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
                df = df[df["date"] >= f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}"]

            count = save_daily_kline(df, code)
            logger.info(f"{code}: {count} 條記錄 (新浪備選)")
            return count

    except Exception as e:
        logger.warning(f"{code}: 新浪備選失敗: {e}")

    time.sleep(random.uniform(1.0, 2.0))  # 備選源間冷卻

    # 備選接口 2：網易 (ak.stock_zh_a_hist_163)
    try:
        logger.info(f"{code}: 嘗試網易備選接口...")
        _patch_akshare_session()
        df = ak.stock_zh_a_hist_163(
            symbol=code, start_date=start_date, adjust="qfq"
        )
        if not df.empty:
            col_map = {
                "日期": "date", "开盘": "open", "最高": "high",
                "最低": "low", "收盘": "close", "成交量": "volume",
                "成交额": "amount",
            }
            df = df.rename(columns=col_map)
            count = save_daily_kline(df, code)
            logger.info(f"{code}: {count} 條記錄 (網易備選)")
            return count

    except Exception as e:
        logger.warning(f"{code}: 網易備選失敗: {e}")

    time.sleep(random.uniform(1.0, 2.0))  # 備選源間冷卻

    # 備選接口 3：騰訊 (ak.stock_zh_a_hist_tx)
    try:
        logger.info(f"{code}: 嘗試騰訊備選接口...")
        _patch_akshare_session()
        df = ak.stock_zh_a_hist_tx(
            symbol=symbol, start_date=start_date, adjust="qfq"
        )
        if not df.empty:
            col_map = {
                "date": "date", "open": "open", "high": "high",
                "low": "low", "close": "close", "volume": "volume",
                "amount": "amount",
            }
            df = df.rename(columns=col_map)
            count = save_daily_kline(df, code)
            logger.info(f"{code}: {count} 條記錄 (騰訊備選)")
            return count

    except Exception as e:
        logger.warning(f"{code}: 騰訊備選失敗: {e}")

    time.sleep(random.uniform(1.0, 2.0))  # 備選源間冷卻

    # 備選接口 4：直接 HTTP 請求（不依賴 akshare）
    try:
        logger.info(f"{code}: 嘗試直接 HTTP 接口...")
        df = _download_a_share_http(code, start_date)
        if df is not None and not df.empty:
            count = save_daily_kline(df, code)
            logger.info(f"{code}: {count} 條記錄 (HTTP 直連)")
            return count
    except Exception as e:
        logger.warning(f"{code}: HTTP 直連失敗: {e}")

    logger.error(f"{code}: 所有數據源均失敗")
    return 0


def _download_a_share_http(code: str, start_date: str = None) -> "pd.DataFrame | None":
    """
    直接 HTTP 請求東方財富歷史 K 線 API（不依賴 akshare）。
    作為最後備選方案。
    """
    import json as _json

    if start_date is None:
        start_date = settings.history_start_date

    # 東方財富歷史 K 線 API
    # secid: 0=深圳, 1=上海
    if code.startswith("6"):
        secid = f"1.{code}"
    else:
        secid = f"0.{code}"

    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": secid,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101",        # 日 K
        "fqt": "1",          # 前復權
        "beg": start_date,
        "end": "20500101",
        "lmt": "5000",
    }

    try:
        resp = _REQ_SESSION.get(url, params=params, timeout=15)
        data = resp.json()

        klines = data.get("data", {}).get("klines", [])
        if not klines:
            return None

        rows = []
        for line in klines:
            parts = line.split(",")
            if len(parts) >= 7:
                rows.append({
                    "date": parts[0],
                    "open": float(parts[1]),
                    "close": float(parts[2]),
                    "high": float(parts[3]),
                    "low": float(parts[4]),
                    "volume": float(parts[5]),
                    "amount": float(parts[6]),
                    "turnover": float(parts[10]) if len(parts) > 10 else 0,
                })

        df = pd.DataFrame(rows)
        return df

    except Exception as e:
        logger.debug(f"HTTP 直連 {code} 失敗: {e}")
        return None


def download_all(codes: list[str] = None, start_date: str = None) -> int:
    """批量下載歷史數據"""
    if codes is None:
        codes = settings.watchlist
    if start_date is None:
        start_date = settings.history_start_date

    init_db()
    total = 0
    logger.info(f"開始下載 {len(codes)} 只股票，起始日期 {start_date}")

    for i, code in enumerate(codes, 1):
        logger.info(f"[{i}/{len(codes)}] {code}")
        count = download_one(code, start_date)
        total += count

        if i < len(codes):
            time.sleep(1)

    # 清除緩存（新數據已到）
    if total > 0:
        clear_data_cache()

    logger.info(f"下載完成，共 {total} 條記錄")
    return total


def download_incremental(codes: list[str] = None, force: bool = False) -> dict:
    """
    增量下載歷史數據。
    檢查每只股票的最新日期，只下載之後的數據。
    
    Args:
        codes: 股票代碼列表，為 None 時使用 watchlist
        force: 強制重新下載全部數據
    
    Returns:
        {"updated": int, "skipped": int, "total_records": int, "details": [...]}
    """
    if codes is None:
        codes = settings.watchlist

    init_db()
    updated = 0
    skipped = 0
    total_records = 0
    details = []

    for i, code in enumerate(codes, 1):
        if force:
            start_date = settings.history_start_date
        else:
            latest = get_latest_date(code)
            if latest:
                # 從最新日期的下一天開始
                try:
                    dt = datetime.strptime(str(latest), "%Y-%m-%d") + timedelta(days=1)
                    start_date = dt.strftime("%Y%m%d")
                    # 如果最新數據距今不到 1 天，跳過
                    if dt.date() >= datetime.now().date():
                        skipped += 1
                        details.append({"code": code, "status": "skipped", "reason": "已是最新"})
                        continue
                except ValueError:
                    start_date = settings.history_start_date
            else:
                start_date = settings.history_start_date

        logger.info(f"[增量 {i}/{len(codes)}] {code} 從 {start_date} 開始")
        count = download_one(code, start_date)
        if count > 0:
            updated += 1
            total_records += count
            details.append({"code": code, "status": "updated", "records": count})
        else:
            details.append({"code": code, "status": "no_new_data"})

        if i < len(codes):
            time.sleep(1)

    # 清除緩存（新數據已到）
    if updated > 0:
        clear_data_cache()

    result = {
        "updated": updated,
        "skipped": skipped,
        "total_records": total_records,
        "details": details,
    }

    logger.info(f"增量更新完成: {updated} 只更新, {skipped} 只跳過, {total_records} 條新數據")
    return result


# ============================================================
# 分鐘 K 線下載
# ============================================================

# 支持的分鐘週期映射
MINUTE_PERIODS = {
    "1m": "1",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "60m": "60",
}


def download_minute_data(code: str, period: str = "5m", adjust: str = "qfq") -> int:
    """
    下載單只股票的分鐘 K 線數據
    
    Args:
        code: 股票代碼
        period: 週期 '1m','5m','15m','30m','60m'
        adjust: 復權方式 'qfq'=前復權, 'hfq'=後復權, ''=不復權
    
    Returns:
        保存的記錄數
    """
    if period not in MINUTE_PERIODS:
        logger.error(f"不支持的週期: {period}，可選: {list(MINUTE_PERIODS.keys())}")
        return 0
    
    ak_period = MINUTE_PERIODS[period]
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            df = ak.stock_zh_a_hist_min_em(
                symbol=code,
                period=ak_period,
                adjust=adjust,
            )
            
            if df.empty:
                logger.warning(f"{code} {period}: 無分鐘K線數據")
                return 0
            
            # 統一列名
            col_map = {
                "时间": "datetime",
                "开盘": "open",
                "最高": "high",
                "最低": "low",
                "收盘": "close",
                "成交量": "volume",
                "成交额": "amount",
            }
            df = df.rename(columns=col_map)
            
            from src.core.db import save_minute_kline
            count = save_minute_kline(df, code, period)
            logger.info(f"{code} {period}: {count} 條分鐘K線")
            
            # 清除分鐘K線緩存
            from src.core.db import _load_minute_kline_cached
            _load_minute_kline_cached.cache_clear()
            
            time.sleep(_RATE_LIMIT)
            return count
            
        except Exception as e:
            if attempt < MAX_RETRIES:
                logger.warning(f"{code} {period}: 分鐘K線下載失敗(第{attempt}次)，重試... ({e})")
                time.sleep(RETRY_DELAY * attempt)
            else:
                logger.error(f"{code} {period}: 分鐘K線下載全部失敗: {e}")
                return 0
    
    return 0


_RATE_LIMIT = 0.5


def download_minute_batch(codes: list[str], period: str = "5m", adjust: str = "qfq") -> dict:
    """
    批量下載分鐘 K 線數據
    
    Args:
        codes: 股票代碼列表
        period: 週期
        adjust: 復權方式
    
    Returns:
        {"total": int, "success": int, "failed": int, "details": [...]}
    """
    init_db()
    total = 0
    success = 0
    failed = 0
    details = []
    
    logger.info(f"開始下載 {len(codes)} 只股票 {period} 分鐘K線")
    
    for i, code in enumerate(codes, 1):
        logger.info(f"[{i}/{len(codes)}] {code}")
        count = download_minute_data(code, period, adjust)
        
        if count > 0:
            success += 1
            total += count
            details.append({"code": code, "status": "ok", "records": count})
        else:
            failed += 1
            details.append({"code": code, "status": "failed", "records": 0})
        
        if i < len(codes):
            time.sleep(1)
    
    result = {
        "total": total,
        "success": success,
        "failed": failed,
        "details": details,
    }
    
    logger.info(f"分鐘K線下載完成: {success} 成功, {failed} 失敗, 共 {total} 條")
    return result
