"""
歷史數據下載模塊（支持增量更新，多市場：A股/加密貨幣/外匯）
"""

import random
import time
from datetime import datetime, timedelta

import akshare as ak
import pandas as pd
import requests

from src.config import settings
from src.core.db import clear_data_cache, get_latest_date, init_db, save_daily_kline
from src.utils.logger import logger

MAX_RETRIES = 3
RETRY_DELAY = 5  # 基礎重試間隔（秒），配合指數退避

_REQ_SESSION = requests.Session()
_REQ_SESSION.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
)


def _patch_akshare_session():
    """修復 akshare 的 requests Session，避免東方財富 API 斷開連接"""
    try:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "keep-alive",
            }
        )
        # 替換 akshare 內部的 requests 模塊 session
        import akshare.core.stock_zh_a_hist as _mod

        if hasattr(_mod, "requests"):
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
    if (
        code.endswith("USDT")
        or code.endswith("BTC")
        or code.endswith("ETH")
        or code.endswith("BNB")
    ):
        return "crypto"
    # 外匯：6 字符，前 3 後 3 都是貨幣代碼
    if len(code) == 6 and code[:3] in (
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
    ):
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
    """下載單個標的歷史日K（自動判斷市場與數據源）。"""
    from src.core.auto_kline_fetch import download_one_auto

    count, _ = download_one_auto(code, start_date=start_date, market=market)
    return count


def download_one_with_source(
    code: str,
    start_date: str = None,
    market: str = None,
) -> tuple[int, str]:
    """下載單標的日 K，返回 (條數, source_slug)。"""
    from src.core.auto_kline_fetch import download_one_auto

    return download_one_auto(code, start_date=start_date, market=market)


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


def _global_market_tag(code: str) -> str:
    if code.endswith(".HK"):
        return "hk_stock"
    if code.endswith("=F"):
        return "commodity"
    if code.endswith("=X"):
        return "forex_yahoo"
    if code.startswith("^"):
        return "index"
    if code.isalpha() or ("-" in code and not code[0].isdigit()):
        return "us_stock"
    return "global"


def _global_try_ib(code: str, start_date: str | None) -> int:
    if not getattr(settings, "ib_enabled", False):
        return 0
    try:
        from src.core.ib_data import fetch_ib_history, ib_available
        from src.core.market_catalog import lookup_instrument
    except Exception:
        return 0
    if not ib_available():
        return 0
    inst = lookup_instrument(code)
    spec = inst.ib if inst else None
    if not spec:
        return 0
    days = 120
    if start_date:
        try:
            sd = datetime.strptime(str(start_date).replace("-", "")[:8], "%Y%m%d")
            days = max(2, min(365, (datetime.now() - sd).days + 1))
        except Exception:
            days = 120
    df_ib = fetch_ib_history(spec, days=days)
    if df_ib is None or df_ib.empty:
        return 0
    market = _global_market_tag(code)
    count = save_daily_kline(df_ib, code, market=market)
    logger.info(f"全球標的 {code}: {count} 條記錄 (IB, market={market})")
    return count


def _global_try_yahoo(code: str, start_date: str | None) -> int:
    from src.core.global_market import download_global_symbol

    df = download_global_symbol(symbol=code, start_date=start_date)
    if df.empty:
        return 0
    count = save_daily_kline(df, code, market=_global_market_tag(code))
    logger.info(f"全球標的 {code}: {count} 條記錄 (Yahoo)")
    return count


def _global_try_twelve(code: str, start_date: str | None) -> int:
    from src.core.global_market import _twelve_time_series

    if not (code.isalpha() or ("-" in code and not code[0].isdigit())):
        return 0
    df = _twelve_time_series(code, start_date)
    if df.empty:
        return 0
    count = save_daily_kline(df, code, market=_global_market_tag(code))
    logger.info(f"全球標的 {code}: {count} 條記錄 (Twelve Data)")
    return count


def _global_try_tradingview(code: str, start_date: str | None) -> int:
    try:
        from src.core.market_catalog import lookup_instrument
        from src.core.tradingview_data import fetch_tv_bundle
    except Exception:
        return 0
    inst = lookup_instrument(code)
    if not inst or not inst.tv:
        return 0
    days = 120
    if start_date:
        try:
            sd = datetime.strptime(str(start_date).replace("-", "")[:8], "%Y%m%d")
            days = max(2, min(365, (datetime.now() - sd).days + 1))
        except Exception:
            pass
    df, _, _ = fetch_tv_bundle(inst.tv, inst.scanner, days, inst.symbol)
    if df.empty:
        return 0
    count = save_daily_kline(df, code, market=_global_market_tag(code))
    logger.info(f"全球標的 {code}: {count} 條記錄 (TradingView)")
    return count


def download_global_auto(code: str, start_date: str = None) -> tuple[int, str]:
    """全球標的：依 data_sources 動態排序自動選源。"""
    from src.core.auto_kline_fetch import _run_ordered_sources

    handlers = {
        "Interactive Brokers": lambda: _global_try_ib(code, start_date),
        "Yahoo Finance": lambda: _global_try_yahoo(code, start_date),
        "Twelve Data": lambda: _global_try_twelve(code, start_date),
        "TradingView": lambda: _global_try_tradingview(code, start_date),
    }
    n, slug = _run_ordered_sources("global_history", handlers)
    if n <= 0:
        logger.error(f"全球標的 {code}: 所有數據源均失敗")
    return n, slug


def _download_global(code: str, start_date: str = None) -> int:
    n, _ = download_global_auto(code, start_date)
    return n


def _download_a_share(code: str, start_date: str = None) -> int:
    """下載 A 股歷史數據（統一降級鏈：kline_fetcher）。"""
    from src.core.kline_fetcher import download_a_share_kline

    count, _ = download_a_share_kline(code, start_date)
    if count <= 0:
        logger.error(f"{code}: 所有數據源均失敗")
    return count


def _download_a_share_http(code: str, start_date: str = None) -> "pd.DataFrame | None":
    """
    直接 HTTP 請求東方財富歷史 K 線 API（不依賴 akshare）。
    作為最後備選方案。
    """

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
        "klt": "101",  # 日 K
        "fqt": "1",  # 前復權
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
                rows.append(
                    {
                        "date": parts[0],
                        "open": float(parts[1]),
                        "close": float(parts[2]),
                        "high": float(parts[3]),
                        "low": float(parts[4]),
                        "volume": float(parts[5]),
                        "amount": float(parts[6]),
                        "turnover": float(parts[10]) if len(parts) > 10 else 0,
                    }
                )

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
                        details.append(
                            {"code": code, "status": "skipped", "reason": "已是最新"}
                        )
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

    logger.info(
        f"增量更新完成: {updated} 只更新, {skipped} 只跳過, {total_records} 條新數據"
    )
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
                logger.warning(
                    f"{code} {period}: 分鐘K線下載失敗(第{attempt}次)，重試... ({e})"
                )
                time.sleep(RETRY_DELAY * attempt)
            else:
                logger.error(f"{code} {period}: 分鐘K線下載全部失敗: {e}")
                return 0

    return 0


_RATE_LIMIT = 0.5


def download_minute_batch(
    codes: list[str], period: str = "5m", adjust: str = "qfq"
) -> dict:
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


async def preload_kline_range(
    code: str, start_date: str = None, end_date: str = None
) -> int:
    """異步預載 K 線至 LRU（不阻塞事件循環）。"""
    import asyncio

    from src.core.db import preload_kline_range as _sync_preload

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _sync_preload, code, start_date, end_date)
