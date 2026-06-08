"""
資金流向數據模塊 — 個股、大盤、北向資金（多源降級）

優先：東方財富 HTTP 直連 → AKShare → 本地庫緩存
"""

import sqlite3
import time

import akshare as ak

from src.core.db import get_conn
from src.utils.logger import logger

_RATE_LIMIT = 0.5

DDL_CAPITAL_FLOW = """
CREATE TABLE IF NOT EXISTS capital_flow (
    code        TEXT NOT NULL,
    date        TEXT NOT NULL,
    flow_type   TEXT NOT NULL,
    main_net    REAL,
    super_net   REAL,
    big_net     REAL,
    mid_net     REAL,
    small_net   REAL,
    close       REAL,
    change_pct  REAL,
    raw_json    TEXT,
    PRIMARY KEY (code, date, flow_type)
)
"""


def _rate_sleep():
    time.sleep(_RATE_LIMIT)


def init_capital_flow_table():
    """向後兼容；表結構由 src.core.database.schema 集中管理。"""
    pass


def _save_capital_flow(records: list[dict], flow_type: str):
    if not records:
        return
    init_capital_flow_table()
    db_records = [
        (
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
            None,
        )
        for r in records
    ]
    with get_conn() as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO capital_flow
               (code, date, flow_type, main_net, super_net, big_net, mid_net, small_net,
                close, change_pct, raw_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            db_records,
        )
        conn.commit()


def load_capital_flow_by_type(
    flow_type: str, code: str = None, days: int = 30
) -> list[dict]:
    """從本地庫讀取資金流向緩存"""
    init_capital_flow_table()
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        if code:
            rows = conn.execute(
                """SELECT * FROM capital_flow
                   WHERE flow_type = ? AND code = ?
                   ORDER BY date DESC LIMIT ?""",
                (flow_type, code, days),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM capital_flow
                   WHERE flow_type = ?
                   ORDER BY date DESC LIMIT ?""",
                (flow_type, days * 3),
            ).fetchall()
    out = []
    for r in rows:
        out.append(
            {
                "code": r["code"],
                "date": r["date"],
                "close": r["close"],
                "change_pct": r["change_pct"],
                "main_net": r["main_net"],
                "super_net": r["super_net"],
                "big_net": r["big_net"],
                "mid_net": r["mid_net"],
                "small_net": r["small_net"],
                "source": "local_db",
            }
        )
    out.sort(key=lambda x: x["date"])
    return out


def get_capital_flow(code: str, days: int = 30) -> list[dict]:
    """個股資金流向"""
    try:
        df = ak.stock_individual_fund_flow(
            stock=code, market="sh" if code.startswith("6") else "sz"
        )
        if df.empty:
            return load_capital_flow_by_type("individual", code, days)

        col_map = {
            "日期": "date",
            "收盘价": "close",
            "涨跌幅": "change_pct",
            "主力净流入-净额": "main_net",
            "超大单净流入-净额": "super_net",
            "大单净流入-净额": "big_net",
            "中单净流入-净额": "mid_net",
            "小单净流入-净额": "small_net",
        }
        rename_map = {}
        for old_name, new_name in col_map.items():
            for col in df.columns:
                if old_name in col or col == old_name:
                    rename_map[col] = new_name
                    break
        df = df.rename(columns=rename_map)
        if len(df) > days:
            df = df.tail(days)

        result = []
        for _, row in df.iterrows():
            result.append(
                {
                    "code": code,
                    "date": str(row.get("date", "")),
                    "close": float(row.get("close", 0) or 0),
                    "change_pct": float(row.get("change_pct", 0) or 0),
                    "main_net": float(row.get("main_net", 0) or 0),
                    "super_net": float(row.get("super_net", 0) or 0),
                    "big_net": float(row.get("big_net", 0) or 0),
                    "mid_net": float(row.get("mid_net", 0) or 0),
                    "small_net": float(row.get("small_net", 0) or 0),
                    "source": "akshare",
                }
            )
        _save_capital_flow(result, "individual")
        _rate_sleep()
        return result
    except Exception as e:
        logger.error(f"獲取 {code} 資金流向失敗: {e}")
        cached = load_capital_flow_by_type("individual", code, days)
        return cached


def get_market_capital_flow() -> list[dict]:
    """大盤資金流向（多源）"""
    from src.core.eastmoney_flow import (
        fetch_market_fund_flow,
        fetch_market_fund_flow_akshare,
    )

    for fetcher in (fetch_market_fund_flow, fetch_market_fund_flow_akshare):
        try:
            result = fetcher() or []
        except Exception as e:
            logger.debug(f"大盤資金 {fetcher.__name__} 失敗: {e}")
            result = []
        if result:
            _save_capital_flow(result, "market")
            _rate_sleep()
            return result

    cached = load_capital_flow_by_type("market", "market", days=120)
    if cached:
        logger.info(f"使用本地大盤資金緩存: {len(cached)} 條")
    else:
        logger.warning("大盤資金流向全部數據源失敗")
    return cached


def aggregate_north_flow_daily(flows: list[dict]) -> list[dict]:
    """將滬股通/深股通逐條記錄按日期合併，供表格與圖表使用。"""
    by_date: dict[str, dict] = {}
    for f in flows or []:
        date = str(f.get("date") or "")[:10]
        if not date:
            continue
        row = by_date.setdefault(
            date,
            {"date": date, "sh_net": 0.0, "sz_net": 0.0, "total_net": 0.0},
        )
        code = str(f.get("code") or "")
        if f.get("sh_net") is not None:
            row["sh_net"] += float(f.get("sh_net") or 0)
        if f.get("sz_net") is not None:
            row["sz_net"] += float(f.get("sz_net") or 0)
        else:
            net = float(f.get("main_net") or f.get("total_net") or 0)
            if "沪" in code:
                row["sh_net"] += net
            elif "深" in code:
                row["sz_net"] += net
        row["total_net"] = row["sh_net"] + row["sz_net"]
    return sorted(by_date.values(), key=lambda x: x["date"])


def get_north_flow(days: int = 30) -> list[dict]:
    """北向資金（多源）"""
    from src.core.eastmoney_flow import fetch_north_flow, fetch_north_flow_akshare

    for fetcher in (
        lambda: fetch_north_flow(days),
        lambda: fetch_north_flow_akshare(days),
    ):
        try:
            result = fetcher() or []
        except Exception as e:
            logger.debug(f"北向資金拉取失敗: {e}")
            result = []
        if result:
            _save_capital_flow(result, "north")
            _rate_sleep()
            return result

    cached = load_capital_flow_by_type("north", days=days * 2)
    if cached:
        logger.info(f"使用本地北向資金緩存: {len(cached)} 條")
    else:
        logger.warning("北向資金全部數據源失敗")
    return cached


def load_capital_flow(code: str, days: int = 30) -> list[dict]:
    return load_capital_flow_by_type("individual", code, days)
