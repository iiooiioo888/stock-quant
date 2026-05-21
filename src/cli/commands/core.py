"""CLI commands: core"""
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
    import uvicorn

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
    from src.core.history import download_all, download_incremental

    ensure_db()
    codes = args.codes if args.codes else None

    if args.incremental:
        result = download_incremental(codes, force=args.force)
        print(f"\n增量更新完成:")
        print(f"  更新: {result['updated']} 只")
        print(f"  跳過: {result['skipped']} 只")
        print(f"  新數據: {result['total_records']} 條")
    else:
        download_all(codes)




def cmd_monitor(args):
    """實時盯盤"""
    import time
    from datetime import datetime
    from src.config import settings
    from src.core.realtime import fetch_realtime
    from src.core.alerts import AlertEngine

    ensure_db()
    engine = AlertEngine()
    codes = settings.watchlist

    print(f"盯盤啟動: {', '.join(codes)} | 間隔 {settings.poll_interval_sec}s | Ctrl+C 停止")

    try:
        while True:
            now = datetime.now()
            if not is_a_share_trading_now(now):
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


