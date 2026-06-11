"""CLI commands: risk"""

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


def cmd_risk(args):
    """風險管理命令"""
    ensure_db()

    if args.risk_action == "position-size":
        # 倉位計算
        from src.core.risk_manager import PositionSizer, calculate_atr

        capital = args.capital
        method = args.method
        max_risk = args.max_risk

        sizer = PositionSizer(total_capital=capital, max_risk_per_trade=max_risk)

        print(f"\n{'='*60}")
        print(f"💰 倉位計算 (資金: ¥{capital:,.0f}, 方法: {method})")
        print(f"{'='*60}")

        if method == "atr":
            atr = args.atr
            code = args.code
            if atr <= 0 and code:
                atr = calculate_atr(code)
                print(f"  自動計算 ATR({code}): {atr:.4f}")
            if atr <= 0:
                print("❌ 請提供 ATR 值 (--atr) 或股票代碼 (--code)")
                return

            shares = sizer.atr_based(atr)
            print(f"  ATR: {atr:.4f}")
            print(f"  每筆最大風險: {max_risk:.1%}")
            print(f"  風險金額: ¥{capital * max_risk:,.0f}")
            print(f"\n  ✅ 建議倉位: {shares} 股")
            print(f"  預估金額: ¥{shares * atr * 30:,.0f}（按 ATR×30 估算價格）")

        elif method == "fixed":
            fraction = args.fraction
            value = sizer.fixed_fraction(fraction)
            print(f"  固定比例: {fraction:.1%}")
            print(f"\n  ✅ 建議倉位: ¥{value:,.0f}")

        elif method == "kelly":
            win_rate = args.win_rate
            # 從最近回測中獲取盈虧數據
            from src.core.db import get_backtest_history

            avg_win = 1.0
            avg_loss = 1.0
            code = args.code
            if code:
                history = get_backtest_history(code=code, limit=5)
                if history:
                    # 使用最近回測的平均盈虧比
                    ratios = [h.get("profit_loss_ratio", 1.0) or 1.0 for h in history]
                    avg_ratio = np.mean(ratios)
                    avg_win = avg_ratio
                    avg_loss = 1.0
                    print(f"  從回測歷史獲取盈虧比: {avg_ratio:.2f}")

            value = sizer.kelly_position(win_rate, avg_win, avg_loss)
            kelly_f = (
                (win_rate * avg_win - (1 - win_rate)) / avg_win if avg_win > 0 else 0
            )
            print(f"  勝率: {win_rate:.1%}")
            print(f"  盈虧比: {avg_win / avg_loss:.2f}")
            print(f"  Kelly 比例: {kelly_f:.4f}")
            print(f"  Half-Kelly: {kelly_f / 2:.4f}")
            print(f"\n  ✅ 建議倉位: ¥{value:,.0f}")

        elif method == "volatility":
            target_vol = 0.15
            current_vol = 0.20
            current_pos = capital * 0.5
            value = sizer.volatility_target(target_vol, current_vol, current_pos)
            print(f"  目標波動率: {target_vol:.1%}")
            print(f"  當前波動率: {current_vol:.1%}")
            print(f"  當前持倉: ¥{current_pos:,.0f}")
            print(f"\n  ✅ 調整後倉位: ¥{value:,.0f}")

        elif method == "drawdown":
            print(f"  回撤調整倉位表:")
            print(f"  {'回撤':>8} {'縮放因子':>10} {'倉位(基礎=10萬)':>16}")
            print(f"  {'-'*36}")
            base = 100000
            for dd in [0, 3, 5, 8, 10, 15, 20, 25, 30]:
                adj = sizer.drawdown_adjusted(dd, base)
                multiplier = adj / base
                print(f"  {dd:>7.1f}% {multiplier:>9.2f}x ¥{adj:>14,.0f}")

    elif args.risk_action == "budget-check":
        # 風險預算檢查
        from src.core.risk_manager import RiskBudget, calculate_volatility
        from src.config import settings

        budget = RiskBudget(
            max_portfolio_risk=args.max_portfolio_risk,
            max_single_risk=args.max_single_risk,
        )

        # 用 watchlist 模擬持倉
        positions = []
        for code in settings.watchlist:
            vol = calculate_volatility(code)
            positions.append(
                {
                    "code": code,
                    "value": 20000,  # 假設每隻 2 萬
                    "vol": vol if vol > 0 else 0.20,
                }
            )

        portfolio = budget.portfolio_risk_budget(positions)
        suggestions = budget.suggest_rebalance(positions)

        print(f"\n{'='*70}")
        print(f"📊 風險預算檢查 (watchlist 模擬)")
        print(f"{'='*70}")
        print(f"  總市值: ¥{portfolio.get('total_value', 0):,.0f}")
        print(f"  總風險: {portfolio.get('total_risk', 0):.4f}")
        print(f"  風險預算使用率: {portfolio.get('risk_budget_used_pct', 0):.1f}%")
        print(f"  最大組合風險: {args.max_portfolio_risk:.1%}")
        print(f"  狀態: {portfolio.get('status', '未知')}")

        print(f"\n{'代碼':>8} {'權重':>8} {'波動率':>8} {'風險貢獻':>10} {'狀態':>8}")
        print("-" * 46)
        for p in portfolio.get("positions", []):
            check = budget.check_position(
                p["value"], portfolio["total_value"], p["vol"]
            )
            status_icon = (
                "✅"
                if check["status"] == "正常"
                else "⚠️" if check["status"] == "警告" else "❌"
            )
            print(
                f"{p['code']:>8} {p['weight_pct']:>7.1f}% {p['vol']:>7.4f} "
                f"{p['risk_contribution']:>9.4f} {status_icon}{check['status']:>6}"
            )

        print(f"\n再平衡建議:")
        for s in suggestions:
            action_icon = (
                "🟢"
                if s["action"] == "加倉"
                else "🔴" if s["action"] == "減倉" else "⚪"
            )
            print(
                f"  {action_icon} {s['code']}: {s['action']}  調整: ¥{s['adjustment']:,.0f}"
            )

    elif args.risk_action == "drawdown":
        # 回撤保護分析
        from src.core.risk_manager import drawdown_circuit_breaker
        import csv

        nav_data = None
        dates_data = None

        if args.nav_file:
            # 從 CSV 文件讀取
            try:
                dates_data = []
                nav_data = []
                with open(args.nav_file, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        dates_data.append(row.get("date", ""))
                        nav_data.append(float(row.get("nav", 0)))
                print(f"已讀取 {len(nav_data)} 條淨值數據")
            except Exception as e:
                print(f"❌ 讀取文件失敗: {e}")
                return

        elif args.code:
            # 用回測結果模擬
            from src.core.backtest import run_backtest

            print(f"正在回測 {args.code} 以獲取淨值序列...")
            result = run_backtest(args.code, strategy_name="dual_ma")
            nav_data = result.get("nav", [])
            dates_data = result.get("dates", [])
            print(f"回測完成，{len(nav_data)} 個數據點")

        else:
            print("❌ 請指定 --nav-file 或 --code")
            return

        if not nav_data or not dates_data:
            print("❌ 無淨值數據")
            return

        max_dd = args.max_dd
        result = drawdown_circuit_breaker(nav_data, dates_data, max_dd)

        print(f"\n{'='*70}")
        print(f"🛡️ 回撤熔斷分析 (最大回撤閾值: {max_dd}%)")
        print(f"{'='*70}")
        print(f"  實際最大回撤: {result['max_drawdown_pct']:.2f}%")
        print(f"  最大回撤日期: {result['max_dd_date']}")
        print(f"  熔斷觸發次數: {result['total_triggers']}")
        print(
            f"  會觸發停止交易: {'是 ❌' if result['would_stop_trading'] else '否 ✅'}"
        )

        breakers = result.get("circuit_breakers", [])
        if breakers:
            print(f"\n熔斷觸發詳情:")
            print(
                f"{'觸發日期':<12} {'回撤%':>8} {'峰值日期':<12} {'峰值':>12} {'觸發值':>12} {'恢復日期':<12} {'恢復天數':>8}"
            )
            print("-" * 80)
            for b in breakers:
                recovery = b.get("recovery_date", "未恢復") or "未恢復"
                days = b.get("recovery_days", "-") or "-"
                print(
                    f"{b['date']:<12} {b['drawdown_pct']:>7.2f}% {b['peak_date']:<12} "
                    f"¥{b['peak_value']:>10,.0f} ¥{b['current_value']:>10,.0f} "
                    f"{recovery:<12} {str(days):>8}"
                )
        else:
            print(f"\n✅ 未觸發回撤熔斷 — 淨值曲線在安全範圍內")

    else:
        print("用法:")
        print("  python main.py risk position-size --capital 100000 --atr 2.5")
        print(
            "  python main.py risk position-size --capital 100000 --code 600519 --method atr"
        )
        print("  python main.py risk budget-check")
        print("  python main.py risk drawdown --nav-file nav.csv")
        print("  python main.py risk drawdown --code 600519")
