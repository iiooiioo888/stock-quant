"""
基本面數據模塊 — PE、PB、ROE、市值、營收淨利等（akshare 多源降級 + SQLite 緩存）
"""
import sqlite3
import time
from datetime import datetime

import akshare as ak
import pandas as pd

from src.core.data_pipeline import is_stale
from src.core.db import get_conn
from src.utils.logger import logger

_RATE_LIMIT = 0.45


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
    """向後兼容；表結構由 src.core.database.schema 集中管理。"""
    pass


# ============================================================
# 基本面數據獲取
# ============================================================

def _normalize_code(code: str) -> str:
    code = str(code).strip()
    if code.isdigit() and len(code) < 6:
        return code.zfill(6)
    return code


def load_fundamentals_db(code: str) -> dict:
    """讀取 fundamentals 表最新一條（不做過期判斷）。"""
    return _load_fundamentals_from_db(_normalize_code(code))


def fundamentals_row_to_fin(row: dict) -> dict:
    """DB / 在線行 → 詳情頁 financials 結構。"""
    if not row:
        return {}
    code = row.get("code", "")
    fin: dict = {"code": code, "has_data": False, "source": row.get("source", "fundamentals_db")}
    for key in (
        "pe_ttm", "pb", "ps_ttm", "roe", "eps", "bvps", "total_mv", "circulating_mv",
        "gross_margin", "net_margin", "debt_ratio", "dividend_yield",
        "revenue", "net_profit", "revenue_yoy", "profit_yoy",
        "update_date", "name",
    ):
        val = row.get(key)
        if val is not None and val != "":
            fin[key] = val
    fin["has_data"] = any(
        fin.get(k) is not None
        for k in fin
        if k not in ("code", "has_data", "source", "name")
    )
    return fin if fin["has_data"] else {}


def get_fundamentals(code: str, max_age_days: int = 7, force_refresh: bool = False) -> dict:
    """
    獲取單只股票基本面：庫內未過期則命中，否則 akshare 拉取並寫庫。
    """
    code = _normalize_code(code)
    if not code.isdigit() or len(code) != 6:
        return {}

    if not force_refresh:
        cached = load_fundamentals_db(code)
        if cached and not is_stale(cached.get("update_date"), max_age_days):
            cached.setdefault("source", "fundamentals_db")
            _record_financials("db_hit")
            return cached

    online = fetch_fundamentals_online(code)
    if online:
        _record_financials("online_fetch")
        return online

    cached = load_fundamentals_db(code)
    if cached:
        cached.setdefault("source", "fundamentals_db_stale")
        _record_financials("stale_fallback")
        return cached
    _record_financials("empty")
    return {}


def _record_financials(outcome: str) -> None:
    try:
        from src.core.pipeline_observability import record_financials

        record_financials(outcome)
    except Exception:
        pass


def fetch_fundamentals_online(code: str) -> dict:
    """從 akshare 多接口拉取財報並持久化。"""
    code = _normalize_code(code)
    result: dict = {}

    for fetcher in (_fetch_analysis_indicator, _fetch_abstract_em):
        try:
            partial = fetcher(code)
            if partial:
                result.update({k: v for k, v in partial.items() if v is not None and v != ""})
        except Exception as e:
            logger.debug(f"{code} 財報接口 {fetcher.__name__} 失敗: {e}")

    if not result:
        logger.warning(f"{code}: 無基本面數據（所有財報接口）")
        return {}

    _enrich_market_cap_em(code, result)
    _enrich_revenue_profit(code, result)

    result["code"] = code
    result.setdefault("update_date", datetime.now().strftime("%Y-%m-%d"))
    result["source"] = "akshare"
    _save_fundamentals(result)
    _rate_sleep()
    return result


def _fetch_analysis_indicator(code: str) -> dict:
    df = ak.stock_financial_analysis_indicator(symbol=code)
    if df is None or df.empty:
        return {}
    latest = df.iloc[0]
    ud = latest.get("日期") or latest.get("报告期") or latest.get("report_date")
    return {
        "name": "",
        "update_date": str(ud)[:10] if ud is not None else datetime.now().strftime("%Y-%m-%d"),
        "pe_ttm": _safe_float(latest, ["市盈率(TTM)", "市盈率", "pe_ttm"]),
        "pb": _safe_float(latest, ["市净率", "市淨率", "pb"]),
        "roe": _safe_float(latest, ["净资产收益率(%)", "净资产收益率", "加权净资产收益率(%)", "roe"]),
        "eps": _safe_float(latest, ["基本每股收益(元)", "基本每股收益", "eps"]),
        "bvps": _safe_float(latest, ["每股净资产(元)", "每股净资产", "bvps"]),
        "gross_margin": _safe_float(latest, ["销售毛利率(%)", "毛利率(%)", "gross_margin"]),
        "net_margin": _safe_float(latest, ["销售净利率(%)", "净利率(%)", "net_margin"]),
        "debt_ratio": _safe_float(latest, ["资产负债率(%)", "资产负债率", "debt_ratio"]),
        "revenue": _safe_float(latest, ["营业总收入(元)", "营业总收入", "营业收入", "revenue"], default=0),
        "net_profit": _safe_float(latest, ["净利润(元)", "净利润", "net_profit"], default=0),
        "dividend_yield": _safe_float(latest, ["股息率(%)", "股息率", "dividend_yield"], default=0),
    }


def _fetch_abstract_em(code: str) -> dict:
    """東財主要財務指標摘要（補齊分析指標接口缺失欄位）。"""
    fn = getattr(ak, "stock_financial_abstract", None)
    if fn is None:
        return {}
    df = fn(symbol=code)
    if df is None or df.empty:
        return {}
    row = df.iloc[0]
    out: dict = {}
    for col in df.columns:
        c = str(col)
        val = row[col]
        if pd.isna(val):
            continue
        if "每股净资产" in c or "每股淨資產" in c:
            out["bvps"] = float(val)
        elif "净资产收益率" in c or "淨資產收益率" in c:
            out["roe"] = float(val)
        elif "资产负债率" in c:
            out["debt_ratio"] = float(val)
        elif "营业总收入" in c or "營業總收入" in c:
            out["revenue"] = _to_yi(float(val))
        elif col == "净利润" or "净利润" in c:
            out["net_profit"] = _to_yi(float(val))
    if "报告期" in df.columns:
        out["update_date"] = str(row.get("报告期", ""))[:10]
    return out


def _enrich_market_cap_em(code: str, result: dict) -> None:
    try:
        _rate_sleep()
        spot_df = ak.stock_individual_info_em(symbol=code)
        if spot_df is None or spot_df.empty:
            return
        for _, row in spot_df.iterrows():
            item = str(row.get("item", ""))
            value = row.get("value", 0)
            if "總市值" in item or "总市值" in item:
                result["total_mv"] = _to_yi(float(value or 0))
            elif "流通市值" in item:
                result["circulating_mv"] = _to_yi(float(value or 0))
            elif "股票簡稱" in item or "名稱" in item or "股票简称" in item:
                result["name"] = str(value)
            elif "股息率" in item and not result.get("dividend_yield"):
                try:
                    result["dividend_yield"] = float(str(value).replace("%", "") or 0)
                except (TypeError, ValueError):
                    pass
    except Exception as e:
        logger.debug(f"{code} 東財個股信息: {e}")


def _enrich_revenue_profit(code: str, result: dict) -> None:
    """利潤表接口補營收 / 淨利（億）。"""
    if result.get("revenue") and result.get("net_profit"):
        return
    market = "SH" if code.startswith(("5", "6", "9")) else "SZ"
    sym = f"{market}{code}"
    fn = getattr(ak, "stock_profit_sheet_by_report_em", None)
    if fn is None:
        return
    try:
        _rate_sleep()
        df = fn(symbol=sym)
        if df is None or df.empty:
            return
        latest = df.iloc[0]
        if not result.get("revenue"):
            rev = _safe_float(latest, ["营业总收入", "營業總收入", "营业收入"], default=0)
            if rev:
                result["revenue"] = _to_yi(rev) if rev > 1e6 else rev
        if not result.get("net_profit"):
            npf = _safe_float(latest, ["净利润", "淨利潤", "归属于母公司所有者的净利润"], default=0)
            if npf:
                result["net_profit"] = _to_yi(npf) if npf > 1e6 else npf
        rd = latest.get("报告日") or latest.get("报告期")
        if rd and not result.get("update_date"):
            result["update_date"] = str(rd)[:10]
    except Exception as e:
        logger.debug(f"{code} 利潤表: {e}")


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
    code = _normalize_code(code)
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """SELECT * FROM fundamentals
               WHERE code = ?
               ORDER BY update_date DESC LIMIT 1""",
            (code,),
        ).fetchone()
    if row:
        d = dict(row)
        d.pop("raw_json", None)
        return d
    return {}
