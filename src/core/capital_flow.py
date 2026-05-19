"""
資金流向數據模塊 — 個股資金流向、大盤資金流向、北向資金
"""
import akshare as ak
import pandas as pd
import time
import sqlite3
from datetime import datetime
from src.core.db import get_conn
from src.utils.logger import logger

_RATE_LIMIT = 0.5


def _rate_sleep():
    """限速等待"""
    time.sleep(_RATE_LIMIT)


# ============================================================
# 數據庫表定義
# ============================================================

DDL_CAPITAL_FLOW = """
CREATE TABLE IF NOT EXISTS capital_flow (
    code        TEXT NOT NULL,
    date        TEXT NOT NULL,
    flow_type   TEXT NOT NULL,  -- 'individual' / 'market' / 'north'
    main_net    REAL,       -- 主力淨流入
    super_net   REAL,       -- 超大單淨流入
    big_net     REAL,       -- 大單淨流入
    mid_net     REAL,       -- 中單淨流入
    small_net   REAL,       -- 小單淨流入
    close       REAL,
    change_pct  REAL,
    raw_json    TEXT,       -- 原始 JSON 數據備份
    PRIMARY KEY (code, date, flow_type)
)
"""


def init_capital_flow_table():
    """初始化資金流向表"""
    with get_conn() as conn:
        conn.execute(DDL_CAPITAL_FLOW)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cf_code ON capital_flow(code)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cf_date ON capital_flow(date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cf_type ON capital_flow(flow_type)")
        conn.commit()
    logger.info("資金流向表就緒")


# ============================================================
# 個股資金流向
# ============================================================

def get_capital_flow(code: str, days: int = 30) -> list[dict]:
    """
    獲取個股資金流向
    
    Args:
        code: 股票代碼
        days: 最近 N 天
    
    Returns:
        資金流向記錄列表
    """
    try:
        df = ak.stock_individual_fund_flow(stock=code, market="sh" if code.startswith("6") else "sz")
        
        if df.empty:
            logger.warning(f"{code}: 無資金流向數據")
            return []
        
        # 統一列名
        col_map = {
            "日期": "date",
            "收盘价": "close",
            "涨跌幅": "change_pct",
            "主力净流入-净额": "main_net",
            "超大单净流入-净额": "super_net",
            "大单净流入-净额": "big_net",
            "中单净流入-净额": "mid_net",
            "小单净流入-净額": "small_net",
        }
        
        # 靈活匹配列名
        rename_map = {}
        for old_name, new_name in col_map.items():
            for col in df.columns:
                if old_name in col or col == old_name:
                    rename_map[col] = new_name
                    break
        df = df.rename(columns=rename_map)
        
        # 只保留最近 N 天
        if len(df) > days:
            df = df.tail(days)
        
        result = []
        for _, row in df.iterrows():
            record = {
                "code": code,
                "date": str(row.get("date", "")),
                "close": float(row.get("close", 0) or 0),
                "change_pct": float(row.get("change_pct", 0) or 0),
                "main_net": float(row.get("main_net", 0) or 0),
                "super_net": float(row.get("super_net", 0) or 0),
                "big_net": float(row.get("big_net", 0) or 0),
                "mid_net": float(row.get("mid_net", 0) or 0),
                "small_net": float(row.get("small_net", 0) or 0),
            }
            result.append(record)
        
        # 存入數據庫
        _save_capital_flow(result, "individual")
        _rate_sleep()
        return result
        
    except Exception as e:
        logger.error(f"獲取 {code} 資金流向失敗: {e}")
        return []


# ============================================================
# 大盤資金流向
# ============================================================

def get_market_capital_flow() -> list[dict]:
    """
    獲取大盤資金流向（滬深兩市）
    
    Returns:
        大盤資金流向記錄
    """
    try:
        df = ak.stock_market_fund_flow()
        
        if df.empty:
            logger.warning("大盤資金流向數據為空")
            return []
        
        result = []
        for _, row in df.iterrows():
            record = {
                "code": "market",
                "date": str(row.get("日期", "")),
                "close": float(row.get("上证指数", 0) or 0),
                "change_pct": float(row.get("上证指数-涨跌幅", 0) or 0),
                "main_net": float(row.get("主力净流入-净额", 0) or 0),
                "super_net": float(row.get("超大单净流入-净额", 0) or 0),
                "big_net": float(row.get("大单净流入-净额", 0) or 0),
                "mid_net": float(row.get("中单净流入-净额", 0) or 0),
                "small_net": float(row.get("小单净流入-净额", 0) or 0),
            }
            result.append(record)
        
        # 存入數據庫
        _save_capital_flow(result, "market")
        _rate_sleep()
        return result
        
    except Exception as e:
        logger.error(f"獲取大盤資金流向失敗: {e}")
        return []


# ============================================================
# 北向資金
# ============================================================

def get_north_flow(days: int = 30) -> list[dict]:
    """
    獲取北向資金（滬股通+深股通）流入數據
    
    Args:
        days: 最近 N 天
    
    Returns:
        北向資金流入記錄
    """
    try:
        # 滬股通
        df_sh = ak.stock_hsgt_north_net_flow_in_em(symbol="沪股通")
        _rate_sleep()
        # 深股通
        df_sz = ak.stock_hsgt_north_net_flow_in_em(symbol="深股通")
        
        result = []
        
        for label, df in [("滬股通", df_sh), ("深股通", df_sz)]:
            if df.empty:
                continue
            
            # 統一列名
            rename_map = {}
            for col in df.columns:
                if "日期" in col or "date" in col.lower():
                    rename_map[col] = "date"
                elif "净流入" in col or "净买" in col:
                    rename_map[col] = "main_net"
            df = df.rename(columns=rename_map)
            
            if len(df) > days:
                df = df.tail(days)
            
            for _, row in df.iterrows():
                record = {
                    "code": label,
                    "date": str(row.get("date", "")),
                    "close": 0,
                    "change_pct": 0,
                    "main_net": float(row.get("main_net", 0) or 0),
                    "super_net": 0,
                    "big_net": 0,
                    "mid_net": 0,
                    "small_net": 0,
                }
                result.append(record)
        
        # 存入數據庫
        if result:
            _save_capital_flow(result, "north")
        
        _rate_sleep()
        return result
        
    except Exception as e:
        logger.error(f"獲取北向資金失敗: {e}")
        return []


# ============================================================
# 數據庫操作
# ============================================================

def _save_capital_flow(records: list[dict], flow_type: str):
    """保存資金流向到數據庫"""
    if not records:
        return
    
    db_records = []
    for r in records:
        db_records.append((
            r.get("code", ""),
            r.get("date", ""),
            flow_type,
            r.get("main_net"),
            r.get("super_net"),
            r.get("big_net"),
            r.get("mid_net"),
            r.get("small_net"),
            r.get("close"),
            r.get("change_pct"),
            None,  # raw_json
        ))
    
    with get_conn() as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO capital_flow
               (code, date, flow_type, main_net, super_net, big_net, mid_net, small_net,
                close, change_pct, raw_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            db_records
        )
    logger.debug(f"保存資金流向 ({flow_type}): {len(db_records)} 條")


def load_capital_flow(code: str, days: int = 30) -> list[dict]:
    """從數據庫讀取資金流向（緩存查詢）"""
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT * FROM capital_flow 
               WHERE code = ? 
               ORDER BY date DESC LIMIT ?""",
            (code, days)
        ).fetchall()
    return [dict(r) for r in rows]
