"""CLI commands: strategy"""
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


