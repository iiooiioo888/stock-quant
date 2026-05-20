"""
股票庫 — 按總市值排名收錄多市場標的基本資料（默認前 20000）
"""
from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime
from typing import Callable, Optional

import akshare as ak
import pandas as pd

from src.config import settings
from src.core.db import get_conn
from src.utils.logger import logger

DDL_STOCK_UNIVERSE = """
CREATE TABLE IF NOT EXISTS stock_universe (
    code            TEXT NOT NULL,
    market          TEXT NOT NULL,
    name            TEXT,
    exchange        TEXT,
    industry        TEXT,
    list_date       TEXT,
    price           REAL,
    change_pct      REAL,
    total_mv        REAL,
    circulating_mv  REAL,
    pe_ttm          REAL,
    pb              REAL,
    volume          REAL,
    amount          REAL,
    turnover        REAL,
    rank_mv         INTEGER,
    updated_at      TEXT NOT NULL,
    source          TEXT,
    extra_json      TEXT,
    PRIMARY KEY (code, market)
)
"""

# 各數據源列名候選（模糊匹配）
_COL_CANDIDATES = {
    "code": ["代码", "代码", "symbol", "股票代码", "code"],
    "name": ["名称", "名称", "name", "股票名称"],
    "price": ["最新价", "最新", "现价", "price", "close"],
    "change_pct": ["涨跌幅", "涨跌幅", "change_pct", "涨跌幅度"],
    "total_mv": ["总市值", "总市值", "市值", "total_market_cap", "mktcap"],
    "circulating_mv": ["流通市值", "流通市值", "circulating_market_cap"],
    "pe_ttm": ["市盈率-动态", "市盈率", "pe", "pe_ttm"],
    "pb": ["市净率", "市净率", "pb"],
    "volume": ["成交量", "volume"],
    "amount": ["成交额", "amount", "turnover"],
    "turnover": ["换手率", "turnover_rate"],
    "industry": ["所属行业", "行业", "板块", "industry"],
}


def init_stock_universe_table():
    with get_conn() as conn:
        conn.execute(DDL_STOCK_UNIVERSE)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_univ_rank ON stock_universe(rank_mv)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_univ_market ON stock_universe(market)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_univ_mv ON stock_universe(total_mv DESC)"
        )
        conn.commit()
    logger.info("股票庫表 stock_universe 就緒")


def _find_col(df: pd.DataFrame, keys: list[str]) -> Optional[str]:
    cols = list(df.columns)
    for k in keys:
        for c in cols:
            if k in str(c):
                return c
    return None


def _normalize_code(code: str, market: str) -> str:
    code = str(code).strip()
    if market == "a_share" and code.isdigit():
        return code.zfill(6)
    return code


def _to_float(val, default=0.0) -> float:
    try:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return default
        return float(val)
    except (TypeError, ValueError):
        return default


def _mv_to_yi(raw: float, market: str) -> float:
    """統一為億元量級便於排序（A/HK 原為元；美股原為美元，僅作相對排序）"""
    if raw <= 0:
        return 0.0
    if market == "us_stock":
        # 美元市值 → 粗略按 7 折算人民幣億元
        return raw / 1e8 * 7.0
    return raw / 1e8


def _parse_spot_df(
    df: pd.DataFrame,
    market: str,
    exchange: str,
    source: str,
) -> list[dict]:
    if df is None or df.empty:
        return []

    code_col = _find_col(df, _COL_CANDIDATES["code"])
    name_col = _find_col(df, _COL_CANDIDATES["name"])
    if not code_col:
        return []

    mv_col = _find_col(df, _COL_CANDIDATES["total_mv"])
    rows = []
    for _, row in df.iterrows():
        code = _normalize_code(row.get(code_col, ""), market)
        if not code or code in ("nan", "None"):
            continue
        name = str(row.get(name_col, "")) if name_col else ""
        raw_mv = _to_float(row.get(mv_col)) if mv_col else 0.0
        total_mv_yi = _mv_to_yi(raw_mv, market)

        item = {
            "code": code,
            "market": market,
            "name": name,
            "exchange": exchange,
            "industry": str(row.get(_find_col(df, _COL_CANDIDATES["industry"]), "") or "")
            if _find_col(df, _COL_CANDIDATES["industry"])
            else "",
            "list_date": "",
            "price": _to_float(row.get(_find_col(df, _COL_CANDIDATES["price"]))),
            "change_pct": _to_float(row.get(_find_col(df, _COL_CANDIDATES["change_pct"]))),
            "total_mv": round(total_mv_yi, 4),
            "circulating_mv": round(
                _mv_to_yi(
                    _to_float(row.get(_find_col(df, _COL_CANDIDATES["circulating_mv"]))),
                    market,
                ),
                4,
            ),
            "pe_ttm": _to_float(row.get(_find_col(df, _COL_CANDIDATES["pe_ttm"]))),
            "pb": _to_float(row.get(_find_col(df, _COL_CANDIDATES["pb"]))),
            "volume": _to_float(row.get(_find_col(df, _COL_CANDIDATES["volume"]))),
            "amount": _to_float(row.get(_find_col(df, _COL_CANDIDATES["amount"]))),
            "turnover": _to_float(row.get(_find_col(df, _COL_CANDIDATES["turnover"]))),
            "source": source,
        }
        rows.append(item)
    return rows


def _fetch_with_retry(fetcher: Callable[[], pd.DataFrame], label: str, retries: int = 2) -> pd.DataFrame:
    last_err = None
    for i in range(retries + 1):
        try:
            df = fetcher()
            if df is not None and not df.empty:
                logger.info(f"股票庫 {label}: {len(df)} 條")
                return df
        except Exception as e:
            last_err = e
            logger.warning(f"股票庫 {label} 第 {i + 1} 次失敗: {e}")
            time.sleep(1.5 * (i + 1))
    if last_err:
        logger.error(f"股票庫 {label} 放棄: {last_err}")
    return pd.DataFrame()


def fetch_all_market_basics() -> list[dict]:
    """從多市場實時行情拉取基本資料並合併。"""
    batches: list[tuple[str, str, str, Callable]] = [
        ("a_share", "CN", "eastmoney_a", lambda: ak.stock_zh_a_spot_em()),
        ("hk_stock", "HK", "eastmoney_hk", lambda: ak.stock_hk_spot_em()),
        ("us_stock", "US", "eastmoney_us", lambda: ak.stock_us_spot_em()),
    ]

    merged: list[dict] = []
    for market, exchange, source, fetcher in batches:
        df = _fetch_with_retry(fetcher, market)
        merged.extend(_parse_spot_df(df, market, exchange, source))
        time.sleep(0.8)

    # 無市值的標的 total_mv=0，排序時靠後
    merged.sort(key=lambda x: x.get("total_mv") or 0, reverse=True)
    return merged


def _fallback_a_share_codes() -> list[dict]:
    """東財全量失敗時：僅代碼+名稱（無市值）。"""
    try:
        df = ak.stock_info_a_code_name()
        if df.empty:
            return []
        out = []
        for _, row in df.iterrows():
            code = _normalize_code(row.get("code", ""), "a_share")
            if not code:
                continue
            out.append({
                "code": code,
                "market": "a_share",
                "name": str(row.get("name", "")),
                "exchange": "CN",
                "industry": "",
                "list_date": "",
                "price": 0,
                "change_pct": 0,
                "total_mv": 0,
                "circulating_mv": 0,
                "pe_ttm": 0,
                "pb": 0,
                "volume": 0,
                "amount": 0,
                "turnover": 0,
                "source": "akshare_code_name",
            })
        logger.info(f"股票庫降級：A 股代碼表 {len(out)} 條（無市值）")
        return out
    except Exception as e:
        logger.error(f"股票庫降級失敗: {e}")
        return []


def sync_stock_universe(
    max_count: int | None = None,
    task_id: str | None = None,
) -> dict:
    """
    同步股票庫：按市值取前 max_count（默認 settings.stock_universe_max_count）。
    """
    from src.core.task_manager import update_task, update_task_meta, is_task_cancelled

    max_count = max_count or settings.stock_universe_max_count
    init_stock_universe_table()
    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if task_id:
        update_task_meta(task_id, message="正在拉取多市場行情…")
        update_task(task_id, progress=5)

    all_rows = fetch_all_market_basics()
    if not all_rows:
        all_rows = _fallback_a_share_codes()

    if task_id and is_task_cancelled(task_id):
        raise RuntimeError("任務已取消")

    # 去重 (code, market)
    seen: set[tuple[str, str]] = set()
    deduped = []
    for r in all_rows:
        key = (r["code"], r["market"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)

    deduped.sort(key=lambda x: x.get("total_mv") or 0, reverse=True)
    top = deduped[:max_count]

    if task_id:
        update_task(task_id, progress=60)
        update_task_meta(
            task_id,
            message=f"寫入股票庫 {len(top)} / {len(deduped)} 條",
        )

    with get_conn() as conn:
        conn.execute("DELETE FROM stock_universe")
        records = []
        for rank, row in enumerate(top, start=1):
            records.append((
                row["code"],
                row["market"],
                row.get("name"),
                row.get("exchange"),
                row.get("industry") or None,
                row.get("list_date") or None,
                row.get("price"),
                row.get("change_pct"),
                row.get("total_mv"),
                row.get("circulating_mv"),
                row.get("pe_ttm"),
                row.get("pb"),
                row.get("volume"),
                row.get("amount"),
                row.get("turnover"),
                rank,
                updated_at,
                row.get("source"),
                json.dumps({"raw_rank_pool": len(deduped)}, ensure_ascii=False),
            ))

        conn.executemany(
            """INSERT OR REPLACE INTO stock_universe (
                code, market, name, exchange, industry, list_date,
                price, change_pct, total_mv, circulating_mv, pe_ttm, pb,
                volume, amount, turnover, rank_mv, updated_at, source, extra_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            records,
        )
        conn.commit()

    by_market: dict[str, int] = {}
    for r in top:
        by_market[r["market"]] = by_market.get(r["market"], 0) + 1

    result = {
        "success": True,
        "total_pool": len(deduped),
        "saved": len(top),
        "max_count": max_count,
        "updated_at": updated_at,
        "by_market": by_market,
        "note": (
            "已按總市值排序取前 N；A 股約 5000+，需港股/美股湊滿更大池。"
            if len(deduped) < max_count
            else None
        ),
    }
    logger.info(
        f"股票庫同步完成: 入庫 {len(top)} 條（池內 {len(deduped)}，上限 {max_count}）"
    )

    if task_id:
        update_task(task_id, progress=100, result=result)
        update_task_meta(task_id, message="股票庫同步完成")

    return result


def query_stock_universe(
    market: str | None = None,
    keyword: str | None = None,
    limit: int = 100,
    offset: int = 0,
    order_by: str = "rank_mv",
) -> tuple[list[dict], int]:
    """查詢股票庫（分頁）。"""
    init_stock_universe_table()
    allowed_order = {"rank_mv", "total_mv", "change_pct", "code", "name"}
    if order_by not in allowed_order:
        order_by = "rank_mv"

    conditions = ["1=1"]
    params: list = []
    if market and market != "all":
        conditions.append("market = ?")
        params.append(market)
    if keyword:
        conditions.append("(code LIKE ? OR name LIKE ?)")
        kw = f"%{keyword.strip()}%"
        params.extend([kw, kw])

    where = " AND ".join(conditions)
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        total = conn.execute(
            f"SELECT COUNT(*) AS c FROM stock_universe WHERE {where}",
            params,
        ).fetchone()["c"]
        rows = conn.execute(
            f"""SELECT * FROM stock_universe WHERE {where}
                ORDER BY {order_by} ASC
                LIMIT ? OFFSET ?""",
            params + [limit, offset],
        ).fetchall()
    return [dict(r) for r in rows], int(total)


def get_universe_stats() -> dict:
    init_stock_universe_table()
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        total = conn.execute("SELECT COUNT(*) AS c FROM stock_universe").fetchone()["c"]
        if total == 0:
            return {"total": 0, "markets": {}, "updated_at": None}
        updated = conn.execute(
            "SELECT MAX(updated_at) AS u FROM stock_universe"
        ).fetchone()["u"]
        markets = conn.execute(
            """SELECT market, COUNT(*) AS cnt,
                      SUM(CASE WHEN total_mv > 0 THEN 1 ELSE 0 END) AS with_mv
               FROM stock_universe GROUP BY market"""
        ).fetchall()
    return {
        "total": total,
        "updated_at": updated,
        "markets": {r["market"]: {"count": r["cnt"], "with_mv": r["with_mv"]} for r in markets},
    }


def load_universe_codes(market: str = "a_share", limit: int | None = None) -> list[str]:
    """供下載/篩選使用的代碼列表。"""
    rows, _ = query_stock_universe(market=market, limit=limit or 50000, offset=0)
    return [r["code"] for r in rows if r.get("code")]
