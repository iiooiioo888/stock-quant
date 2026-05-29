"""P6: SQLite → PostgreSQL 數據遷移工具。

Usage:
  SQ_DATABASE_URL=postgresql://user:pass@host:5432/db python scripts/migrate_sqlite_to_pg.py
"""
import sqlite3
import os
import sys

sys.path.insert(0, ".")

from src.core.database.models import Base
from src.core.database.postgres_config import get_database_url, is_postgres
from src.utils.logger import logger


def migrate():
    if not is_postgres():
        print("ERROR: SQ_DATABASE_URL must point to PostgreSQL")
        print("Example: SQ_DATABASE_URL=postgresql://user:pass@localhost:5432/stockquant")
        return

    # 1. Create all tables via ORM
    from sqlalchemy import create_engine
    url = get_database_url()
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    print(f"[OK] Created tables on {url.split('@')[-1] if '@' in url else url}")

    # 2. Read from SQLite
    db_path = os.environ.get("SQ_DB_PATH", "data/stock.db")
    if not os.path.exists(db_path):
        print(f"ERROR: SQLite not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 3. Get list of tables from SQLite
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in cursor.fetchall()]
    print(f"[INFO] Found {len(tables)} tables in SQLite")

    # 4. Migrate each table
    from sqlalchemy import text
    pg_engine = create_engine(url)
    total_rows = 0

    for table_name in tables:
        if table_name == "sqlite_sequence":
            continue
        cursor.execute(f'SELECT * FROM "{table_name}"')
        rows = cursor.fetchall()
        if not rows:
            print(f"  {table_name}: empty, skip")
            continue

        columns = [desc[0] for desc in cursor.description]
        placeholders = ", ".join([f":{c}" for c in columns])
        col_names = ", ".join([f'"{c}"' for c in columns])
        insert_sql = f'INSERT INTO "{table_name}" ({col_names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'

        with pg_engine.begin() as pg_conn:
            for row in rows:
                data = {columns[i]: row[i] for i in range(len(columns))}
                pg_conn.execute(text(insert_sql), data)

        print(f"  {table_name}: {len(rows)} rows migrated")
        total_rows += len(rows)

    conn.close()
    print(f"\n[DONE] Total {total_rows} rows migrated to PostgreSQL")


if __name__ == "__main__":
    migrate()