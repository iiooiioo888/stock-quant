"""CLI 入口：解析參數並分發到命令處理函數。"""
from __future__ import annotations

import argparse
from typing import Callable

from src.cli.parser import build_parser
from src.cli.commands import (
    cmd_adaptive_regime,
    cmd_anti_corr,
    cmd_arbitrate,
    cmd_auto_optimize,
    cmd_backtest,
    cmd_black_litterman,
    cmd_config,
    cmd_cvar,
    cmd_degradation,
    cmd_download,
    cmd_seed,
    cmd_dynamic_portfolio,
    cmd_dynamic_rebalance,
    cmd_export,
    cmd_heatmap,
    cmd_hrp,
    cmd_kelly,
    cmd_max_diversification,
    cmd_monitor,
    cmd_momentum_of_momentum,
    cmd_monte_carlo,
    cmd_mvo,
    cmd_multi_timeframe,
    cmd_optimize,
    cmd_portfolio,
    cmd_regime_switch,
    cmd_report,
    cmd_risk,
    cmd_risk_parity,
    cmd_rolling_metrics,
    cmd_scheduler,
    cmd_screen,
    cmd_sector_limit,
    cmd_signals,
    cmd_serve,
    cmd_stock_universe,
    cmd_strategy_create,
    cmd_strategy_leaderboard,
    cmd_strategy_list,
    cmd_user_create,
    cmd_user_list,
    cmd_user_reset_password,
    cmd_vol_target,
    cmd_voting_portfolio,
    cmd_walkforward,
    cmd_ops,
)

Handler = Callable[[argparse.Namespace], None]

# 頂層命令 → 處理函數（無子命令或子命令在函數內部分支）
_SIMPLE_HANDLERS: dict[str, Handler] = {
    "serve": cmd_serve,
    "download": cmd_download,
    "seed": cmd_seed,
    "backtest": cmd_backtest,
    "optimize": cmd_optimize,
    "portfolio": cmd_portfolio,
    "monitor": cmd_monitor,
    "walkforward": cmd_walkforward,
    "auto-optimize": cmd_auto_optimize,
    "heatmap": cmd_heatmap,
    "screen": cmd_screen,
    "dynamic-portfolio": cmd_dynamic_portfolio,
    "kelly": cmd_kelly,
    "degradation": cmd_degradation,
    "arbitrate": cmd_arbitrate,
    "risk-parity": cmd_risk_parity,
    "mvo": cmd_mvo,
    "vol-target": cmd_vol_target,
    "max-diversification": cmd_max_diversification,
    "anti-correlation": cmd_anti_corr,
    "regime-switch": cmd_regime_switch,
    "voting-portfolio": cmd_voting_portfolio,
    "momentum-of-momentum": cmd_momentum_of_momentum,
    "adaptive-regime": cmd_adaptive_regime,
    "black-litterman": cmd_black_litterman,
    "hrp": cmd_hrp,
    "cvar": cmd_cvar,
    "multi-timeframe": cmd_multi_timeframe,
    "dynamic-rebalance": cmd_dynamic_rebalance,
    "sector-limit": cmd_sector_limit,
    "monte-carlo": cmd_monte_carlo,
    "rolling-metrics": cmd_rolling_metrics,
    "export": cmd_export,
    "config": cmd_config,
    "signals": cmd_signals,
    "risk": cmd_risk,
}


def _normalize_signals_args(args: argparse.Namespace) -> None:
    """統一 signals 的 code / codes 位置參數。"""
    if not getattr(args, "codes", None) and getattr(args, "code", None):
        args.codes = [args.code]
    elif (
        getattr(args, "codes", None)
        and getattr(args, "action", None) in ("history", "strength")
        and not getattr(args, "code", None)
    ):
        args.code = args.codes[0]


def _dispatch_nested(
    args: argparse.Namespace,
    *,
    action_attr: str,
    handlers: dict[str, Handler],
    help_hint: str,
) -> None:
    action = getattr(args, action_attr, None)
    fn = handlers.get(action) if action else None
    if fn:
        fn(args)
    else:
        print(help_hint)


def dispatch(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    cmd = args.command
    if not cmd:
        parser.print_help()
        return

    if cmd == "report":
        _dispatch_nested(
            args,
            action_attr="report_action",
            handlers={
                "full": cmd_report,
                "comparison": cmd_report,
                "strategy": cmd_report,
            },
            help_hint="用法: python main.py report {full|comparison|strategy} ...",
        )
        return

    if cmd == "strategy":
        _dispatch_nested(
            args,
            action_attr="strategy_action",
            handlers={
                "create": cmd_strategy_create,
                "list": cmd_strategy_list,
                "leaderboard": cmd_strategy_leaderboard,
            },
            help_hint="用法: python main.py strategy {create|list|leaderboard} ...",
        )
        return

    if cmd == "user":
        _dispatch_nested(
            args,
            action_attr="user_action",
            handlers={
                "create": cmd_user_create,
                "list": cmd_user_list,
                "reset-password": cmd_user_reset_password,
            },
            help_hint="用法: python main.py user {create|list|reset-password} ...",
        )
        return

    if cmd == "scheduler":
        if getattr(args, "scheduler_action", None):
            cmd_scheduler(args)
        else:
            print("用法: python main.py scheduler {list|setup|run|enable|disable} [job_id]")
        return

    if cmd == "stock-universe":
        if getattr(args, "universe_action", None):
            cmd_stock_universe(args)
        else:
            print("用法: python main.py stock-universe {sync|stats|list}")
        return

    if cmd == "ops":
        if getattr(args, "ops_action", None):
            cmd_ops(args)
        else:
            print("用法: python main.py ops check [--json] [--verbose]")
        return

    if cmd == "signals":
        _normalize_signals_args(args)

    handler = _SIMPLE_HANDLERS.get(cmd)
    if handler:
        handler(args)
        return

    parser.print_help()


def main(argv: list[str] | None = None) -> None:
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = build_parser()
    args = parser.parse_args(argv)
    dispatch(args, parser)
