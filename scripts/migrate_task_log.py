"""為 task_log 添加 params_json 欄位"""
import sqlite3
from pathlib import Path

db = Path(__file__).resolve().parents[1] / "data" / "stock.db"
conn = sqlite3.connect(db)
cols = [r[1] for r in conn.execute("PRAGMA table_info(task_log)").fetchall()]
print("columns:", cols)
if "params_json" not in cols:
    conn.execute("ALTER TABLE task_log ADD COLUMN params_json TEXT")
    conn.commit()
    print("added params_json")
else:
    print("params_json already exists")
conn.close()
