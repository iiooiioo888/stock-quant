"""
基本面數據模塊 — PE、PB、ROE、市值等基本面指標
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

DDL_FUNDAMENTALS = """
CREATE TABLE IF NOT EXISTS fundamentals (
    code            TEXT NOT NULL,
    name            TEXT,
    update_date     TEXT NOT NULL,
    pe_ttm          REAL,       -- 市盈率(TTM)
    pb              REAL,       -- 市淨率
    roe             REAL,       -- 淨資產收益率
    eps             REAL,       -- 每股收益
    bvps            REAL,       -- 每股淨資產
    total_mv        REAL,       -- 總市值（億）
    circulating_mv  REAL,       -- 流通市值（億）
    revenue         REAL,       -- 營業收入（億）
    net_profit      REAL,       -- 淨利潤（億）
    gross_margin    REAL,       -- 毛利率
    net_margin      REAL,       -- 淨利率
    debt_ratio      REAL,       -- 資產負債率
    dividend_yield  REAL,       -- 股息率
    raw_json        TEXT,
    PRIMARY KEY (code, update_date)
)
"""


_EXTRA_FUND_COLS = [
    ("ps_ttm", "REAL"),
    ("revenue_yoy", "REAL"),
    ("profit_yoy", "REAL"),
]


def init_fundamentals_table():
    """初始化基本面數據表"""
    with get_conn() as conn:
        conn.execute(DDL_FUNDAMENTALS)
        for col, typ in _EXTRA_FUND_COLS:
            try:
                conn.execute(f"ALTER TABLE fundamentals ADD COLUMN {col} {typ}")
            except sqlite3.OperationalError:
                pass
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fund_code ON fundamentals(code)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fund_date ON fundamentals(update_date)")
        conn.commit()
    logger.info("基本面數據表就緒")


# ============================================================
# 基本面數據獲取
# ============================================================

def get_fundamentals(code: str) -> dict:
    """
    獲取單只股票的基本面指標
    
    Args:
        code: 股票代碼
    
    Returns:
        基本面指標字典
    """
    # 先查緩存
    cached = _load_fundamentals_from_db(code)
    if cached:
        return cached
    
    try:
        # 使用財務分析指標接口
        df = ak.stock_financial_analysis_indicator(symbol=code)
        
        if df.empty:
            logger.warning(f"{code}: 無基本面數據")
            return {}
        
        # 取最新一條
        latest = df.iloc[0]
        
        # 靈活匹配列名
        result = {
            "code": code,
            "name": "",
            "update_date": str(latest.get("日期", datetime.now().strftime("%Y-%m-%d"))),
            "pe_ttm": _safe_float(latest, ["市盈率(TTM)", "市盈率", "pe_ttm"]),
            "pb": _safe_float(latest, ["市净率", "市淨率", "pb"]),
            "roe": _safe_float(latest, ["净资产收益率(%)", "净资产收益率", "加权净资产收益率(%)", "roe"]),
            "eps": _safe_float(latest, ["基本每股收益(元)", "基本每股收益", "eps"]),
            "bvps": _safe_float(latest, ["每股净资产(元)", "每股净资产", "bvps"]),
            "total_mv": 0,
            "circulating_mv": 0,
            "revenue": 0,
            "net_profit": 0,
            "gross_margin": _safe_float(latest, ["销售毛利率(%)", "毛利率(%)", "gross_margin"]),
            "net_margin": _safe_float(latest, ["销售净利率(%)", "净利率(%)", "net_margin"]),
            "debt_ratio": _safe_float(latest, ["资产负债率(%)", "资产负债率", "debt_ratio"]),
            "dividend_yield": 0,
        }
        
        # 嘗試獲取市值信息
        try:
            _rate_sleep()
            spot_df = ak.stock_individual_info_em(symbol=code)
            if not spot_df.empty:
                for _, row in spot_df.iterrows():
                    item = str(row.get("item", ""))
                    value = row.get("value", 0)
                    if "總市值" in item:
                        result["total_mv"] = _to_yi(float(value or 0))
                    elif "流通市值" in item:
                        result["circulating_mv"] = _to_yi(float(value or 0))
                    elif "股票簡稱" in item or "名稱" in item:
                        result["name"] = str(value)
        except Exception:
            pass
        
        # 存入數據庫
        _save_fundamentals(result)
        _rate_sleep()
        return result
        
    except Exception as e:
        logger.error(f"獲取 {code} 基本面失敗: {e}")
        return {}


def screen_by_fundamentals(filters: dict) -> list[dict]:
    """
    按基本面指標篩選股票
    
    Args:
        filters: 篩選條件
            - pe_max: PE < 某值
            - pb_max: PB < 某值
            - roe_min: ROE > 某值%
            - debt_max: 資產負債率 < 某值%
            - mv_min: 總市值 > 某億
            - dividend_min: 股息率 > 某值%
    
    Returns:
        符合條件的股票列表
    """
    # 先從數據庫篩選
    results = _screen_from_db(filters)
    if results:
        return results
    
    # 數據庫無數據時，嘗試從實時行情中批量獲取
    logger.info("數據庫無基本面數據，嘗試從 API 篩選...")
    return _screen_from_api(filters)


def _screen_from_db(filters: dict) -> list[dict]:
    """從數據庫篩選"""
    conditions = []
    params = []
    
    if "pe_max" in filters:
        conditions.append("pe_ttm IS NOT NULL AND pe_ttm > 0 AND pe_ttm <= ?")
        params.append(filters["pe_max"])
    if "pb_max" in filters:
        conditions.append("pb IS NOT NULL AND pb > 0 AND pb <= ?")
        params.append(filters["pb_max"])
    if "roe_min" in filters:
        conditions.append("roe IS NOT NULL AND roe >= ?")
        params.append(filters["roe_min"])
    if "debt_max" in filters:
        conditions.append("debt_ratio IS NOT NULL AND debt_ratio <= ?")
        params.append(filters["debt_max"])
    if "mv_min" in filters:
        conditions.append("total_mv IS NOT NULL AND total_mv >= ?")
        params.append(filters["mv_min"])
    if "dividend_min" in filters:
        conditions.append("dividend_yield IS NOT NULL AND dividend_yield >= ?")
        params.append(filters["dividend_min"])
    if "eps_min" in filters:
        conditions.append("eps IS NOT NULL AND eps >= ?")
        params.append(filters["eps_min"])
    if "gross_margin_min" in filters:
        conditions.append("gross_margin IS NOT NULL AND gross_margin >= ?")
        params.append(filters["gross_margin_min"])
    if "net_margin_min" in filters:
        conditions.append("net_margin IS NOT NULL AND net_margin >= ?")
        params.append(filters["net_margin_min"])
    if "pe_min" in filters:
        conditions.append("pe_ttm IS NOT NULL AND pe_ttm >= ?")
        params.append(filters["pe_min"])

    if not conditions:
        return []
    
    where = " AND ".join(conditions)
    
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""SELECT * FROM fundamentals 
                WHERE {where}
                ORDER BY roe DESC NULLS LAST
                LIMIT 100""",
            params
        ).fetchall()
    
    return [dict(r) for r in rows]


def _screen_from_api(filters: dict) -> list[dict]:
    """從 API 批量獲取並篩選（較慢，用於數據庫無數據時）"""
    try:
        # 獲取 A 股實時行情（含 PE/PB 等）
        df = ak.stock_zh_a_spot_em()
        if df.empty:
            return []
        
        # 列名映射
        col_map = {
            "代码": "code",
            "名称": "name",
            "市盈率-动态": "pe_ttm",
            "市净率": "pb",
            "总市值": "total_mv_raw",
        }
        rename = {}
        for old, new in col_map.items():
            for col in df.columns:
                if old in col:
                    rename[col] = new
                    break
        df = df.rename(columns=rename)
        
        # 篩選
        if "pe_max" in filters and "pe_ttm" in df.columns:
            df = df[(df["pe_ttm"].notna()) & (df["pe_ttm"] > 0) & (df["pe_ttm"] <= filters["pe_max"])]
        if "pb_max" in filters and "pb" in df.columns:
            df = df[(df["pb"].notna()) & (df["pb"] > 0) & (df["pb"] <= filters["pb_max"])]
        if "mv_min" in filters and "total_mv_raw" in df.columns:
            df = df[(df["total_mv_raw"].notna()) & (df["total_mv_raw"] >= filters["mv_min"] * 1e8)]
        
        result = []
        for _, row in df.head(50).iterrows():
            result.append({
                "code": str(row.get("code", "")),
                "name": str(row.get("name", "")),
                "pe_ttm": float(row.get("pe_ttm", 0) or 0),
                "pb": float(row.get("pb", 0) or 0),
                "total_mv": _to_yi(float(row.get("total_mv_raw", 0) or 0)),
            })
        
        return result
        
    except Exception as e:
        logger.error(f"API 篩選基本面失敗: {e}")
        return []


# ============================================================
# 輔助函數
# ============================================================

def _safe_float(row, candidates: list, default=0):
    """安全取浮點值"""
    for col in candidates:
        if col in row.index:
            val = row[col]
            if pd.notna(val):
                try:
                    return float(val)
                except (ValueError, TypeError):
                    continue
    return default


def _to_yi(value: float) -> float:
    """轉換為億"""
    if value > 1e12:
        return round(value / 1e8, 2)
    elif value > 1e8:
        return round(value / 1e8, 2)
    return round(value, 2)


# ============================================================
# 數據庫操作
# ============================================================

def _save_fundamentals(data: dict):
    """保存基本面數據到數據庫"""
    now = datetime.now().strftime("%Y-%m-%d")
    with get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO fundamentals
               (code, name, update_date, pe_ttm, pb, roe, eps, bvps,
                total_mv, circulating_mv, revenue, net_profit,
                gross_margin, net_margin, debt_ratio, dividend_yield, raw_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data.get("code", ""),
                data.get("name", ""),
                data.get("update_date", now),
                data.get("pe_ttm"),
                data.get("pb"),
                data.get("roe"),
                data.get("eps"),
                data.get("bvps"),
                data.get("total_mv"),
                data.get("circulating_mv"),
                data.get("revenue"),
                data.get("net_profit"),
                data.get("gross_margin"),
                data.get("net_margin"),
                data.get("debt_ratio"),
                data.get("dividend_yield"),
                None,
            )
        )
    logger.debug(f"保存基本面: {data.get('code')}")


def _load_fundamentals_from_db(code: str) -> dict:
    """從數據庫讀取基本面（最近一條）"""
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """SELECT * FROM fundamentals 
               WHERE code = ? 
               ORDER BY update_date DESC LIMIT 1""",
            (code,)
        ).fetchone()
    if row:
        return dict(row)
    return {}
