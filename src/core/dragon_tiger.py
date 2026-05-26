"""
龍虎榜數據模塊 — 獲取龍虎榜明細及歷史
"""
import akshare as ak
import pandas as pd
import time
import sqlite3
from datetime import datetime, timedelta
from src.core.db import get_conn
from src.utils.logger import logger

_RATE_LIMIT = 0.5


def _rate_sleep():
    """限速等待"""
    time.sleep(_RATE_LIMIT)


# ============================================================
# 數據庫表定義
# ============================================================

DDL_DRAGON_TIGER = """
CREATE TABLE IF NOT EXISTS dragon_tiger (
    code            TEXT NOT NULL,
    name            TEXT,
    date            TEXT NOT NULL,
    close           REAL,
    change_pct      REAL,
    reason          TEXT,       -- 上榜原因
    buy_amount      REAL,       -- 買入總額
    sell_amount     REAL,       -- 賣出總額
    net_amount      REAL,       -- 淨買入
    turnover_rate   REAL,
    amount          REAL,       -- 成交額
    circulating_mv  REAL,       -- 流通市值
    raw_json        TEXT,
    PRIMARY KEY (code, date)
)
"""


def init_dragon_tiger_table():
    """向後兼容；表結構由 src.core.database.schema 集中管理。"""
    pass


# ============================================================
# 龍虎榜數據
# ============================================================

def get_dragon_tiger(date: str = None) -> list[dict]:
    """
    獲取指定日期的龍虎榜數據
    
    Args:
        date: 日期字符串 "YYYYMMDD"，默認為今天
    
    Returns:
        龍虎榜明細列表
    """
    if date is None:
        date = datetime.now().strftime("%Y%m%d")
    
    try:
        df = ak.stock_lhb_detail_em(
            start_date=date,
            end_date=date,
        )
        
        if df.empty:
            logger.warning(f"龍虎榜 {date} 無數據")
            return []
        
        # 靈活匹配列名
        result = []
        for _, row in df.iterrows():
            record = {
                "code": str(_get_col(row, ["代码", "股票代码", "code"], "")),
                "name": str(_get_col(row, ["名称", "股票名称", "name"], "")),
                "date": str(_get_col(row, ["上榜日期", "日期", "date"], date)),
                "close": float(_get_col(row, ["收盘价", "收盘"], 0) or 0),
                "change_pct": float(_get_col(row, ["涨跌幅"], 0) or 0),
                "reason": str(_get_col(row, ["上榜原因", "解读"], "")),
                "buy_amount": float(_get_col(row, ["买入总额", "龙虎榜买入额"], 0) or 0),
                "sell_amount": float(_get_col(row, ["卖出总额", "龙虎榜卖出额"], 0) or 0),
                "net_amount": float(_get_col(row, ["净买入额", "龙虎榜净买额"], 0) or 0),
                "turnover_rate": float(_get_col(row, ["换手率"], 0) or 0),
                "amount": float(_get_col(row, ["成交额"], 0) or 0),
                "circulating_mv": float(_get_col(row, ["流通市值"], 0) or 0),
            }
            result.append(record)
        
        # 存入數據庫
        result = _enrich_market_and_sector(result)
        _save_dragon_tiger(result)
        _rate_sleep()
        return result
        
    except Exception as e:
        logger.error(f"獲取龍虎榜 {date} 失敗: {e}")
        return []


def _get_col(row, candidates: list, default):
    """從多個候選列名中取值"""
    for col in candidates:
        if col in row.index:
            val = row[col]
            if pd.notna(val):
                return val
    return default


def _infer_market(code: str) -> tuple[str, str]:
    """從代碼推斷市場，股票庫無資料時作為兜底。"""
    c = str(code or "").strip().upper()
    if not c:
        return "unknown", "未知"
    if c.endswith(".HK") or (c.isdigit() and len(c) == 5):
        return "hk_stock", "港股"
    if c.isalpha() or "." in c:
        return "us_stock", "美股"
    if c.isdigit() and len(c) == 6:
        return "a_share", "A股"
    return "unknown", "未知"


def _market_name(market: str) -> str:
    return {
        "a_share": "A股",
        "hk_stock": "港股",
        "us_stock": "美股",
    }.get(market or "", "未知")


def _enrich_market_and_sector(records: list[dict]) -> list[dict]:
    """用股票庫與本地板塊成分表補齊市場與板塊資訊。"""
    if not records:
        return records

    codes = sorted({str(r.get("code") or "").strip() for r in records if r.get("code")})
    if not codes:
        return records

    universe_map: dict[str, dict] = {}
    sector_map: dict[str, str] = {}

    try:
        placeholders = ",".join("?" for _ in codes)
        with get_conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"""SELECT code, market, industry
                    FROM stock_universe
                    WHERE code IN ({placeholders})""",
                codes,
            ).fetchall()
            for row in rows:
                universe_map[str(row["code"])] = dict(row)
    except sqlite3.Error as e:
        logger.debug(f"讀取股票庫補龍虎榜市場/行業失敗: {e}")

    try:
        placeholders = ",".join("?" for _ in codes)
        with get_conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"""SELECT code, sector_name, sector_type
                    FROM sector_data
                    WHERE code IN ({placeholders})
                    ORDER BY CASE sector_type WHEN 'industry' THEN 0 ELSE 1 END, sector_name""",
                codes,
            ).fetchall()
            for row in rows:
                row_code = str(row["code"])
                if row_code not in sector_map:
                    sector_map[row_code] = str(row["sector_name"] or "")
    except sqlite3.Error as e:
        logger.debug(f"讀取板塊成分補龍虎榜板塊失敗: {e}")

    for record in records:
        code = str(record.get("code") or "").strip()
        inferred_market, inferred_name = _infer_market(code)
        universe = universe_map.get(code, {})
        market = universe.get("market") or inferred_market
        sector = universe.get("industry") or sector_map.get(code) or "未分類"

        record["market"] = market
        record["market_name"] = _market_name(market) if market != "unknown" else inferred_name
        record["sector"] = sector

    return records


def get_dragon_tiger_history(code: str, days: int = 30) -> list[dict]:
    """
    獲取某只股票的龍虎榜歷史
    
    Args:
        code: 股票代碼
        days: 最近 N 天
    
    Returns:
        龍虎榜歷史記錄
    """
    # 先從數據庫查
    cached = _load_dragon_tiger_from_db(code, days)
    if cached:
        return _enrich_market_and_sector(cached)
    
    # 數據庫無數據，嘗試從 API 獲取最近一段時間
    try:
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        
        df = ak.stock_lhb_detail_em(
            start_date=start_date,
            end_date=end_date,
        )
        
        if df.empty:
            return []
        
        # 按股票代碼過濾
        code_col = None
        for col in ["代码", "股票代码"]:
            if col in df.columns:
                code_col = col
                break
        
        if code_col:
            df = df[df[code_col].astype(str) == str(code)]
        
        if df.empty:
            return []
        
        result = []
        for _, row in df.iterrows():
            record = {
                "code": str(_get_col(row, ["代码", "股票代码", "code"], code)),
                "name": str(_get_col(row, ["名称", "股票名称", "name"], "")),
                "date": str(_get_col(row, ["上榜日期", "日期", "date"], "")),
                "close": float(_get_col(row, ["收盘价", "收盘"], 0) or 0),
                "change_pct": float(_get_col(row, ["涨跌幅"], 0) or 0),
                "reason": str(_get_col(row, ["上榜原因", "解读"], "")),
                "buy_amount": float(_get_col(row, ["买入总额", "龙虎榜买入额"], 0) or 0),
                "sell_amount": float(_get_col(row, ["卖出总额", "龙虎榜卖出额"], 0) or 0),
                "net_amount": float(_get_col(row, ["净买入额", "龙虎榜净买额"], 0) or 0),
                "turnover_rate": float(_get_col(row, ["换手率"], 0) or 0),
                "amount": float(_get_col(row, ["成交额"], 0) or 0),
                "circulating_mv": float(_get_col(row, ["流通市值"], 0) or 0),
            }
            result.append(record)
        
        _save_dragon_tiger(result)
        _rate_sleep()
        return result
        
    except Exception as e:
        logger.error(f"獲取 {code} 龍虎榜歷史失敗: {e}")
        return []


# ============================================================
# 數據庫操作
# ============================================================

def _save_dragon_tiger(records: list[dict]):
    """保存龍虎榜數據到數據庫"""
    if not records:
        return
    
    db_records = []
    for r in records:
        db_records.append((
            r.get("code", ""),
            r.get("name", ""),
            r.get("date", ""),
            r.get("close"),
            r.get("change_pct"),
            r.get("reason", ""),
            r.get("buy_amount"),
            r.get("sell_amount"),
            r.get("net_amount"),
            r.get("turnover_rate"),
            r.get("amount"),
            r.get("circulating_mv"),
            None,  # raw_json
        ))
    
    with get_conn() as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO dragon_tiger
               (code, name, date, close, change_pct, reason,
                buy_amount, sell_amount, net_amount,
                turnover_rate, amount, circulating_mv, raw_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            db_records
        )
    logger.debug(f"保存龍虎榜: {len(db_records)} 條")


def _load_dragon_tiger_from_db(code: str, days: int) -> list[dict]:
    """從數據庫讀取龍虎榜歷史"""
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT * FROM dragon_tiger 
               WHERE code = ? AND date >= ?
               ORDER BY date DESC""",
            (code, cutoff)
        ).fetchall()
    return [dict(r) for r in rows]
