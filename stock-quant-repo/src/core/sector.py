"""
板塊數據模塊 — 行業板塊 + 概念板塊
使用 AKShare 接口獲取板塊列表、成分股、板塊漲跌排行
新增：快照存儲、板塊輪動、趨勢分析、資金流向、全景數據
"""
import akshare as ak
import pandas as pd
import time
import sqlite3
from datetime import datetime, timedelta
from src.core.db import get_conn
from src.utils.logger import logger

# 請求間隔（秒），防止被封
_RATE_LIMIT = 0.5


def _rate_sleep():
    """限速等待"""
    time.sleep(_RATE_LIMIT)


# ============================================================
# 數據庫表定義
# ============================================================

DDL_SECTOR = """
CREATE TABLE IF NOT EXISTS sector_data (
    sector_name TEXT NOT NULL,
    sector_type TEXT NOT NULL,  -- 'industry' 或 'concept'
    code        TEXT NOT NULL,
    stock_name  TEXT,
    update_date TEXT,
    PRIMARY KEY (sector_name, sector_type, code)
)
"""

DDL_SECTOR_SNAPSHOT = """
CREATE TABLE IF NOT EXISTS sector_snapshot (
    sector_name      TEXT NOT NULL,
    sector_type      TEXT NOT NULL,
    change_pct       REAL,
    amount           REAL,
    rise_count       INTEGER,
    fall_count       INTEGER,
    leader           TEXT,
    leader_change_pct REAL,
    snapshot_date    TEXT NOT NULL,
    PRIMARY KEY (sector_name, sector_type, snapshot_date)
)
"""


def init_sector_table():
    """初始化板塊數據表 + 快照表"""
    with get_conn() as conn:
        conn.execute(DDL_SECTOR)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sector_name ON sector_data(sector_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sector_code ON sector_data(code)")
        conn.execute(DDL_SECTOR_SNAPSHOT)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshot_date ON sector_snapshot(snapshot_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshot_type ON sector_snapshot(sector_type)")
        conn.commit()
    logger.info("板塊數據表 + 快照表就緒")


# ============================================================
# 行業板塊（原有）
# ============================================================

def get_sector_list(sector_type: str = "industry") -> list[dict]:
    """
    獲取所有板塊列表
    
    Args:
        sector_type: 'industry' 行業板塊, 'concept' 概念板塊
    
    Returns:
        [{"name": "銀行", "code": "BK0475", ...}, ...]
    """
    try:
        if sector_type == "concept":
            df = ak.stock_board_concept_name_em()
        else:
            df = ak.stock_board_industry_name_em()
        
        if df.empty:
            logger.warning(f"獲取{sector_type}板塊列表為空")
            return []
        
        # 統一列名
        result = []
        for _, row in df.iterrows():
            result.append({
                "name": str(row.get("板块名称", row.get("板块名称", ""))),
                "code": str(row.get("板块代码", row.get("板块代码", ""))),
                "change_pct": float(row.get("涨跌幅", 0) or 0),
                "turnover": float(row.get("换手率", 0) or 0),
                "amount": float(row.get("总成交额", 0) or 0),
                "stock_count": int(row.get("上涨家数", 0) or 0),
                "rise_count": int(row.get("上涨家数", 0) or 0),
                "fall_count": int(row.get("下跌家数", 0) or 0),
                "leader": str(row.get("领涨股票", "")),
                "leader_change_pct": float(row.get("领涨股票-涨跌幅", 0) or 0),
                "type": sector_type,
            })
        
        _rate_sleep()
        return result
        
    except Exception as e:
        logger.error(f"獲取{sector_type}板塊列表失敗: {e}")
        return []


def get_sector_stocks(sector_name: str, sector_type: str = "industry") -> list[dict]:
    """
    獲取指定板塊的成分股
    
    Args:
        sector_name: 板塊名稱，如 "銀行"
        sector_type: 'industry' 或 'concept'
    
    Returns:
        [{"code": "000001", "name": "平安銀行", ...}, ...]
    """
    try:
        if sector_type == "concept":
            df = ak.stock_board_concept_cons_em(symbol=sector_name)
        else:
            df = ak.stock_board_industry_cons_em(symbol=sector_name)
        
        if df.empty:
            logger.warning(f"板塊 {sector_name} 無成分股數據")
            return []
        
        result = []
        for _, row in df.iterrows():
            result.append({
                "code": str(row.get("代码", "")),
                "name": str(row.get("名称", "")),
                "price": float(row.get("最新价", 0) or 0),
                "change_pct": float(row.get("涨跌幅", 0) or 0),
                "volume": float(row.get("成交量", 0) or 0),
                "amount": float(row.get("成交额", 0) or 0),
                "turnover": float(row.get("换手率", 0) or 0),
            })
        
        # 存入數據庫
        _save_sector_stocks(sector_name, sector_type, result)
        _rate_sleep()
        return result
        
    except Exception as e:
        logger.error(f"獲取板塊 {sector_name} 成分股失敗: {e}")
        return []


def _save_sector_stocks(sector_name: str, sector_type: str, stocks: list[dict]):
    """保存板塊成分股到數據庫"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    records = []
    for s in stocks:
        records.append((
            sector_name,
            sector_type,
            s.get("code", ""),
            s.get("name", ""),
            now,
        ))
    
    if not records:
        return
    
    with get_conn() as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO sector_data
               (sector_name, sector_type, code, stock_name, update_date)
               VALUES (?, ?, ?, ?, ?)""",
            records
        )
    logger.debug(f"保存板塊 {sector_name} 成分股: {len(records)} 只")


def get_sector_performance(sector_type: str = "industry", top_n: int = 20) -> list[dict]:
    """
    獲取板塊漲跌排行
    
    Args:
        sector_type: 'industry' 或 'concept'
        top_n: 返回前 N 個板塊
    
    Returns:
        按漲跌幅排序的板塊列表
    """
    sectors = get_sector_list(sector_type)
    if not sectors:
        return []
    
    # 按漲跌幅排序
    sectors.sort(key=lambda x: x.get("change_pct", 0), reverse=True)
    return sectors[:top_n]


def get_cached_sector_stocks(sector_name: str) -> list[str]:
    """從數據庫讀取板塊成分股代碼（緩存）"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT code FROM sector_data WHERE sector_name = ?",
            (sector_name,)
        ).fetchall()
    return [r[0] for r in rows]


# ============================================================
# 板塊快照 — 每日存儲板塊漲跌數據
# ============================================================

def save_sector_snapshot(sector_type: str = "industry") -> int:
    """
    保存當日板塊快照到 sector_snapshot 表。
    同一天同一板塊只存一條（REPLACE）。
    
    Args:
        sector_type: 'industry' 或 'concept'
    
    Returns:
        保存的記錄數
    """
    sectors = get_sector_list(sector_type)
    if not sectors:
        logger.warning(f"save_sector_snapshot: {sector_type} 無數據")
        return 0

    today = datetime.now().strftime("%Y-%m-%d")
    records = []
    for s in sectors:
        records.append((
            s.get("name", ""),
            sector_type,
            s.get("change_pct", 0),
            s.get("amount", 0),
            s.get("rise_count", 0),
            s.get("fall_count", 0),
            s.get("leader", ""),
            s.get("leader_change_pct", 0),
            today,
        ))

    with get_conn() as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO sector_snapshot
               (sector_name, sector_type, change_pct, amount, rise_count, fall_count,
                leader, leader_change_pct, snapshot_date)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            records,
        )
        conn.commit()

    logger.info(f"保存 {sector_type} 板塊快照: {len(records)} 個板塊, 日期={today}")
    return len(records)


# ============================================================
# 板塊輪動分析
# ============================================================

def get_sector_rotation(days: int = 10) -> list[dict]:
    """
    板塊輪動分析：比較今天和 N 天前的排名變化。
    返回排名上升最多（新興熱點）和下降最多（退潮）的板塊。
    """
    with get_conn() as conn:
        # 獲取最近有數據的不同日期（降序）
        rows = conn.execute(
            "SELECT DISTINCT snapshot_date FROM sector_snapshot ORDER BY snapshot_date DESC LIMIT ?",
            (days + 1,)
        ).fetchall()

    dates = [r[0] for r in rows]
    if len(dates) < 2:
        logger.warning("板塊輪動：需要至少 2 天數據")
        return []

    latest_date = dates[0]
    # 取 days 天前的數據，如果不足則取最早的一天
    prev_date = dates[min(days, len(dates) - 1)]

    with get_conn() as conn:
        # 今日數據
        today_rows = conn.execute(
            "SELECT sector_name, change_pct, amount FROM sector_snapshot WHERE snapshot_date = ? ORDER BY change_pct DESC",
            (latest_date,),
        ).fetchall()
        # 歷史數據
        prev_rows = conn.execute(
            "SELECT sector_name, change_pct, amount FROM sector_snapshot WHERE snapshot_date = ? ORDER BY change_pct DESC",
            (prev_date,),
        ).fetchall()

    # 建立排名映射
    today_ranks = {r[0]: (i + 1, r[1], r[2]) for i, r in enumerate(today_rows)}
    prev_ranks = {r[0]: (i + 1, r[1], r[2]) for i, r in enumerate(prev_rows)}

    result = []
    for name, (cur_rank, cur_change, cur_amount) in today_ranks.items():
        if name in prev_ranks:
            prev_rank = prev_ranks[name][0]
            rank_change = prev_rank - cur_rank  # 正數=排名上升
            avg_change = round((cur_change + prev_ranks[name][1]) / 2, 2)
            result.append({
                "name": name,
                "rank_change": rank_change,
                "current_rank": cur_rank,
                "prev_rank": prev_rank,
                "avg_change_pct": avg_change,
                "amount": cur_amount,
            })

    # 按排名變化排序
    result.sort(key=lambda x: x["rank_change"], reverse=True)
    return result


# ============================================================
# 板塊歷史趨勢
# ============================================================

def get_sector_trend(sector_name: str, days: int = 20) -> list[dict]:
    """
    從 sector_snapshot 讀取指定板塊最近 N 天的漲跌數據。
    """
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT snapshot_date, change_pct FROM sector_snapshot
               WHERE sector_name = ?
               ORDER BY snapshot_date DESC LIMIT ?""",
            (sector_name, days),
        ).fetchall()

    if not rows:
        return []

    # 反轉為時間正序
    rows = rows[::-1]

    # 計算每天的排名
    dates = [r[0] for r in rows]
    result = []
    for date, change_pct in rows:
        # 查該天所有板塊排名
        with get_conn() as conn:
            all_sectors = conn.execute(
                "SELECT sector_name, change_pct FROM sector_snapshot WHERE snapshot_date = ? ORDER BY change_pct DESC",
                (date,),
            ).fetchall()
        rank_map = {s[0]: i + 1 for i, s in enumerate(all_sectors)}
        result.append({
            "date": date,
            "change_pct": round(change_pct, 2) if change_pct else 0,
            "rank": rank_map.get(sector_name, 0),
        })

    return result


# ============================================================
# 板塊資金流向
# ============================================================

def get_sector_capital_flow(sector_name: str = None) -> list[dict]:
    """
    板塊資金流向 — 使用 AKShare 獲取板塊資金流向排名。
    如果指定 sector_name，只返回該板塊的數據。
    """
    try:
        df = ak.stock_sector_fund_flow_rank(indicator="今日")
        if df is None or df.empty:
            logger.warning("板塊資金流向數據為空")
            return []

        result = []
        for _, row in df.iterrows():
            item = {
                "name": str(row.get("名称", "")),
                "change_pct": float(row.get("今日涨跌幅", 0) or 0),
                "main_net": float(row.get("主力净流入-净额", 0) or 0),
                "main_net_pct": float(row.get("主力净流入-净占比", 0) or 0),
                "super_large_net": float(row.get("超大单净流入-净额", 0) or 0),
                "large_net": float(row.get("大单净流入-净额", 0) or 0),
                "medium_net": float(row.get("中单净流入-净额", 0) or 0),
                "small_net": float(row.get("小单净流入-净額", 0) or 0),
            }
            if sector_name and item["name"] != sector_name:
                continue
            result.append(item)

        _rate_sleep()
        return result

    except Exception as e:
        logger.error(f"獲取板塊資金流向失敗: {e}")
        return []


# ============================================================
# 板塊全景數據（熱力圖）
# ============================================================

def get_sector_heatmap_data(sector_type: str = "industry") -> list[dict]:
    """
    返回所有板塊的漲跌幅和成交額，用於前端矩陣圖。
    格式：[{"name": "銀行", "change_pct": 1.2, "amount": 5.6e9, "stock_count": 42}, ...]
    """
    sectors = get_sector_list(sector_type)
    if not sectors:
        return []

    result = []
    for s in sectors:
        result.append({
            "name": s.get("name", ""),
            "change_pct": s.get("change_pct", 0),
            "amount": s.get("amount", 0),
            "stock_count": s.get("rise_count", 0) + s.get("fall_count", 0),
            "rise_count": s.get("rise_count", 0),
            "fall_count": s.get("fall_count", 0),
            "leader": s.get("leader", ""),
            "leader_change_pct": s.get("leader_change_pct", 0),
        })

    return result
