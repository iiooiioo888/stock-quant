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
    """初始化龍虎榜表"""
    with get_conn() as conn:
        conn.execute(DDL_DRAGON_TIGER)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dt_code ON dragon_tiger(code)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dt_date ON dragon_tiger(date)")
        conn.commit()
    logger.info("龍虎榜表就緒")


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
        return cached
    
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
