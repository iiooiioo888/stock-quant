"""
回測結果對比 + 實驗版本管理

- compare_backtests：多條回測記錄的指標對比、參數差異分析、排名
- 實驗（Experiment）：把一組回測結果打上命名版本快照，便於回溯與分享
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from src.utils.logger import logger

#: 對比時關注的指標（欄位, 顯示名, 越大越好?）
_COMPARE_METRICS: tuple[tuple[str, str, bool], ...] = (
    ("total_return_pct", "總收益率%", True),
    ("annual_return_pct", "年化收益%", True),
    ("sharpe_ratio", "夏普比率", True),
    ("sortino_ratio", "索提諾比率", True),
    ("calmar_ratio", "卡瑪比率", True),
    ("max_drawdown_pct", "最大回撤%", False),
    ("win_rate_pct", "勝率%", True),
    ("total_trades", "交易次數", True),
    ("final_value", "最終資產", True),
)


def _metric_value(row: dict, key: str) -> float | None:
    v = row.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def compare_backtests(ids: list[int], metric: str = "sharpe_ratio") -> dict:
    """
    對比多條回測記錄。

    Returns:
        {
          "items": [...],           # 原始記錄（按 id 升序）
          "missing_ids": [...],     # 找不到的 id
          "params_diff": {key: {"<id>": value, ...}},  # 取值不一致的參數
          "ranking": [{"id", "code", "strategy", "metric", "value", "rank"}],
          "best": {metric_key: {"id", "value"}},       # 每個指標的最佳記錄
          "metric": metric,
        }
    """
    from src.core.db import get_backtest_by_ids

    ids = [int(i) for i in dict.fromkeys(ids or [])]
    if not ids:
        raise ValueError("請提供至少一個回測記錄 ID")
    if len(ids) > 50:
        raise ValueError("單次對比上限 50 條記錄")

    rows = get_backtest_by_ids(ids)
    found_ids = {int(r["id"]) for r in rows}
    missing = [i for i in ids if i not in found_ids]
    if not rows:
        raise ValueError("找不到任何指定的回測記錄")

    # 參數差異：只保留取值不一致的 key
    param_keys: set[str] = set()
    for r in rows:
        param_keys.update((r.get("params") or {}).keys())
    params_diff: dict[str, dict[str, Any]] = {}
    for k in sorted(param_keys):
        values = {str(r["id"]): (r.get("params") or {}).get(k) for r in rows}
        if len({repr(v) for v in values.values()}) > 1:
            params_diff[k] = values

    # 排名（指定指標，None 排最後）
    metric_keys = {m[0] for m in _COMPARE_METRICS}
    if metric not in metric_keys:
        metric = "sharpe_ratio"
    ascending = next((not higher for k, _, higher in _COMPARE_METRICS if k == metric), False)

    def _sort_key(r: dict):
        v = _metric_value(r, metric)
        return (v is None, -v if not ascending and v is not None else v)

    ranked = sorted(rows, key=_sort_key)
    ranking = [
        {
            "id": r["id"],
            "code": r.get("code"),
            "strategy": r.get("strategy"),
            "strategy_name": r.get("strategy_name"),
            "metric": metric,
            "value": _metric_value(r, metric),
            "rank": i + 1,
        }
        for i, r in enumerate(ranked)
    ]

    # 每個指標的最佳記錄
    best: dict[str, Any] = {}
    for key, label, higher_better in _COMPARE_METRICS:
        candidates = [
            (r["id"], _metric_value(r, key)) for r in rows if _metric_value(r, key) is not None
        ]
        if not candidates:
            continue
        best_id, best_val = (
            max(candidates, key=lambda x: x[1])
            if higher_better
            else min(candidates, key=lambda x: x[1])
        )
        best[key] = {"id": best_id, "value": best_val, "label": label}

    return {
        "items": rows,
        "missing_ids": missing,
        "params_diff": params_diff,
        "ranking": ranking,
        "best": best,
        "metric": metric,
    }


# ============================================================
# 實驗版本管理（Experiment）
# ============================================================


def create_experiment(
    name: str,
    backtest_ids: list[int],
    note: str = "",
    user_id: Optional[int] = None,
) -> dict:
    """建立實驗版本快照：把一組回測結果歸檔到命名版本下。"""
    from src.core.db import get_backtest_by_ids, get_conn

    name = (name or "").strip()
    if not name:
        raise ValueError("實驗名稱不可為空")
    if len(name) > 100:
        raise ValueError("實驗名稱過長（上限 100 字元）")

    ids = [int(i) for i in dict.fromkeys(backtest_ids or [])]
    if not ids:
        raise ValueError("實驗至少需要一條回測記錄")

    rows = get_backtest_by_ids(ids)
    found = {int(r["id"]) for r in rows}
    missing = [i for i in ids if i not in found]
    if missing:
        raise ValueError(f"回測記錄不存在: {missing}")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO backtest_experiments (user_id, name, note, created_at) VALUES (?, ?, ?, ?)",
            (user_id, name, (note or "")[:2000], now),
        )
        exp_id = int(cur.lastrowid)
        conn.executemany(
            "INSERT OR IGNORE INTO backtest_experiment_items (experiment_id, backtest_id) VALUES (?, ?)",
            [(exp_id, bid) for bid in ids],
        )
    logger.info(f"實驗已建立: #{exp_id}「{name}」（{len(ids)} 條回測）")
    return {
        "id": exp_id,
        "name": name,
        "note": note or "",
        "backtest_ids": ids,
        "created_at": now,
    }


def list_experiments(user_id: Optional[int] = None, limit: int = 50) -> list[dict]:
    """列出實驗版本（含成員數）。"""
    from src.core.db import get_conn

    sql = """
        SELECT e.id, e.name, e.note, e.created_at, e.user_id,
               (SELECT COUNT(*) FROM backtest_experiment_items i WHERE i.experiment_id = e.id) AS item_count
        FROM backtest_experiments e
    """
    params: list = []
    if user_id is not None:
        sql += " WHERE (e.user_id = ? OR e.user_id IS NULL)"
        params.append(user_id)
    sql += " ORDER BY e.id DESC LIMIT ?"
    params.append(max(1, min(int(limit), 200)))

    with get_conn() as conn:
        conn.row_factory = __import__("sqlite3").Row
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_experiment(experiment_id: int, *, with_compare: bool = True) -> Optional[dict]:
    """取實驗詳情（含成員回測記錄與對比結果）。"""
    from src.core.db import get_conn

    with get_conn() as conn:
        conn.row_factory = __import__("sqlite3").Row
        row = conn.execute(
            "SELECT id, name, note, created_at, user_id FROM backtest_experiments WHERE id = ?",
            (int(experiment_id),),
        ).fetchone()
        if not row:
            return None
        exp = dict(row)
        items = conn.execute(
            "SELECT backtest_id FROM backtest_experiment_items WHERE experiment_id = ? ORDER BY backtest_id",
            (int(experiment_id),),
        ).fetchall()
    ids = [int(r[0]) for r in items]
    exp["backtest_ids"] = ids
    if with_compare and ids:
        exp["compare"] = compare_backtests(ids)
    return exp


def delete_experiment(experiment_id: int, user_id: Optional[int] = None) -> bool:
    """刪除實驗版本（僅刪分組，不動回測記錄本身）。"""
    from src.core.db import get_conn

    with get_conn() as conn:
        if user_id is not None:
            row = conn.execute(
                "SELECT user_id FROM backtest_experiments WHERE id = ?",
                (int(experiment_id),),
            ).fetchone()
            if not row:
                return False
            owner = row[0]
            if owner is not None and int(owner) != int(user_id):
                return False
        cur = conn.execute(
            "DELETE FROM backtest_experiments WHERE id = ?", (int(experiment_id),)
        )
        if cur.rowcount == 0:
            return False
        conn.execute(
            "DELETE FROM backtest_experiment_items WHERE experiment_id = ?",
            (int(experiment_id),),
        )
    logger.info(f"實驗已刪除: #{experiment_id}")
    return True
