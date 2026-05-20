#!/usr/bin/env python3
"""
stock-quant 主入口

用法:
  python main.py serve              # 啟動 Web 服務
  python main.py serve --port 8080  # 自定義端口
  python main.py download           # 下載歷史數據
  python main.py download 000001 600519
  python main.py backtest 000001    # 回測
  python main.py backtest 000001 macd
  python main.py backtest 000001 all
  python main.py backtest 000001 momentum     # 動量策略
  python main.py backtest 000001 mean_reversion  # 均值回歸
  python main.py backtest 000001 composite    # 多策略組合
  python main.py optimize 000001   # 參數優化
  python main.py optimize 000001 --method optuna
  python main.py portfolio          # 組合回測
  python main.py voting-portfolio   # 投票式組合
  python main.py momentum-of-momentum  # 動量的動量組合
  python main.py adaptive-regime    # 自適應狀態組合
  python main.py monitor            # 實時盯盤
"""
import sys
import argparse
import numpy as np
import uvicorn
from datetime import datetime


# 默認組合分配（可通過 --alloc 參數覆蓋）
DEFAULT_ALLOCATIONS = [
    {"strategy": "dual_ma", "code": "000001"},
    {"strategy": "macd", "code": "600519"},
    {"strategy": "bollinger", "code": "000858"},
]


def parse_allocations(alloc_str: str) -> list[dict]:
    """
    解析組合分配字符串。
    格式: "strategy:code,strategy:code,..."
    例: "dual_ma:000001,macd:600519,bollinger:000858"
    """
    if not alloc_str:
        return DEFAULT_ALLOCATIONS
    allocs = []
    for pair in alloc_str.split(","):
        parts = pair.strip().split(":")
        if len(parts) == 2:
            allocs.append({"strategy": parts[0].strip(), "code": parts[1].strip()})
    return allocs if allocs else DEFAULT_ALLOCATIONS


def add_alloc_arg(parser):
    """為子命令添加 --alloc 參數"""
    parser.add_argument(
        "--alloc", type=str, default="",
        help='組合分配，格式: "strategy:code,strategy:code,..."（留空使用默認）',
    )


def cmd_config(args):
    """查看當前配置"""
    from src.config import settings

    if args.config_action == "show":
        print(settings.summary())
        if args.verbose:
            print(f"\n{'='*60}")
            print("策略參數:")
            for name, params in sorted(settings.strategy_params.items()):
                params_str = ", ".join(f"{k}={v}" for k, v in params.items())
                print(f"  {name:<20} {params_str}")
            print(f"\n預設組合:")
            for key, preset in settings.portfolio_presets.items():
                n = len(preset.get("allocations", []))
                print(f"  {key:<20} {preset['name']}  ({n} 子策略)")

    elif args.config_action == "validate":
        errors = []
        warnings = []

        # 檢查策略參數是否完整
        try:
            from src.core.backtest import STRATEGIES
            for name in STRATEGIES:
                if name not in settings.strategy_params:
                    warnings.append(f"策略 '{name}' 缺少默認參數配置")
        except ImportError:
            pass

        # 檢查 watchlist 格式
        for code in settings.watchlist:
            if not code.isdigit() or len(code) != 6:
                errors.append(f"無效股票代碼: {code}")

        # 檢查端口
        if settings.web_port < 1024:
            warnings.append(f"端口 {settings.web_port} 需要 root 權限")

        # 檢查 Redis 連接
        if settings.redis_enabled:
            try:
                import redis
                r = redis.from_url(settings.redis_url)
                r.ping()
                print("  ✅ Redis 連接正常")
            except Exception as e:
                errors.append(f"Redis 連接失敗: {e}")

        # 輸出
        print(f"\n{'='*60}")
        print("配置驗證結果")
        print(f"{'='*60}")
        if errors:
            for e in errors:
                print(f"  ❌ {e}")
        if warnings:
            for w in warnings:
                print(f"  ⚠️  {w}")
        if not errors and not warnings:
            print("  ✅ 所有配置項通過驗證")
        print(f"\n  錯誤: {len(errors)} | 警告: {len(warnings)}")


def cmd_serve(args):
    """啟動 Web 服務"""
    from src.config import settings
    uvicorn.run(
        "src.api.app:app",
        host=args.host or settings.web_host,
        port=args.port or settings.web_port,
        workers=args.workers or settings.web_workers,
        reload=args.reload,
        log_level="info",
    )


def cmd_download(args):
    """下載歷史數據"""
    from src.core.db import init_db
    from src.core.history import download_all, download_incremental

    init_db()
    codes = args.codes if args.codes else None

    if args.incremental:
        result = download_incremental(codes, force=args.force)
        print(f"\n增量更新完成:")
        print(f"  更新: {result['updated']} 只")
        print(f"  跳過: {result['skipped']} 只")
        print(f"  新數據: {result['total_records']} 條")
    else:
        download_all(codes)


def cmd_backtest(args):
    """回測"""
    from src.core.db import init_db
    from src.core.backtest import run_backtest, run_multi_strategy

    init_db()

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
    from src.core.db import init_db
    from src.core.optimize import grid_search, optuna_search, optimize_all

    init_db()

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


def cmd_portfolio(args):
    """組合回測"""
    from src.core.db import init_db
    from src.core.portfolio import run_portfolio

    init_db()

    allocations = parse_allocations(getattr(args, 'alloc', ''))
    run_portfolio(allocations=allocations)


def cmd_monitor(args):
    """實時盯盤"""
    import time
    from datetime import datetime
    from src.config import settings
    from src.core.db import init_db
    from src.core.realtime import fetch_realtime
    from src.core.alerts import AlertEngine

    init_db()
    engine = AlertEngine()
    codes = settings.watchlist

    print(f"盯盤啟動: {', '.join(codes)} | 間隔 {settings.poll_interval_sec}s | Ctrl+C 停止")

    try:
        while True:
            now = datetime.now()
            if now.weekday() >= 5 or not (915 <= now.hour * 100 + now.minute <= 1500):
                print(f"\r⏳ {now.strftime('%H:%M:%S')} 非交易時段...", end="", flush=True)
                time.sleep(30)
                continue

            try:
                df = fetch_realtime(codes)
                if not df.empty:
                    engine.process(df)
                    print(f"\n── {now.strftime('%H:%M:%S')} ──")
                    for _, row in df.iterrows():
                        chg = row.get('change_pct', 0)
                        icon = "🔴" if chg > 0 else "🟢" if chg < 0 else "  "
                        print(f"  {row['code']} {row['price']:>8.2f} {icon}{chg:>+.2f}%")
            except Exception as e:
                print(f"\n⚠ {e}")

            time.sleep(settings.poll_interval_sec)
    except KeyboardInterrupt:
        print(f"\n盯盤結束，觸發 {engine.total_alerts} 條預警")


def cmd_walkforward(args):
    """Walk-Forward 分析"""
    from src.core.db import init_db
    from src.core.walkforward import walk_forward

    init_db()

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
    from src.core.db import init_db
    from src.core.auto_optimize import auto_optimize_watchlist

    init_db()

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
    from src.core.db import init_db
    from src.core.heatmap import param_heatmap

    init_db()

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
    from src.core.db import init_db
    from src.core.screener import screen_stocks

    init_db()

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


def cmd_dynamic_portfolio(args):
    """動態權重組合回測"""
    from src.core.db import init_db
    from src.core.portfolio import dynamic_weight_portfolio

    init_db()

    allocations = parse_allocations(getattr(args, 'alloc', ''))

    print(f"動態權重組合回測: 窗口={args.window}天, 調整頻率={args.freq}天")
    result = dynamic_weight_portfolio(
        allocations=allocations,
        rolling_window=args.window,
        rebalance_freq_days=args.freq,
    )

    if not result:
        print("回測失敗")
        return

    pm = result.get("portfolio", {})
    print(f"\n{'='*60}")
    print(f"動態權重組合結果")
    print(f"{'='*60}")
    print(f"總收益: {pm.get('total_return_pct', 0):+.2f}%")
    print(f"年化收益: {pm.get('annual_return_pct', 0):+.2f}%")
    print(f"夏普比率: {pm.get('sharpe_ratio', 0):.4f}")
    print(f"最大回撤: {pm.get('max_drawdown_pct', 0):.2f}%")

    print(f"\n子策略表現:")
    for s in result.get("sub_strategies", []):
        print(f"  {s['strategy']}/{s['code']}: {s['total_return_pct']:+.2f}%  夏普={s.get('sharpe_ratio', 0):.2f}")


def cmd_kelly(args):
    """Kelly 公式計算最優倉位"""
    from src.core.db import init_db
    from src.core.portfolio import kelly_criterion

    init_db()

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
    from src.core.db import init_db
    from src.core.portfolio import detect_degradation

    init_db()

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
    from src.core.db import init_db
    from src.core.portfolio import arbitrate_signals

    init_db()

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
    from src.core.db import init_db
    from src.core.portfolio import risk_parity_portfolio

    init_db()

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
    from src.core.db import init_db
    from src.core.portfolio import mean_variance_optimize

    init_db()

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
    from src.core.db import init_db
    from src.core.portfolio import volatility_targeting

    init_db()

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
    from src.core.db import init_db
    from src.core.portfolio import max_diversification_portfolio

    init_db()

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
    from src.core.db import init_db
    from src.core.portfolio import anti_correlation_portfolio

    init_db()

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
    from src.core.db import init_db
    from src.core.portfolio import regime_switch_portfolio

    init_db()

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
    from src.core.db import init_db
    from src.core.portfolio import black_litterman_portfolio

    init_db()

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
    from src.core.db import init_db
    from src.core.portfolio import hierarchical_risk_parity

    init_db()

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
    from src.core.db import init_db
    from src.core.portfolio import cvar_optimize

    init_db()

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
    from src.core.db import init_db
    from src.core.portfolio import multi_timeframe_signal

    init_db()

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
    from src.core.db import init_db
    from src.core.portfolio import dynamic_rebalance_trigger

    init_db()

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
    from src.core.db import init_db
    from src.core.portfolio import sector_exposure_limit

    init_db()

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
    from src.core.db import init_db
    from src.core.portfolio import strategy_voting_portfolio

    init_db()

    alloc_input = getattr(args, 'alloc', '')
    if alloc_input:
        allocations = parse_allocations(alloc_input)
    else:
        # 投票式組合需要較多子策略，使用擴展默認
        allocations = [
            {"strategy": "dual_ma", "code": "000001"},
            {"strategy": "macd", "code": "600519"},
            {"strategy": "bollinger", "code": "000858"},
            {"strategy": "rsi", "code": "000001"},
            {"strategy": "momentum", "code": "600519"},
        ]

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
    from src.core.db import init_db
    from src.core.portfolio import momentum_of_momentum

    init_db()

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
    from src.core.db import init_db
    from src.core.portfolio import adaptive_regime_portfolio

    init_db()

    alloc_input = getattr(args, 'alloc', '')
    if alloc_input:
        allocations = parse_allocations(alloc_input)
    else:
        allocations = [
            {"strategy": "dual_ma", "code": "000001"},
            {"strategy": "macd", "code": "600519"},
            {"strategy": "bollinger", "code": "000858"},
            {"strategy": "rsi", "code": "000001"},
            {"strategy": "momentum", "code": "600519"},
        ]

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


def cmd_strategy_create(args):
    """創建策略模板"""
    from src.core.strategy_base import create_strategy_template

    filepath = args.filepath if hasattr(args, "filepath") and args.filepath else None
    result_path = create_strategy_template(args.name, filepath)
    print(f"✅ 策略模板已創建: {result_path}")
    print(f"   策略名稱: {args.name}")
    print(f"   編輯文件後運行: python main.py strategy list")


def cmd_strategy_list(args):
    """列出所有策略"""
    from src.core.backtest import STRATEGIES
    from src.core.strategy_base import list_user_strategies

    print(f"\n{'='*60}")
    print(f"📋 策略列表")
    print(f"{'='*60}")

    # 內置策略
    print(f"\n🔧 內置策略 ({len(STRATEGIES)} 個):")
    print(f"  {'名稱':<16} {'說明'}")
    print(f"  {'-'*16} {'-'*40}")
    for name, cls in STRATEGIES.items():
        doc = (cls.__doc__ or "").strip().split("\n")[0]
        print(f"  {name:<16} {doc}")

    # 用戶策略
    user_strategies = list_user_strategies()
    if user_strategies:
        print(f"\n👤 用戶策略 ({len(user_strategies)} 個):")
        print(f"  {'名稱':<16} {'說明':<30} {'參數'}")
        print(f"  {'-'*16} {'-'*30} {'-'*20}")
        for s in user_strategies:
            params_str = ", ".join(f"{k}={v}" for k, v in s["params"].items())
            print(f"  {s['name']:<16} {s['description'][:28]:<30} {params_str}")
    else:
        print(f"\n👤 用戶策略: 無")
        print(f"   創建策略: python main.py strategy create <名稱>")

    print(f"\n共 {len(STRATEGIES) + len(user_strategies)} 個策略")


def cmd_strategy_leaderboard(args):
    """顯示策略排行榜"""
    from src.core.leaderboard import update_leaderboard, get_leaderboard

    print("📊 正在更新排行榜（這可能需要一些時間）...")
    codes = args.codes if hasattr(args, "codes") and args.codes else None
    update_leaderboard(codes=codes)

    sort_by = args.sort_by if hasattr(args, "sort_by") and args.sort_by else "sharpe"
    results = get_leaderboard(sort_by=sort_by, limit=args.limit if hasattr(args, "limit") else 20)

    if not results:
        print("暫無排行榜數據")
        return

    print(f"\n{'='*80}")
    print(f"🏆 策略排行榜 (按 {sort_by} 排序)")
    print(f"{'='*80}")
    print(f"{'排名':>4} {'策略':<16} {'類型':<8} {'股票':<10} {'夏普':>8} {'收益率':>10} {'回撤':>10} {'勝率':>8}")
    print(f"{'-'*4} {'-'*16} {'-'*8} {'-'*10} {'-'*8} {'-'*10} {'-'*10} {'-'*8}")

    for r in results:
        source_icon = "🔧" if r.get("source") == "builtin" else "👤"
        sharpe = f"{r.get('sharpe_ratio', 0):.2f}" if r.get("sharpe_ratio") else "N/A"
        ret = f"{r.get('total_return_pct', 0):.2f}%" if r.get("total_return_pct") is not None else "N/A"
        dd = f"{r.get('max_drawdown_pct', 0):.2f}%" if r.get("max_drawdown_pct") is not None else "N/A"
        wr = f"{r.get('win_rate_pct', 0):.1f}%" if r.get("win_rate_pct") is not None else "N/A"
        print(f"{r.get('rank', 0):>4} {r.get('strategy_name', ''):<16} {source_icon:<8} "
              f"{r.get('code', ''):<10} {sharpe:>8} {ret:>10} {dd:>10} {wr:>8}")


def cmd_report(args):
    """增強報告"""
    from src.core.db import init_db
    init_db()

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
    from src.core.db import init_db
    from src.core.backtest import run_backtest, monte_carlo_simulation

    init_db()

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
    from src.core.db import init_db
    from src.core.backtest import run_backtest, rolling_metrics

    init_db()

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
    from src.core.db import init_db

    init_db()

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


def cmd_signals(args):
    """實時交易信號"""
    from src.core.db import init_db, get_signal_logs
    from src.core.signals import (
        SignalEngine, score_signal_strength,
        compute_and_push_signals, get_historical_signals,
    )

    init_db()

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
        strategy = args.strategy if hasattr(args, "strategy") and args.strategy else None

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
            print(f"{s['triggered_at']:<12} {s['strategy']:<14} {sig_icon} {s['price']:>10.2f} {s.get('strength', 0):>8.1f}")

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
        print(f"{'排名':>4} {'代碼':>8} {'綜合分數':>10} {'推薦':>10} {'最新價格':>10} {'信號數':>6}")
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
                    print(f"        {sig_icon} {strat:<14} 強度={detail['strength']:>6.1f}  權重={detail['weight']:.3f}")

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

        print(f"\n圖例: >30 🟢強買 | 10~30 🔵偏多 | -10~10 ⚪中性 | -30~-10 🟡偏空 | <-30 🔴強賣")

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

        print(f"\n{'策略':<14} {'信號數':>6} {'買/賣':>8} {'1d準確':>8} {'3d準確':>8} {'5d準確':>8} {'10d準確':>8} {'1d收益':>8}")
        print("-" * 80)

        for strat_name, stats in sorted(by_strategy.items(), key=lambda x: x[1].get("accuracy_1d", 0), reverse=True):
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
            print(f"{'日期':<12} {'代碼':>8} {'策略':<14} {'信號':>6} {'價格':>10} {'1d收益':>8}")
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


def cmd_risk(args):
    """風險管理命令"""
    from src.core.db import init_db
    init_db()

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
            kelly_f = (win_rate * avg_win - (1 - win_rate)) / avg_win if avg_win > 0 else 0
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
            positions.append({
                "code": code,
                "value": 20000,  # 假設每隻 2 萬
                "vol": vol if vol > 0 else 0.20,
            })

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
            check = budget.check_position(p["value"], portfolio["total_value"], p["vol"])
            status_icon = "✅" if check["status"] == "正常" else "⚠️" if check["status"] == "警告" else "❌"
            print(
                f"{p['code']:>8} {p['weight_pct']:>7.1f}% {p['vol']:>7.4f} "
                f"{p['risk_contribution']:>9.4f} {status_icon}{check['status']:>6}"
            )

        print(f"\n再平衡建議:")
        for s in suggestions:
            action_icon = "🟢" if s["action"] == "加倉" else "🔴" if s["action"] == "減倉" else "⚪"
            print(f"  {action_icon} {s['code']}: {s['action']}  調整: ¥{s['adjustment']:,.0f}")

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
        print(f"  會觸發停止交易: {'是 ❌' if result['would_stop_trading'] else '否 ✅'}")

        breakers = result.get("circuit_breakers", [])
        if breakers:
            print(f"\n熔斷觸發詳情:")
            print(f"{'觸發日期':<12} {'回撤%':>8} {'峰值日期':<12} {'峰值':>12} {'觸發值':>12} {'恢復日期':<12} {'恢復天數':>8}")
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
        print("  python main.py risk position-size --capital 100000 --code 600519 --method atr")
        print("  python main.py risk budget-check")
        print("  python main.py risk drawdown --nav-file nav.csv")
        print("  python main.py risk drawdown --code 600519")


def cmd_user_create(args):
    """創建用戶"""
    from src.core.db import init_db
    from src.core.auth import create_user

    init_db()

    try:
        user = create_user(args.username, args.password, role=args.role)
        print(f"✅ 用戶創建成功:")
        print(f"   ID:       {user.id}")
        print(f"   用戶名:   {user.username}")
        print(f"   角色:     {user.role}")
        print(f"   創建時間: {user.created_at}")
    except ValueError as e:
        print(f"❌ 創建失敗: {e}")


def cmd_user_list(args):
    """列出所有用戶"""
    from src.core.db import init_db
    from src.core.auth import list_users

    init_db()

    users = list_users()
    if not users:
        print("暫無用戶")
        return

    print(f"\n{'='*60}")
    print(f"📋 用戶列表 (共 {len(users)} 個)")
    print(f"{'='*60}")
    print(f"{'ID':>4} {'用戶名':<16} {'角色':<8} {'創建時間':<20}")
    print(f"{'-'*4} {'-'*16} {'-'*8} {'-'*20}")

    for u in users:
        role_icon = "👑" if u["role"] == "admin" else "👤"
        print(f"{u['id']:>4} {u['username']:<16} {role_icon}{u['role']:<7} {u.get('created_at', ''):<20}")


def cmd_user_reset_password(args):
    """重置用戶密碼"""
    from src.core.db import init_db
    from src.core.auth import get_user_by_username, reset_password

    init_db()

    user = get_user_by_username(args.username)
    if not user:
        print(f"❌ 用戶 '{args.username}' 不存在")
        return

    new_password = args.new_password
    if not new_password:
        import getpass
        new_password = getpass.getpass("請輸入新密碼: ")
        if not new_password:
            print("❌ 密碼不能為空")
            return
    success = reset_password(user.id, new_password)
    if success:
        print(f"✅ 密碼已重置:")
        print(f"   用戶名:   {args.username}")
        print(f"   新密碼:   {new_password}")
        print(f"   請盡快修改密碼！")
    else:
        print(f"❌ 重置失敗")


def cmd_scheduler(args):
    """定時任務管理 (APScheduler)"""
    from src.core.scheduler import (
        get_catalog,
        list_jobs,
        setup_from_settings,
        run_job_now,
        enable_job,
        disable_job,
        _DISABLE_BY_ID,
    )

    action = args.scheduler_action
    if action == "list":
        catalog = get_catalog()
        jobs = list_jobs()
        print(f"\n{'='*60}")
        print("定時任務目錄")
        print(f"{'='*60}")
        for c in catalog:
            mark = "✅" if c["enabled"] else "○"
            print(f"  {mark} {c['id']:<22} {c['name']}")
            print(f"      計劃: {c['schedule']}")
            print(f"      說明: {c['description']}")
        print(f"\n已註冊任務 ({len(jobs)}):")
        if not jobs:
            print("  (無 — 執行 python main.py scheduler setup 註冊)")
        for j in jobs:
            print(f"  • {j['id']}: 下次 {j['next_run'] or '-'} | {j['trigger']}")
        print()

    elif action == "setup":
        jobs = setup_from_settings()
        print(f"✅ 已按配置註冊 {len(jobs)} 個定時任務")
        for j in jobs:
            print(f"   • {j['id']}: 下次 {j['next_run']}")

    elif action == "run":
        if not args.job_id:
            print("❌ 請指定任務 ID，例如: python main.py scheduler run incremental_update")
            return
        print(f"⏳ 執行任務: {args.job_id} ...")
        run_job_now(args.job_id)
        print(f"✅ 任務 {args.job_id} 已執行")

    elif action == "enable":
        if not args.job_id:
            jobs = setup_from_settings()
            print(f"✅ 已啟用默認任務套件 ({len(jobs)} 個)")
        else:
            enable_job(args.job_id)
            print(f"✅ 已啟用: {args.job_id}")

    elif action == "disable":
        if not args.job_id:
            for fn in _DISABLE_BY_ID.values():
                fn()
            print("✅ 已禁用全部定時任務")
        else:
            disable_job(args.job_id)
            print(f"✅ 已禁用: {args.job_id}")

    else:
        print("用法: python main.py scheduler {list|setup|run|enable|disable} [job_id]")


def cmd_stock_universe(args):
    from src.core.stock_universe import (
        sync_stock_universe,
        get_universe_stats,
        query_stock_universe,
    )

    action = getattr(args, "universe_action", None)
    if action == "sync":
        cap = args.max or None
        print(f"正在同步股票庫（上限 {cap or '配置默認'}）…")
        result = sync_stock_universe(max_count=cap)
        print(f"完成: 入庫 {result['saved']} 條，池內 {result['total_pool']} 條")
        if result.get("by_market"):
            for m, c in result["by_market"].items():
                print(f"  {m}: {c}")
        if result.get("note"):
            print(f"提示: {result['note']}")
    elif action == "stats":
        s = get_universe_stats()
        print(f"總數: {s.get('total', 0)}  更新: {s.get('updated_at')}")
        for m, info in (s.get("markets") or {}).items():
            print(f"  {m}: {info['count']}（含市值 {info['with_mv']}）")
    elif action == "list":
        rows, total = query_stock_universe(
            market=None if args.market == "all" else args.market,
            keyword=args.keyword,
            limit=args.limit,
        )
        print(f"共 {total} 條，顯示前 {len(rows)} 條：")
        for r in rows:
            mv = r.get("total_mv") or 0
            print(
                f"  #{r.get('rank_mv')} {r.get('code')} {r.get('name')} "
                f"[{r.get('market')}] 市值(億): {mv:.2f}"
            )
    else:
        print("用法: python main.py stock-universe {sync|stats|list}")


def main():
    parser = argparse.ArgumentParser(
        prog="stock-quant",
        description="📈 stock-quant — A股量化回測 + 實時盯盤預警系統",
        epilog="示例:\n"
               "  python main.py serve --port 8080\n"
               "  python main.py download 000001 600519\n"
               "  python main.py backtest 600519 macd\n"
               "  python main.py optimize 600519 --method optuna\n"
               "  python main.py portfolio --alloc \"dual_ma:000001,macd:600519\"\n"
               "  python main.py config show -v\n"
               "  python main.py strategy list",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command")

    # serve
    p_serve = subparsers.add_parser("serve", help="啟動 Web 服務")
    p_serve.add_argument("--host", default=None)
    p_serve.add_argument("--port", type=int, default=None)
    p_serve.add_argument("--workers", type=int, default=None)
    p_serve.add_argument("--reload", action="store_true")

    # download
    p_dl = subparsers.add_parser("download", help="下載歷史數據")
    p_dl.add_argument("codes", nargs="*", help="股票代碼")
    p_dl.add_argument("--incremental", action="store_true", help="增量下載")
    p_dl.add_argument("--force", action="store_true", help="強制重新下載全部")

    # backtest
    p_bt = subparsers.add_parser(
        "backtest",
        help="策略回測",
        epilog="可用策略: dual_ma, macd, bollinger, kdj, rsi, grid, turtle, dual_thrust, "
               "momentum, mean_reversion, volume_price, breakout, composite, vwap, "
               "envelope, parabolic_sar, obv, bollinger_squeeze, adx_trend",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_bt.add_argument("code", help="股票代碼")
    p_bt.add_argument("strategy", nargs="?", default="dual_ma")
    p_bt.add_argument("--slippage", type=float, default=0.0, help="滑點百分比（默認 0.0，如 0.1 表示 0.1%%）")
    p_bt.add_argument("--no-t1", action="store_true", help="禁用 T+1 限制（默認啟用）")
    p_bt.add_argument("--no-limit", action="store_true", help="禁用漲跌停限制（默認啟用）")

    # optimize
    p_opt = subparsers.add_parser("optimize", help="參數優化")
    p_opt.add_argument("code", help="股票代碼")
    p_opt.add_argument("strategy", nargs="?", default="all")
    p_opt.add_argument("--method", choices=["grid", "optuna"], default="grid")
    p_opt.add_argument("--objective", choices=["sharpe", "return", "calmar"], default="sharpe")
    p_opt.add_argument("--trials", type=int, default=100)

    # portfolio
    p_pf = subparsers.add_parser("portfolio", help="組合回測")
    add_alloc_arg(p_pf)

    # monitor
    p_mon = subparsers.add_parser("monitor", help="實時盯盤")

    # walkforward
    p_wf = subparsers.add_parser("walkforward", help="Walk-Forward 分析")
    p_wf.add_argument("code", help="股票代碼")
    p_wf.add_argument("strategy", nargs="?", default="dual_ma")
    p_wf.add_argument("--train-days", type=int, default=750)
    p_wf.add_argument("--test-days", type=int, default=250)
    p_wf.add_argument("--step-days", type=int, default=250)
    p_wf.add_argument("--objective", choices=["sharpe", "return", "calmar"], default="sharpe")
    p_wf.add_argument("--trials", type=int, default=50)

    # auto-optimize
    p_ao = subparsers.add_parser("auto-optimize", help="自動參數優化")
    p_ao.add_argument("--method", choices=["grid", "optuna"], default="optuna")
    p_ao.add_argument("--objective", choices=["sharpe", "return", "calmar"], default="sharpe")
    p_ao.add_argument("--trials", type=int, default=50)

    # heatmap
    p_hm = subparsers.add_parser("heatmap", help="參數熱力圖")
    p_hm.add_argument("code", help="股票代碼")
    p_hm.add_argument("strategy", help="策略名稱")
    p_hm.add_argument("param_x", help="X 軸參數")
    p_hm.add_argument("param_y", help="Y 軸參數")
    p_hm.add_argument("--grid-size", type=int, default=10, help="網格大小")
    p_hm.add_argument("--objective", choices=["sharpe", "return", "calmar", "win_rate"], default="sharpe")

    # screen
    p_scr = subparsers.add_parser("screen", help="股票篩選")
    p_scr.add_argument("codes", nargs="*", help="股票代碼")
    p_scr.add_argument("--ma-bullish", action="store_true", help="MA 多頭排列")
    p_scr.add_argument("--volume-surge", type=float, help="成交量暴增倍數")
    p_scr.add_argument("--above-ma", type=int, help="站上 N 日均線")
    p_scr.add_argument("--near-high", type=float, help="接近 52 週新高百分比")
    p_scr.add_argument("--price-change", type=float, help="N 日漲幅百分比")

    # dynamic-portfolio
    p_dp = subparsers.add_parser("dynamic-portfolio", help="動態權重組合回測")
    p_dp.add_argument("--window", type=int, default=60, help="滾動窗口天數")
    p_dp.add_argument("--freq", type=int, default=20, help="權重調整頻率（天）")
    add_alloc_arg(p_dp)

    # kelly
    p_kelly = subparsers.add_parser("kelly", help="Kelly 公式最優倉位")
    p_kelly.add_argument("--limit", type=float, default=0.5, help="Kelly 比例上限")
    add_alloc_arg(p_kelly)

    # degradation
    p_deg = subparsers.add_parser("degradation", help="策略衰退檢測")
    p_deg.add_argument("--lookback", type=int, default=30, help="回看天數")
    p_deg.add_argument("--threshold", type=int, default=5, help="連續跑輸天數閾值")
    add_alloc_arg(p_deg)

    # arbitrate
    p_arb = subparsers.add_parser("arbitrate", help="信號衝突仲裁")
    add_alloc_arg(p_arb)

    # risk-parity
    p_rp = subparsers.add_parser("risk-parity", help="風險平價組合")
    add_alloc_arg(p_rp)

    # mvo
    p_mvo = subparsers.add_parser("mvo", help="均值-方差優化 (Markowitz)")
    p_mvo.add_argument("--objective", choices=["max_sharpe", "min_variance", "max_return"], default="max_sharpe")
    p_mvo.add_argument("--simulations", type=int, default=5000, help="蒙特卡羅模擬次數")
    add_alloc_arg(p_mvo)

    # vol-target
    p_vt = subparsers.add_parser("vol-target", help="波動率目標組合")
    p_vt.add_argument("--target", type=float, default=0.15, help="目標年化波動率")
    p_vt.add_argument("--lookback", type=int, default=20, help="波動率計算窗口")
    add_alloc_arg(p_vt)

    # max-diversification
    p_md = subparsers.add_parser("max-diversification", help="最大分散化組合")
    add_alloc_arg(p_md)

    # anti-correlation
    p_ac = subparsers.add_parser("anti-correlation", help="反相關組合")
    add_alloc_arg(p_ac)

    # regime-switch
    p_rs = subparsers.add_parser("regime-switch", help="市場狀態切換組合")
    p_rs.add_argument("--method", choices=["volatility", "trend"], default="volatility", help="狀態判定方法")
    p_rs.add_argument("--lookback", type=int, default=60, help="狀態判定窗口天數")
    add_alloc_arg(p_rs)

    # voting-portfolio
    p_vp = subparsers.add_parser("voting-portfolio", help="投票式組合回測")
    p_vp.add_argument("--min-votes", type=int, default=2, help="最低同意票數（默認 2）")
    add_alloc_arg(p_vp)

    # momentum-of-momentum
    p_mm = subparsers.add_parser("momentum-of-momentum", help="動量的動量組合回測")
    p_mm.add_argument("--lookback", type=int, default=60, help="動量計算回看天數（默認 60）")
    add_alloc_arg(p_mm)

    # adaptive-regime
    p_ar = subparsers.add_parser("adaptive-regime", help="自適應市場狀態組合回測")
    add_alloc_arg(p_ar)

    # black-litterman
    p_bl = subparsers.add_parser("black-litterman", help="Black-Litterman 模型組合")
    add_alloc_arg(p_bl)

    # hrp
    p_hrp = subparsers.add_parser("hrp", help="層次風險平價 (HRP) 組合")
    add_alloc_arg(p_hrp)

    # cvar
    p_cvar = subparsers.add_parser("cvar", help="CVaR 優化組合")
    p_cvar.add_argument("--alpha", type=float, default=0.05, help="VaR 顯著性水平（默認 0.05）")
    add_alloc_arg(p_cvar)

    # multi-timeframe
    p_mtf = subparsers.add_parser("multi-timeframe", help="多時間框架信號確認")
    p_mtf.add_argument("--windows", default="5,20,60", help="時間窗口（逗號分隔，默認 5,20,60）")
    add_alloc_arg(p_mtf)

    # dynamic-rebalance
    p_dr = subparsers.add_parser("dynamic-rebalance", help="動態再平衡觸發")
    p_dr.add_argument("--threshold", type=float, default=5.0, help="權重偏移觸發閾值 %%（默認 5.0）")
    p_dr.add_argument("--vol-window", type=int, default=20, help="波動率計算窗口（默認 20）")
    add_alloc_arg(p_dr)

    # sector-limit
    p_sl = subparsers.add_parser("sector-limit", help="板塊敞口限制")
    p_sl.add_argument("--max-pct", type=float, default=40.0, help="單板塊最大佔比 %%（默認 40.0）")
    add_alloc_arg(p_sl)

    # config
    p_cfg = subparsers.add_parser("config", help="查看/驗證配置")
    cfg_sub = p_cfg.add_subparsers(dest="config_action")
    p_cfg_show = cfg_sub.add_parser("show", help="顯示當前配置")
    p_cfg_show.add_argument("-v", "--verbose", action="store_true", help="顯示詳細信息")
    cfg_sub.add_parser("validate", help="驗證配置完整性")

    # strategy
    p_strat = subparsers.add_parser("strategy", help="策略管理")
    strat_sub = p_strat.add_subparsers(dest="strategy_action")

    # strategy create
    p_strat_create = strat_sub.add_parser("create", help="創建策略模板")
    p_strat_create.add_argument("name", help="策略名稱（英文）")
    p_strat_create.add_argument("filepath", nargs="?", help="輸出路徑（可選）")

    # strategy list
    strat_sub.add_parser("list", help="列出所有策略")

    # strategy leaderboard
    p_strat_lb = strat_sub.add_parser("leaderboard", help="策略排行榜")
    p_strat_lb.add_argument("--codes", nargs="*", help="股票代碼（默認 watchlist）")
    p_strat_lb.add_argument("--sort-by", choices=["sharpe", "return", "drawdown", "win_rate"], default="sharpe")
    p_strat_lb.add_argument("--limit", type=int, default=20, help="顯示條數")

    # report（增強報告）
    p_rpt = subparsers.add_parser("report", help="增強回測報告")
    rpt_sub = p_rpt.add_subparsers(dest="report_action")

    # report full
    p_rpt_full = rpt_sub.add_parser("full", help="全面回測報告")
    p_rpt_full.add_argument("code", help="股票代碼")
    p_rpt_full.add_argument("strategy", nargs="?", default="dual_ma", help="策略名稱")

    # report comparison
    p_rpt_cmp = rpt_sub.add_parser("comparison", help="多股對比報告")
    p_rpt_cmp.add_argument("codes", nargs="+", help="股票代碼列表")
    p_rpt_cmp.add_argument("--strategy", default="dual_ma", help="策略名稱")

    # report strategy
    p_rpt_strat = rpt_sub.add_parser("strategy", help="策略分析報告")
    p_rpt_strat.add_argument("strategy_name", help="策略名稱")
    p_rpt_strat.add_argument("codes", nargs="*", help="股票代碼（默認 watchlist）")

    # monte-carlo
    p_mc = subparsers.add_parser("monte-carlo", help="蒙特卡羅模擬")
    p_mc.add_argument("code", help="股票代碼")
    p_mc.add_argument("strategy", nargs="?", default="dual_ma", help="策略名稱")
    p_mc.add_argument("--simulations", type=int, default=1000, help="模擬次數")
    p_mc.add_argument("--days", type=int, default=252, help="模擬天數")

    # rolling-metrics
    p_rm = subparsers.add_parser("rolling-metrics", help="滾動性能指標")
    p_rm.add_argument("code", help="股票代碼")
    p_rm.add_argument("--window", type=int, default=60, help="滾動窗口天數")

    # export
    p_exp = subparsers.add_parser("export", help="導出數據")
    p_exp.add_argument("type", choices=["backtest", "trades"], help="導出類型")
    p_exp.add_argument("--id", type=int, help="回測結果 ID")
    p_exp.add_argument("--code", help="股票代碼")
    p_exp.add_argument("--strategy", help="策略名稱")
    p_exp.add_argument("--format", choices=["csv", "json"], default="csv", help="導出格式")
    p_exp.add_argument("--output", "-o", help="輸出文件路徑")

    # signals
    p_sig = subparsers.add_parser("signals", help="實時交易信號")
    p_sig.add_argument("action", choices=["compute", "history", "strength", "ranking", "heatmap", "backtest"], help="操作類型")
    p_sig.add_argument("codes", nargs="*", help="股票代碼 (compute 模式) 或目標代碼 (history/strength)")
    p_sig.add_argument("--code", help="股票代碼 (history/strength)")
    p_sig.add_argument("--days", type=int, default=30, help="歷史天數 (history 模式)")
    p_sig.add_argument("--strategy", help="策略名稱過濾")

    # risk（風險管理）
    p_risk = subparsers.add_parser("risk", help="風險管理")
    risk_sub = p_risk.add_subparsers(dest="risk_action")

    # risk position-size
    p_risk_ps = risk_sub.add_parser("position-size", help="計算倉位大小")
    p_risk_ps.add_argument("--capital", type=float, default=100000, help="總資金")
    p_risk_ps.add_argument("--atr", type=float, default=0, help="ATR 值")
    p_risk_ps.add_argument("--code", help="股票代碼（自動計算 ATR）")
    p_risk_ps.add_argument("--method", choices=["atr", "fixed", "kelly", "volatility", "drawdown"], default="atr", help="計算方法")
    p_risk_ps.add_argument("--fraction", type=float, default=0.1, help="固定比例（fixed 方法）")
    p_risk_ps.add_argument("--win-rate", type=float, default=0.5, help="勝率（kelly 方法）")
    p_risk_ps.add_argument("--max-risk", type=float, default=0.02, help="每筆最大風險比例")

    # risk budget-check
    p_risk_bc = risk_sub.add_parser("budget-check", help="風險預算檢查")
    p_risk_bc.add_argument("--max-portfolio-risk", type=float, default=0.15, help="組合最大風險")
    p_risk_bc.add_argument("--max-single-risk", type=float, default=0.05, help="單持倉最大風險")

    # risk drawdown
    p_risk_dd = risk_sub.add_parser("drawdown", help="回撤保護分析")
    p_risk_dd.add_argument("--nav-file", help="CSV 文件路徑（含 date,nav 列）")
    p_risk_dd.add_argument("--max-dd", type=float, default=20.0, help="最大回撤百分比")
    p_risk_dd.add_argument("--code", help="股票代碼（用於模擬分析）")

    # scheduler（定時任務）
    p_sched = subparsers.add_parser("scheduler", help="定時任務 (APScheduler)")
    sched_sub = p_sched.add_subparsers(dest="scheduler_action")
    sched_sub.add_parser("list", help="列出任務目錄與狀態")
    sched_sub.add_parser("setup", help="按 config 註冊默認任務")
    p_sched_run = sched_sub.add_parser("run", help="立即執行一次")
    p_sched_run.add_argument("job_id", nargs="?", help="任務 ID，如 incremental_update")
    p_sched_en = sched_sub.add_parser("enable", help="啟用任務")
    p_sched_en.add_argument("job_id", nargs="?", help="任務 ID（省略則啟用全套）")
    p_sched_dis = sched_sub.add_parser("disable", help="禁用任務")
    p_sched_dis.add_argument("job_id", nargs="?", help="任務 ID（省略則全部禁用）")

    # user（多用戶管理）
    p_user = subparsers.add_parser("user", help="用戶管理")
    user_sub = p_user.add_subparsers(dest="user_action")

    # user create
    p_user_create = user_sub.add_parser("create", help="創建用戶")
    p_user_create.add_argument("username", help="用戶名")
    p_user_create.add_argument("password", help="密碼")
    p_user_create.add_argument("--role", choices=["admin", "user"], default="user", help="角色（默認 user）")

    # user list
    user_sub.add_parser("list", help="列出所有用戶")

    # user reset-password
    p_user_reset = user_sub.add_parser("reset-password", help="重置用戶密碼")
    p_user_reset.add_argument("username", help="用戶名")
    p_user_reset.add_argument("new_password", nargs="?", default=None, help="新密碼（不提供則交互輸入）")

    # stock-universe（股票庫）
    p_univ = subparsers.add_parser("stock-universe", help="股票庫（按市值前 N）")
    univ_sub = p_univ.add_subparsers(dest="universe_action")
    p_univ_sync = univ_sub.add_parser("sync", help="同步多市場基本資料入庫")
    p_univ_sync.add_argument(
        "--max",
        type=int,
        default=None,
        help="入庫數量上限（默認 SQ_STOCK_UNIVERSE_MAX_COUNT=20000）",
    )
    univ_sub.add_parser("stats", help="查看股票庫統計")
    p_univ_list = univ_sub.add_parser("list", help="列出股票庫")
    p_univ_list.add_argument("--market", default="all", help="a_share/hk_stock/us_stock/all")
    p_univ_list.add_argument("--limit", type=int, default=20)
    p_univ_list.add_argument("--keyword", default=None)

    args = parser.parse_args()

    if args.command == "serve":
        cmd_serve(args)
    elif args.command == "download":
        cmd_download(args)
    elif args.command == "backtest":
        cmd_backtest(args)
    elif args.command == "optimize":
        cmd_optimize(args)
    elif args.command == "portfolio":
        cmd_portfolio(args)
    elif args.command == "monitor":
        cmd_monitor(args)
    elif args.command == "walkforward":
        cmd_walkforward(args)
    elif args.command == "auto-optimize":
        cmd_auto_optimize(args)
    elif args.command == "heatmap":
        cmd_heatmap(args)
    elif args.command == "screen":
        cmd_screen(args)
    elif args.command == "dynamic-portfolio":
        cmd_dynamic_portfolio(args)
    elif args.command == "kelly":
        cmd_kelly(args)
    elif args.command == "degradation":
        cmd_degradation(args)
    elif args.command == "arbitrate":
        cmd_arbitrate(args)
    elif args.command == "risk-parity":
        cmd_risk_parity(args)
    elif args.command == "mvo":
        cmd_mvo(args)
    elif args.command == "vol-target":
        cmd_vol_target(args)
    elif args.command == "max-diversification":
        cmd_max_diversification(args)
    elif args.command == "anti-correlation":
        cmd_anti_corr(args)
    elif args.command == "regime-switch":
        cmd_regime_switch(args)
    elif args.command == "voting-portfolio":
        cmd_voting_portfolio(args)
    elif args.command == "momentum-of-momentum":
        cmd_momentum_of_momentum(args)
    elif args.command == "adaptive-regime":
        cmd_adaptive_regime(args)
    elif args.command == "black-litterman":
        cmd_black_litterman(args)
    elif args.command == "hrp":
        cmd_hrp(args)
    elif args.command == "cvar":
        cmd_cvar(args)
    elif args.command == "multi-timeframe":
        cmd_multi_timeframe(args)
    elif args.command == "dynamic-rebalance":
        cmd_dynamic_rebalance(args)
    elif args.command == "sector-limit":
        cmd_sector_limit(args)
    elif args.command == "report":
        cmd_report(args)
    elif args.command == "monte-carlo":
        cmd_monte_carlo(args)
    elif args.command == "rolling-metrics":
        cmd_rolling_metrics(args)
    elif args.command == "export":
        cmd_export(args)
    elif args.command == "config":
        cmd_config(args)
    elif args.command == "strategy":
        if args.strategy_action == "create":
            cmd_strategy_create(args)
        elif args.strategy_action == "list":
            cmd_strategy_list(args)
        elif args.strategy_action == "leaderboard":
            cmd_strategy_leaderboard(args)
        else:
            p_strat.print_help()
    elif args.command == "signals":
        # signals 命令：第一個位置參數是 action，第二個開始是 codes
        if not args.codes and args.code:
            args.codes = [args.code]
        elif args.codes and args.action in ("history", "strength") and not args.code:
            args.code = args.codes[0]
        cmd_signals(args)
    elif args.command == "risk":
        cmd_risk(args)
    elif args.command == "user":
        if args.user_action == "create":
            cmd_user_create(args)
        elif args.user_action == "list":
            cmd_user_list(args)
        elif args.user_action == "reset-password":
            cmd_user_reset_password(args)
        else:
            p_user.print_help()
    elif args.command == "scheduler":
        if args.scheduler_action:
            cmd_scheduler(args)
        else:
            p_sched.print_help()
    elif args.command == "stock-universe":
        if args.universe_action:
            cmd_stock_universe(args)
        else:
            p_univ.print_help()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
