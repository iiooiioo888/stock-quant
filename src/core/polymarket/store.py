"""
Polymarket 本地快照存儲 — SQLite 緩存熱門市場與價格歷史點。

供儀表盤快速讀取與 MCP 離線查詢；同步由 POST /api/polymarket/sync 觸發。
"""
import json
from datetime import datetime

from src.core.db import get_conn
from src.utils.logger import logger

DDL_MARKET_SNAPSHOT = """
CREATE TABLE IF NOT EXISTS polymarket_market_snapshot (
    market_id       TEXT NOT NULL,
    slug            TEXT,
    question        TEXT,
    yes_price       REAL,
    no_price        REAL,
    volume          REAL,
    liquidity       REAL,
    active          INTEGER,
    end_date        TEXT,
    payload_json    TEXT,
    fetched_at      TEXT NOT NULL,
    PRIMARY KEY (market_id)
)
"""

DDL_PRICE_POINT = """
CREATE TABLE IF NOT EXISTS polymarket_price_point (
    token_id        TEXT NOT NULL,
    ts              INTEGER NOT NULL,
    price           REAL NOT NULL,
    interval        TEXT DEFAULT '1d',
    fetched_at      TEXT NOT NULL,
    PRIMARY KEY (token_id, ts, interval)
)
"""


def init_polymarket_tables() -> None:
    """建表與索引（init_db 時調用）。"""
    from src.core.polymarket.alert_store import init_polymarket_alert_tables

    init_polymarket_alert_tables()
    with get_conn() as conn:
        conn.execute(DDL_MARKET_SNAPSHOT)
        conn.execute(DDL_PRICE_POINT)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pm_snapshot_slug "
            "ON polymarket_market_snapshot(slug)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pm_snapshot_fetched "
            "ON polymarket_market_snapshot(fetched_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pm_price_token_ts "
            "ON polymarket_price_point(token_id, ts)"
        )
        conn.commit()
    logger.debug("Polymarket 快照表已就緒")


def upsert_market_snapshots(markets: list[dict]) -> int:
    """批量寫入市場快照，返回寫入條數。"""
    if not markets:
        return 0
    now = datetime.now().isoformat(timespec="seconds")
    rows = []
    for m in markets:
        mid = m.get("market_id") or ""
        if not mid:
            continue
        rows.append((
            mid,
            m.get("slug") or "",
            m.get("question") or "",
            m.get("yes_price", 0),
            m.get("no_price", 0),
            m.get("volume", 0),
            m.get("liquidity", 0),
            1 if m.get("active") else 0,
            m.get("end_date") or "",
            json.dumps(m, ensure_ascii=False),
            now,
        ))
    with get_conn() as conn:
        conn.executemany(
            """
            INSERT INTO polymarket_market_snapshot (
                market_id, slug, question, yes_price, no_price,
                volume, liquidity, active, end_date, payload_json, fetched_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(market_id) DO UPDATE SET
                slug=excluded.slug, question=excluded.question,
                yes_price=excluded.yes_price, no_price=excluded.no_price,
                volume=excluded.volume, liquidity=excluded.liquidity,
                active=excluded.active, end_date=excluded.end_date,
                payload_json=excluded.payload_json, fetched_at=excluded.fetched_at
            """,
            rows,
        )
        conn.commit()
    return len(rows)


def load_market_snapshots(limit: int = 50) -> list[dict]:
    """讀取本地快照（按成交量降序）。"""
    with get_conn() as conn:
        cur = conn.execute(
            """
            SELECT payload_json FROM polymarket_market_snapshot
            ORDER BY volume DESC LIMIT ?
            """,
            (limit,),
        )
        out = []
        for (payload,) in cur.fetchall():
            try:
                out.append(json.loads(payload))
            except json.JSONDecodeError:
                continue
        return out


def upsert_price_points(token_id: str, points: list[dict], interval: str = "1d") -> int:
    """緩存價格歷史點。"""
    if not token_id or not points:
        return 0
    now = datetime.now().isoformat(timespec="seconds")
    rows = [
        (token_id, p["ts"], p["price"], interval, now)
        for p in points
        if p.get("ts") is not None
    ]
    if not rows:
        return 0
    with get_conn() as conn:
        conn.executemany(
            """
            INSERT INTO polymarket_price_point (token_id, ts, price, interval, fetched_at)
            VALUES (?,?,?,?,?)
            ON CONFLICT(token_id, ts, interval) DO UPDATE SET
                price=excluded.price, fetched_at=excluded.fetched_at
            """,
            rows,
        )
        conn.commit()
    return len(rows)
