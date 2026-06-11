"""CLI commands: signals"""

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


def cmd_signals(args):
    """實時交易信號"""
    from src.core.db import get_signal_logs
    from src.core.signals import (
        SignalEngine,
        score_signal_strength,
        compute_and_push_signals,
        get_historical_signals,
    )

    ensure_db()

    if args.action == "compute":
        # 計算實時信號
        engine = SignalEngine()
        engine.update_weights_from_backtest()

        codes = args.codes if args.codes else None
        signals_data = compute_and_push_signals(engine, codes)

        if not signals_data:
            print("無信號數據（可能缺少歷史 K 線）")
            return

        print(f"\n{'='*70}")
        print(f"實時交易信號  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*70}")

        for item in signals_data:
            code = item["code"]
            strength = item["strength"]
            signals = item["signals"]

            # 強度標記
            if strength > 30:
                icon = "🟢 強買"
            elif strength > 10:
                icon = "🟢 偏多"
            elif strength < -30:
                icon = "🔴 強賣"
            elif strength < -10:
                icon = "🔴 偏空"
            else:
                icon = "⚪ 中性"

            print(f"\n  {code}  強度: {strength:>6.1f}  {icon}")

            for s in signals:
                sig = s["signal"]
                strat = s["strategy"]
                if sig == "buy":
                    sig_icon = "🟢買"
                elif sig == "sell":
                    sig_icon = "🔴賣"
                else:
                    sig_icon = "⚪持"
                print(f"    {strat:<14} {sig_icon}  價格: {s['price']:.2f}")

        # 策略權重
        print(f"\n策略權重（夏普加權）:")
        for name, w in engine.weights.items():
            print(f"  {name:<14} {w:.2f}")

    elif args.action == "history":
        # 查看歷史信號
        code = args.code
        if not code:
            print("請指定股票代碼: python main.py signals history 600519")
            return

        days = args.days or 30
        strategy = (
            args.strategy if hasattr(args, "strategy") and args.strategy else None
        )

        # 先查數據庫
        logs = get_signal_logs(code=code, strategy=strategy, days=days)
        if not logs:
            print(f"數據庫中無 {code} 的信號記錄，嘗試回放計算...")
            logs = get_historical_signals(code=code, days=days, strategy=strategy)

        if not logs:
            print(f"無信號記錄")
            return

        print(f"\n{'='*70}")
        print(f"{code} 歷史信號 (最近 {days} 天)")
        print(f"{'='*70}")
        print(f"{'日期':<12} {'策略':<14} {'信號':>6} {'價格':>10} {'強度':>8}")
        print("-" * 54)

        for s in logs[:200]:
            sig = s["signal"]
            if sig == "buy":
                sig_icon = "  🟢買"
            elif sig == "sell":
                sig_icon = "  🔴賣"
            else:
                sig_icon = "  ⚪持"
            print(
                f"{s['triggered_at']:<12} {s['strategy']:<14} {sig_icon} {s['price']:>10.2f} {s.get('strength', 0):>8.1f}"
            )

    elif args.action == "strength":
        # 查看信號強度
        code = args.code
        if not code:
            print("請指定股票代碼: python main.py signals strength 600519")
            return

        engine = SignalEngine()
        engine.update_weights_from_backtest()
        raw_signals = engine.compute_signals([code])

        if not raw_signals:
            print(f"無法計算 {code} 的信號強度")
            return

        strength = score_signal_strength(raw_signals)

        print(f"\n{'='*50}")
        print(f"{code} 信號強度分析")
        print(f"{'='*50}")
        print(f"  綜合強度: {strength:.1f} / 100")

        if strength > 50:
            print(f"  判斷: 🟢🟢 強烈買入")
        elif strength > 20:
            print(f"  判斷: 🟢 偏多")
        elif strength > -20:
            print(f"  判斷: ⚪ 觀望")
        elif strength > -50:
            print(f"  判斷: 🔴 偏空")
        else:
            print(f"  判斷: 🔴🔴 強烈賣出")

        print(f"\n  向上計票:")
        buy_count = sum(1 for s in raw_signals if s["signal"] == "buy")
        sell_count = sum(1 for s in raw_signals if s["signal"] == "sell")
        hold_count = sum(1 for s in raw_signals if s["signal"] == "hold")
        print(f"    🟢 買入: {buy_count} 策略")
        print(f"    🔴 賣出: {sell_count} 策略")
        print(f"    ⚪ 持有: {hold_count} 策略")

        for s in raw_signals:
            sig = s["signal"]
            if sig == "buy":
                sig_icon = "🟢"
            elif sig == "sell":
                sig_icon = "🔴"
            else:
                sig_icon = "⚪"
            print(f"    {sig_icon} {s['strategy']:<14} {s.get('strength', 0):>6.1f}")

    elif args.action == "ranking":
        # 綜合信號排名
        from src.core.signals import composite_signal_ranking

        code_list = args.codes if args.codes else None
        rankings = composite_signal_ranking(codes=code_list)

        if not rankings:
            print("無法計算信號排名（可能缺少數據）")
            return

        print(f"\n{'='*80}")
        print(f"📊 綜合信號排名")
        print(f"{'='*80}")
        print(
            f"{'排名':>4} {'代碼':>8} {'綜合分數':>10} {'推薦':>10} {'最新價格':>10} {'信號數':>6}"
        )
        print("-" * 60)

        for r in rankings[:50]:
            score = r["composite_score"]
            if score > 30:
                icon = "🟢"
            elif score > 10:
                icon = "🔵"
            elif score > -10:
                icon = "⚪"
            elif score > -30:
                icon = "🟡"
            else:
                icon = "🔴"

            print(
                f"{r['rank']:>4} {r['code']:>8} {score:>8.1f}  "
                f"{icon}{r['recommendation']:>8} "
                f"{r['latest_price']:>10.2f} {r['signal_count']:>6}"
            )

            # 顯示策略詳情（前 10 名）
            if r["rank"] <= 10:
                for strat, detail in r.get("strategy_details", {}).items():
                    sig = detail["signal"]
                    sig_icon = "🟢" if sig == "buy" else "🔴" if sig == "sell" else "⚪"
                    print(
                        f"        {sig_icon} {strat:<14} 強度={detail['strength']:>6.1f}  權重={detail['weight']:.3f}"
                    )

    elif args.action == "heatmap":
        # 信號熱力圖
        from src.core.signals import signal_heatmap

        code_list = args.codes if args.codes else ([args.code] if args.code else None)
        days = args.days or 30

        heatmap = signal_heatmap(codes=code_list, days=days)

        if not heatmap or not heatmap.get("dates"):
            print("無法生成信號熱力圖（可能缺少數據）")
            return

        codes = heatmap["codes"]
        dates = heatmap["dates"]
        matrix = heatmap["matrix"]

        print(f"\n{'='*80}")
        print(f"🔥 信號熱力圖 (最近 {days} 天)")
        print(f"{'='*80}")
        print(f"分數範圍: {heatmap['min_score']:.1f} ~ {heatmap['max_score']:.1f}")

        # 顯示最近 15 天的文本熱力圖
        show_dates = dates[-15:] if len(dates) > 15 else dates
        date_indices = [dates.index(d) for d in show_dates]

        # 表頭
        header = f"{'':>8}" + "".join(f"{d[5:]:>6}" for d in show_dates)
        print(f"\n{header}")
        print("-" * (8 + len(show_dates) * 6))

        for i, code in enumerate(codes):
            row = f"{code:>8}"
            for j in date_indices:
                if j < len(matrix[i]):
                    score = matrix[i][j]
                    # 用顏色符號表示強度
                    if score > 30:
                        cell = "  ██"  # 強買
                    elif score > 10:
                        cell = "  ▓▓"  # 偏多
                    elif score > -10:
                        cell = "  ░░"  # 中性
                    elif score > -30:
                        cell = "  ▒▒"  # 偏空
                    else:
                        cell = "  ██"  # 強賣
                    row += f"{score:>6.0f}"
                else:
                    row += f"{'N/A':>6}"
            print(row)

        print(
            f"\n圖例: >30 🟢強買 | 10~30 🔵偏多 | -10~10 ⚪中性 | -30~-10 🟡偏空 | <-30 🔴強賣"
        )

    elif args.action == "backtest":
        # 信號回測驗證
        from src.core.signals import backtest_signals

        code_list = args.codes if args.codes else ([args.code] if args.code else None)
        days = args.days or 250

        print(f"正在回測驗證信號（最近 {days} 天）...")
        result = backtest_signals(codes=code_list, days=days)

        if not result:
            print("無法完成信號回測（可能缺少數據）")
            return

        overall = result.get("overall", {})
        by_strategy = result.get("by_strategy", {})

        print(f"\n{'='*80}")
        print(f"📈 信號回測驗證結果 (最近 {days} 天)")
        print(f"{'='*80}")
        print(f"總信號數: {overall.get('total_signals', 0)}")
        print(f"\n整體準確率:")
        for key in ["1d", "3d", "5d", "10d"]:
            acc = overall.get(f"accuracy_{key}", 0)
            print(f"  {key} 方向正確率: {acc:.1%}")

        print(
            f"\n{'策略':<14} {'信號數':>6} {'買/賣':>8} {'1d準確':>8} {'3d準確':>8} {'5d準確':>8} {'10d準確':>8} {'1d收益':>8}"
        )
        print("-" * 80)

        for strat_name, stats in sorted(
            by_strategy.items(), key=lambda x: x[1].get("accuracy_1d", 0), reverse=True
        ):
            print(
                f"{strat_name:<14} {stats['total_signals']:>6} "
                f"{stats['buy_signals']:>3}/{stats['sell_signals']:<3} "
                f"{stats.get('accuracy_1d', 0):>7.1%} "
                f"{stats.get('accuracy_3d', 0):>7.1%} "
                f"{stats.get('accuracy_5d', 0):>7.1%} "
                f"{stats.get('accuracy_10d', 0):>7.1%} "
                f"{stats.get('avg_return_1d', 0):>7.2f}%"
            )

        # 最近信號明細
        details = result.get("signal_details", [])
        if details:
            print(f"\n最近信號明細 (前 20 條):")
            print(
                f"{'日期':<12} {'代碼':>8} {'策略':<14} {'信號':>6} {'價格':>10} {'1d收益':>8}"
            )
            print("-" * 62)
            for d in details[:20]:
                sig = d.get("signal", "")
                sig_icon = "🟢" if sig == "buy" else "🔴" if sig == "sell" else "⚪"
                print(
                    f"{d.get('date', ''):<12} {d.get('code', ''):>8} {d.get('strategy', ''):<14} "
                    f"{sig_icon}{sig:>4} {d.get('price', 0):>10.2f} {d.get('return_1d', 0):>7.2f}%"
                )

    else:
        print("用法:")
        print("  python main.py signals compute [codes...]    # 計算實時信號")
        print("  python main.py signals history <code>        # 查看歷史信號")
        print("  python main.py signals strength <code>       # 查看信號強度")
        print("  python main.py signals ranking               # 綜合信號排名")
        print("  python main.py signals heatmap --code 600519 # 信號熱力圖")
        print("  python main.py signals backtest --code 600519 # 信號回測驗證")
