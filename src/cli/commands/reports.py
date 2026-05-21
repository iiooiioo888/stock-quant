"""CLI commands: reports"""
from datetime import datetime

import numpy as np

from src.cli.helpers import (
    DEFAULT_ALLOCATIONS,
    add_alloc_arg,
    ensure_db,
    fail_result,
    get_allocations,
    is_a_share_trading_now,
    parse_allocations,
    print_portfolio_metrics,
)


def cmd_report(args):
    """增強報告"""
    ensure_db()

    action = args.report_action

    if action == "full":
        from src.core.report_enhanced import generate_full_report
        print(f"📊 生成全面報告: {args.code}/{args.strategy}")
        report = generate_full_report(args.code, args.strategy)

        perf = report.get("performance", {})
        trades = report.get("trades", {})
        ta = report.get("trade_analysis", {})
        mc = report.get("monte_carlo", {})
        rm_summary = report.get("rolling_metrics", {}).get("summary", {})
        bc = report.get("benchmark_comparison", {})

        print(f"\n{'='*60}")
        print(f"全面回測報告: {args.code} / {args.strategy}")
        print(f"{'='*60}")

        print(f"\n📈 績效指標:")
        print(f"  總收益率:   {perf.get('total_return_pct', 0):+.2f}%")
        print(f"  年化收益:   {perf.get('annual_return_pct', 0):+.2f}%")
        print(f"  夏普比率:   {perf.get('sharpe_ratio', 0):.4f}")
        print(f"  Sortino:    {perf.get('sortino_ratio', 0):.4f}")
        print(f"  Calmar:     {perf.get('calmar_ratio', 0):.4f}")
        print(f"  最大回撤:   {perf.get('max_drawdown_pct', 0):.2f}%")
        print(f"  年化波動:   {perf.get('annual_volatility', 0):.4f}")

        print(f"\n📋 交易統計:")
        print(f"  總交易:     {trades.get('total', 0)}")
        print(f"  勝率:       {trades.get('win_rate_pct', 0):.1f}%")
        print(f"  盈虧比:     {trades.get('profit_loss_ratio', 0):.2f}")
        print(f"  月勝率:     {trades.get('monthly_win_rate', 0):.1f}%")

        print(f"\n🔍 交易深度分析:")
        streak = ta.get("streak", {})
        print(f"  最長連勝:   {streak.get('max_win_streak', 0)}")
        print(f"  最長連敗:   {streak.get('max_loss_streak', 0)}")
        print(f"  盈虧因子:   {ta.get('profit_factor', 0):.4f}")
        print(f"  期望收益:   {ta.get('expectancy', 0):.4f}")
        hp = ta.get("hold_period", {})
        print(f"  盈利均持:   {hp.get('avg_winner_days', 0):.1f} 天")
        print(f"  虧損均持:   {hp.get('avg_loser_days', 0):.1f} 天")
        print(f"  恢復因子:   {ta.get('recovery_factor', 0):.4f}")
        bm = ta.get("best_month")
        wm = ta.get("worst_month")
        if bm:
            print(f"  最佳月份:   {bm['month']} (¥{bm['pnl']:+.2f})")
        if wm:
            print(f"  最差月份:   {wm['month']} (¥{wm['pnl']:+.2f})")

        print(f"\n🎲 蒙特卡羅模擬 ({mc.get('n_simulations', 0)} 次, {mc.get('days', 0)} 天):")
        pct = mc.get("percentiles", {})
        print(f"  盈利概率:   {mc.get('prob_profit', 0):.1%}")
        print(f"  >20%回撤概率: {mc.get('prob_large_drawdown', 0):.1%}")
        print(f"  5th百分位:  {pct.get('p5', 0):.4f}")
        print(f"  中位數:     {pct.get('p50', 0):.4f}")
        print(f"  95th百分位: {pct.get('p95', 0):.4f}")

        if rm_summary:
            print(f"\n📉 滾動指標 ({report.get('rolling_metrics', {}).get('window', 60)}日):")
            print(f"  夏普均值:   {rm_summary.get('sharpe_mean', 0):.4f}")
            print(f"  夏普範圍:   [{rm_summary.get('sharpe_min', 0):.4f}, {rm_summary.get('sharpe_max', 0):.4f}]")
            print(f"  波動率均值: {rm_summary.get('volatility_mean', 0):.4f}")

        if bc.get("benchmark_available"):
            print(f"\n📊 基準對比 (滬深300):")
            print(f"  上行捕獲:   {bc.get('up_capture', 0):.4f}")
            print(f"  下行捕獲:   {bc.get('down_capture', 0):.4f}")
            print(f"  打擊率:     {bc.get('batting_average', 0):.1%}")
            print(f"  牛市相關:   {bc.get('bull_correlation', 0):.4f}")
            print(f"  熊市相關:   {bc.get('bear_correlation', 0):.4f}")

    elif action == "comparison":
        from src.core.report_enhanced import generate_comparison_report
        codes = args.codes
        strategy = args.strategy
        print(f"📊 多股對比報告: {', '.join(codes)} / {strategy}")
        report = generate_comparison_report(codes, strategy)

        print(f"\n{'='*80}")
        print(f"多股對比: {strategy}")
        print(f"{'='*80}")

        ranking = report.get("ranking", [])
        if ranking:
            print(f"\n{'排名':>4} {'代碼':<10} {'收益':>10} {'夏普':>8} {'Sortino':>8} {'回撤':>10} {'勝率':>8} {'交易':>6} {'盈虧比':>8}")
            print("-" * 80)
            for r in ranking:
                print(f"{r.get('rank', 0):>4} {r['code']:<10} "
                      f"{r.get('total_return_pct', 0):>+9.2f}% "
                      f"{r.get('sharpe_ratio', 0):>8.2f} "
                      f"{r.get('sortino_ratio', 0):>8.2f} "
                      f"{r.get('max_drawdown_pct', 0):>9.2f}% "
                      f"{r.get('win_rate_pct', 0):>7.1f}% "
                      f"{r.get('total_trades', 0):>6} "
                      f"{r.get('profit_factor', 0):>8.2f}")

        best = report.get("best")
        worst = report.get("worst")
        if best:
            print(f"\n🏆 最佳: {best['code']} (夏普 {best.get('sharpe_ratio', 0):.2f})")
        if worst:
            print(f"📉 最差: {worst['code']} (夏普 {worst.get('sharpe_ratio', 0):.2f})")
        print(f"📊 一致性分數: {report.get('consistency_score', 0):.4f}")

    elif action == "strategy":
        from src.core.report_enhanced import generate_strategy_report
        strategy = args.strategy_name
        codes = args.codes if hasattr(args, "codes") and args.codes else None
        print(f"📊 策略分析報告: {strategy}")
        report = generate_strategy_report(strategy, codes=codes)

        if "error" in report:
            print(f"❌ {report['error']}")
            return

        print(f"\n{'='*80}")
        print(f"策略: {strategy} — {report.get('description', '')}")
        print(f"{'='*80}")

        avg = report.get("avg_metrics", {})
        if avg:
            print(f"\n平均指標 ({report.get('success_stocks', 0)} 只股票):")
            print(f"  收益率:     {avg.get('avg_total_return_pct', 0):+.2f}% (±{avg.get('std_total_return_pct', 0):.2f}%)")
            print(f"  夏普:       {avg.get('avg_sharpe_ratio', 0):.4f} (±{avg.get('std_sharpe_ratio', 0):.4f})")
            print(f"  回撤:       {avg.get('avg_max_drawdown_pct', 0):.2f}% (±{avg.get('std_max_drawdown_pct', 0):.2f}%)")
            print(f"  勝率:       {avg.get('avg_win_rate_pct', 0):.1f}%")
            print(f"  盈虧比:     {avg.get('avg_profit_factor', 0):.2f}")

        print(f"\n一致性分數: {report.get('consistency_score', 0):.4f}")

        best = report.get("best_stock")
        worst = report.get("worst_stock")
        if best:
            print(f"🏆 最佳股票: {best['code']} (夏普 {best.get('sharpe_ratio', 0):.2f}, 收益 {best.get('total_return_pct', 0):+.2f}%)")
        if worst:
            print(f"📉 最差股票: {worst['code']} (夏普 {worst.get('sharpe_ratio', 0):.2f}, 收益 {worst.get('total_return_pct', 0):+.2f}%)")

        suggestions = report.get("param_suggestions", [])
        if suggestions:
            print(f"\n💡 參數建議:")
            for s in suggestions:
                icon = "🔴" if s.get("level") == "high" else "🟡" if s.get("level") == "medium" else "ℹ️"
                print(f"  {icon} {s.get('message', '')}")
    else:
        print("用法:")
        print("  python main.py report full <code> <strategy>")
        print("  python main.py report comparison <code1> <code2> ... --strategy <strategy>")
        print("  python main.py report strategy <strategy_name>")




def cmd_monte_carlo(args):
    """蒙特卡羅模擬"""
    from src.core.backtest import run_backtest, monte_carlo_simulation

    ensure_db()

    print(f"🎲 蒙特卡羅模擬: {args.code}/{args.strategy} ({args.simulations}次, {args.days}天)")

    bt_result = run_backtest(args.code, strategy_name=args.strategy)
    mc = monte_carlo_simulation(bt_result.get("daily_returns", []), n_simulations=args.simulations, days=args.days)

    pct = mc.get("percentiles", {})
    ci = mc.get("confidence_intervals", {})

    print(f"\n{'='*50}")
    print(f"蒙特卡羅模擬結果")
    print(f"{'='*50}")
    print(f"模擬次數:   {mc.get('n_simulations', 0)}")
    print(f"模擬天數:   {mc.get('days', 0)}")
    print(f"盈利概率:   {mc.get('prob_profit', 0):.1%}")
    print(f">20%回撤:   {mc.get('prob_large_drawdown', 0):.1%}")

    print(f"\n終值淨值分佈:")
    print(f"  5th:      {pct.get('p5', 0):.4f}")
    print(f"  25th:     {pct.get('p25', 0):.4f}")
    print(f"  中位數:   {pct.get('p50', 0):.4f}")
    print(f"  75th:     {pct.get('p75', 0):.4f}")
    print(f"  95th:     {pct.get('p95', 0):.4f}")
    print(f"  均值:     {pct.get('mean', 0):.4f}")
    print(f"  標準差:   {pct.get('std', 0):.4f}")

    print(f"\n信賴區間:")
    ci_90 = ci.get("90pct", [0, 0])
    ci_50 = ci.get("50pct", [0, 0])
    print(f"  90%:      [{ci_90[0]:.4f}, {ci_90[1]:.4f}]")
    print(f"  50%:      [{ci_50[0]:.4f}, {ci_50[1]:.4f}]")




def cmd_rolling_metrics(args):
    """滾動指標"""
    from src.core.backtest import run_backtest, rolling_metrics

    ensure_db()

    print(f"📉 滾動指標: {args.code} (窗口={args.window}天)")

    bt_result = run_backtest(args.code, strategy_name="dual_ma")
    rm = rolling_metrics(bt_result.get("daily_returns", []), bt_result.get("dates", []), window=args.window)

    summary = rm.get("summary", {})

    print(f"\n{'='*50}")
    print(f"滾動指標摘要 (窗口={args.window}天)")
    print(f"{'='*50}")

    if summary:
        print(f"\n夏普比率:")
        print(f"  均值:     {summary.get('sharpe_mean', 0):.4f}")
        print(f"  最小:     {summary.get('sharpe_min', 0):.4f}")
        print(f"  最大:     {summary.get('sharpe_max', 0):.4f}")

        print(f"\nSortino:")
        print(f"  均值:     {summary.get('sortino_mean', 0):.4f}")
        print(f"  最小:     {summary.get('sortino_min', 0):.4f}")
        print(f"  最大:     {summary.get('sortino_max', 0):.4f}")

        print(f"\n最大回撤 (%):")
        print(f"  均值:     {summary.get('max_dd_mean', 0):.2f}%")
        print(f"  最差:     {summary.get('max_dd_worst', 0):.2f}%")

        print(f"\n年化波動率:")
        print(f"  均值:     {summary.get('volatility_mean', 0):.4f}")
        print(f"  最小:     {summary.get('volatility_min', 0):.4f}")
        print(f"  最大:     {summary.get('volatility_max', 0):.4f}")

    data_points = len(rm.get("rolling_sharpe", []))
    print(f"\n數據點: {data_points}")




def cmd_export(args):
    """導出數據"""

    ensure_db()

    if args.type == "backtest":
        from src.core.export import export_backtest_csv, export_backtest_json
        if args.format == "json":
            content = export_backtest_json(args.id)
        else:
            content = export_backtest_csv(args.id)
    elif args.type == "trades":
        from src.core.export import export_trades_csv, export_trades_json
        if not args.code or not args.strategy:
            print("導出交易明細需要指定 --code 和 --strategy")
            return
        if args.format == "json":
            content = export_trades_json(args.code, args.strategy)
        else:
            content = export_trades_csv(args.code, args.strategy)
    else:
        print(f"未知導出類型: {args.type}")
        return

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"已導出到: {args.output}")
    else:
        print(content)


