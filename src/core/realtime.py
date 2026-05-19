"""
實時行情獲取模塊（多源備選，增強容錯）
"""
import akshare as ak
import pandas as pd
import requests
import time
from src.core.db import save_realtime_snapshot
from src.utils.logger import logger

MAX_RETRIES = 2
_REQ_SESSION = requests.Session()
_REQ_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
})


# ============================================================
# 數據源 1：東方財富五檔盤口 (ak.stock_bid_ask_em)
# ============================================================
def _fetch_em_bid_ask(code: str) -> dict | None:
    """東方財富五檔盤口（最詳細，含買賣五檔）"""
    try:
        df = ak.stock_bid_ask_em(symbol=code)
        if df.empty:
            return None
        data = dict(zip(df["item"], df["value"]))
        return {
            "code": code,
            "name": "",
            "price": float(data.get("最新", 0)),
            "change_pct": float(data.get("涨幅", 0)),
            "change": float(data.get("涨跌", 0)),
            "volume": float(data.get("总手", 0)),
            "amount": float(data.get("金额", 0)),
            "open": float(data.get("今开", 0)),
            "high": float(data.get("最高", 0)),
            "low": float(data.get("最低", 0)),
            "prev_close": float(data.get("昨收", 0)),
            "turnover": float(data.get("换手", 0)),
            "avg_price": float(data.get("均价", 0)),
            "volume_ratio": float(data.get("量比", 0)),
            "limit_up": float(data.get("涨停", 0)),
            "limit_down": float(data.get("跌停", 0)),
        }
    except Exception as e:
        logger.debug(f"東財盤口 {code} 失敗: {e}")
        return None


# ============================================================
# 數據源 2：東方財富全量行情 (ak.stock_zh_a_spot_em)
# ============================================================
_spot_cache: dict = {}
_spot_cache_ts: float = 0

def _fetch_em_spot_batch(codes: list[str]) -> dict[str, dict]:
    """
    東方財富全量行情（一次請求拿全部 A 股，緩存 10 秒）。
    返回 {code: quote_dict}
    """
    global _spot_cache, _spot_cache_ts
    now = time.time()

    # 緩存 10 秒
    if _spot_cache and (now - _spot_cache_ts) < 10:
        return {c: _spot_cache[c] for c in codes if c in _spot_cache}

    try:
        df = ak.stock_zh_a_spot_em()
        if df.empty:
            return {}
        col_map = {
            "代码": "code", "名称": "name", "最新价": "price",
            "涨跌幅": "change_pct", "涨跌额": "change",
            "成交量": "volume", "成交额": "amount",
            "今开": "open", "最高": "high", "最低": "low",
            "昨收": "prev_close", "换手率": "turnover",
            "量比": "volume_ratio",
        }
        df = df.rename(columns=col_map)

        # 向量化處理：比 iterrows() 快 10-50 倍
        _spot_cache = {}
        code_series = df["code"].astype(str)
        for col in ("price", "change_pct", "change", "volume", "amount",
                     "open", "high", "low", "prev_close", "turnover", "volume_ratio"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        for i in range(len(df)):
            row = df.iloc[i]
            c = code_series.iloc[i]
            if c:
                _spot_cache[c] = {
                    "code": c,
                    "name": str(row.get("name", "")),
                    "price": float(row.get("price", 0)),
                    "change_pct": float(row.get("change_pct", 0)),
                    "change": float(row.get("change", 0)),
                    "volume": float(row.get("volume", 0)),
                    "amount": float(row.get("amount", 0)),
                    "open": float(row.get("open", 0)),
                    "high": float(row.get("high", 0)),
                    "low": float(row.get("low", 0)),
                    "prev_close": float(row.get("prev_close", 0)),
                    "turnover": float(row.get("turnover", 0)),
                    "volume_ratio": float(row.get("volume_ratio", 0)),
                }
        _spot_cache_ts = now
        return {c: _spot_cache[c] for c in codes if c in _spot_cache}
    except Exception as e:
        logger.debug(f"東財全量行情失敗: {e}")
        return {}


# ============================================================
# 數據源 3：新浪實時行情（HTTP 直連）
# ============================================================
def _fetch_sina(code: str) -> dict | None:
    """新浪實時行情（HTTP 直連，不依賴 akshare）"""
    if code.startswith("6"):
        symbol = f"sh{code}"
    else:
        symbol = f"sz{code}"

    try:
        url = f"https://hq.sinajs.cn/list={symbol}"
        resp = _REQ_SESSION.get(url, timeout=5)
        resp.encoding = "gbk"
        text = resp.text.strip()

        if "=" not in text or '""' in text:
            return None

        # 解析：var hq_str_sh600519="貴州茅台,1800.00,..."
        data_str = text.split('="')[1].rstrip('";')
        parts = data_str.split(",")

        if len(parts) < 32:
            return None

        name = parts[0]
        open_p = float(parts[1] or 0)
        prev_close = float(parts[2] or 0)
        price = float(parts[3] or 0)
        high = float(parts[4] or 0)
        low = float(parts[5] or 0)
        volume = float(parts[8] or 0)  # 成交量（手）
        amount = float(parts[9] or 0)  # 成交額

        change = price - prev_close if prev_close else 0
        change_pct = (change / prev_close * 100) if prev_close else 0

        return {
            "code": code,
            "name": name,
            "price": price,
            "change_pct": round(change_pct, 2),
            "change": round(change, 2),
            "volume": volume,
            "amount": amount,
            "open": open_p,
            "high": high,
            "low": low,
            "prev_close": prev_close,
            "turnover": 0,
            "volume_ratio": 0,
        }
    except Exception as e:
        logger.debug(f"新浪行情 {code} 失敗: {e}")
        return None


# ============================================================
# 數據源 4：騰訊實時行情（HTTP 直連）
# ============================================================
def _fetch_tencent(code: str) -> dict | None:
    """騰訊實時行情（HTTP 直連）"""
    if code.startswith("6"):
        symbol = f"sh{code}"
    else:
        symbol = f"sz{code}"

    try:
        url = f"https://qt.gtimg.cn/q={symbol}"
        resp = _REQ_SESSION.get(url, timeout=5)
        resp.encoding = "gbk"
        text = resp.text.strip()

        if "~" not in text:
            return None

        data_str = text.split('="')[1].rstrip('";')
        parts = data_str.split("~")

        if len(parts) < 45:
            return None

        name = parts[1]
        price = float(parts[3] or 0)
        prev_close = float(parts[4] or 0)
        open_p = float(parts[5] or 0)
        volume = float(parts[6] or 0)
        amount = float(parts[37] or 0) if len(parts) > 37 else 0
        high = float(parts[33] or 0) if len(parts) > 33 else 0
        low = float(parts[34] or 0) if len(parts) > 34 else 0
        change_pct = float(parts[32] or 0) if len(parts) > 32 else 0
        change = float(parts[31] or 0) if len(parts) > 31 else 0

        return {
            "code": code,
            "name": name,
            "price": price,
            "change_pct": round(change_pct, 2),
            "change": round(change, 2),
            "volume": volume,
            "amount": amount,
            "open": open_p,
            "high": high,
            "low": low,
            "prev_close": prev_close,
            "turnover": 0,
            "volume_ratio": 0,
        }
    except Exception as e:
        logger.debug(f"騰訊行情 {code} 失敗: {e}")
        return None


# ============================================================
# 數據源 5：東財 push2 接口（HTTP 直連，批量更快）
# ============================================================
_EM_SECID_MAP = {}

def _fetch_em_push2(code: str) -> dict | None:
    """東財 push2 接口（比 akshare 更快，直接 HTTP）"""
    try:
        if code.startswith("6"):
            secid = f"1.{code}"
        else:
            secid = f"0.{code}"

        url = "https://push2.eastmoney.com/api/qt/stock/get"
        params = {
            "secid": secid,
            "fields": "f43,f44,f45,f46,f47,f48,f57,f58,f60,f169,f170,f171",
            "ut": "fa5fd1943c7b386f172d6893dbbd1",
        }
        resp = _REQ_SESSION.get(url, params=params, timeout=5)
        data = resp.json().get("data", {})

        if not data:
            return None

        # 東財價格是整數，需除以 100
        price = data.get("f43", 0) / 100
        prev_close = data.get("f60", 0) / 100
        open_p = data.get("f46", 0) / 100
        high = data.get("f44", 0) / 100
        low = data.get("f45", 0) / 100
        volume = data.get("f47", 0)
        amount = data.get("f48", 0)
        change_pct = data.get("f170", 0) / 100
        change = data.get("f169", 0) / 100
        name = data.get("f58", "")

        return {
            "code": code,
            "name": name,
            "price": round(price, 2),
            "change_pct": round(change_pct, 2),
            "change": round(change, 2),
            "volume": volume,
            "amount": amount,
            "open": round(open_p, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "prev_close": round(prev_close, 2),
            "turnover": 0,
            "volume_ratio": 0,
        }
    except Exception as e:
        logger.debug(f"東財 push2 {code} 失敗: {e}")
        return None


# ============================================================
# 統一入口：自動降級
# ============================================================
def fetch_one_realtime(code: str) -> dict | None:
    """
    獲取單只股票實時行情（多源自動降級）。

    優先級：
    1. 東財五檔盤口（最詳細）
    2. 新浪 HTTP（快速、穩定）
    3. 騰訊 HTTP（備選）
    """
    # 源 1：東財盤口
    result = _fetch_em_bid_ask(code)
    if result and result.get("price", 0) > 0:
        return result

    # 源 2：新浪
    result = _fetch_sina(code)
    if result and result.get("price", 0) > 0:
        logger.debug(f"{code}: 使用新浪備選源")
        return result

    # 源 3：騰訊
    result = _fetch_tencent(code)
    if result and result.get("price", 0) > 0:
        logger.debug(f"{code}: 使用騰訊備選源")
        return result

    # 源 4：東財 push2（直接 HTTP，比 akshare 快）
    result = _fetch_em_push2(code)
    if result and result.get("price", 0) > 0:
        logger.debug(f"{code}: 使用東財 push2 備選源")
        return result

    logger.warning(f"{code}: 所有實時行情源均失敗")
    return None


def fetch_realtime(codes: list[str]) -> pd.DataFrame:
    """
    批量獲取實時行情（智能降級）。

    如果東財全量接口可用，批量獲取更快；
    否則逐個查詢（東財→新浪→騰訊）。
    """
    # 先嘗試東財全量批量接口
    batch = _fetch_em_spot_batch(codes)
    if len(batch) >= len(codes) * 0.5:  # 超過一半的股票有數據就用批量結果
        rows = [batch[c] for c in codes if c in batch]
        if rows:
            df = pd.DataFrame(rows)
            save_realtime_snapshot(df)
            return df

    # 批量接口不足，逐個查詢
    import random
    rows = []
    for code in codes:
        row = fetch_one_realtime(code)
        if row:
            rows.append(row)
        time.sleep(random.uniform(0.1, 0.3))  # 隨機抖動，降低被限流風險

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    save_realtime_snapshot(df)
    return df
