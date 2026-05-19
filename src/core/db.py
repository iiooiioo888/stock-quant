"""
數據庫操作層 — SQLite 讀寫封裝（含 LRU 緩存 + 線程本地連接池）
"""
import sqlite3
import os
import threading
import pandas as pd
from functools import lru_cache
from contextlib import contextmanager
from src.config import settings
from src.utils.logger import logger


# ============================================================
# 線程本地連接池（避免每次請求都 connect/close）
# ============================================================
_thread_local = threading.local()


def _get_thread_conn() -> sqlite3.Connection:
    """獲取當前線程的數據庫連接（複用）"""
    conn = getattr(_thread_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(settings.db_path, check_same_thread=False, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-8000")  # 8MB 緩存
        conn.execute("PRAGMA busy_timeout=5000")  # 5 秒等待鎖釋放
        _thread_local.conn = conn
    return conn


@contextmanager
def get_conn():
    """獲取數據庫連接（上下文管理器，使用線程本地連接池）"""
    conn = _get_thread_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# ============================================================
# LRU 緩存層
# ============================================================

@lru_cache(maxsize=64)
def _load_daily_kline_cached(code: str, start_date: str = None, end_date: str = None) -> tuple:
    """緩存版本 — 返回 tuple 以便 hashable"""
    sql = "SELECT * FROM daily_kline WHERE code = ?"
    params = [code]

    if start_date:
        sql += " AND date >= ?"
        params.append(start_date)
    if end_date:
        sql += " AND date <= ?"
        params.append(end_date)

    sql += " ORDER BY date"

    with get_conn() as conn:
        df = pd.read_sql(sql, conn, params=params)

    if df.empty:
        return ((), ())
    return (tuple(df.itertuples(index=False, name=None)), tuple(df.columns))


def clear_data_cache():
    """清除數據緩存"""
    _load_daily_kline_cached.cache_clear()
    try:
        _load_minute_kline_cached.cache_clear()
    except Exception:
        pass
    logger.info("數據緩存已清除")


DDL_DAILY = """
CREATE TABLE IF NOT EXISTS daily_kline (
    code        TEXT    NOT NULL,
    date        TEXT    NOT NULL,
    open        REAL,
    high        REAL,
    low         REAL,
    close       REAL,
    volume      REAL,
    amount      REAL,
    turnover    REAL,
    market      TEXT    DEFAULT 'a_share',
    PRIMARY KEY (code, date)
)
"""

DDL_REALTIME = """
CREATE TABLE IF NOT EXISTS realtime_snapshot (
    code        TEXT    PRIMARY KEY,
    name        TEXT,
    price       REAL,
    change_pct  REAL,
    volume      REAL,
    amount      REAL,
    high        REAL,
    low         REAL,
    open        REAL,
    prev_close  REAL,
    updated_at  TEXT
)
"""

DDL_ALERTS = """
CREATE TABLE IF NOT EXISTS alert_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT    NOT NULL,
    rule_type   TEXT    NOT NULL,
    message     TEXT    NOT NULL,
    price       REAL,
    triggered_at TEXT   NOT NULL
)
"""

DDL_BACKTEST_RESULTS = """
CREATE TABLE IF NOT EXISTS backtest_results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT NOT NULL,
    strategy        TEXT NOT NULL,
    params          TEXT,
    total_return_pct REAL,
    sharpe_ratio    REAL,
    max_drawdown_pct REAL,
    annual_return_pct REAL,
    sortino_ratio   REAL,
    calmar_ratio    REAL,
    var_95          REAL,
    cvar_95         REAL,
    total_trades    INTEGER,
    win_rate_pct    REAL,
    initial_cash    REAL,
    final_value     REAL,
    created_at      TEXT NOT NULL
)
"""

DDL_MINUTE_KLINE = """
CREATE TABLE IF NOT EXISTS minute_kline (
    code        TEXT    NOT NULL,
    datetime    TEXT    NOT NULL,
    period      TEXT    NOT NULL,  -- '1m','5m','15m','30m','60m'
    open        REAL,
    high        REAL,
    low         REAL,
    close       REAL,
    volume      REAL,
    amount      REAL,
    PRIMARY KEY (code, datetime, period)
)
"""

DDL_SIGNAL_LOG = """
CREATE TABLE IF NOT EXISTS signal_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT NOT NULL,
    strategy        TEXT NOT NULL,
    signal          TEXT NOT NULL,
    price           REAL,
    strength        REAL,
    params          TEXT,
    triggered_at    TEXT NOT NULL
)
"""

# ====== 用戶系統表 ======

DDL_USERS = """
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,
    role            TEXT DEFAULT 'user',
    settings        TEXT DEFAULT '{}',
    created_at      TEXT NOT NULL
)
"""

DDL_USER_WATCHLISTS = """
CREATE TABLE IF NOT EXISTS user_watchlists (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    name            TEXT NOT NULL,
    codes           TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
)
"""

DDL_USER_ALERT_RULES = """
CREATE TABLE IF NOT EXISTS user_alert_rules (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    code            TEXT NOT NULL,
    rule_type       TEXT NOT NULL,
    params          TEXT NOT NULL,
    enabled         INTEGER DEFAULT 1,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
)
"""


def init_db():
    """初始化數據庫，建表 + 建索引"""
    os.makedirs(os.path.dirname(settings.db_path), exist_ok=True)

    with get_conn() as conn:
        conn.execute(DDL_DAILY)
        conn.execute(DDL_REALTIME)
        conn.execute(DDL_ALERTS)
        conn.execute(DDL_BACKTEST_RESULTS)
        conn.execute(DDL_SIGNAL_LOG)
        conn.execute(DDL_MINUTE_KLINE)
        # 用戶系統表
        conn.execute(DDL_USERS)
        conn.execute(DDL_USER_WATCHLISTS)
        conn.execute(DDL_USER_ALERT_RULES)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_daily_code ON daily_kline(code)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_daily_date ON daily_kline(date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bt_code ON backtest_results(code)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bt_created ON backtest_results(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sig_code ON signal_log(code)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sig_triggered ON signal_log(triggered_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sig_strategy ON signal_log(strategy)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_minute_code ON minute_kline(code)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_minute_period ON minute_kline(period)")
        # 用戶表索引
        conn.execute("CREATE INDEX IF NOT EXISTS idx_user_username ON users(username)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_watchlist_user ON user_watchlists(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_alert_user ON user_alert_rules(user_id)")

        # ====== 遷移：添加 market 列（兼容舊數據庫）======
        try:
            conn.execute("ALTER TABLE daily_kline ADD COLUMN market TEXT DEFAULT 'a_share'")
        except sqlite3.OperationalError:
            pass  # 列已存在

        # 市場索引
        conn.execute("CREATE INDEX IF NOT EXISTS idx_daily_market ON daily_kline(market)")

        conn.commit()
    
    # 初始化擴展數據表（板塊、資金流向、龍虎榜、基本面）
    try:
        from src.core.sector import init_sector_table
        from src.core.capital_flow import init_capital_flow_table
        from src.core.dragon_tiger import init_dragon_tiger_table
        from src.core.fundamental import init_fundamentals_table
        init_sector_table()
        init_capital_flow_table()
        init_dragon_tiger_table()
        init_fundamentals_table()
    except Exception as e:
        logger.warning(f"擴展數據表初始化跳過: {e}")
    
    # 創建默認管理員賬號（首次運行時）
    try:
        from src.core.auth import ensure_default_admin
        ensure_default_admin()
    except Exception as e:
        logger.warning(f"默認管理員初始化跳過: {e}")
    
    logger.info(f"數據庫就緒: {settings.db_path}")


def save_daily_kline(df: pd.DataFrame, code: str, market: str = "a_share") -> int:
    """保存日K數據（upsert），支持多市場"""
    if df.empty:
        return 0

    # 統一列名
    col_map = {"日期": "date", "开盘": "open", "最高": "high", "最低": "low",
               "收盘": "close", "成交量": "volume", "成交额": "amount", "换手率": "turnover"}
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    # 向量化構建 records — 比 iterrows() 快 10 倍+
    records = list(zip(
        [code] * len(df),
        df["date"].astype(str),
        pd.to_numeric(df["open"], errors="coerce").fillna(0),
        pd.to_numeric(df["high"], errors="coerce").fillna(0),
        pd.to_numeric(df["low"], errors="coerce").fillna(0),
        pd.to_numeric(df["close"], errors="coerce").fillna(0),
        pd.to_numeric(df["volume"], errors="coerce").fillna(0),
        pd.to_numeric(df.get("amount", pd.Series(0, index=df.index)), errors="coerce").fillna(0),
        pd.to_numeric(df.get("turnover", pd.Series(0, index=df.index)), errors="coerce").fillna(0),
        [market] * len(df),
    ))

    with get_conn() as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO daily_kline
               (code, date, open, high, low, close, volume, amount, turnover, market)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            records
        )
    logger.debug(f"保存 {code} 日K: {len(records)} 條 (market={market})")
    return len(records)


def load_daily_kline(code: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
    """讀取日K數據（帶 LRU 緩存）"""
    rows, cols = _load_daily_kline_cached(code, start_date, end_date)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows, columns=cols)


def load_all_codes() -> list[str]:
    """獲取數據庫中所有股票代碼"""
    with get_conn() as conn:
        rows = conn.execute("SELECT DISTINCT code FROM daily_kline ORDER BY code").fetchall()
    return [r[0] for r in rows]


def load_all_codes_by_market(market: str = "a_share") -> list[str]:
    """獲取指定市場的所有代碼"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT code FROM daily_kline WHERE market = ? ORDER BY code",
            (market,)
        ).fetchall()
    return [r[0] for r in rows]


def load_all_markets() -> list[dict]:
    """獲取所有市場及其代碼數量"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT market, COUNT(DISTINCT code) as count FROM daily_kline GROUP BY market ORDER BY market"
        ).fetchall()
    return [{"market": r[0], "count": r[1]} for r in rows]


def get_market_for_code(code: str) -> str:
    """根據代碼判斷市場類型"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT market FROM daily_kline WHERE code = ? LIMIT 1",
            (code,)
        ).fetchone()
    if row:
        return row[0]
    # 根據代碼格式推斷
    if code.isdigit() and len(code) == 6:
        return "a_share"
    if code.endswith("USDT") or code.endswith("BTC") or code.endswith("ETH"):
        return "crypto"
    if len(code) == 6 and code[:3] in ("USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "CNY", "HKD"):
        return "forex"
    return "a_share"


def save_realtime_snapshot(df: pd.DataFrame):
    """保存實時行情快照"""
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 向量化構建 records
    for col in ("price", "change_pct", "volume", "amount", "high", "low", "open", "prev_close"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    records = list(zip(
        df.get("code", pd.Series("", index=df.index)).astype(str),
        df.get("name", pd.Series("", index=df.index)).astype(str),
        df.get("price", pd.Series(0, index=df.index)),
        df.get("change_pct", pd.Series(0, index=df.index)),
        df.get("volume", pd.Series(0, index=df.index)),
        df.get("amount", pd.Series(0, index=df.index)),
        df.get("high", pd.Series(0, index=df.index)),
        df.get("low", pd.Series(0, index=df.index)),
        df.get("open", pd.Series(0, index=df.index)),
        df.get("prev_close", pd.Series(0, index=df.index)),
        [now] * len(df),
    ))

    with get_conn() as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO realtime_snapshot
               (code, name, price, change_pct, volume, amount,
                high, low, open, prev_close, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            records
        )


def log_alert(code: str, rule_type: str, message: str, price: float):
    """記錄預警日誌"""
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO alert_log (code, rule_type, message, price, triggered_at)
               VALUES (?, ?, ?, ?, ?)""",
            (code, rule_type, message, price, now)
        )


def get_alert_logs(limit: int = 100, code: str = None) -> list[dict]:
    """獲取預警日誌"""
    sql = "SELECT * FROM alert_log"
    params = []
    if code:
        sql += " WHERE code = ?"
        params.append(code)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_db_stats() -> dict:
    """獲取數據庫統計"""
    import os
    db_size = os.path.getsize(settings.db_path) if os.path.exists(settings.db_path) else 0

    with get_conn() as conn:
        stock_count = conn.execute("SELECT COUNT(DISTINCT code) FROM daily_kline").fetchone()[0]
        kline_count = conn.execute("SELECT COUNT(*) FROM daily_kline").fetchone()[0]
        alert_count = conn.execute("SELECT COUNT(*) FROM alert_log").fetchone()[0]

    return {
        "db_size_mb": round(db_size / 1024 / 1024, 2),
        "total_stocks": stock_count,
        "total_klines": kline_count,
        "total_alerts": alert_count,
    }


def save_backtest_result(result: dict):
    """保存回測結果到數據庫"""
    import json
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    params_json = json.dumps(result.get("params", {}), ensure_ascii=False)
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO backtest_results
               (code, strategy, params, total_return_pct, sharpe_ratio, max_drawdown_pct,
                annual_return_pct, sortino_ratio, calmar_ratio, var_95, cvar_95,
                total_trades, win_rate_pct, initial_cash, final_value, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                result.get("code", ""),
                result.get("strategy", ""),
                params_json,
                result.get("total_return_pct"),
                result.get("sharpe_ratio"),
                result.get("max_drawdown_pct"),
                result.get("annual_return_pct"),
                result.get("sortino_ratio"),
                result.get("calmar_ratio"),
                result.get("var_95"),
                result.get("cvar_95"),
                result.get("total_trades"),
                result.get("win_rate_pct"),
                result.get("initial_cash"),
                result.get("final_value"),
                now,
            )
        )


def get_backtest_history(code: str = None, strategy: str = None, limit: int = 50) -> list[dict]:
    """查詢回測歷史"""
    sql = "SELECT * FROM backtest_results WHERE 1=1"
    params = []
    if code:
        sql += " AND code = ?"
        params.append(code)
    if strategy:
        sql += " AND strategy = ?"
        params.append(strategy)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        import json
        d["params"] = json.loads(d["params"]) if d.get("params") else {}
        results.append(d)
    return results


def get_backtest_by_ids(ids: list[int]) -> list[dict]:
    """按 ID 列表查詢回測結果"""
    if not ids:
        return []
    placeholders = ",".join("?" * len(ids))
    sql = f"SELECT * FROM backtest_results WHERE id IN ({placeholders}) ORDER BY id"

    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, ids).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        import json
        d["params"] = json.loads(d["params"]) if d.get("params") else {}
        results.append(d)
    return results


def get_latest_date(code: str) -> str | None:
    """獲取某股票最新數據日期"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT MAX(date) FROM daily_kline WHERE code = ?", (code,)
        ).fetchone()
    if row and row[0]:
        return str(row[0])
    return None


def get_signal_logs(code: str = None, strategy: str = None, days: int = 30, limit: int = 500) -> list[dict]:
    """查詢信號歷史記錄"""
    sql = "SELECT * FROM signal_log WHERE 1=1"
    params = []

    if code:
        sql += " AND code = ?"
        params.append(code)
    if strategy:
        sql += " AND strategy = ?"
        params.append(strategy)

    # 按天數過濾
    if days:
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        sql += " AND triggered_at >= ?"
        params.append(cutoff)

    sql += " ORDER BY triggered_at DESC LIMIT ?"
    params.append(limit)

    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


# ============================================================
# 分鐘 K 線數據
# ============================================================

@lru_cache(maxsize=32)
def _load_minute_kline_cached(code: str, period: str) -> tuple:
    """緩存版本 — 返回 tuple 以便 hashable"""
    sql = "SELECT * FROM minute_kline WHERE code = ? AND period = ? ORDER BY datetime"
    
    with get_conn() as conn:
        df = pd.read_sql(sql, conn, params=[code, period])
    
    if df.empty:
        return ((), ())
    return (tuple(df.itertuples(index=False, name=None)), tuple(df.columns))


def save_minute_kline(df: pd.DataFrame, code: str, period: str) -> int:
    """
    保存分鐘 K 線數據（upsert）
    
    Args:
        df: K 線 DataFrame
        code: 股票代碼
        period: 週期 '1m','5m','15m','30m','60m'
    
    Returns:
        保存的記錄數
    """
    if df.empty:
        return 0
    
    records = []
    for _, row in df.iterrows():
        records.append((
            code,
            str(row.get("datetime", row.get("时间", ""))),
            period,
            float(row.get("open", row.get("开盘", 0))),
            float(row.get("high", row.get("最高", 0))),
            float(row.get("low", row.get("最低", 0))),
            float(row.get("close", row.get("收盘", 0))),
            float(row.get("volume", row.get("成交量", 0))),
            float(row.get("amount", row.get("成交额", 0))),
        ))
    
    with get_conn() as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO minute_kline
               (code, datetime, period, open, high, low, close, volume, amount)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            records
        )
    logger.debug(f"保存 {code} {period} 分鐘K: {len(records)} 條")
    return len(records)


def load_minute_kline(code: str, period: str = "5m") -> pd.DataFrame:
    """
    讀取分鐘 K 線數據（帶 LRU 緩存）
    
    Args:
        code: 股票代碼
        period: 週期 '1m','5m','15m','30m','60m'
    
    Returns:
        分鐘 K 線 DataFrame
    """
    rows, cols = _load_minute_kline_cached(code, period)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows, columns=cols)
