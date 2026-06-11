"""
數據導出 — CSV / JSON 格式
"""

import csv
import io
import json

from src.core.db import get_backtest_by_ids
from src.utils.logger import logger


def export_backtest_csv(result_id: int) -> str:
    """
    導出回測結果為 CSV 字符串。

    Args:
        result_id: 回測結果 ID

    Returns:
        CSV 格式字符串
    """
    results = get_backtest_by_ids([result_id])
    if not results:
        return ""

    r = results[0]
    output = io.StringIO()
    writer = csv.writer(output)

    # 寫入標題和數據
    fields = [
        ("ID", r.get("id", "")),
        ("股票代碼", r.get("code", "")),
        ("策略", r.get("strategy", "")),
        ("參數", json.dumps(r.get("params", {}), ensure_ascii=False)),
        ("總收益率(%)", r.get("total_return_pct", "")),
        ("夏普比率", r.get("sharpe_ratio", "")),
        ("最大回撤(%)", r.get("max_drawdown_pct", "")),
        ("年化收益率(%)", r.get("annual_return_pct", "")),
        ("Sortino", r.get("sortino_ratio", "")),
        ("Calmar", r.get("calmar_ratio", "")),
        ("VaR 95%", r.get("var_95", "")),
        ("CVaR 95%", r.get("cvar_95", "")),
        ("總交易次數", r.get("total_trades", "")),
        ("勝率(%)", r.get("win_rate_pct", "")),
        ("初始資金", r.get("initial_cash", "")),
        ("最終市值", r.get("final_value", "")),
        ("創建時間", r.get("created_at", "")),
    ]

    writer.writerow(["字段", "值"])
    for name, val in fields:
        writer.writerow([name, val])

    return output.getvalue()


def export_backtest_json(result_id: int) -> str:
    """導出回測結果為 JSON 字符串"""
    results = get_backtest_by_ids([result_id])
    if not results:
        return "{}"
    return json.dumps(results[0], ensure_ascii=False, indent=2)


def export_trades_csv(code: str, strategy: str) -> str:
    """
    導出交易明細為 CSV 字符串。
    從最近的回測結果中提取交易明細。

    Args:
        code: 股票代碼
        strategy: 策略名稱

    Returns:
        CSV 格式字符串
    """
    from src.core.db import get_backtest_history

    results = get_backtest_history(code=code, strategy=strategy, limit=1)
    if not results:
        return ""

    # 重新跑一次回測以獲取交易明細
    from src.core.backtest import run_backtest

    try:
        bt_result = run_backtest(code, strategy_name=strategy)
    except Exception as e:
        logger.error(f"導出交易明細失敗: {e}")
        return ""

    trades = bt_result.get("trade_details", [])
    if not trades:
        return ""

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(
        [
            "買入日期",
            "買入價格",
            "賣出日期",
            "賣出價格",
            "數量",
            "盈虧",
            "收益率(%)",
            "持有天數",
        ]
    )

    for t in trades:
        writer.writerow(
            [
                t.get("buy_date", ""),
                t.get("buy_price", ""),
                t.get("sell_date", ""),
                t.get("sell_price", ""),
                t.get("size", ""),
                t.get("pnl", ""),
                t.get("return_pct", ""),
                t.get("hold_days", ""),
            ]
        )

    return output.getvalue()


def export_trades_json(code: str, strategy: str) -> str:
    """導出交易明細為 JSON 字符串"""
    from src.core.backtest import run_backtest

    try:
        bt_result = run_backtest(code, strategy_name=strategy)
        trades = bt_result.get("trade_details", [])
        return json.dumps(trades, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"導出交易明細失敗: {e}")
        return "[]"
