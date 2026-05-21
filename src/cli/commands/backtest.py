"""CLI commands: backtest"""
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


def cmd_backtest(args):
    """回測"""
    from src.core.backtest import run_backtest, run_multi_strategy

    ensure_db()

    # 解析進階參數
    slippage = getattr(args, 'slippage', 0.0) or 0.0
    no_t1 = getattr(args, 'no_t1', False)
    no_limit = getattr(args, 'no_limit', False)
    enable_t1 = not no_t1
    enable_limit = not no_limit

    if args.strategy == "all":
        results = run_multi_strategy(args.code)
        if results:
            print(f"\n{'策略':<14} {'收益率':>10} {'夏普':>10} {'回撤':>10} {'勝率':>8} {'交易':>8}")
            print("-" * 62)
            for r in results:
                sharpe = f"{r['sharpe_ratio']:.2f}" if r['sharpe_ratio'] else "N/A"
                print(f"{r['strategy']:<14} {r['total_return_pct']:>9.2f}% {sharpe:>10} "
                      f"{r['max_drawdown_pct']:>9.2f}% {r['win_rate_pct']:>7.1f}% {r['total_trades']:>8d}")
    else:
        result = run_backtest(
            args.code, strategy_name=args.strategy,
            slippage_pct=slippage, enable_t1=enable_t1, enable_limit=enable_limit,
        )
        # 顯示進階回測摘要
        if slippage > 0 or no_t1 or no_limit:
            print(f"\n📋 進階回測配置:")
            if slippage > 0:
                print(f"  滑點: {slippage}%")
            print(f"  T+1 限制: {'啟用' if enable_t1 else '禁用'}")
            print(f"  漲跌停限制: {'啟用' if enable_limit else '禁用'}")

            # 顯示過濾器結果
            lf = result.get("limit_filter", {})
            if lf:
                print(f"  漲跌停阻止: 買入 {lf.get('blocked_buys', 0)} 次, 賣出 {lf.get('blocked_sells', 0)} 次")
            tf = result.get("t1_filter", {})
            if tf:
                print(f"  T+1 阻止賣出: {tf.get('blocked_sells', 0)} 次")

        # 顯示權益曲線分析摘要
        ea = result.get("equity_analysis", {})
        if ea:
            print(f"\n📊 權益曲線分析:")
            print(f"  水下時間佔比: {ea.get('underwater_pct', 0):.1f}%")
            print(f"  最長水下天數: {ea.get('max_underwater_days', 0)} 天")
            print(f"  平均水下天數: {ea.get('avg_underwater_days', 0)} 天")
            dd_dist = ea.get("drawdown_durations", {})
            if dd_dist:
                print(f"  回撤次數: {dd_dist.get('count', 0)}")
                print(f"  回撤平均持續: {dd_dist.get('mean_days', 0)} 天")




def cmd_optimize(args):
    """參數優化"""
    from src.core.optimize import grid_search, optuna_search, optimize_all

    ensure_db()

    if args.strategy == "all":
        optimize_all(args.code, objective=args.objective, method=args.method, n_trials=args.trials)
    else:
        if args.method == "optuna":
            results = optuna_search(args.code, args.strategy, objective=args.objective, n_trials=args.trials)
        else:
            results = grid_search(args.code, args.strategy, objective=args.objective)

        if results:
            print(f"\nTop {len(results)} 結果:")
            for i, r in enumerate(results, 1):
                params_str = ", ".join(f"{k}={v}" for k, v in r["params"].items())
                print(f"  {i}. score={r['score']:.4f}  return={r['total_return_pct']:.2f}%  "
                      f"sharpe={r.get('sharpe_ratio', 0):.2f}  [{params_str}]")




def cmd_walkforward(args):
    """Walk-Forward 分析"""
    from src.core.walkforward import walk_forward

    ensure_db()

    print(f"Walk-Forward 分析: {args.code}/{args.strategy}")
    print(f"  訓練 {args.train_days} 天, 測試 {args.test_days} 天, 步進 {args.step_days} 天")

    result = walk_forward(
        code=args.code,
        strategy_name=args.strategy,
        train_days=args.train_days,
        test_days=args.test_days,
        step_days=args.step_days,
        objective=args.objective,
        n_trials=args.trials,
    )

    print(f"\n{'='*60}")
    print(f"Walk-Forward 分析結果")
    print(f"{'='*60}")
    print(f"窗口數: {result['n_windows']}")
    print(f"平均樣本外收益: {result['avg_oos_return_pct']:+.2f}%")
    print(f"平均樣本外夏普: {result['avg_oos_sharpe']:.4f}")
    print(f"收益標準差: {result['std_oos_return_pct']:.2f}%")
    print(f"穩定性分數: {result['stability_score']:.4f}")
    print(f"過擬合比率: {result['overfit_ratio']:.4f}")
    print(f"正收益窗口: {result['positive_windows']}/{result['total_windows']}")

    print(f"\n各窗口詳情:")
    for w in result["windows"]:
        print(f"  窗口 {w['window']}: "
              f"測試 {w['test_period']} | "
              f"收益 {w['test_return_pct']:+.2f}% | "
              f"夏普 {w['test_sharpe']:.2f} | "
              f"回撤 {w['test_max_dd_pct']:.1f}% | "
              f"交易 {w['test_trades']} 次")




def cmd_auto_optimize(args):
    """自動參數優化"""
    from src.core.auto_optimize import auto_optimize_watchlist

    ensure_db()

    print(f"自動參數優化: method={args.method}, trials={args.trials}, objective={args.objective}")

    result = auto_optimize_watchlist(
        method=args.method,
        n_trials=args.trials,
        objective=args.objective,
    )

    print(f"\n{result['summary']}")

    print(f"\n{'='*60}")
    print("注意: 以上為推薦參數，不會自動寫入 config.py")
    print("如需使用，請手動更新 src/config.py 中的 strategy_params")
    print(f"{'='*60}")




def cmd_heatmap(args):
    """參數熱力圖"""
    from src.core.heatmap import param_heatmap

    ensure_db()

    print(f"熱力圖: {args.code}/{args.strategy} [{args.param_x} × {args.param_y}]")

    result = param_heatmap(
        code=args.code,
        strategy_name=args.strategy,
        param_x=args.param_x,
        param_y=args.param_y,
        grid_size=args.grid_size,
        objective=args.objective,
    )

    print(f"\n最佳參數: {result['best_params']}")
    print(f"最佳分數: {result['best_score']}")
    print(f"X 軸: {result['param_x']} = {result['x_values']}")
    print(f"Y 軸: {result['param_y']} = {result['y_values']}")

    # 簡單文本熱力圖
    print(f"\n{'='*40}")
    header = f"{'':>8}" + "".join(f"{v:>8}" for v in result["x_values"])
    print(header)
    for i, y_val in enumerate(result["y_values"]):
        row = f"{y_val:>8}" + "".join(
            f"{v:>8.2f}" if v is not None and v == v else f"{'N/A':>8}"
            for v in result["matrix"][i]
        )
        print(row)




def cmd_screen(args):
    """股票篩選"""
    from src.core.screener import screen_stocks

    ensure_db()

    filters = {}
    if args.ma_bullish:
        filters["ma_bullish"] = True
    if args.volume_surge:
        filters["volume_surge"] = {"days": 5, "ratio": args.volume_surge}
    if args.above_ma:
        filters["above_ma"] = {"period": args.above_ma}
    if args.near_high:
        filters["near_52w_high"] = {"pct": args.near_high}
    if args.price_change:
        filters["price_change_ndays"] = {"days": 5, "min_pct": args.price_change}

    if not filters:
        print("請指定至少一個篩選條件")
        return

    codes = args.codes if args.codes else None
    results = screen_stocks(codes=codes, filters=filters)

    if not results:
        print("沒有符合條件的股票")
        return

    print(f"\n{'='*60}")
    print(f"篩選結果: {len(results)} 只股票")
    print(f"{'='*60}")

    for r in results:
        filters_str = ", ".join(r["filters_passed"])
        print(f"  {r['code']:>8} {r.get('name', ''):>8}  | {filters_str}")
        if r.get("data"):
            data_str = "  ".join(f"{k}={v}" for k, v in r["data"].items())
            print(f"{'':>20}  {data_str}")


