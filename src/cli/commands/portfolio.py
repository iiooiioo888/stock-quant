"""CLI commands: portfolio"""
from datetime import datetime

import numpy as np

from src.cli.helpers import (
    DEFAULT_ALLOCATIONS,
    EXTENDED_ALLOCATIONS,
    add_alloc_arg,
    ensure_db,
    fail_result,
    get_allocations,
    is_a_share_trading_now,
    parse_allocations,
    print_portfolio_metrics,
)


def cmd_portfolio(args):
    """組合回測"""
    from src.core.portfolio import run_portfolio

    ensure_db()
    run_portfolio(allocations=get_allocations(args))




def cmd_dynamic_portfolio(args):
    """動態權重組合回測"""
    from src.core.portfolio import dynamic_weight_portfolio

    ensure_db()

    print(f"動態權重組合回測: 窗口={args.window}天, 調整頻率={args.freq}天")
    result = dynamic_weight_portfolio(
        allocations=get_allocations(args),
        rolling_window=args.window,
        rebalance_freq_days=args.freq,
    )
    if fail_result(result, label="回測"):
        return

    print_portfolio_metrics(result.get("portfolio", {}), title="動態權重組合結果")

    print(f"\n子策略表現:")
    for s in result.get("sub_strategies", []):
        print(f"  {s['strategy']}/{s['code']}: {s['total_return_pct']:+.2f}%  夏普={s.get('sharpe_ratio', 0):.2f}")




def cmd_kelly(args):
    """Kelly 公式計算最優倉位"""
    from src.core.portfolio import kelly_criterion

    ensure_db()

    allocations = parse_allocations(getattr(args, "alloc", ""))

    print(f"Kelly 公式計算: 上限={args.limit}")
    result = kelly_criterion(
        allocations=allocations,
        fraction_limit=args.limit,
    )

    if not result:
        print("計算失敗")
        return

    print(f"\n{'='*70}")
    print(f"{'策略':<14} {'勝率':>8} {'賠率':>8} {'Kelly':>10} {'半Kelly':>10} {'推薦倉位':>12}")
    print("-" * 70)
    for r in result.get("kelly_results", []):
        if "error" in r:
            print(f"{r['strategy']}/{r['code']:<8} 計算錯誤: {r['error']}")
            continue
        print(
            f"{r['strategy']}/{r['code']:<8} "
            f"{r['win_rate']:>7.1f}% "
            f"{r['odds_ratio']:>8.2f} "
            f"{r['kelly_fraction']:>10.4f} "
            f"{r['half_kelly_fraction']:>10.4f} "
            f"¥{r['recommended_position']:>10,.0f}"
        )




def cmd_degradation(args):
    """策略衰退檢測"""
    from src.core.portfolio import detect_degradation

    ensure_db()

    allocations = parse_allocations(getattr(args, "alloc", ""))

    print(f"衰退檢測: 回看={args.lookback}天, 閾值={args.threshold}天")
    result = detect_degradation(
        allocations=allocations,
        lookback_days=args.lookback,
        threshold_days=args.threshold,
    )

    if not result:
        print("檢測失敗")
        return

    print(f"\n{'='*70}")
    print(f"{'策略':<14} {'連續跑輸':>10} {'狀態':>8} {'近期收益':>10} {'基準收益':>10} {'調整權重':>10}")
    print("-" * 70)
    for i, s in enumerate(result.get("degradation_status", [])):
        status = "⚠ 衰退" if s["is_degraded"] else "✓ 正常"
        w = result["adjusted_weights"][i]
        print(
            f"{s['strategy']}/{s['code']:<8} "
            f"{s['consecutive_underperform_days']:>8}天 "
            f"{status:>8} "
            f"{s['recent_return_pct']:>+9.2f}% "
            f"{s['benchmark_return_pct']:>+9.2f}% "
            f"{w:>10.2%}"
        )




def cmd_arbitrate(args):
    """信號衝突仲裁"""
    from src.core.portfolio import arbitrate_signals

    ensure_db()

    # 示例：模擬多策略信號
    strategy_signals = [
        {"strategy": "dual_ma", "code": "000001", "signal": "buy"},
        {"strategy": "macd", "code": "600519", "signal": "sell"},
        {"strategy": "bollinger", "code": "000858", "signal": "buy"},
    ]

    allocations = parse_allocations(getattr(args, "alloc", ""))

    print(f"信號衝突仲裁: {len(strategy_signals)} 個策略信號")
    result = arbitrate_signals(
        strategy_signals=strategy_signals,
        allocations=allocations,
    )

    if not result:
        print("仲裁失敗")
        return

    print(f"\n{'='*60}")
    print(f"投票詳情:")
    for v in result.get("vote_details", []):
        print(f"  {v['strategy']}/{v['code']}: {v['signal']:>4}  權重={v['weight']:.4f}  投票值={v['vote_value']:+.4f}")

    print(f"\n{'='*60}")
    print(f"最終決策: {result['final_action'].upper()}")
    print(f"信心度: {result['confidence']:.2%}")
    print(f"買入分: {result['buy_score']:.4f}  賣出分: {result['sell_score']:.4f}  持有分: {result['hold_score']:.4f}")
    print(f"衝突程度: {result['conflict_level']}")




def cmd_risk_parity(args):
    """風險平價組合"""
    from src.core.portfolio import risk_parity_portfolio

    ensure_db()

    allocations = parse_allocations(getattr(args, "alloc", ""))

    print(f"風險平價組合回測...")
    result = risk_parity_portfolio(allocations=allocations)

    if not result or "error" in result:
        print(f"失敗: {result.get('error', '未知錯誤')}")
        return

    pm = result.get("portfolio", {})
    print(f"\n{'='*70}")
    print(f"風險平價組合結果")
    print(f"{'='*70}")
    print(f"總收益: {pm.get('total_return_pct', 0):+.2f}%")
    print(f"年化收益: {pm.get('annual_return_pct', 0):+.2f}%")
    print(f"夏普比率: {pm.get('sharpe_ratio', 0):.4f}")
    print(f"最大回撤: {pm.get('max_drawdown_pct', 0):.2f}%")

    print(f"\n{'策略':<14} {'權重':>8} {'風險貢獻':>10} {'收益率':>10} {'夏普':>8}")
    print("-" * 54)
    for s in result.get("sub_strategies", []):
        print(
            f"{s['strategy']}/{s['code']:<8} "
            f"{s['weight']:>7.1%} "
            f"{s.get('risk_contribution_pct', 0):>9.1f}% "
            f"{s['total_return_pct']:>+9.2f}% "
            f"{s.get('sharpe_ratio', 0):>8.2f}"
        )




def cmd_mvo(args):
    """均值-方差優化"""
    from src.core.portfolio import mean_variance_optimize

    ensure_db()

    allocations = parse_allocations(getattr(args, "alloc", ""))

    print(f"均值-方差優化: 目標={args.objective}, 模擬={args.simulations}次")
    result = mean_variance_optimize(
        allocations=allocations,
        objective=args.objective,
        n_simulations=args.simulations,
    )

    if not result or "error" in result:
        print(f"失敗: {result.get('error', '未知錯誤')}")
        return

    pm = result.get("portfolio", {})
    print(f"\n{'='*70}")
    print(f"Markowitz 最優組合 ({args.objective})")
    print(f"{'='*70}")
    print(f"最優年化收益: {result.get('optimal_return_pct', 0):+.2f}%")
    print(f"最優年化波動: {result.get('optimal_volatility_pct', 0):.2f}%")
    print(f"最優夏普比率: {result.get('optimal_sharpe', 0):.4f}")
    print(f"組合最大回撤: {pm.get('max_drawdown_pct', 0):.2f}%")

    print(f"\n最優權重:")
    for s in result.get("sub_strategies", []):
        print(f"  {s['strategy']}/{s['code']}: {s['weight']:.1%}")

    frontier = result.get("frontier_points", [])
    if frontier:
        print(f"\n有效前沿: {len(frontier)} 個點")
        print(f"  風險範圍: {frontier[0]['risk']:.2f}% ~ {frontier[-1]['risk']:.2f}%")




def cmd_vol_target(args):
    """波動率目標組合"""
    from src.core.portfolio import volatility_targeting

    ensure_db()

    allocations = parse_allocations(getattr(args, "alloc", ""))

    print(f"波動率目標組合: 目標={args.target:.0%}, 窗口={args.lookback}天")
    result = volatility_targeting(
        allocations=allocations,
        target_vol=args.target,
        lookback_days=args.lookback,
    )

    if not result or "error" in result:
        print(f"失敗: {result.get('error', '未知錯誤')}")
        return

    pm = result.get("portfolio", {})
    print(f"\n{'='*70}")
    print(f"波動率目標組合結果")
    print(f"{'='*70}")
    print(f"總收益: {pm.get('total_return_pct', 0):+.2f}%")
    print(f"年化收益: {pm.get('annual_return_pct', 0):+.2f}%")
    print(f"夏普比率: {pm.get('sharpe_ratio', 0):.4f}")
    print(f"最大回撤: {pm.get('max_drawdown_pct', 0):.2f}%")
    print(f"平均槓桿: {result.get('avg_leverage', 0):.2f}x")
    print(f"槓桿範圍: {result.get('min_leverage', 0):.2f}x ~ {result.get('max_leverage', 0):.2f}x")




def cmd_max_diversification(args):
    """最大分散化組合"""
    from src.core.portfolio import max_diversification_portfolio

    ensure_db()

    allocations = parse_allocations(getattr(args, "alloc", ""))

    print(f"最大分散化組合...")
    result = max_diversification_portfolio(allocations=allocations)

    if not result or "error" in result:
        print(f"失敗: {result.get('error', '未知錯誤')}")
        return

    pm = result.get("portfolio", {})
    print(f"\n{'='*70}")
    print(f"最大分散化組合結果")
    print(f"{'='*70}")
    print(f"分散化比率: {result.get('diversification_ratio', 0):.4f}")
    print(f"總收益: {pm.get('total_return_pct', 0):+.2f}%")
    print(f"年化收益: {pm.get('annual_return_pct', 0):+.2f}%")
    print(f"夏普比率: {pm.get('sharpe_ratio', 0):.4f}")
    print(f"最大回撤: {pm.get('max_drawdown_pct', 0):.2f}%")

    print(f"\n最優權重:")
    for s in result.get("sub_strategies", []):
        print(f"  {s['strategy']}/{s['code']}: {s['weight']:.1%}")




def cmd_anti_corr(args):
    """反相關組合"""
    from src.core.portfolio import anti_correlation_portfolio

    ensure_db()

    allocations = parse_allocations(getattr(args, "alloc", ""))

    print(f"反相關組合...")
    result = anti_correlation_portfolio(allocations=allocations)

    if not result or "error" in result:
        print(f"失敗: {result.get('error', '未知錯誤')}")
        return

    pm = result.get("portfolio", {})
    print(f"\n{'='*70}")
    print(f"反相關組合結果")
    print(f"{'='*70}")
    print(f"平均相關性: {result.get('avg_pairwise_correlation', 0):.4f}")
    print(f"組合相關性分數: {result.get('portfolio_correlation_score', 0):.4f}")
    print(f"總收益: {pm.get('total_return_pct', 0):+.2f}%")
    print(f"夏普比率: {pm.get('sharpe_ratio', 0):.4f}")
    print(f"最大回撤: {pm.get('max_drawdown_pct', 0):.2f}%")

    print(f"\n最優權重:")
    for s in result.get("sub_strategies", []):
        print(f"  {s['strategy']}/{s['code']}: {s['weight']:.1%}")

    # 相關性矩陣
    corr = result.get("correlation_matrix", {})
    if corr.get("labels"):
        print(f"\n相關性矩陣:")
        labels = corr["labels"]
        header = f"{'':>16}" + "".join(f"{l:>16}" for l in labels)
        print(header)
        for i, row in enumerate(corr["matrix"]):
            row_str = f"{labels[i]:>16}" + "".join(f"{v:>16.4f}" for v in row)
            print(row_str)




def cmd_regime_switch(args):
    """市場狀態切換組合"""
    from src.core.portfolio import regime_switch_portfolio

    ensure_db()

    allocations = parse_allocations(getattr(args, "alloc", ""))

    print(f"狀態切換組合: 方法={args.method}, 窗口={args.lookback}天")
    result = regime_switch_portfolio(
        allocations=allocations,
        regime_method=args.method,
        lookback_days=args.lookback,
    )

    if not result or "error" in result:
        print(f"失敗: {result.get('error', '未知錯誤')}")
        return

    pm = result.get("portfolio", {})
    print(f"\n{'='*70}")
    print(f"狀態切換組合結果")
    print(f"{'='*70}")
    print(f"總收益: {pm.get('total_return_pct', 0):+.2f}%")
    print(f"年化收益: {pm.get('annual_return_pct', 0):+.2f}%")
    print(f"夏普比率: {pm.get('sharpe_ratio', 0):.4f}")
    print(f"最大回撤: {pm.get('max_drawdown_pct', 0):.2f}%")

    print(f"\n狀態分佈:")
    for regime, count in result.get("regime_counts", {}).items():
        print(f"  {regime}: {count} 次")




def cmd_black_litterman(args):
    """Black-Litterman 模型組合"""
    from src.core.portfolio import black_litterman_portfolio

    ensure_db()

    allocations = parse_allocations(getattr(args, "alloc", ""))

    # 默認觀點
    views = {"dual_ma/000001": 0.10, "macd/600519": 0.15}
    confidence = {"dual_ma/000001": 0.7, "macd/600519": 0.8}

    print(f"Black-Litterman 模型: {len(allocations)} 個子策略")
    result = black_litterman_portfolio(
        allocations=allocations, views=views, confidence=confidence,
    )

    if not result or "error" in result:
        print(f"失敗: {result.get('error', '未知錯誤')}")
        return

    pm = result.get("portfolio", {})
    print(f"\n{'='*70}")
    print(f"Black-Litterman 組合結果")
    print(f"{'='*70}")
    print(f"風險厭惡係數: {result.get('risk_aversion', 0):.4f}")
    print(f"總收益: {pm.get('total_return_pct', 0):+.2f}%")
    print(f"年化收益: {pm.get('annual_return_pct', 0):+.2f}%")
    print(f"夏普比率: {pm.get('sharpe_ratio', 0):.4f}")
    print(f"最大回撤: {pm.get('max_drawdown_pct', 0):.2f}%")

    print(f"\n{'策略':<16} {'先驗收益':>10} {'後驗收益':>10} {'最優權重':>10}")
    print("-" * 50)
    for s in result.get("sub_strategies", []):
        print(
            f"{s['strategy']}/{s['code']:<10} "
            f"{s.get('prior_return', 0):>+9.2f}% "
            f"{s.get('posterior_return', 0):>+9.2f}% "
            f"{s['weight']:>9.1%}"
        )




def cmd_hrp(args):
    """層次風險平價組合"""
    from src.core.portfolio import hierarchical_risk_parity

    ensure_db()

    allocations = parse_allocations(getattr(args, "alloc", ""))

    print(f"層次風險平價 (HRP) 組合...")
    result = hierarchical_risk_parity(allocations=allocations)

    if not result or "error" in result:
        print(f"失敗: {result.get('error', '未知錯誤')}")
        return

    pm = result.get("portfolio", {})
    print(f"\n{'='*70}")
    print(f"HRP 組合結果")
    print(f"{'='*70}")
    print(f"總收益: {pm.get('total_return_pct', 0):+.2f}%")
    print(f"年化收益: {pm.get('annual_return_pct', 0):+.2f}%")
    print(f"夏普比率: {pm.get('sharpe_ratio', 0):.4f}")
    print(f"最大回撤: {pm.get('max_drawdown_pct', 0):.2f}%")

    print(f"\n最優權重:")
    for s in result.get("sub_strategies", []):
        print(f"  {s['strategy']}/{s['code']}: {s['weight']:.1%}")

    sort_order = result.get("sort_order", [])
    if sort_order:
        print(f"\n聚類排序: {' → '.join(sort_order)}")




def cmd_cvar(args):
    """CVaR 優化組合"""
    from src.core.portfolio import cvar_optimize

    ensure_db()

    allocations = parse_allocations(getattr(args, "alloc", ""))

    print(f"CVaR 優化: alpha={args.alpha}")
    result = cvar_optimize(allocations=allocations, alpha=args.alpha)

    if not result or "error" in result:
        print(f"失敗: {result.get('error', '未知錯誤')}")
        return

    pm = result.get("portfolio", {})
    print(f"\n{'='*70}")
    print(f"CVaR 優化結果")
    print(f"{'='*70}")
    print(f"最優 CVaR: {result.get('optimal_cvar', 0):.4f}%")
    print(f"最優 VaR:  {result.get('optimal_var', 0):.4f}%")
    print(f"等權 CVaR: {result.get('equal_weight_cvar', 0):.4f}%")
    print(f"總收益: {pm.get('total_return_pct', 0):+.2f}%")
    print(f"夏普比率: {pm.get('sharpe_ratio', 0):.4f}")
    print(f"最大回撤: {pm.get('max_drawdown_pct', 0):.2f}%")

    print(f"\n最優權重:")
    for s in result.get("sub_strategies", []):
        print(f"  {s['strategy']}/{s['code']}: {s['weight']:.1%}  (個股CVaR={s.get('individual_cvar', 0):.4f}%)")




def cmd_multi_timeframe(args):
    """多時間框架信號確認"""
    from src.core.portfolio import multi_timeframe_signal

    ensure_db()

    allocations = parse_allocations(getattr(args, "alloc", ""))

    windows = [int(w) for w in args.windows.split(",")] if args.windows else [5, 20, 60]
    print(f"多時間框架信號: 窗口={windows}")
    result = multi_timeframe_signal(allocations=allocations, windows=windows)

    if not result or "error" in result:
        print(f"失敗: {result.get('error', '未知錯誤')}")
        return

    print(f"\n{'='*70}")
    print(f"多時間框架信號結果")
    print(f"{'='*70}")

    for s in result.get("strategy_signals", []):
        print(f"\n  {s['label']}:")
        for tf, sig in s.get("timeframe_signals", {}).items():
            icon = "🟢" if sig["signal"] == "buy" else "🔴" if sig["signal"] == "sell" else "⚪"
            print(f"    {tf:>4}: {icon} {sig['signal']:>4}  收益={sig.get('return_pct', 0):+.2f}%")
        conf_icon = "🟢" if s["confirmed_signal"] == "buy" else "🔴" if s["confirmed_signal"] == "sell" else "⚪"
        print(f"    確認: {conf_icon} {s['confirmed_signal']}  (一致性={s['agreement_score']:.0%})")

    print(f"\n整體信號: {result.get('overall_signal', 'hold').upper()}")
    print(f"  買入: {result.get('overall_buy_count', 0)}  賣出: {result.get('overall_sell_count', 0)}  持有: {result.get('overall_hold_count', 0)}")




def cmd_dynamic_rebalance(args):
    """動態再平衡觸發"""
    from src.core.portfolio import dynamic_rebalance_trigger

    ensure_db()

    allocations = parse_allocations(getattr(args, "alloc", ""))

    print(f"動態再平衡: 閾值={args.threshold}%, 波動率窗口={args.vol_window}天")
    result = dynamic_rebalance_trigger(
        allocations=allocations, threshold_pct=args.threshold, vol_window=args.vol_window,
    )

    if not result or "error" in result:
        print(f"失敗: {result.get('error', '未知錯誤')}")
        return

    pm = result.get("portfolio", {})
    print(f"\n{'='*70}")
    print(f"動態再平衡結果")
    print(f"{'='*70}")
    print(f"總收益: {pm.get('total_return_pct', 0):+.2f}%")
    print(f"夏普比率: {pm.get('sharpe_ratio', 0):.4f}")
    print(f"最大回撤: {pm.get('max_drawdown_pct', 0):.2f}%")
    print(f"再平衡次數: {result.get('total_rebalances', 0)}")

    for rb in result.get("rebalance_history", [])[:10]:
        print(f"\n  [{rb['date']}] 偏移={rb['max_drift_pct']:.1f}%")
        for reason in rb.get("reasons", []):
            print(f"    → {reason}")




def cmd_sector_limit(args):
    """板塊敞口限制"""
    from src.core.portfolio import sector_exposure_limit

    ensure_db()

    allocations = parse_allocations(getattr(args, "alloc", ""))

    print(f"板塊敞口限制: 最大佔比={args.max_pct}%")
    result = sector_exposure_limit(allocations=allocations, max_sector_pct=args.max_pct)

    if not result or "error" in result:
        print(f"失敗: {result.get('error', '未知錯誤')}")
        return

    pm = result.get("portfolio", {})
    print(f"\n{'='*70}")
    print(f"板塊敞口限制結果")
    print(f"{'='*70}")
    print(f"總收益: {pm.get('total_return_pct', 0):+.2f}%")
    print(f"夏普比率: {pm.get('sharpe_ratio', 0):.4f}")
    print(f"最大回撤: {pm.get('max_drawdown_pct', 0):.2f}%")

    print(f"\n板塊分佈:")
    for sector, info in result.get("sector_breakdown", {}).items():
        print(f"  {sector}: {info['weight_pct']:.1f}%  ({info['count']} 策略)")

    print(f"\n最優權重:")
    for s in result.get("sub_strategies", []):
        print(f"  {s['strategy']}/{s['code']}: {s['weight']:.1%}  [{s.get('sector', '')}]")




def cmd_voting_portfolio(args):
    """投票式組合回測"""
    from src.core.portfolio import strategy_voting_portfolio

    ensure_db()
    allocations = get_allocations(args) if getattr(args, "alloc", "") else list(EXTENDED_ALLOCATIONS)

    print(f"投票式組合: 最低票數={args.min_votes}")
    result = strategy_voting_portfolio(
        allocations=allocations,
        min_votes=args.min_votes,
    )

    if not result or "error" in result:
        print(f"失敗: {result.get('error', '未知錯誤')}")
        return

    pm = result.get("portfolio", {})
    vs = result.get("vote_summary", {})
    print(f"\n{'='*70}")
    print(f"投票式組合結果")
    print(f"{'='*70}")
    print(f"總收益: {pm.get('total_return_pct', 0):+.2f}%")
    print(f"年化收益: {pm.get('annual_return_pct', 0):+.2f}%")
    print(f"夏普比率: {pm.get('sharpe_ratio', 0):.4f}")
    print(f"最大回撤: {pm.get('max_drawdown_pct', 0):.2f}%")
    print(f"\n投票統計:")
    print(f"  買入天數: {vs.get('buy_days', 0)}")
    print(f"  賣出天數: {vs.get('sell_days', 0)}")
    print(f"  持有天數: {vs.get('hold_days', 0)}")
    print(f"  總天數: {vs.get('total_days', 0)}")




def cmd_momentum_of_momentum(args):
    """動量的動量組合回測"""
    from src.core.portfolio import momentum_of_momentum

    ensure_db()

    allocations = parse_allocations(getattr(args, "alloc", ""))

    print(f"動量的動量: 回看={args.lookback}天")
    result = momentum_of_momentum(
        allocations=allocations,
        lookback=args.lookback,
    )

    if not result or "error" in result:
        print(f"失敗: {result.get('error', '未知錯誤')}")
        return

    pm = result.get("portfolio", {})
    print(f"\n{'='*70}")
    print(f"動量的動量組合結果")
    print(f"{'='*70}")
    print(f"總收益: {pm.get('total_return_pct', 0):+.2f}%")
    print(f"年化收益: {pm.get('annual_return_pct', 0):+.2f}%")
    print(f"夏普比率: {pm.get('sharpe_ratio', 0):.4f}")
    print(f"最大回撤: {pm.get('max_drawdown_pct', 0):.2f}%")

    # 顯示最近一次動量記錄
    mom = result.get("momentum_history", [])
    if mom:
        latest = mom[-1]
        print(f"\n最新動量記錄 (第 {latest['day']} 天):")
        for i, s in enumerate(result.get("sub_strategies", [])):
            fm = latest["first_momentum"][i] if i < len(latest["first_momentum"]) else 0
            sm = latest["second_momentum"][i] if i < len(latest["second_momentum"]) else 0
            w = latest["weights"][i] if i < len(latest["weights"]) else 0
            trend = "↑" if sm > 0 else "↓" if sm < 0 else "→"
            print(f"  {s['strategy']}/{s['code']}: Sharpe={fm:.2f} {trend} (Δ={sm:+.2f}), 權重={w:.1%}")




def cmd_adaptive_regime(args):
    """自適應市場狀態組合回測"""
    from src.core.portfolio import adaptive_regime_portfolio

    ensure_db()
    allocations = get_allocations(args) if getattr(args, "alloc", "") else list(EXTENDED_ALLOCATIONS)

    print(f"自適應市場狀態組合...")
    result = adaptive_regime_portfolio(allocations=allocations)

    if not result or "error" in result:
        print(f"失敗: {result.get('error', '未知錯誤')}")
        return

    pm = result.get("portfolio", {})
    rc = result.get("regime_counts", {})
    rws = result.get("regime_weight_summary", {})
    print(f"\n{'='*70}")
    print(f"自適應市場狀態組合結果")
    print(f"{'='*70}")
    print(f"總收益: {pm.get('total_return_pct', 0):+.2f}%")
    print(f"年化收益: {pm.get('annual_return_pct', 0):+.2f}%")
    print(f"夏普比率: {pm.get('sharpe_ratio', 0):.4f}")
    print(f"最大回撤: {pm.get('max_drawdown_pct', 0):.2f}%")

    thresholds = result.get("vol_thresholds", {})
    print(f"\n波動率閾值: 低<{thresholds.get('low', 0.15):.0%}, 高>{thresholds.get('high', 0.25):.0%}")

    print(f"\n狀態分佈:")
    for regime, count in rc.items():
        print(f"  {regime}: {count} 次")

    if rws:
        print(f"\n各狀態平均權重:")
        for regime, info in rws.items():
            weights_str = ", ".join(
                f"{result['sub_strategies'][i]['strategy']}={w:.1%}"
                for i, w in enumerate(info["avg_weights"])
            )
            print(f"  {regime} ({info['count']}次): {weights_str}")


