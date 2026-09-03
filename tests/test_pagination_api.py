"""alerts offset/total 與 stocks 遊標分頁（不依賴完整 FastAPI app）。"""

import os
import tempfile
import uuid

import pytest


@pytest.fixture
def isolated_db(monkeypatch):
    from src.config import settings
    from src.core.database.connection import reset_thread_connection

    reset_thread_connection()
    path = os.path.join(tempfile.gettempdir(), f"test_page_{uuid.uuid4().hex}.db")
    monkeypatch.setenv("SQ_DB_PATH", path)
    settings.db_path = path
    reset_thread_connection()
    yield path
    reset_thread_connection()
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


def test_alert_logs_offset_and_count(isolated_db):
    from src.core.database import init_database
    from src.core.db import count_alert_logs, get_alert_logs, get_conn

    init_database()
    with get_conn() as conn:
        for i in range(5):
            conn.execute(
                "INSERT INTO alert_log(code, rule_type, message, price, triggered_at) VALUES (?,?,?,?,?)",
                ("000001", "price_above", f"m{i}", 10 + i, f"2026-01-0{i+1} 00:00:00"),
            )
    total = count_alert_logs()
    assert total == 5
    page = get_alert_logs(limit=2, offset=0)
    assert len(page) == 2
    page2 = get_alert_logs(limit=2, offset=2)
    assert len(page2) == 2
    ids = {r["id"] for r in page} & {r["id"] for r in page2}
    assert not ids


def test_stock_universe_cursor(isolated_db):
    from src.core.database import init_database
    from src.core.db import get_conn
    from src.core.stock_universe import query_stock_universe

    init_database()
    with get_conn() as conn:
        for i, code in enumerate(["000001", "000002", "600000", "600519"]):
            conn.execute(
                """INSERT INTO stock_universe(code, name, market, rank_mv, total_mv, updated_at)
                   VALUES (?,?,?,?,?,?)""",
                (code, code, "a_share", i + 1, 1e10 - i, "2026-01-01"),
            )
    rows, total = query_stock_universe(limit=2, offset=0, order_by="rank_mv")
    assert total == 4
    assert len(rows) == 2
    last = rows[-1]
    cursor = f"{last['rank_mv']}|{last['code']}"
    more, total2 = query_stock_universe(limit=2, cursor=cursor, order_by="rank_mv")
    assert total2 == 4
    assert {r["code"] for r in rows}.isdisjoint({r["code"] for r in more})
    assert len(more) == 2
