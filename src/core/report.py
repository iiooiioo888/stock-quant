"""
報告生成模塊 — 生成每日策略報告（文本格式，適合 Webhook 推送）
"""
from datetime import datetime
from src.core.backtest import run_backtest, STRATEGIES
from src.core.db import get_alert_logs
from src.config import settings
from src.utils.logger import logger


def generate_daily_report(codes: list[str] = None) -> str:
    """
    生成每日策略報告

    內容:
    1. 各股票最佳策略
    2. 信號觸發
    3. 風險警告（高回撤、低勝率）
    """
    if codes is None:
        codes = settings.watchlist

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"📊 每日策略報告",
        f"📅 {now}",
        f"{'='*40}",
    ]

    best_per_stock = {}
    risk_warnings = []

    for code in codes:
        best_strategy = None
        best_sharpe = -999
        best_result = None

        for strat_name in STRATEGIES:
            try:
                r = run_backtest(code, strategy_name=strat_name)
                sharpe = r.get("sharpe_ratio", 0) or 0

                # 收集風險警告
                if r.get("max_drawdown_pct", 0) > 20:
                    risk_warnings.append(
                        f"⚠️ {code}/{strat_name}: 回撤 {r['max_drawdown_pct']:.1f}%"
                    )
                if r.get("win_rate_pct", 0) < 30 and r.get("total_trades", 0) > 5:
                    risk_warnings.append(
                        f"⚠️ {code}/{strat_name}: 勝率僅 {r['win_rate_pct']:.1f}%"
                    )

                if sharpe > best_sharpe:
                    best_sharpe = sharpe
                    best_strategy = strat_name
                    best_result = r
            except Exception:
                continue

        if best_result:
            best_per_stock[code] = {
                "strategy": best_strategy,
                "sharpe": best_sharpe,
                "return_pct": best_result.get("total_return_pct", 0),
                "max_dd": best_result.get("max_drawdown_pct", 0),
                "win_rate": best_result.get("win_rate_pct", 0),
                "trades": best_result.get("total_trades", 0),
            }

    # 最佳策略摘要
    lines.append("")
    lines.append("🏆 各股票最佳策略:")
    for code, info in best_per_stock.items():
        name = settings.alert_rules.get(code, {}).get("name", code)
        lines.append(
            f"  {name}({code}): {info['strategy']} | "
            f"夏普 {info['sharpe']:.2f} | "
            f"收益 {info['return_pct']:+.2f}% | "
            f"回撤 {info['max_dd']:.1f}% | "
            f"勝率 {info['win_rate']:.0f}% | "
            f"交易 {info['trades']} 次"
        )

    # 信號觸發
    lines.append("")
    lines.append("📡 近期預警:")
    recent_alerts = get_alert_logs(limit=5)
    if recent_alerts:
        for a in recent_alerts:
            lines.append(f"  {a['triggered_at']}: {a['message']}")
    else:
        lines.append("  無近期預警")

    # 風險警告
    if risk_warnings:
        lines.append("")
        lines.append("🚨 風險警告:")
        for w in risk_warnings[:10]:
            lines.append(f"  {w}")
    else:
        lines.append("")
        lines.append("✅ 無風險警告")

    lines.append("")
    lines.append(f"{'='*40}")

    report = "\n".join(lines)
    logger.info(f"每日報告生成完成: {len(best_per_stock)} 只股票")
    return report


def generate_backtest_report(result: dict) -> str:
    """生成單次回測完成通知"""
    code = result.get("code", "")
    strategy = result.get("strategy", "")
    name = settings.alert_rules.get(code, {}).get("name", code)

    lines = [
        f"📈 回測完成",
        f"股票: {name}({code})",
        f"策略: {strategy}",
        f"收益率: {result.get('total_return_pct', 0):+.2f}%",
        f"夏普比率: {result.get('sharpe_ratio', 0):.4f}",
        f"最大回撤: {result.get('max_drawdown_pct', 0):.2f}%",
        f"勝率: {result.get('win_rate_pct', 0):.1f}%",
        f"交易次數: {result.get('total_trades', 0)}",
    ]
    return "\n".join(lines)
