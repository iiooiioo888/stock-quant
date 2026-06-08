"""CLI 共用工具。"""

import argparse

DEFAULT_ALLOCATIONS = [
    {"strategy": "dual_ma", "code": "000001"},
    {"strategy": "macd", "code": "600519"},
    {"strategy": "bollinger", "code": "000858"},
]

# 投票 / 自適應組合預設（子策略較多）
EXTENDED_ALLOCATIONS = [
    *DEFAULT_ALLOCATIONS,
    {"strategy": "rsi", "code": "000001"},
    {"strategy": "momentum", "code": "600519"},
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
        "--alloc",
        type=str,
        default="",
        help='組合分配，格式: "strategy:code,strategy:code,..."（留空使用默認）',
    )


def ensure_db():
    from src.core.db import init_db

    init_db()


def get_allocations(args) -> list[dict]:
    return parse_allocations(getattr(args, "alloc", "") or "")


def print_portfolio_metrics(pm: dict, *, title: str = "組合結果") -> None:
    print(f"\n{'='*70}")
    print(title)
    print(f"{'='*70}")
    print(f"總收益: {pm.get('total_return_pct', 0):+.2f}%")
    print(f"年化收益: {pm.get('annual_return_pct', 0):+.2f}%")
    print(f"夏普比率: {pm.get('sharpe_ratio', 0):.4f}")
    print(f"最大回撤: {pm.get('max_drawdown_pct', 0):.2f}%")


def fail_result(result, *, label: str = "操作") -> bool:
    if not result:
        print(f"{label}失敗")
        return True
    if isinstance(result, dict) and result.get("error"):
        print(f"失敗: {result.get('error', '未知錯誤')}")
        return True
    return False


def is_a_share_trading_now(now=None) -> bool:
    from datetime import datetime as dt

    now = now or dt.now()
    if now.weekday() >= 5:
        return False
    t = now.hour * 100 + now.minute
    return 915 <= t <= 1500
