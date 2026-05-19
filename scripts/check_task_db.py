import sqlite3
from pathlib import Path

db = Path(__file__).resolve().parents[1] / "data" / "stock.db"
print("db exists", db.exists(), db)
if not db.exists():
    raise SystemExit(0)
conn = sqlite3.connect(db)
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print("task_log" in tables)
if "task_log" in tables:
    rows = conn.execute(
        "SELECT task_id, length(params_json), status FROM task_log WHERE task_id LIKE ?",
        ("portfolio_47e49cc6%",),
    ).fetchall()
    print("portfolio rows", rows)
