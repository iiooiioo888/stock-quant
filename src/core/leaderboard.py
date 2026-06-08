"""
策略排行榜 — 對所有策略（內置 + 用戶）進行回測並按夏普比率排名

功能：
  - update_leaderboard(): 跑所有策略，計算 Sharpe/收益/回撤，存入 DB
  - get_leaderboard(): 讀取排行榜，支持按不同指標排序
  - strategy_leaderboard 表存儲歷史排名
"""

import json
from datetime import datetime

from src.core.db import get_conn
from src.utils.logger import logger

# ============================================================
# 排行榜數據表
# ============================================================

DDL_LEADERBOARD = """
CREATE TABLE IF NOT EXISTS strategy_leaderboard (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name   TEXT    NOT NULL,
    source          TEXT    NOT NULL DEFAULT 'builtin',
    code            TEXT    NOT NULL,
    total_return_pct REAL,
    sharpe_ratio    REAL,
    sortino_ratio   REAL,
    calmar_ratio    REAL,
    max_drawdown_pct REAL,
    win_rate_pct    REAL,
    total_trades    INTEGER,
    annual_return_pct REAL,
    var_95          REAL,
    rank            INTEGER,
    params          TEXT,
    evaluated_at    TEXT    NOT NULL
)
"""


def init_leaderboard_table():
    """向後兼容；表結構由 src.core.database.schema 集中管理。"""
    pass


def update_leaderboard(codes: list[str] = None) -> list[dict]:
    """
    更新策略排行榜。

    對所有策略（內置 + 用戶）在指定股票上跑回測，按 Sharpe 排名並存入 DB。

    參數:
        codes: 股票代碼列表，默認為 watchlist
    返回:
        排名後的結果列表
    """
    from src.config import settings
    from src.core.backtest import STRATEGIES, run_backtest
    from src.core.strategy_base import (
        list_user_strategies,
        quick_backtest_user_strategy,
    )

    init_leaderboard_table()

    if codes is None:
        codes = settings.watchlist

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    results = []

    # 1. 內置策略
    for strategy_name, strategy_cls in STRATEGIES.items():
        for code in codes:
            try:
                r = run_backtest(code, strategy_name=strategy_name, benchmark=False)
                results.append(
                    {
                        "strategy_name": strategy_name,
                        "source": "builtin",
                        "code": code,
                        "total_return_pct": r.get("total_return_pct", 0),
                        "sharpe_ratio": r.get("sharpe_ratio", 0),
                        "sortino_ratio": r.get("sortino_ratio", 0),
                        "calmar_ratio": r.get("calmar_ratio", 0),
                        "max_drawdown_pct": r.get("max_drawdown_pct", 0),
                        "win_rate_pct": r.get("win_rate_pct", 0),
                        "total_trades": r.get("total_trades", 0),
                        "annual_return_pct": r.get("annual_return_pct", 0),
                        "var_95": r.get("var_95", 0),
                        "params": json.dumps(
                            settings.strategy_params.get(strategy_name, {}),
                            ensure_ascii=False,
                        ),
                    }
                )
            except Exception as e:
                logger.debug(f"排行榜回測跳過: {strategy_name}/{code} — {e}")

    # 2. 用戶策略
    user_strategies = list_user_strategies()
    for s_info in user_strategies:
        cls = s_info["class"]
        for code in codes:
            try:
                instance = cls()
                r = quick_backtest_user_strategy(instance, code)
                results.append(
                    {
                        "strategy_name": s_info["name"],
                        "source": "user",
                        "code": code,
                        "total_return_pct": r.get("total_return_pct", 0),
                        "sharpe_ratio": r.get("sharpe_ratio", 0),
                        "sortino_ratio": 0,
                        "calmar_ratio": 0,
                        "max_drawdown_pct": r.get("max_drawdown_pct", 0),
                        "win_rate_pct": r.get("win_rate_pct", 0),
                        "total_trades": r.get("total_trades", 0),
                        "annual_return_pct": 0,
                        "var_95": 0,
                        "params": json.dumps(
                            s_info.get("params", {}), ensure_ascii=False
                        ),
                    }
                )
            except Exception as e:
                logger.debug(f"用戶策略排行榜回測跳過: {s_info['name']}/{code} — {e}")

    # 按夏普比率排名
    results.sort(key=lambda x: x.get("sharpe_ratio", 0) or 0, reverse=True)
    for i, r in enumerate(results):
        r["rank"] = i + 1

    # 寫入 DB
    with get_conn() as conn:
        # 清除舊的同批次數據（可選，這裡保留歷史）
        for r in results:
            conn.execute(
                """INSERT INTO strategy_leaderboard
                   (strategy_name, source, code, total_return_pct, sharpe_ratio,
                    sortino_ratio, calmar_ratio, max_drawdown_pct, win_rate_pct,
                    total_trades, annual_return_pct, var_95, rank, params, evaluated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    r["strategy_name"],
                    r["source"],
                    r["code"],
                    r["total_return_pct"],
                    r["sharpe_ratio"],
                    r.get("sortino_ratio", 0),
                    r.get("calmar_ratio", 0),
                    r["max_drawdown_pct"],
                    r["win_rate_pct"],
                    r["total_trades"],
                    r.get("annual_return_pct", 0),
                    r.get("var_95", 0),
                    r["rank"],
                    r.get("params", "{}"),
                    now,
                ),
            )
        conn.commit()

    logger.info(f"排行榜更新完成: {len(results)} 條記錄")
    return results


def _sql_scalar(conn, sql: str, params: tuple = ()) -> object | None:
    """讀取單值；避免線程連接殘留 row_factory 導致 fetchone()[0] 變成 KeyError(0)"""
    prev = conn.row_factory
    conn.row_factory = None
    try:
        row = conn.execute(sql, params).fetchone()
        return row[0] if row is not None else None
    finally:
        conn.row_factory = prev


def get_leaderboard(
    sort_by: str = "sharpe", limit: int = 50, latest_only: bool = True
) -> list[dict]:
    """
    獲取策略排行榜。

    參數:
        sort_by: 排序字段 — sharpe/return/drawdown/win_rate/sortino/calmar
        limit: 返回條數
        latest_only: 是否只返回最新一次評估的結果
    返回:
        排名列表
    """
    init_leaderboard_table()

    # 排序字段映射
    sort_map = {
        "sharpe": "sharpe_ratio",
        "return": "total_return_pct",
        "drawdown": "max_drawdown_pct",
        "win_rate": "win_rate_pct",
        "sortino": "sortino_ratio",
        "calmar": "calmar_ratio",
    }
    order_col = sort_map.get(sort_by, "sharpe_ratio")
    # 回撤是越小越好，需要 ASC
    order_dir = "ASC" if sort_by == "drawdown" else "DESC"

    with get_conn() as conn:
        prev_factory = conn.row_factory
        conn.row_factory = _dict_row_factory
        try:
            if latest_only:
                max_ts = _sql_scalar(
                    conn, "SELECT MAX(evaluated_at) FROM strategy_leaderboard"
                )
                if not max_ts:
                    return []
                rows = conn.execute(
                    f"""SELECT * FROM strategy_leaderboard
                        WHERE evaluated_at = ?
                        ORDER BY {order_col} {order_dir}
                        LIMIT ?""",
                    (max_ts, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"""SELECT * FROM strategy_leaderboard
                        ORDER BY {order_col} {order_dir}, evaluated_at DESC
                        LIMIT ?""",
                    (limit,),
                ).fetchall()
        finally:
            conn.row_factory = prev_factory

    return rows


def get_leaderboard_summary() -> dict:
    """
    獲取排行榜摘要信息。

    返回:
        {"total_evaluations": ..., "latest_eval": ..., "top_strategy": ..., ...}
    """
    init_leaderboard_table()

    with get_conn() as conn:
        total = _sql_scalar(conn, "SELECT COUNT(*) FROM strategy_leaderboard") or 0
        latest = _sql_scalar(conn, "SELECT MAX(evaluated_at) FROM strategy_leaderboard")

        top = None
        if latest:
            prev_factory = conn.row_factory
            conn.row_factory = _dict_row_factory
            try:
                row = conn.execute(
                    """SELECT * FROM strategy_leaderboard
                       WHERE evaluated_at = ?
                       ORDER BY sharpe_ratio DESC LIMIT 1""",
                    (latest,),
                ).fetchone()
                if row:
                    top = row
            finally:
                conn.row_factory = prev_factory

    return {
        "total_evaluations": total,
        "latest_eval": latest,
        "top_strategy": top,
    }


def _dict_row_factory(cursor, row):
    """sqlite3 Row 工廠 — 返回字典"""
    fields = [column[0] for column in cursor.description]
    return {key: value for key, value in zip(fields, row)}
