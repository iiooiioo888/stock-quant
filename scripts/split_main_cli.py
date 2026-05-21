"""一次性腳本：將 main.py 拆分到 src/cli/。"""
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
text = (root / "main.py").read_text(encoding="utf-8")
idx = text.index("def main():")
funcs_block = text[text.index("def parse_allocations") : idx]
main_block = text[idx:]

helpers_start = text.index("DEFAULT_ALLOCATIONS")
helpers_end = text.index("def cmd_config")
helpers_body = text[helpers_start:helpers_end]

cli = root / "src" / "cli"
(cli / "commands").mkdir(parents=True, exist_ok=True)

GROUPS = {
    "core": [
        "cmd_config", "cmd_serve", "cmd_download", "cmd_monitor",
        "cmd_scheduler", "cmd_stock_universe",
    ],
    "backtest": [
        "cmd_backtest", "cmd_optimize", "cmd_walkforward", "cmd_auto_optimize",
        "cmd_heatmap", "cmd_screen",
    ],
    "portfolio": [
        "cmd_portfolio", "cmd_dynamic_portfolio", "cmd_kelly", "cmd_degradation",
        "cmd_arbitrate", "cmd_risk_parity", "cmd_mvo", "cmd_vol_target",
        "cmd_max_diversification", "cmd_anti_corr", "cmd_regime_switch",
        "cmd_black_litterman", "cmd_hrp", "cmd_cvar", "cmd_multi_timeframe",
        "cmd_dynamic_rebalance", "cmd_sector_limit", "cmd_voting_portfolio",
        "cmd_momentum_of_momentum", "cmd_adaptive_regime",
    ],
    "strategy": ["cmd_strategy_create", "cmd_strategy_list", "cmd_strategy_leaderboard"],
    "reports": ["cmd_report", "cmd_monte_carlo", "cmd_rolling_metrics", "cmd_export"],
    "signals": ["cmd_signals"],
    "risk": ["cmd_risk"],
    "users": ["cmd_user_create", "cmd_user_list", "cmd_user_reset_password"],
}

pattern = re.compile(r"^def (cmd_\w+)\([^)]*\):.*?(?=^def cmd_|\Z)", re.M | re.S)
matches = {m.group(1): m.group(0) for m in pattern.finditer(funcs_block)}

all_assigned: set[str] = set()
for group, names in GROUPS.items():
    parts = []
    for n in names:
        if n not in matches:
            raise SystemExit(f"missing {n}")
        parts.append(matches[n])
        all_assigned.add(n)
    header = (
        f'"""CLI commands: {group}"""\n'
        "from datetime import datetime\n\n"
        "import numpy as np\n\n"
        "from src.cli.helpers import (\n"
        "    DEFAULT_ALLOCATIONS,\n"
        "    add_alloc_arg,\n"
        "    ensure_db,\n"
        "    fail_result,\n"
        "    get_allocations,\n"
        "    is_a_share_trading_now,\n"
        "    parse_allocations,\n"
        "    print_portfolio_metrics,\n"
        ")\n\n\n"
    )
    (cli / "commands" / f"{group}.py").write_text(header + "\n\n".join(parts), encoding="utf-8")

if set(matches) - all_assigned:
    raise SystemExit(f"unassigned: {set(matches) - all_assigned}")

helpers_content = (
    '"""CLI 共用工具。"""\n'
    "import argparse\n\n\n"
    + helpers_body
    + """

def ensure_db():
    from src.core.db import init_db
    init_db()


def get_allocations(args) -> list[dict]:
    return parse_allocations(getattr(args, "alloc", "") or "")


def print_portfolio_metrics(pm: dict, *, title: str = "組合結果") -> None:
    print(f"\\n{'='*70}")
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
"""
)
(cli / "helpers.py").write_text(helpers_content, encoding="utf-8")

init = '"""CLI 命令處理函數。"""\n'
for group, names in GROUPS.items():
    init += f"from src.cli.commands.{group} import (\n"
    for n in names:
        init += f"    {n},\n"
    init += ")\n\n"
(cli / "commands" / "__init__.py").write_text(init, encoding="utf-8")
(cli / "__init__.py").write_text('"""stock-quant CLI 套件。"""\n', encoding="utf-8")
(root / "src" / "cli" / "parser.py").write_text(
    main_block.replace("def main():", "def build_parser():").replace(
        "    args = parser.parse_args()\n\n    if args.command",
        "    return parser\n\n\ndef _legacy_dispatch_removed():\n    if False and args.command",
    ),
    encoding="utf-8",
)
print("OK", sorted(p.name for p in (cli / "commands").glob("*.py")))
