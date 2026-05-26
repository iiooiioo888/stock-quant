"""
Polymarket 預警規則與概率狀態 — SQLite 持久化。

規則驅動 yes 機率閾值與變動幅度預警；狀態表記錄上次 yes_price 供 prob_change 判斷。
"""
import sqlite3
from datetime import datetime
from typing import Optional

from src.core.db import get_conn

DDL_ALERT_RULES = """
CREATE TABLE IF NOT EXISTS polymarket_alert_rules (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    market_key      TEXT NOT NULL,
    name            TEXT,
    question        TEXT,
    enabled         INTEGER NOT NULL DEFAULT 1,
    yes_above       REAL,
    yes_below       REAL,
    prob_change_pct REAL,
    notes           TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    UNIQUE(market_key)
)
"""

DDL_PROB_STATE = """
CREATE TABLE IF NOT EXISTS polymarket_prob_state (
    market_key      TEXT PRIMARY KEY,
    yes_price       REAL NOT NULL,
    no_price        REAL,
    checked_at      TEXT NOT NULL
)
"""


def init_polymarket_alert_tables() -> None:
    """向後兼容；表結構由 src.core.database.schema 集中管理。"""
    pass


def list_alert_rules(enabled_only: bool = False) -> list[dict]:
    """列出全部預警規則。"""
    sql = "SELECT * FROM polymarket_alert_rules"
    if enabled_only:
        sql += " WHERE enabled = 1"
    sql += " ORDER BY id ASC"
    with get_conn() as conn:
        conn.row_factory = _row_factory
        rows = conn.execute(sql).fetchall()
    return [_rule_row_to_dict(r) for r in rows]


def get_alert_rule(rule_id: int) -> Optional[dict]:
    with get_conn() as conn:
        conn.row_factory = _row_factory
        row = conn.execute(
            "SELECT * FROM polymarket_alert_rules WHERE id = ?", (rule_id,),
        ).fetchone()
    return _rule_row_to_dict(row) if row else None


def get_alert_rule_by_market_key(market_key: str) -> Optional[dict]:
    key = (market_key or "").strip()
    if not key:
        return None
    with get_conn() as conn:
        conn.row_factory = _row_factory
        row = conn.execute(
            "SELECT * FROM polymarket_alert_rules WHERE market_key = ?", (key,),
        ).fetchone()
    return _rule_row_to_dict(row) if row else None


def upsert_alert_rule(data: dict) -> dict:
    """新增或按 market_key 更新規則。"""
    key = (data.get("market_key") or "").strip()
    if not key:
        raise ValueError("market_key 必填（slug 或 market_id）")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    existing = get_alert_rule_by_market_key(key)
    fields = {
        "name": data.get("name") or "",
        "question": data.get("question") or "",
        "enabled": 1 if data.get("enabled", True) else 0,
        "yes_above": _opt_float(data.get("yes_above")),
        "yes_below": _opt_float(data.get("yes_below")),
        "prob_change_pct": _opt_float(data.get("prob_change_pct")),
        "notes": data.get("notes") or "",
        "updated_at": now,
    }
    with get_conn() as conn:
        if existing:
            conn.execute(
                """UPDATE polymarket_alert_rules SET
                   name=?, question=?, enabled=?, yes_above=?, yes_below=?,
                   prob_change_pct=?, notes=?, updated_at=?
                   WHERE market_key=?""",
                (
                    fields["name"], fields["question"], fields["enabled"],
                    fields["yes_above"], fields["yes_below"],
                    fields["prob_change_pct"], fields["notes"], fields["updated_at"],
                    key,
                ),
            )
            rule_id = existing["id"]
        else:
            cur = conn.execute(
                """INSERT INTO polymarket_alert_rules
                   (market_key, name, question, enabled, yes_above, yes_below,
                    prob_change_pct, notes, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    key, fields["name"], fields["question"], fields["enabled"],
                    fields["yes_above"], fields["yes_below"],
                    fields["prob_change_pct"], fields["notes"], now, now,
                ),
            )
            rule_id = cur.lastrowid
        conn.commit()
    return get_alert_rule(rule_id)


def delete_alert_rule(rule_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM polymarket_alert_rules WHERE id = ?", (rule_id,),
        )
        conn.commit()
        return cur.rowcount > 0


def load_prob_state(market_key: str) -> Optional[dict]:
    with get_conn() as conn:
        conn.row_factory = _row_factory
        row = conn.execute(
            "SELECT * FROM polymarket_prob_state WHERE market_key = ?",
            (market_key,),
        ).fetchone()
    return dict(row) if row else None


def save_prob_state(market_key: str, yes_price: float, no_price: float = None) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO polymarket_prob_state
               (market_key, yes_price, no_price, checked_at)
               VALUES (?, ?, ?, ?)""",
            (market_key, yes_price, no_price, now),
        )
        conn.commit()


def _opt_float(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _row_factory(cursor, row):
    return sqlite3.Row(cursor, row)


def _rule_row_to_dict(row) -> Optional[dict]:
    if not row:
        return None
    d = dict(row)
    d["enabled"] = bool(d.get("enabled"))
    return d
