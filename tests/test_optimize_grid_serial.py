"""串行網格搜索 top_n 切片修復"""
from unittest.mock import patch

from src.core.optimize import grid_search


def test_grid_search_serial_returns_top_n():
    fake_results = [
        {"params": {"fast": 5, "slow": 20}, "total_trades": 5, "sharpe_ratio": 1.0,
         "total_return_pct": 10, "max_drawdown_pct": 5, "win_rate_pct": 50, "final_value": 110000},
        {"params": {"fast": 3, "slow": 30}, "total_trades": 8, "sharpe_ratio": 2.0,
         "total_return_pct": 20, "max_drawdown_pct": 8, "win_rate_pct": 60, "final_value": 120000},
        {"params": {"fast": 8, "slow": 40}, "total_trades": 3, "sharpe_ratio": 0.5,
         "total_return_pct": 2, "max_drawdown_pct": 12, "win_rate_pct": 40, "final_value": 102000},
    ]

    def fake_run(code, strategy_name, params, run_ctx=None):
        for r in fake_results:
            if r["params"] == params:
                return {k: v for k, v in r.items()}
        raise ValueError("unknown params")

    with patch("src.core.optimize.settings") as st:
        st.task_parallel_grid = False
        with patch("src.core.optimize.PARAM_GRIDS", {"dual_ma": {"fast": [3, 5, 8], "slow": [20, 30, 40]}}):
            with patch("src.core.optimize._run_single", side_effect=fake_run):
                with patch("src.core.optimize._add_oos_validation", side_effect=lambda x, *a: x):
                    out = grid_search("600519", "dual_ma", top_n=2, verbose=False)
    assert len(out) == 2
    assert out[0]["sharpe_ratio"] >= out[1]["sharpe_ratio"]
