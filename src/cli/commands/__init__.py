"""CLI 命令處理函數。"""

from src.cli.commands.ops import cmd_ops
from src.cli.commands.core import (
    cmd_config,
    cmd_serve,
    cmd_download,
    cmd_seed,
    cmd_monitor,
    cmd_scheduler,
    cmd_stock_universe,
)

from src.cli.commands.backtest import (
    cmd_backtest,
    cmd_optimize,
    cmd_walkforward,
    cmd_auto_optimize,
    cmd_heatmap,
    cmd_screen,
)

from src.cli.commands.portfolio import (
    cmd_portfolio,
    cmd_dynamic_portfolio,
    cmd_kelly,
    cmd_degradation,
    cmd_arbitrate,
    cmd_risk_parity,
    cmd_mvo,
    cmd_vol_target,
    cmd_max_diversification,
    cmd_anti_corr,
    cmd_regime_switch,
    cmd_black_litterman,
    cmd_hrp,
    cmd_cvar,
    cmd_multi_timeframe,
    cmd_dynamic_rebalance,
    cmd_sector_limit,
    cmd_voting_portfolio,
    cmd_momentum_of_momentum,
    cmd_adaptive_regime,
)

from src.cli.commands.strategy import (
    cmd_strategy_create,
    cmd_strategy_list,
    cmd_strategy_leaderboard,
)

from src.cli.commands.reports import (
    cmd_report,
    cmd_monte_carlo,
    cmd_rolling_metrics,
    cmd_export,
)

from src.cli.commands.signals import (
    cmd_signals,
)

from src.cli.commands.risk import (
    cmd_risk,
)

from src.cli.commands.users import (
    cmd_user_create,
    cmd_user_list,
    cmd_user_reset_password,
)
