"""
數據庫操作層 — SQLite 讀寫封裝（含 LRU 緩存 + 線程本地連接池）
"""
import sqlite3
import time
from functools import lru_cache

import pandas as pd

from src.config import settings
from src.core.database.bootstrap import init_database
from src.core.database.connection import get_conn
from src.utils.logger import logger

_KLINE_COLS = "code, date, open, high, low, close, volume, amount, turnover, market"
_codes_cache: dict = {"ts": 0.0, "data": []}
_db_stats_cache: dict = {"ts": 0.0, "data": {}}
_STATS_CACHE_TTL = 5.0
_CODES_CACHE_TTL = 30.0


# get_conn 由 src.core.database.connection 提供（向後兼容 re-export）

# ============================================================
# LRU 緩存層
# ============================================================

@lru_cache(maxsize=256)
def _load_daily_kline_cached(code: str, start_date: str = None, end_date: str = None) -> tuple:
    """緩存版本 — 返回 tuple 以便 hashable"""
    sql = f"SELECT {_KLINE_COLS} FROM daily_kline WHERE code = ?"
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


def clear_data_cache(quiet: bool = False, reason: str = ""):
    """清除數據緩存（進程內 LRU + 計算結果緩存）"""
    global _codes_cache, _db_stats_cache
    _load_daily_kline_cached.cache_clear()
    _codes_cache = {"ts": 0.0, "data": []}
    _db_stats_cache = {"ts": 0.0, "data": {}}
    try:
        from src.core.backtest import clear_prepare_cache
        clear_prepare_cache()
    except Exception:
        pass
    try:
        from src.core.api_cache import clear_all
        clear_all()
    except Exception:
        pass
    try:
        _load_minute_kline_cached.cache_clear()
    except Exception:
        pass
    try:
        from src.core.result_cache import invalidate_compute
        invalidate_compute()
    except Exception:
        pass
    suffix = f" ({reason})" if reason else ""
    if quiet:
        logger.debug(f"數據緩存已清除{suffix}")
    else:
        logger.info(f"數據緩存已清除{suffix}")


def init_db():
    """初始化數據庫（版本化遷移 + 默認管理員）— 向後兼容入口"""
    init_database()


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
    """獲取數據庫中所有股票代碼（短 TTL 進程緩存）"""
    global _codes_cache
    now = time.time()
    if _codes_cache["data"] and now - _codes_cache["ts"] < _CODES_CACHE_TTL:
        return list(_codes_cache["data"])
    with get_conn() as conn:
        rows = conn.execute("SELECT DISTINCT code FROM daily_kline ORDER BY code").fetchall()
    codes = [r[0] for r in rows]
    _codes_cache = {"ts": now, "data": codes}
    return codes


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


def log_alert(code: str, rule_type: str, message: str, price: float, user_id: int = None):
    """記錄預警日誌"""
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO alert_log (code, rule_type, message, price, triggered_at, user_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (code, rule_type, message, price, now, user_id)
        )


def get_alert_logs(limit: int = 100, code: str = None, user_id: int = None) -> list[dict]:
    """獲取預警日誌（支持按用戶過濾）"""
    sql = "SELECT * FROM alert_log WHERE 1=1"
    params: list = []
    if user_id is not None:
        sql += " AND (user_id = ? OR user_id IS NULL)"
        params.append(user_id)
    if code:
        sql += " AND code = ?"
        params.append(code)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_db_stats() -> dict:
    """獲取數據庫統計（短 TTL 緩存，避免頻繁全表 COUNT）"""
    global _db_stats_cache
    now = time.time()
    if _db_stats_cache["data"] and now - _db_stats_cache["ts"] < _STATS_CACHE_TTL:
        return dict(_db_stats_cache["data"])

    import os
    db_size = os.path.getsize(settings.db_path) if os.path.exists(settings.db_path) else 0

    with get_conn() as conn:
        stock_count = conn.execute("SELECT COUNT(DISTINCT code) FROM daily_kline").fetchone()[0]
        kline_count = conn.execute("SELECT COUNT(*) FROM daily_kline").fetchone()[0]
        alert_count = conn.execute("SELECT COUNT(*) FROM alert_log").fetchone()[0]

    result = {
        "db_size_mb": round(db_size / 1024 / 1024, 2),
        "total_stocks": stock_count,
        "total_klines": kline_count,
        "total_alerts": alert_count,
    }
    _db_stats_cache = {"ts": now, "data": result}
    return result


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
                total_trades, win_rate_pct, initial_cash, final_value, created_at, user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                result.get("user_id"),
            )
        )


def count_backtest_history(code: str = None, strategy: str = None, user_id: int = None) -> int:
    """回測歷史總筆數（分頁用）。"""
    sql = "SELECT COUNT(*) FROM backtest_results WHERE 1=1"
    params: list = []
    if user_id is not None:
        sql += " AND (user_id = ? OR user_id IS NULL)"
        params.append(user_id)
    if code:
        sql += " AND code = ?"
        params.append(code)
    if strategy:
        sql += " AND strategy = ?"
        params.append(strategy)
    with get_conn() as conn:
        row = conn.execute(sql, params).fetchone()
    return int(row[0] if row else 0)


def get_backtest_history(
    code: str = None,
    strategy: str = None,
    limit: int = 50,
    offset: int = 0,
    user_id: int = None,
) -> list[dict]:
    """查詢回測歷史（支持按用戶過濾）"""
    sql = "SELECT * FROM backtest_results WHERE 1=1"
    params: list = []
    if user_id is not None:
        sql += " AND (user_id = ? OR user_id IS NULL)"
        params.append(user_id)
    if code:
        sql += " AND code = ?"
        params.append(code)
    if strategy:
        sql += " AND strategy = ?"
        params.append(strategy)
    sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([limit, max(0, offset)])

    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        import json
        d["params"] = json.loads(d["params"]) if d.get("params") else {}
        _attach_strategy_display_name(d)
        results.append(d)
    return results


def preload_kline_range(code: str, start_date: str = None, end_date: str = None) -> int:
    """
    預載日 K 至進程 LRU（不觸發外網下載）。
    用於啟動預熱或腳本 warmup_cache。
    """
    rows, _cols = _load_daily_kline_cached(code, start_date, end_date)
    return len(rows)


def _attach_strategy_display_name(row: dict) -> None:
    """為回測記錄附加策略中文顯示名。"""
    try:
        from src.core.backtest import STRATEGY_NAMES
        key = row.get("strategy") or ""
        if key and not row.get("strategy_name"):
            row["strategy_name"] = STRATEGY_NAMES.get(key, key)
    except Exception:
        pass


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
        _attach_strategy_display_name(d)
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


def get_signal_logs(code: str = None, strategy: str = None, days: int = 30, limit: int = 500, user_id: int = None) -> list[dict]:
    """查詢信號歷史記錄（支持按用戶過濾）"""
    sql = "SELECT * FROM signal_log WHERE 1=1"
    params: list = []

    if user_id is not None:
        sql += " AND (user_id = ? OR user_id IS NULL)"
        params.append(user_id)

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
