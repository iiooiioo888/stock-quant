"""從 git HEAD 的 main.py 還原損壞的 CLI 模組（僅替換 init_db，不改其他縮排）。"""
from pathlib import Path
import re
import subprocess

root = Path(__file__).resolve().parents[1]
text = subprocess.check_output(
    ["git", "show", "HEAD:main.py"],
    cwd=root,
    text=True,
    encoding="utf-8",
    errors="replace",
)
idx = text.index("def main():")
funcs_block = text[text.index("def parse_allocations") : idx]
pattern = re.compile(r"^def (cmd_\w+)\([^)]*\):.*?(?=^def cmd_|\Z)", re.M | re.S)
matches = {m.group(1): m.group(0) for m in pattern.finditer(funcs_block)}


def patch_init_db(body: str) -> str:
    body = re.sub(r"^from src\.core\.db import init_db\n", "", body, flags=re.M)
    body = re.sub(r"^    init_db\(\)\n", "    ensure_db()\n", body, flags=re.M)
    return body


GROUPS = {
    "reports": ["cmd_report", "cmd_monte_carlo", "cmd_rolling_metrics", "cmd_export"],
    "risk": ["cmd_risk"],
    "signals": ["cmd_signals"],
    "users": ["cmd_user_create", "cmd_user_list", "cmd_user_reset_password"],
    "portfolio": [
        "cmd_portfolio", "cmd_dynamic_portfolio", "cmd_kelly", "cmd_degradation",
        "cmd_arbitrate", "cmd_risk_parity", "cmd_mvo", "cmd_vol_target",
        "cmd_max_diversification", "cmd_anti_corr", "cmd_regime_switch",
        "cmd_black_litterman", "cmd_hrp", "cmd_cvar", "cmd_multi_timeframe",
        "cmd_dynamic_rebalance", "cmd_sector_limit", "cmd_voting_portfolio",
        "cmd_momentum_of_momentum", "cmd_adaptive_regime",
    ],
}

HEADER = '''"""CLI commands: {group}"""
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


'''

cli = root / "src" / "cli" / "commands"
for group, names in GROUPS.items():
    hdr = HEADER.format(group=group)
    if group != "portfolio":
        hdr = hdr.replace("    EXTENDED_ALLOCATIONS,\n", "")
    parts = [patch_init_db(matches[n]) for n in names]
    (cli / f"{group}.py").write_text(hdr + "\n\n".join(parts), encoding="utf-8")
    print("rewrote", group)
