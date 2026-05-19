"""
組合回測模塊 — 多策略 + 多股票 + 資金分配 + 再平衡
"""
import backtrader as bt
import pandas as pd
import numpy as np
from src.core.db import load_daily_kline
from src.config import settings
from src.core.backtest import STRATEGIES, prepare_data
from src.utils.logger import logger


def _run_strategy_on_data(
    strategy_name: str,
    code: str,
    params: dict = None,
    cash: float = None,
) -> dict:
    """單策略單股票回測，返回每日淨值序列"""
    if cash is None:
        cash = settings.backtest_cash

    strategy_cls = STRATEGIES[strategy_name]
    cerebro = bt.Cerebro()

    if params:
        cerebro.addstrategy(strategy_cls, **params)
    else:
        cerebro.addstrategy(strategy_cls)

    data = prepare_data(code)
    cerebro.adddata(data, name=code)

    cerebro.broker.setcash(cash)
    cerebro.broker.setcommission(commission=settings.backtest_commission)

    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe", riskfreerate=0.03)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(bt.analyzers.TimeReturn, _name="timereturn")

    initial_value = cerebro.broker.getvalue()
    results = cerebro.run()
    final_value = cerebro.broker.getvalue()
    strat = results[0]

    time_returns = strat.analyzers.timereturn.get_analysis()
    dates = sorted(time_returns.keys())
    daily_returns = [time_returns[d] for d in dates]

    nav = [1.0]
    for r in daily_returns:
        nav.append(nav[-1] * (1 + r))

    sharpe = strat.analyzers.sharpe.get_analysis()
    drawdown = strat.analyzers.drawdown.get_analysis()
    trades = strat.analyzers.trades.get_analysis()

    total_return = (final_value - initial_value) / initial_value * 100
    max_dd = drawdown.get("max", {}).get("drawdown", 0)
    total_trades = trades.get("total", {}).get("total", 0)
    won = trades.get("won", {}).get("total", 0)
    win_rate = (won / total_trades * 100) if total_trades > 0 else 0

    return {
        "strategy": strategy_name,
        "code": code,
        "params": params or {},
        "dates": dates,
        "daily_returns": daily_returns,
        "nav": nav,
        "total_return_pct": round(total_return, 4),
        "sharpe_ratio": sharpe.get("sharperatio"),
        "max_drawdown_pct": round(max_dd, 4),
        "total_trades": total_trades,
        "win_rate_pct": round(win_rate, 2),
        "final_value": final_value,
    }


def _align_navs(sub_results: list) -> tuple:
    """對齊多個子策略的淨值曲線"""
    date_sets = [set(r["dates"]) for r in sub_results]
    common_dates = sorted(set.intersection(*date_sets))

    if not common_dates:
        all_dates = sorted(set.union(*date_sets))
        aligned_navs = []
        for r in sub_results:
            date_to_return = dict(zip(r["dates"], r["daily_returns"]))
            nav = [1.0]
            for d in all_dates:
                ret = date_to_return.get(d, 0.0)
                nav.append(nav[-1] * (1 + ret))
            aligned_navs.append(nav)
        return all_dates, aligned_navs

    aligned_navs = []
    for r in sub_results:
        date_to_return = dict(zip(r["dates"], r["daily_returns"]))
        nav = [1.0]
        for d in common_dates:
            ret = date_to_return.get(d, 0.0)
            nav.append(nav[-1] * (1 + ret))
        aligned_navs.append(nav)

    return common_dates, aligned_navs


def _calc_portfolio_nav(
    aligned_navs: list,
    weights: list,
    rebalance_dates: list = None,
) -> list:
    """計算組合淨值"""
    total_weight = sum(weights)
    norm_weights = [w / total_weight for w in weights]

    n_periods = len(aligned_navs[0])
    portfolio_nav = [1.0]

    if rebalance_dates is None:
        for i in range(1, n_periods):
            portfolio_return = 0.0
            for j, nav in enumerate(aligned_navs):
                strategy_return = nav[i] / nav[i - 1] - 1
                portfolio_return += norm_weights[j] * strategy_return
            portfolio_nav.append(portfolio_nav[-1] * (1 + portfolio_return))
    else:
        current_weights = list(norm_weights)
        for i in range(1, n_periods):
            returns = [nav[i] / nav[i - 1] - 1 for nav in aligned_navs]
            portfolio_return = sum(w * r for w, r in zip(current_weights, returns))
            portfolio_nav.append(portfolio_nav[-1] * (1 + portfolio_return))

            new_values = [w * (1 + r) for w, r in zip(current_weights, returns)]
            total_val = sum(new_values)
            current_weights = [v / total_val for v in new_values]

            if i in rebalance_dates:
                current_weights = list(norm_weights)

    return portfolio_nav


def _calc_metrics(nav: list, dates: list, risk_free: float = 0.03) -> dict:
    """從淨值序列計算組合指標（含完整風險指標）"""
    n = len(nav)
    if n < 2:
        return {}

    total_return = (nav[-1] / nav[0] - 1) * 100

    from datetime import datetime
    if dates:
        start = dates[0] if isinstance(dates[0], datetime) else datetime.strptime(str(dates[0]), "%Y-%m-%d")
        end = dates[-1] if isinstance(dates[-1], datetime) else datetime.strptime(str(dates[-1]), "%Y-%m-%d")
        years = (end - start).days / 365.25
        annual_return = ((nav[-1] / nav[0]) ** (1 / years) - 1) * 100 if years > 0 else 0
    else:
        annual_return = 0

    daily_returns = [nav[i] / nav[i - 1] - 1 for i in range(1, n)]
    dr = np.array(daily_returns) if daily_returns else np.array([0.0])

    peak = nav[0]
    max_dd = 0
    for v in nav:
        if v > peak:
            peak = v
        dd = (peak - v) / peak * 100
        if dd > max_dd:
            max_dd = dd

    if daily_returns:
        mean_ret = np.mean(dr)
        std_ret = np.std(dr)
        sharpe = (mean_ret - risk_free / 252) / std_ret * (252 ** 0.5) if std_ret > 0 else 0
    else:
        sharpe = 0

    calmar = annual_return / max_dd if max_dd > 0 else 0

    # VaR 95%
    var_95 = float(np.percentile(dr, 5)) if len(dr) > 1 else 0
    # CVaR
    cvar_95 = float(np.mean(dr[dr <= var_95])) if len(dr) > 1 and np.any(dr <= var_95) else var_95
    # Sortino
    downside = dr[dr < 0]
    downside_std = float(np.std(downside)) if len(downside) > 0 else 1e-9
    sortino_ratio = (float(mean_ret) - risk_free / 252) / downside_std * np.sqrt(252) if downside_std > 0 and daily_returns else 0
    # Annual volatility
    annual_volatility = float(np.std(dr) * np.sqrt(252)) if len(dr) > 1 else 0
    # Max drawdown recovery days
    max_dd_recovery_days = 0
    peak_v = nav[0]
    peak_idx = 0
    dd_start_idx = None
    max_dd_idx = 0
    max_dd_val = 0
    for i, v in enumerate(nav):
        if v > peak_v:
            peak_v = v
            peak_idx = i
            dd_start_idx = None
        dd = (peak_v - v) / peak_v
        if dd > max_dd_val:
            max_dd_val = dd
            max_dd_idx = i
            dd_start_idx = peak_idx
    if dd_start_idx is not None and max_dd_val > 0:
        peak_at_dd = nav[dd_start_idx]
        for i in range(max_dd_idx, len(nav)):
            if nav[i] >= peak_at_dd:
                max_dd_recovery_days = i - max_dd_idx
                break
        else:
            max_dd_recovery_days = len(nav) - 1 - max_dd_idx
    # Monthly win rate
    monthly_win_rate = 0
    if dates and len(dates) > 20:
        from collections import defaultdict
        month_returns = defaultdict(float)
        for i, d in enumerate(dates):
            dt = d if isinstance(d, datetime) else datetime.strptime(str(d), "%Y-%m-%d")
            key = dt.strftime("%Y-%m")
            if i < len(daily_returns):
                month_returns[key] += daily_returns[i]
        if month_returns:
            wins = sum(1 for v in month_returns.values() if v > 0)
            monthly_win_rate = wins / len(month_returns) * 100
    # Profit/Loss ratio
    profit_loss_ratio = 0
    wins_arr = dr[dr > 0]
    losses_arr = dr[dr < 0]
    if len(wins_arr) > 0 and len(losses_arr) > 0:
        profit_loss_ratio = float(np.mean(wins_arr) / abs(np.mean(losses_arr)))

    return {
        "total_return_pct": round(total_return, 4),
        "annual_return_pct": round(annual_return, 4),
        "max_drawdown_pct": round(max_dd, 4),
        "sharpe_ratio": round(sharpe, 4),
        "calmar_ratio": round(calmar, 4),
        "var_95": round(var_95, 6),
        "cvar_95": round(cvar_95, 6),
        "sortino_ratio": round(sortino_ratio, 4),
        "annual_volatility": round(annual_volatility, 4),
        "max_drawdown_recovery_days": max_dd_recovery_days,
        "monthly_win_rate": round(monthly_win_rate, 2),
        "profit_loss_ratio": round(profit_loss_ratio, 4),
    }


def run_portfolio(
    allocations: list[dict],
    weights: list[float] = None,
    rebalance: str = "none",
    rebalance_freq_days: int = 20,
    cash: float = None,
    verbose: bool = True,
) -> dict:
    """組合回測"""
    if cash is None:
        cash = settings.backtest_cash

    if weights is None:
        weights = []
        for a in allocations:
            if "weight" in a:
                weights.append(a["weight"])
            else:
                weights.append(1.0 / len(allocations))

    total_w = sum(weights)
    weights = [w / total_w for w in weights]

    logger.info(f"組合回測: {len(allocations)} 個子策略, 再平衡={rebalance}")

    sub_results = []
    for i, a in enumerate(allocations):
        try:
            r = _run_strategy_on_data(
                a["strategy"], a["code"],
                params=a.get("params"),
                cash=cash * weights[i],
            )
            sub_results.append(r)
            logger.info(f"  [{i+1}] {a['strategy']}/{a['code']}: {r['total_return_pct']:.2f}%")
        except Exception as e:
            logger.error(f"  [{i+1}] {a['strategy']}/{a['code']} 失敗: {e}")

    if not sub_results:
        logger.error("所有子策略均失敗")
        return {}

    common_dates, aligned_navs = _align_navs(sub_results)
    active_weights = [weights[i] for i in range(len(sub_results))]

    rebalance_dates = None
    if rebalance == "periodic" and rebalance_freq_days:
        n_periods = len(aligned_navs[0])
        rebalance_dates = list(range(rebalance_freq_days, n_periods, rebalance_freq_days))

    portfolio_nav = _calc_portfolio_nav(aligned_navs, active_weights, rebalance_dates)
    equal_weight_nav = _calc_portfolio_nav(aligned_navs, [1.0] * len(aligned_navs), None)

    portfolio_metrics = _calc_metrics(portfolio_nav, common_dates)

    sub_metrics = []
    for i, r in enumerate(sub_results):
        m = _calc_metrics(r["nav"], r["dates"])
        m["strategy"] = r["strategy"]
        m["code"] = r["code"]
        m["weight"] = active_weights[i]
        sub_metrics.append(m)

    result = {
        "portfolio": portfolio_metrics,
        "sub_strategies": sub_metrics,
        "portfolio_nav": portfolio_nav,
        "equal_weight_nav": equal_weight_nav,
        "dates": [str(d) for d in common_dates],
        "weights": active_weights,
        "rebalance": rebalance,
        "cash": cash,
    }

    # 計算相關性矩陣和風險貢獻
    try:
        correlations = calc_strategy_correlations(sub_results)
        result["correlations"] = correlations
    except Exception as e:
        logger.debug(f"相關性計算跳過: {e}")

    try:
        risk_contrib = _calc_risk_contribution(sub_results, active_weights)
        result["risk_contribution"] = risk_contrib
    except Exception as e:
        logger.debug(f"風險貢獻計算跳過: {e}")

    logger.info(
        f"組合回測完成: 收益 {portfolio_metrics.get('total_return_pct', 0):.2f}%, "
        f"夏普 {portfolio_metrics.get('sharpe_ratio', 0):.2f}, "
        f"回撤 {portfolio_metrics.get('max_drawdown_pct', 0):.2f}%"
    )

    return result


def calc_strategy_correlations(sub_results: list) -> dict:
    """
    計算子策略之間的相關性矩陣。
    
    Args:
        sub_results: _run_strategy_on_data 返回的結果列表
    
    Returns:
        {"labels": [...], "matrix": [[...], ...]}
    """
    if len(sub_results) < 2:
        return {"labels": [], "matrix": []}

    # 對齊日期
    date_sets = [set(r["dates"]) for r in sub_results]
    common_dates = sorted(set.intersection(*date_sets))

    if len(common_dates) < 20:
        return {"labels": [], "matrix": []}

    labels = [f"{r['strategy']}/{r['code']}" for r in sub_results]

    # 構建收益率矩陣
    returns_matrix = []
    for r in sub_results:
        date_to_ret = dict(zip(r["dates"], r["daily_returns"]))
        returns_matrix.append([date_to_ret.get(d, 0.0) for d in common_dates])

    import numpy as np
    returns_arr = np.array(returns_matrix)
    corr_matrix = np.corrcoef(returns_arr)

    matrix = []
    for row in corr_matrix:
        matrix.append([round(float(v), 4) for v in row])

    return {"labels": labels, "matrix": matrix}


def _calc_risk_contribution(sub_results: list, weights: list) -> list:
    """計算每個子策略的風險貢獻"""
    if len(sub_results) < 2:
        return []

    import numpy as np

    date_sets = [set(r["dates"]) for r in sub_results]
    common_dates = sorted(set.intersection(*date_sets))

    if len(common_dates) < 20:
        return []

    returns_matrix = []
    for r in sub_results:
        date_to_ret = dict(zip(r["dates"], r["daily_returns"]))
        returns_matrix.append([date_to_ret.get(d, 0.0) for d in common_dates])

    returns_arr = np.array(returns_matrix)
    cov_matrix = np.cov(returns_arr)

    total_weight = sum(weights)
    norm_weights = np.array([w / total_weight for w in weights])

    port_var = norm_weights @ cov_matrix @ norm_weights
    if port_var <= 0:
        return []

    marginal_contrib = cov_matrix @ norm_weights
    risk_contrib = norm_weights * marginal_contrib / np.sqrt(port_var)

    labels = [f"{r['strategy']}/{r['code']}" for r in sub_results]
    result = []
    for i, label in enumerate(labels):
        result.append({
            "strategy": sub_results[i]["strategy"],
            "code": sub_results[i]["code"],
            "weight": round(float(norm_weights[i]), 4),
            "risk_contribution": round(float(risk_contrib[i]), 4),
            "risk_pct": round(float(risk_contrib[i] / np.sum(np.abs(risk_contrib)) * 100), 2)
            if np.sum(np.abs(risk_contrib)) > 0 else 0,
        })

    return result


def dynamic_weight_portfolio(
    allocations: list[dict],
    rolling_window: int = 60,
    rebalance_freq_days: int = 20,
    cash: float = None,
) -> dict:
    """
    動態權重組合回測。
    根據最近 N 天的滾動夏普比率動態調整子策略權重，
    表現好的策略獲得更高權重。

    Args:
        allocations: 子策略配置列表 [{"strategy": ..., "code": ..., "params": ...}]
        rolling_window: 滾動窗口天數（用於計算近期夏普）
        rebalance_freq_days: 權重調整頻率（天）
        cash: 初始資金

    Returns:
        包含動態權重軌跡和組合指標的字典
    """
    if cash is None:
        cash = settings.backtest_cash

    logger.info(f"動態權重組合: {len(allocations)} 個子策略, 窗口={rolling_window}天")

    # 運行所有子策略
    sub_results = []
    for i, a in enumerate(allocations):
        try:
            r = _run_strategy_on_data(
                a["strategy"], a["code"],
                params=a.get("params"),
                cash=cash / len(allocations),
            )
            sub_results.append(r)
            logger.info(f"  [{i+1}] {a['strategy']}/{a['code']}: {r['total_return_pct']:.2f}%")
        except Exception as e:
            logger.error(f"  [{i+1}] {a['strategy']}/{a['code']} 失敗: {e}")

    if not sub_results:
        return {}

    # 對齊日期
    common_dates, aligned_navs = _align_navs(sub_results)
    n_periods = len(aligned_navs[0])
    n_strategies = len(sub_results)

    # 計算每日收益率
    daily_returns_matrix = []
    for nav in aligned_navs:
        dr = [0.0] + [nav[i] / nav[i - 1] - 1 for i in range(1, n_periods)]
        daily_returns_matrix.append(dr)

    # 動態權重計算：根據滾動窗口夏普分配權重
    default_weight = 1.0 / n_strategies
    current_weights = [default_weight] * n_strategies
    weight_history = [[default_weight] * n_strategies]
    portfolio_nav = [1.0]

    for i in range(1, n_periods):
        # 計算組合收益
        port_ret = sum(
            current_weights[j] * (aligned_navs[j][i] / aligned_navs[j][i - 1] - 1)
            for j in range(n_strategies)
        )
        portfolio_nav.append(portfolio_nav[-1] * (1 + port_ret))

        # 按固定頻率調整權重
        if i % rebalance_freq_days == 0 and i >= rolling_window:
            # 計算每個策略的滾動夏普
            sharpes = []
            for j in range(n_strategies):
                window_returns = daily_returns_matrix[j][max(0, i - rolling_window + 1):i + 1]
                if len(window_returns) < 10 or np.std(window_returns) == 0:
                    sharpes.append(0.0)
                else:
                    sr = np.mean(window_returns) / np.std(window_returns) * np.sqrt(252)
                    sharpes.append(sr)

            # 將夏普轉為權重（只獎勵正夏普，負夏普給最低權重）
            min_sharpe = min(sharpes)
            shifted = [s - min_sharpe + 0.1 for s in sharpes]  # 平移確保正值
            total = sum(shifted)
            current_weights = [s / total for s in shifted]
            logger.debug(f"  第 {i} 天權重調整: {[round(w, 3) for w in current_weights]}")

        weight_history.append(list(current_weights))

    # 計算指標
    portfolio_metrics = _calc_metrics(portfolio_nav, common_dates)

    sub_metrics = []
    for i, r in enumerate(sub_results):
        m = _calc_metrics(r["nav"], r["dates"])
        m["strategy"] = r["strategy"]
        m["code"] = r["code"]
        sub_metrics.append(m)

    return {
        "portfolio": portfolio_metrics,
        "sub_strategies": sub_metrics,
        "portfolio_nav": portfolio_nav,
        "dates": [str(d) for d in common_dates],
        "weight_history": weight_history,
        "rolling_window": rolling_window,
        "rebalance_freq_days": rebalance_freq_days,
        "cash": cash,
    }


def detect_degradation(
    allocations: list[dict],
    lookback_days: int = 30,
    threshold_days: int = 5,
    weight_reduction: float = 0.5,
    cash: float = None,
) -> dict:
    """
    策略衰退檢測。
    如果某子策略連續 N 天跑輸基準（所有策略等權組合），則標記為衰退，
    並將其權重縮減。

    Args:
        allocations: 子策略配置列表
        lookback_days: 回看天數
        threshold_days: 連續跑輸天數閾值
        weight_reduction: 衰退策略的權重縮減比例 (0-1)
        cash: 初始資金

    Returns:
        包含各策略衰退狀態和調整後權重的字典
    """
    if cash is None:
        cash = settings.backtest_cash

    logger.info(f"衰退檢測: 回看={lookback_days}天, 閾值={threshold_days}天")

    # 運行所有子策略
    sub_results = []
    for i, a in enumerate(allocations):
        try:
            r = _run_strategy_on_data(
                a["strategy"], a["code"],
                params=a.get("params"),
                cash=cash / len(allocations),
            )
            sub_results.append(r)
        except Exception as e:
            logger.error(f"  [{i+1}] {a['strategy']}/{a['code']} 失敗: {e}")

    if not sub_results:
        return {}

    # 對齊
    common_dates, aligned_navs = _align_navs(sub_results)
    n_periods = len(aligned_navs[0])
    n_strategies = len(sub_results)

    # 計算基準（等權組合）每日收益
    benchmark_returns = []
    for i in range(1, n_periods):
        eq_ret = sum(
            aligned_navs[j][i] / aligned_navs[j][i - 1] - 1
            for j in range(n_strategies)
        ) / n_strategies
        benchmark_returns.append(eq_ret)

    # 檢測每個策略的衰退狀態
    degradation_status = []
    adjusted_weights = []

    for j in range(n_strategies):
        strat_returns = [
            aligned_navs[j][i] / aligned_navs[j][i - 1] - 1
            for i in range(1, n_periods)
        ]

        # 取最近 lookback_days 天
        recent_strat = strat_returns[-lookback_days:] if len(strat_returns) >= lookback_days else strat_returns
        recent_bench = benchmark_returns[-lookback_days:] if len(benchmark_returns) >= lookback_days else benchmark_returns

        # 計算連續跑輸天數（從最近往回數）
        consecutive_under = 0
        for k in range(len(recent_strat) - 1, -1, -1):
            if recent_strat[k] < recent_bench[k]:
                consecutive_under += 1
            else:
                break

        is_degraded = consecutive_under >= threshold_days
        status = {
            "strategy": sub_results[j]["strategy"],
            "code": sub_results[j]["code"],
            "consecutive_underperform_days": consecutive_under,
            "is_degraded": is_degraded,
            "recent_return_pct": round(sum(recent_strat) * 100, 4),
            "benchmark_return_pct": round(sum(recent_bench) * 100, 4),
        }
        degradation_status.append(status)

        if is_degraded:
            adjusted_weights.append(weight_reduction)
            logger.warning(
                f"  ⚠ {status['strategy']}/{status['code']} 衰退！"
                f"連續 {consecutive_under} 天跑輸基準"
            )
        else:
            adjusted_weights.append(1.0)

    # 歸一化權重
    total_w = sum(adjusted_weights)
    adjusted_weights = [w / total_w for w in adjusted_weights]

    return {
        "degradation_status": degradation_status,
        "adjusted_weights": adjusted_weights,
        "lookback_days": lookback_days,
        "threshold_days": threshold_days,
        "weight_reduction": weight_reduction,
    }


def kelly_criterion(
    allocations: list[dict],
    cash: float = None,
    fraction_limit: float = 0.5,
) -> dict:
    """
    Kelly 公式計算最優倉位比例。
    f* = (b*p - q) / b
    其中 b = 平均盈利/平均虧損, p = 勝率, q = 1 - p

    Args:
        allocations: 子策略配置列表
        cash: 初始資金
        fraction_limit: Kelly 比例上限（防止過度集中）

    Returns:
        包含每個策略的 Kelly 最優比例和推薦倉位的字典
    """
    if cash is None:
        cash = settings.backtest_cash

    logger.info(f"Kelly 公式: {len(allocations)} 個子策略")

    results = []
    for i, a in enumerate(allocations):
        try:
            r = _run_strategy_on_data(
                a["strategy"], a["code"],
                params=a.get("params"),
                cash=cash,
            )

            # 從日收益率計算 Kelly 參數
            daily_rets = np.array(r["daily_returns"])
            wins = daily_rets[daily_rets > 0]
            losses = daily_rets[daily_rets < 0]

            if len(wins) == 0 or len(losses) == 0:
                # 無法計算 Kelly（沒有盈利或虧損交易）
                results.append({
                    "strategy": a["strategy"],
                    "code": a["code"],
                    "kelly_fraction": 0.0,
                    "recommended_position": 0.0,
                    "win_rate": round(len(wins) / len(daily_rets) * 100, 2) if len(daily_rets) > 0 else 0,
                    "avg_win": 0.0,
                    "avg_loss": 0.0,
                    "note": "數據不足或單邊收益，無法計算 Kelly",
                })
                continue

            avg_win = float(np.mean(wins))
            avg_loss = float(np.mean(np.abs(losses)))
            b = avg_win / avg_loss  # 賠率
            p = len(wins) / len(daily_rets)  # 勝率
            q = 1 - p

            # Kelly 公式: f* = (bp - q) / b
            kelly_f = (b * p - q) / b

            # 限制上限，避免過度集中
            kelly_f = max(0.0, min(kelly_f, fraction_limit))

            recommended_position = round(cash * kelly_f, 2)

            results.append({
                "strategy": a["strategy"],
                "code": a["code"],
                "kelly_fraction": round(kelly_f, 6),
                "recommended_position": recommended_position,
                "win_rate": round(p * 100, 2),
                "avg_win_pct": round(avg_win * 100, 4),
                "avg_loss_pct": round(avg_loss * 100, 4),
                "odds_ratio": round(b, 4),
                "expected_growth": round(kelly_f * (p * avg_win - q * avg_loss), 8),
            })

            logger.info(
                f"  [{i+1}] {a['strategy']}/{a['code']}: "
                f"Kelly={kelly_f:.4f}, 勝率={p*100:.1f}%, 賠率={b:.2f}"
            )

        except Exception as e:
            logger.error(f"  [{i+1}] {a['strategy']}/{a['code']} 失敗: {e}")
            results.append({
                "strategy": a["strategy"],
                "code": a["code"],
                "kelly_fraction": 0.0,
                "error": str(e),
            })

    # 半 Kelly（更保守的建議）
    for r in results:
        r["half_kelly_fraction"] = round(r.get("kelly_fraction", 0) / 2, 6)
        r["half_kelly_position"] = round(cash * r.get("kelly_fraction", 0) / 2, 2)

    return {
        "kelly_results": results,
        "total_capital": cash,
        "fraction_limit": fraction_limit,
    }


def arbitrate_signals(
    strategy_signals: list[dict],
    allocations: list[dict] = None,
    rolling_window: int = 60,
    cash: float = None,
) -> dict:
    """
    信號衝突仲裁。
    當多個策略給出矛盾信號（部分買入、部分賣出）時，
    使用加權投票系統決定最終動作。權重基於近期夏普比率。

    Args:
        strategy_signals: 策略信號列表
            [{"strategy": str, "code": str, "signal": "buy"|"sell"|"hold"}]
        allocations: 子策略配置（用於計算近期夏普作為投票權重），
                     若為 None 則使用等權投票
        rolling_window: 滾動窗口天數
        cash: 初始資金

    Returns:
        包含仲裁結果和投票詳情的字典
    """
    if cash is None:
        cash = settings.backtest_cash

    logger.info(f"信號仲裁: {len(strategy_signals)} 個策略信號")

    # 計算每個策略的投票權重（基於近期夏普）
    weights = {}
    if allocations:
        for i, a in enumerate(allocations):
            try:
                r = _run_strategy_on_data(
                    a["strategy"], a["code"],
                    params=a.get("params"),
                    cash=cash / len(allocations),
                )
                daily_rets = np.array(r["daily_returns"])
                # 取最近 rolling_window 天
                recent = daily_rets[-rolling_window:] if len(daily_rets) >= rolling_window else daily_rets
                if len(recent) > 1 and np.std(recent) > 0:
                    sr = float(np.mean(recent) / np.std(recent) * np.sqrt(252))
                    # 將夏普轉為正權重（最低 0.1）
                    weights[f"{a['strategy']}/{a['code']}"] = max(0.1, sr + 1.0)
                else:
                    weights[f"{a['strategy']}/{a['code']}"] = 1.0
            except Exception:
                weights[f"{a['strategy']}/{a['code']}"] = 1.0
    else:
        # 等權
        for s in strategy_signals:
            key = f"{s['strategy']}/{s['code']}"
            weights[key] = 1.0

    # 加權投票
    vote_details = []
    buy_score = 0.0
    sell_score = 0.0
    hold_score = 0.0

    for s in strategy_signals:
        key = f"{s['strategy']}/{s['code']}"
        w = weights.get(key, 1.0)
        signal = s.get("signal", "hold").lower()

        detail = {
            "strategy": s["strategy"],
            "code": s["code"],
            "signal": signal,
            "weight": round(w, 4),
            "vote_value": 0.0,
        }

        if signal == "buy":
            buy_score += w
            detail["vote_value"] = round(w, 4)
        elif signal == "sell":
            sell_score += w
            detail["vote_value"] = round(-w, 4)
        else:  # hold
            hold_score += w
            detail["vote_value"] = 0.0

        vote_details.append(detail)

    total_score = buy_score + sell_score + hold_score
    # 決定最終動作
    if buy_score > sell_score and buy_score > hold_score:
        final_action = "buy"
        confidence = buy_score / total_score if total_score > 0 else 0
    elif sell_score > buy_score and sell_score > hold_score:
        final_action = "sell"
        confidence = sell_score / total_score if total_score > 0 else 0
    else:
        final_action = "hold"
        confidence = hold_score / total_score if total_score > 0 else 0

    # 衝突程度
    conflict_level = "none"
    active_votes = buy_score + sell_score
    if active_votes > 0:
        minority = min(buy_score, sell_score)
        conflict_ratio = minority / active_votes
        if conflict_ratio > 0.4:
            conflict_level = "high"
        elif conflict_ratio > 0.2:
            conflict_level = "medium"
        else:
            conflict_level = "low"

    result = {
        "final_action": final_action,
        "confidence": round(confidence, 4),
        "buy_score": round(buy_score, 4),
        "sell_score": round(sell_score, 4),
        "hold_score": round(hold_score, 4),
        "conflict_level": conflict_level,
        "vote_details": vote_details,
    }

    logger.info(
        f"  仲裁結果: {final_action} (信心={confidence:.2f}), "
        f"買={buy_score:.2f} 賣={sell_score:.2f} 持={hold_score:.2f}, "
        f"衝突={conflict_level}"
    )

    return result


# ============================================================
# 策略組合進階 — 第二批功能
# ============================================================


def risk_parity_portfolio(
    allocations: list[dict],
    cash: float = None,
    max_iter: int = 1000,
    tol: float = 1e-8,
) -> dict:
    """
    風險平價組合。
    每個子策略對組合總風險的貢獻相等（而非簡單等權）。
    使用迭代法求解最優權重，使得各策略的邊際風險貢獻趨於一致。

    Args:
        allocations: 子策略配置列表
        cash: 初始資金
        max_iter: 最大迭代次數
        tol: 收斂精度

    Returns:
        包含風險平價權重和組合指標的字典
    """
    if cash is None:
        cash = settings.backtest_cash

    logger.info(f"風險平價組合: {len(allocations)} 個子策略")

    # 運行所有子策略
    sub_results = []
    for i, a in enumerate(allocations):
        try:
            r = _run_strategy_on_data(a["strategy"], a["code"], params=a.get("params"), cash=cash / len(allocations))
            sub_results.append(r)
            logger.info(f"  [{i+1}] {a['strategy']}/{a['code']}: {r['total_return_pct']:.2f}%")
        except Exception as e:
            logger.error(f"  [{i+1}] {a['strategy']}/{a['code']} 失敗: {e}")

    if len(sub_results) < 2:
        return {"error": "至少需要 2 個有效子策略"}

    # 對齊收益率
    common_dates, aligned_navs = _align_navs(sub_results)
    n = len(aligned_navs[0])
    n_strats = len(sub_results)

    returns_matrix = []
    for nav in aligned_navs:
        dr = [0.0] + [nav[i] / nav[i - 1] - 1 for i in range(1, n)]
        returns_matrix.append(dr)

    returns_arr = np.array(returns_matrix)
    cov_matrix = np.cov(returns_arr)

    # 迭代求解風險平價權重
    # 目標：每個策略的 w_i * (Σw)_i / σ_p 相等
    weights = np.ones(n_strats) / n_strats

    for iteration in range(max_iter):
        port_var = weights @ cov_matrix @ weights
        if port_var <= 0:
            break
        port_vol = np.sqrt(port_var)

        # 邊際風險貢獻
        marginal = cov_matrix @ weights
        # 每個策略的風險貢獻
        risk_contrib = weights * marginal / port_vol

        # 目標：所有風險貢獻相等
        target_rc = port_vol / n_strats

        # 更新權重（梯度下降）
        new_weights = weights.copy()
        for i in range(n_strats):
            if risk_contrib[i] > 0:
                # 風險貢獻過高 → 降權重，過低 → 升權重
                adjustment = target_rc / risk_contrib[i]
                new_weights[i] *= adjustment ** 0.5  # 用 0.5 次方避免震盪

        # 歸一化
        new_weights = new_weights / np.sum(new_weights)

        # 檢查收斂
        if np.max(np.abs(new_weights - weights)) < tol:
            weights = new_weights
            logger.info(f"  風險平價收斂: 第 {iteration} 次迭代")
            break
        weights = new_weights

    # 計算組合淨值
    weights_list = [float(w) for w in weights]
    portfolio_nav = _calc_portfolio_nav(aligned_navs, weights_list)

    # 計算指標
    portfolio_metrics = _calc_metrics(portfolio_nav, common_dates)

    # 計算各策略的風險貢獻百分比
    port_var = weights @ cov_matrix @ weights
    port_vol = np.sqrt(port_var) if port_var > 0 else 1e-9
    marginal = cov_matrix @ weights
    risk_contrib = weights * marginal / port_vol
    total_rc = np.sum(np.abs(risk_contrib))
    risk_pcts = [float(rc / total_rc * 100) if total_rc > 0 else 0 for rc in risk_contrib]

    sub_metrics = []
    for i, r in enumerate(sub_results):
        m = _calc_metrics(r["nav"], r["dates"])
        m["strategy"] = r["strategy"]
        m["code"] = r["code"]
        m["weight"] = round(weights_list[i], 4)
        m["risk_contribution_pct"] = round(risk_pcts[i], 2)
        sub_metrics.append(m)

    return {
        "portfolio": portfolio_metrics,
        "sub_strategies": sub_metrics,
        "portfolio_nav": portfolio_nav,
        "dates": [str(d) for d in common_dates],
        "weights": [round(w, 4) for w in weights_list],
        "method": "risk_parity",
        "cash": cash,
    }


def mean_variance_optimize(
    allocations: list[dict],
    objective: str = "max_sharpe",
    cash: float = None,
    n_simulations: int = 5000,
) -> dict:
    """
    均值-方差優化（Markowitz）。
    通過蒙特卡羅模擬找到最優權重組合。

    Args:
        allocations: 子策略配置列表
        objective: 優化目標
            - "max_sharpe": 最大夏普比率
            - "min_variance": 最小方差
            - "max_return": 最大收益（約束下）
        cash: 初始資金
        n_simulations: 蒙特卡羅模擬次數

    Returns:
        包含最優權重和有效前沿信息的字典
    """
    if cash is None:
        cash = settings.backtest_cash

    logger.info(f"均值-方差優化: 目標={objective}, 模擬={n_simulations}次")

    # 運行所有子策略
    sub_results = []
    for i, a in enumerate(allocations):
        try:
            r = _run_strategy_on_data(a["strategy"], a["code"], params=a.get("params"), cash=cash / len(allocations))
            sub_results.append(r)
        except Exception as e:
            logger.error(f"  [{i+1}] {a['strategy']}/{a['code']} 失敗: {e}")

    if len(sub_results) < 2:
        return {"error": "至少需要 2 個有效子策略"}

    # 對齊
    common_dates, aligned_navs = _align_navs(sub_results)
    n = len(aligned_navs[0])
    n_strats = len(sub_results)

    returns_matrix = []
    for nav in aligned_navs:
        dr = [0.0] + [nav[i] / nav[i - 1] - 1 for i in range(1, n)]
        returns_matrix.append(dr)

    returns_arr = np.array(returns_matrix)
    mean_returns = np.mean(returns_arr, axis=1) * 252  # 年化
    cov_matrix = np.cov(returns_arr) * 252  # 年化

    # 蒙特卡羅模擬
    results = []
    for _ in range(n_simulations):
        w = np.random.dirichlet(np.ones(n_strats))
        port_ret = float(w @ mean_returns)
        port_vol = float(np.sqrt(w @ cov_matrix @ w))
        sharpe = (port_ret - 0.03) / port_vol if port_vol > 0 else 0
        results.append({"weights": w, "return": port_ret, "volatility": port_vol, "sharpe": sharpe})

    # 按目標選擇最優組合
    if objective == "max_sharpe":
        best = max(results, key=lambda x: x["sharpe"])
    elif objective == "min_variance":
        best = min(results, key=lambda x: x["volatility"])
    elif objective == "max_return":
        best = max(results, key=lambda x: x["return"])
    else:
        best = max(results, key=lambda x: x["sharpe"])

    best_weights = [float(w) for w in best["weights"]]

    # 計算組合淨值
    portfolio_nav = _calc_portfolio_nav(aligned_navs, best_weights)
    portfolio_metrics = _calc_metrics(portfolio_nav, common_dates)

    sub_metrics = []
    for i, r in enumerate(sub_results):
        m = _calc_metrics(r["nav"], r["dates"])
        m["strategy"] = r["strategy"]
        m["code"] = r["code"]
        m["weight"] = round(best_weights[i], 4)
        sub_metrics.append(m)

    # 收集有效前沿點（取前 100 個不同風險水平的最優點）
    frontier_points = []
    results.sort(key=lambda x: x["volatility"])
    step = max(1, len(results) // 100)
    for r in results[::step][:100]:
        frontier_points.append({
            "return": round(r["return"] * 100, 4),
            "risk": round(r["volatility"] * 100, 4),
            "sharpe": round(r["sharpe"], 4),
            "weights": [round(float(w), 4) for w in r["weights"]],
        })

    return {
        "portfolio": portfolio_metrics,
        "sub_strategies": sub_metrics,
        "portfolio_nav": portfolio_nav,
        "dates": [str(d) for d in common_dates],
        "optimal_weights": [round(w, 4) for w in best_weights],
        "objective": objective,
        "optimal_return_pct": round(best["return"] * 100, 4),
        "optimal_volatility_pct": round(best["volatility"] * 100, 4),
        "optimal_sharpe": round(best["sharpe"], 4),
        "frontier_points": frontier_points,
        "n_simulations": n_simulations,
        "cash": cash,
    }


def volatility_targeting(
    allocations: list[dict],
    target_vol: float = 0.15,
    lookback_days: int = 20,
    leverage_range: tuple = (0.2, 2.0),
    cash: float = None,
) -> dict:
    """
    波動率目標組合。
    根據近期實際波動率動態調整總倉位比例：
    - 波動率高 → 降倉（避免過大風險）
    - 波動率低 → 加倉（充分利用資金）

    Args:
        allocations: 子策略配置列表
        target_vol: 目標年化波動率（如 0.15 = 15%）
        lookback_days: 波動率計算窗口
        leverage_range: 槓桿範圍 (最小, 最大)
        cash: 初始資金

    Returns:
        包含槓桿軌跡和組合指標的字典
    """
    if cash is None:
        cash = settings.backtest_cash

    logger.info(f"波動率目標: 目標={target_vol:.1%}, 窗口={lookback_days}天")

    # 運行所有子策略
    sub_results = []
    for i, a in enumerate(allocations):
        try:
            r = _run_strategy_on_data(a["strategy"], a["code"], params=a.get("params"), cash=cash / len(allocations))
            sub_results.append(r)
        except Exception as e:
            logger.error(f"  [{i+1}] {a['strategy']}/{a['code']} 失敗: {e}")

    if not sub_results:
        return {"error": "所有子策略均失敗"}

    # 對齊
    common_dates, aligned_navs = _align_navs(sub_results)
    n = len(aligned_navs[0])
    n_strats = len(sub_results)

    # 等權組合的每日收益
    eq_weights = [1.0 / n_strats] * n_strats
    daily_returns = []
    for i in range(1, n):
        port_ret = sum(
            eq_weights[j] * (aligned_navs[j][i] / aligned_navs[j][i - 1] - 1)
            for j in range(n_strats)
        )
        daily_returns.append(port_ret)

    # 動態調整槓桿
    leverage_history = []
    portfolio_nav = [1.0]

    for i in range(len(daily_returns)):
        # 計算近期已實現波動率
        start_idx = max(0, i - lookback_days + 1)
        window = daily_returns[start_idx:i + 1]
        if len(window) >= 5:
            realized_vol = float(np.std(window) * np.sqrt(252))
        else:
            realized_vol = target_vol  # 初始假設等於目標

        # 槓桿 = 目標波動率 / 已實現波動率
        if realized_vol > 0:
            leverage = target_vol / realized_vol
        else:
            leverage = 1.0

        # 限制範圍
        leverage = max(leverage_range[0], min(leverage, leverage_range[1]))
        leverage_history.append(round(leverage, 4))

        # 計算帶槓桿的組合收益
        leveraged_ret = daily_returns[i] * leverage
        portfolio_nav.append(portfolio_nav[-1] * (1 + leveraged_ret))

    portfolio_metrics = _calc_metrics(portfolio_nav, common_dates)

    sub_metrics = []
    for i, r in enumerate(sub_results):
        m = _calc_metrics(r["nav"], r["dates"])
        m["strategy"] = r["strategy"]
        m["code"] = r["code"]
        sub_metrics.append(m)

    # 計算槓桿統計
    lev_arr = np.array(leverage_history)

    return {
        "portfolio": portfolio_metrics,
        "sub_strategies": sub_metrics,
        "portfolio_nav": portfolio_nav,
        "dates": [str(d) for d in common_dates],
        "leverage_history": leverage_history,
        "target_vol": target_vol,
        "avg_leverage": round(float(np.mean(lev_arr)), 4),
        "min_leverage": round(float(np.min(lev_arr)), 4),
        "max_leverage": round(float(np.max(lev_arr)), 4),
        "lookback_days": lookback_days,
        "cash": cash,
    }


def max_diversification_portfolio(
    allocations: list[dict],
    cash: float = None,
    n_simulations: int = 5000,
) -> dict:
    """
    最大分散化組合。
    最大化「分散化比率」= 各資產加權平均波動率 / 組合波動率。
    該比率越高，組合越分散，越不依賴單一策略。

    Args:
        allocations: 子策略配置列表
        cash: 初始資金
        n_simulations: 蒙特卡羅模擬次數

    Returns:
        包含最大分散化權重和分散化比率的字典
    """
    if cash is None:
        cash = settings.backtest_cash

    logger.info(f"最大分散化組合: {len(allocations)} 個子策略")

    # 運行所有子策略
    sub_results = []
    for i, a in enumerate(allocations):
        try:
            r = _run_strategy_on_data(a["strategy"], a["code"], params=a.get("params"), cash=cash / len(allocations))
            sub_results.append(r)
        except Exception as e:
            logger.error(f"  [{i+1}] {a['strategy']}/{a['code']} 失敗: {e}")

    if len(sub_results) < 2:
        return {"error": "至少需要 2 個有效子策略"}

    # 對齊
    common_dates, aligned_navs = _align_navs(sub_results)
    n = len(aligned_navs[0])
    n_strats = len(sub_results)

    returns_matrix = []
    for nav in aligned_navs:
        dr = [0.0] + [nav[i] / nav[i - 1] - 1 for i in range(1, n)]
        returns_matrix.append(dr)

    returns_arr = np.array(returns_matrix)
    vols = np.std(returns_arr, axis=1)  # 各策略波動率
    cov_matrix = np.cov(returns_arr)

    # 蒙特卡羅搜索最大分散化比率
    best_ratio = 0
    best_weights = np.ones(n_strats) / n_strats

    for _ in range(n_simulations):
        w = np.random.dirichlet(np.ones(n_strats))
        port_vol = np.sqrt(w @ cov_matrix @ w)
        weighted_avg_vol = w @ vols  # 加權平均波動率
        div_ratio = weighted_avg_vol / port_vol if port_vol > 0 else 0

        if div_ratio > best_ratio:
            best_ratio = div_ratio
            best_weights = w.copy()

    best_weights_list = [float(w) for w in best_weights]

    # 計算組合淨值
    portfolio_nav = _calc_portfolio_nav(aligned_navs, best_weights_list)
    portfolio_metrics = _calc_metrics(portfolio_nav, common_dates)

    sub_metrics = []
    for i, r in enumerate(sub_results):
        m = _calc_metrics(r["nav"], r["dates"])
        m["strategy"] = r["strategy"]
        m["code"] = r["code"]
        m["weight"] = round(best_weights_list[i], 4)
        sub_metrics.append(m)

    return {
        "portfolio": portfolio_metrics,
        "sub_strategies": sub_metrics,
        "portfolio_nav": portfolio_nav,
        "dates": [str(d) for d in common_dates],
        "optimal_weights": [round(w, 4) for w in best_weights_list],
        "diversification_ratio": round(best_ratio, 4),
        "individual_vols": [round(float(v), 6) for v in vols],
        "method": "max_diversification",
        "cash": cash,
    }


def anti_correlation_portfolio(
    allocations: list[dict],
    cash: float = None,
    n_simulations: int = 5000,
) -> dict:
    """
    反相關組合。
    最小化策略間的總相關性，優先選擇低相關甚至負相關的策略組合。
    權重優化目標：最小化 w^T * R * w（R 為相關性矩陣）。

    Args:
        allocations: 子策略配置列表
        cash: 初始資金
        n_simulations: 蒙特卡羅模擬次數

    Returns:
        包含反相關最優權重和相關性矩陣的字典
    """
    if cash is None:
        cash = settings.backtest_cash

    logger.info(f"反相關組合: {len(allocations)} 個子策略")

    # 運行所有子策略
    sub_results = []
    for i, a in enumerate(allocations):
        try:
            r = _run_strategy_on_data(a["strategy"], a["code"], params=a.get("params"), cash=cash / len(allocations))
            sub_results.append(r)
        except Exception as e:
            logger.error(f"  [{i+1}] {a['strategy']}/{a['code']} 失敗: {e}")

    if len(sub_results) < 2:
        return {"error": "至少需要 2 個有效子策略"}

    # 對齊
    common_dates, aligned_navs = _align_navs(sub_results)
    n = len(aligned_navs[0])
    n_strats = len(sub_results)

    returns_matrix = []
    for nav in aligned_navs:
        dr = [0.0] + [nav[i] / nav[i - 1] - 1 for i in range(1, n)]
        returns_matrix.append(dr)

    returns_arr = np.array(returns_matrix)
    corr_matrix = np.corrcoef(returns_arr)

    # 蒙特卡羅搜索最小化相關性加權組合
    # 目標函數：w^T * R * w（越小越好，代表組合內部相關性越低）
    best_score = float("inf")
    best_weights = np.ones(n_strats) / n_strats

    for _ in range(n_simulations):
        w = np.random.dirichlet(np.ones(n_strats))
        score = float(w @ corr_matrix @ w)
        if score < best_score:
            best_score = score
            best_weights = w.copy()

    best_weights_list = [float(w) for w in best_weights]

    # 計算組合淨值
    portfolio_nav = _calc_portfolio_nav(aligned_navs, best_weights_list)
    portfolio_metrics = _calc_metrics(portfolio_nav, common_dates)

    # 相關性矩陣
    labels = [f"{r['strategy']}/{r['code']}" for r in sub_results]
    corr_data = {
        "labels": labels,
        "matrix": [[round(float(corr_matrix[i][j]), 4) for j in range(n_strats)] for i in range(n_strats)],
    }

    # 計算組合平均相關性
    off_diag = []
    for i in range(n_strats):
        for j in range(i + 1, n_strats):
            off_diag.append(float(corr_matrix[i][j]))
    avg_corr = np.mean(off_diag) if off_diag else 0

    sub_metrics = []
    for i, r in enumerate(sub_results):
        m = _calc_metrics(r["nav"], r["dates"])
        m["strategy"] = r["strategy"]
        m["code"] = r["code"]
        m["weight"] = round(best_weights_list[i], 4)
        sub_metrics.append(m)

    return {
        "portfolio": portfolio_metrics,
        "sub_strategies": sub_metrics,
        "portfolio_nav": portfolio_nav,
        "dates": [str(d) for d in common_dates],
        "optimal_weights": [round(w, 4) for w in best_weights_list],
        "correlation_matrix": corr_data,
        "avg_pairwise_correlation": round(float(avg_corr), 4),
        "portfolio_correlation_score": round(best_score, 4),
        "method": "anti_correlation",
        "cash": cash,
    }


def regime_switch_portfolio(
    allocations: list[dict],
    regime_method: str = "volatility",
    lookback_days: int = 60,
    cash: float = None,
) -> dict:
    """
    市場狀態切換組合。
    根據市場狀態（趨勢/震盪、高波動/低波動）動態切換策略權重。

    狀態判定方法 (regime_method):
    - "volatility": 高波動時用防守型策略，低波動時用進攻型策略
    - "trend": 上升趨勢時用趨勢策略，震盪時用均值回歸策略

    Args:
        allocations: 子策略配置列表
        regime_method: 狀態判定方法 ("volatility" 或 "trend")
        lookback_days: 狀態判定窗口
        cash: 初始資金

    Returns:
        包含狀態軌跡和各狀態下權重的字典
    """
    if cash is None:
        cash = settings.backtest_cash

    logger.info(f"狀態切換組合: 方法={regime_method}, 窗口={lookback_days}天")

    # 運行所有子策略
    sub_results = []
    for i, a in enumerate(allocations):
        try:
            r = _run_strategy_on_data(a["strategy"], a["code"], params=a.get("params"), cash=cash / len(allocations))
            sub_results.append(r)
        except Exception as e:
            logger.error(f"  [{i+1}] {a['strategy']}/{a['code']} 失敗: {e}")

    if not sub_results:
        return {"error": "所有子策略均失敗"}

    # 對齊
    common_dates, aligned_navs = _align_navs(sub_results)
    n = len(aligned_navs[0])
    n_strats = len(sub_results)

    # 計算各策略每日收益
    returns_matrix = []
    for nav in aligned_navs:
        dr = [0.0] + [nav[i] / nav[i - 1] - 1 for i in range(1, n)]
        returns_matrix.append(dr)

    # 等權組合收益（用於判定市場狀態）
    eq_returns = []
    for i in range(n):
        eq_ret = sum(returns_matrix[j][i] for j in range(n_strats)) / n_strats
        eq_returns.append(eq_ret)

    # 根據市場狀態分配策略
    # 趨勢策略 vs 均值回歸策略的典型分類
    trend_strategies = {"dual_ma", "macd", "turtle", "dual_thrust"}
    mean_revert_strategies = {"bollinger", "rsi", "kdj", "grid"}

    # 為每個策略計算「趨勢傾向分數」
    trend_scores = []
    for r in sub_results:
        if r["strategy"] in trend_strategies:
            trend_scores.append(1.0)  # 趨勢型
        elif r["strategy"] in mean_revert_strategies:
            trend_scores.append(0.0)  # 均值回歸型
        else:
            trend_scores.append(0.5)  # 中性

    # 動態權重計算
    default_weight = 1.0 / n_strats
    current_weights = [default_weight] * n_strats
    weight_history = [[default_weight] * n_strats]
    regime_history = ["neutral"]
    portfolio_nav = [1.0]

    for i in range(1, n):
        # 計算組合收益
        port_ret = sum(current_weights[j] * returns_matrix[j][i] for j in range(n_strats))
        portfolio_nav.append(portfolio_nav[-1] * (1 + port_ret))

        # 每 lookback_days 天重新判定狀態
        if i % lookback_days == 0 and i >= lookback_days:
            window = eq_returns[max(0, i - lookback_days + 1):i + 1]

            if regime_method == "volatility":
                # 高波動 → 防守（偏向均值回歸策略）
                realized_vol = float(np.std(window) * np.sqrt(252))
                median_vol = 0.20  # 歷史中位數假設
                if realized_vol > median_vol * 1.2:
                    regime = "high_vol"
                    # 偏向均值回歸策略
                    current_weights = [
                        0.5 if ts < 0.5 else 0.5 / n_strats
                        for ts in trend_scores
                    ]
                elif realized_vol < median_vol * 0.8:
                    regime = "low_vol"
                    # 偏向趨勢策略
                    current_weights = [
                        1.5 if ts > 0.5 else 0.3 / n_strats
                        for ts in trend_scores
                    ]
                else:
                    regime = "neutral"
                    current_weights = [default_weight] * n_strats

            elif regime_method == "trend":
                # 趨勢判定：近期收益的夏普
                recent_sharpe = (np.mean(window) / np.std(window) * np.sqrt(252)) if np.std(window) > 0 else 0
                if recent_sharpe > 0.5:
                    regime = "uptrend"
                    current_weights = [1.5 if ts > 0.5 else 0.3 / n_strats for ts in trend_scores]
                elif recent_sharpe < -0.5:
                    regime = "downtrend"
                    current_weights = [0.3 if ts > 0.5 else 1.5 / n_strats for ts in trend_scores]
                else:
                    regime = "range"
                    current_weights = [default_weight] * n_strats
            else:
                regime = "neutral"
                current_weights = [default_weight] * n_strats

            # 歸一化
            total_w = sum(current_weights)
            current_weights = [w / total_w for w in current_weights]
            regime_history.append(regime)

        weight_history.append(list(current_weights))

    portfolio_metrics = _calc_metrics(portfolio_nav, common_dates)

    sub_metrics = []
    for i, r in enumerate(sub_results):
        m = _calc_metrics(r["nav"], r["dates"])
        m["strategy"] = r["strategy"]
        m["code"] = r["code"]
        sub_metrics.append(m)

    # 統計各狀態出現次數
    from collections import Counter
    regime_counts = dict(Counter(regime_history))

    return {
        "portfolio": portfolio_metrics,
        "sub_strategies": sub_metrics,
        "portfolio_nav": portfolio_nav,
        "dates": [str(d) for d in common_dates],
        "weight_history": weight_history,
        "regime_history": regime_history,
        "regime_counts": regime_counts,
        "regime_method": regime_method,
        "lookback_days": lookback_days,
        "cash": cash,
    }


# ============================================================
# 策略組合進階 — 第三批功能
# ============================================================


def black_litterman_portfolio(
    allocations: list[dict],
    views: dict,
    confidence: dict,
    cash: float = None,
) -> dict:
    """
    Black-Litterman 模型組合優化。
    將市場均衡收益與投資者觀點結合，生成後驗收益估計，
    再據此計算最優權重。

    Args:
        allocations: 子策略配置列表
        views: 投資者觀點，如 {"dual_ma/600519": 0.15}（預期年化收益）
        confidence: 觀點信心，如 {"dual_ma/600519": 0.8}（0-1）
        cash: 初始資金

    Returns:
        包含 BL 後驗收益、最優權重和組合指標的字典
    """
    if cash is None:
        cash = settings.backtest_cash

    logger.info(f"Black-Litterman 組合: {len(allocations)} 個子策略, {len(views)} 個觀點")

    # 運行所有子策略
    sub_results = []
    for i, a in enumerate(allocations):
        try:
            r = _run_strategy_on_data(a["strategy"], a["code"], params=a.get("params"), cash=cash / len(allocations))
            sub_results.append(r)
        except Exception as e:
            logger.error(f"  [{i+1}] {a['strategy']}/{a['code']} 失敗: {e}")

    if len(sub_results) < 2:
        return {"error": "至少需要 2 個有效子策略"}

    # 對齊收益率
    common_dates, aligned_navs = _align_navs(sub_results)
    n = len(aligned_navs[0])
    n_strats = len(sub_results)

    returns_matrix = []
    for nav in aligned_navs:
        dr = [0.0] + [nav[i] / nav[i - 1] - 1 for i in range(1, n)]
        returns_matrix.append(dr)

    returns_arr = np.array(returns_matrix)
    cov_matrix = np.cov(returns_arr) * 252  # 年化協方差矩陣

    # 標籤
    labels = [f"{r['strategy']}/{r['code']}" for r in sub_results]

    # 風險厭惡係數（從市場收益推導）
    mean_returns = np.mean(returns_arr, axis=1) * 252
    # 假設市場組合為等權
    market_weights = np.ones(n_strats) / n_strats
    market_return = float(market_weights @ mean_returns)
    market_var = float(market_weights @ cov_matrix @ market_weights)
    risk_aversion = market_return / market_var if market_var > 0 else 2.5

    # 市場均衡收益（CAPM 隱含收益）
    pi = risk_aversion * cov_matrix @ market_weights  # 均衡超額收益

    # 構建觀點矩陣 P 和觀點收益向量 Q
    # 每個觀點對應一個策略的絕對觀點
    view_keys = [k for k in views.keys() if k in labels]
    if not view_keys:
        return {"error": f"觀點中的 key 必須是策略標籤之一: {labels}"}

    k_views = len(view_keys)
    P = np.zeros((k_views, n_strats))
    Q = np.zeros(k_views)
    for vi, vk in enumerate(view_keys):
        idx = labels.index(vk)
        P[vi, idx] = 1.0  # 絕對觀點
        Q[vi] = views[vk]

    # 觀點不確定性矩陣 Omega（對角矩陣）
    # 信心越高 → Omega 越小（觀點越精確）
    omega_diag = []
    for vk in view_keys:
        conf = confidence.get(vk, 0.5)
        conf = max(0.01, min(1.0, conf))
        # Omega = (1/conf - 1) * P @ Σ @ P^T（He-Litterman 簡化）
        idx = labels.index(vk)
        p_row = P[[view_keys.index(vk)], :]
        diag_val = float((1.0 / conf - 1.0) * (p_row @ cov_matrix @ p_row.T))
        omega_diag.append(max(diag_val, 1e-8))
    Omega = np.diag(omega_diag)

    # BL 後驗收益公式:
    # E[R] = [(τΣ)^{-1} + P^T Ω^{-1} P]^{-1} [(τΣ)^{-1} π + P^T Ω^{-1} Q]
    tau = 0.05  # 不確定性縮放因子

    tau_cov_inv = np.linalg.inv(tau * cov_matrix)
    omega_inv = np.linalg.inv(Omega)

    # 後驗精度矩陣
    posterior_precision = tau_cov_inv + P.T @ omega_inv @ P
    posterior_cov = np.linalg.inv(posterior_precision)

    # 後驗收益
    posterior_returns = posterior_cov @ (tau_cov_inv @ pi + P.T @ omega_inv @ Q)

    # 最優權重（均值-方差）
    # w* = (1/λ) * Σ^{-1} * E[R]
    cov_inv = np.linalg.inv(cov_matrix + np.eye(n_strats) * 1e-8)
    optimal_weights = cov_inv @ posterior_returns / risk_aversion

    # 歸一化到 [0, 1]
    optimal_weights = np.maximum(optimal_weights, 0)
    total_w = np.sum(optimal_weights)
    if total_w > 0:
        optimal_weights = optimal_weights / total_w
    else:
        optimal_weights = np.ones(n_strats) / n_strats

    weights_list = [float(w) for w in optimal_weights]

    # 計算組合淨值
    portfolio_nav = _calc_portfolio_nav(aligned_navs, weights_list)
    portfolio_metrics = _calc_metrics(portfolio_nav, common_dates)

    sub_metrics = []
    for i, r in enumerate(sub_results):
        m = _calc_metrics(r["nav"], r["dates"])
        m["strategy"] = r["strategy"]
        m["code"] = r["code"]
        m["weight"] = round(weights_list[i], 4)
        m["prior_return"] = round(float(pi[i]) * 100, 4)
        m["posterior_return"] = round(float(posterior_returns[i]) * 100, 4)
        sub_metrics.append(m)

    return {
        "portfolio": portfolio_metrics,
        "sub_strategies": sub_metrics,
        "portfolio_nav": portfolio_nav,
        "dates": [str(d) for d in common_dates],
        "optimal_weights": [round(w, 4) for w in weights_list],
        "posterior_returns": {labels[i]: round(float(posterior_returns[i]) * 100, 4) for i in range(n_strats)},
        "prior_returns": {labels[i]: round(float(pi[i]) * 100, 4) for i in range(n_strats)},
        "risk_aversion": round(risk_aversion, 4),
        "views_applied": view_keys,
        "method": "black_litterman",
        "cash": cash,
    }


def hierarchical_risk_parity(
    allocations: list[dict],
    cash: float = None,
) -> dict:
    """
    層次風險平價 (HRP) 組合。
    基於相關性矩陣的層次聚類和遞歸二分法分配權重，
    不需要矩陣求逆，數值穩定性更好。

    Args:
        allocations: 子策略配置列表
        cash: 初始資金

    Returns:
        包含 HRP 權重和組合指標的字典
    """
    if cash is None:
        cash = settings.backtest_cash

    logger.info(f"層次風險平價 (HRP): {len(allocations)} 個子策略")

    # 運行所有子策略
    sub_results = []
    for i, a in enumerate(allocations):
        try:
            r = _run_strategy_on_data(a["strategy"], a["code"], params=a.get("params"), cash=cash / len(allocations))
            sub_results.append(r)
        except Exception as e:
            logger.error(f"  [{i+1}] {a['strategy']}/{a['code']} 失敗: {e}")

    if len(sub_results) < 2:
        return {"error": "至少需要 2 個有效子策略"}

    # 對齊收益率
    common_dates, aligned_navs = _align_navs(sub_results)
    n = len(aligned_navs[0])
    n_strats = len(sub_results)

    returns_matrix = []
    for nav in aligned_navs:
        dr = [0.0] + [nav[i] / nav[i - 1] - 1 for i in range(1, n)]
        returns_matrix.append(dr)

    returns_arr = np.array(returns_matrix)
    corr_matrix = np.corrcoef(returns_arr)
    cov_matrix = np.cov(returns_arr)

    labels = [f"{r['strategy']}/{r['code']}" for r in sub_results]

    # 步驟 1: 計算距離矩陣
    dist_matrix = np.sqrt(0.5 * (1 - corr_matrix))

    # 步驟 2: 層次聚類（單連接法，純 numpy 實現）
    # 使用貪心合併：每次合併距離最近的兩個簇
    clusters = {i: [i] for i in range(n_strats)}
    merge_order = []  # 記錄合併順序
    active = set(range(n_strats))
    cluster_id = n_strats  # 新簇的起始 ID

    # 當前距離矩陣（動態更新）
    current_dist = dist_matrix.copy()
    cluster_map = {i: i for i in range(n_strats)}  # 節點 → 所屬簇

    # 記錄每個簇的成員
    cluster_members = {i: [i] for i in range(n_strats)}

    for _ in range(n_strats - 1):
        # 找最近的兩個活躍簇
        min_d = float("inf")
        merge_i, merge_j = -1, -1
        active_list = sorted(active)
        for ii in range(len(active_list)):
            for jj in range(ii + 1, len(active_list)):
                ci, cj = active_list[ii], active_list[jj]
                # 平均連接法：兩個簇所有成員對之間的平均距離
                members_i = cluster_members[ci]
                members_j = cluster_members[cj]
                d_sum = 0.0
                count = 0
                for mi in members_i:
                    for mj in members_j:
                        d_sum += dist_matrix[mi][mj]
                        count += 1
                d_avg = d_sum / count if count > 0 else float("inf")
                if d_avg < min_d:
                    min_d = d_avg
                    merge_i, merge_j = ci, cj

        if merge_i == -1:
            break

        # 合併
        new_id = cluster_id
        cluster_id += 1
        cluster_members[new_id] = cluster_members[merge_i] + cluster_members[merge_j]
        merge_order.append((merge_i, merge_j, min_d))
        active.discard(merge_i)
        active.discard(merge_j)
        active.add(new_id)

    # 步驟 3: 準對角化（按聚類順序排列資產）
    # 從合併順序重建排序
    sort_order = cluster_members.get(max(cluster_members.keys()), list(range(n_strats)))

    # 步骤 4: 遞歸二分法分配權重
    def _get_cluster_var(indices):
        """計算子組合方差"""
        if len(indices) == 1:
            return float(cov_matrix[indices[0], indices[0]])
        sub_cov = cov_matrix[np.ix_(indices, indices)]
        inv_diag = 1.0 / np.diag(sub_cov)
        inv_diag = inv_diag / np.sum(inv_diag)
        return float(inv_diag @ sub_cov @ inv_diag)

    def _recursive_bisection(indices):
        """遞歸二分法"""
        weights = np.ones(len(indices))
        stack = [list(range(len(indices)))]

        while stack:
            current = stack.pop()
            if len(current) <= 1:
                continue

            mid = len(current) // 2
            left = current[:mid]
            right = current[mid:]

            # 對應到原始索引
            left_orig = [indices[i] for i in left]
            right_orig = [indices[i] for i in right]

            var_left = _get_cluster_var(left_orig)
            var_right = _get_cluster_var(right_orig)

            # 分配比例：方差大的分配少
            alloc = 1.0 - var_left / (var_left + var_right) if (var_left + var_right) > 0 else 0.5

            for i in left:
                weights[i] *= alloc
            for i in right:
                weights[i] *= (1.0 - alloc)

            stack.append(left)
            stack.append(right)

        return weights

    # 對排序後的資產執行遞歸二分
    h_weights = _recursive_bisection(sort_order)

    # 還原到原始順序
    final_weights = np.zeros(n_strats)
    for i, orig_idx in enumerate(sort_order):
        final_weights[orig_idx] = h_weights[i]

    # 歸一化
    total_w = np.sum(final_weights)
    if total_w > 0:
        final_weights = final_weights / total_w
    else:
        final_weights = np.ones(n_strats) / n_strats

    weights_list = [float(w) for w in final_weights]

    # 計算組合淨值
    portfolio_nav = _calc_portfolio_nav(aligned_navs, weights_list)
    portfolio_metrics = _calc_metrics(portfolio_nav, common_dates)

    sub_metrics = []
    for i, r in enumerate(sub_results):
        m = _calc_metrics(r["nav"], r["dates"])
        m["strategy"] = r["strategy"]
        m["code"] = r["code"]
        m["weight"] = round(weights_list[i], 4)
        sub_metrics.append(m)

    # 聚類信息
    cluster_info = []
    for ci, (c1, c2, d) in enumerate(merge_order):
        cluster_info.append({
            "step": ci + 1,
            "merged": [c1, c2],
            "distance": round(d, 4),
        })

    return {
        "portfolio": portfolio_metrics,
        "sub_strategies": sub_metrics,
        "portfolio_nav": portfolio_nav,
        "dates": [str(d) for d in common_dates],
        "optimal_weights": [round(w, 4) for w in weights_list],
        "sort_order": [labels[i] for i in sort_order],
        "cluster_steps": cluster_info,
        "method": "hierarchical_risk_parity",
        "cash": cash,
    }


def cvar_optimize(
    allocations: list[dict],
    alpha: float = 0.05,
    cash: float = None,
) -> dict:
    """
    CVaR（條件風險價值）優化組合。
    最小化組合的條件在險價值（Expected Shortfall），
    使用歷史模擬法和網格搜索。

    Args:
        allocations: 子策略配置列表
        alpha: VaR 顯著性水平（默認 0.05 = 5%）
        cash: 初始資金

    Returns:
        包含 CVaR 最優權重和風險指標的字典
    """
    if cash is None:
        cash = settings.backtest_cash

    logger.info(f"CVaR 優化: alpha={alpha}, {len(allocations)} 個子策略")

    # 運行所有子策略
    sub_results = []
    for i, a in enumerate(allocations):
        try:
            r = _run_strategy_on_data(a["strategy"], a["code"], params=a.get("params"), cash=cash / len(allocations))
            sub_results.append(r)
        except Exception as e:
            logger.error(f"  [{i+1}] {a['strategy']}/{a['code']} 失敗: {e}")

    if len(sub_results) < 2:
        return {"error": "至少需要 2 個有效子策略"}

    # 對齊收益率
    common_dates, aligned_navs = _align_navs(sub_results)
    n = len(aligned_navs[0])
    n_strats = len(sub_results)

    returns_matrix = []
    for nav in aligned_navs:
        dr = [0.0] + [nav[i] / nav[i - 1] - 1 for i in range(1, n)]
        returns_matrix.append(dr)

    returns_arr = np.array(returns_matrix)  # (n_strats, n_periods)

    # 網格搜索：生成大量隨機權重組合，找最小 CVaR
    n_simulations = 10000
    best_cvar = float("inf")
    best_weights = np.ones(n_strats) / n_strats

    # 同時也搜索等權作為基準
    eq_weights = np.ones(n_strats) / n_strats
    eq_port_returns = returns_arr.T @ eq_weights
    eq_sorted = np.sort(eq_port_returns)
    cutoff = max(1, int(np.ceil(alpha * len(eq_sorted))))
    eq_cvar = float(np.mean(eq_sorted[:cutoff]))

    for _ in range(n_simulations):
        w = np.random.dirichlet(np.ones(n_strats))
        port_returns = returns_arr.T @ w  # 組合每日收益
        sorted_returns = np.sort(port_returns)
        cutoff = max(1, int(np.ceil(alpha * len(sorted_returns))))
        cvar = float(np.mean(sorted_returns[:cutoff]))

        if cvar < best_cvar:
            best_cvar = cvar
            best_weights = w.copy()

    # 二次精細搜索（在最優附近微調）
    for _ in range(5000):
        # 在最優權重附近擾動
        noise = np.random.normal(0, 0.05, n_strats)
        w = best_weights + noise
        w = np.maximum(w, 0.01)
        w = w / np.sum(w)

        port_returns = returns_arr.T @ w
        sorted_returns = np.sort(port_returns)
        cutoff = max(1, int(np.ceil(alpha * len(sorted_returns))))
        cvar = float(np.mean(sorted_returns[:cutoff]))

        if cvar < best_cvar:
            best_cvar = cvar
            best_weights = w.copy()

    weights_list = [float(w) for w in best_weights]

    # 計算組合淨值
    portfolio_nav = _calc_portfolio_nav(aligned_navs, weights_list)
    portfolio_metrics = _calc_metrics(portfolio_nav, common_dates)

    # 計算最優組合的詳細風險指標
    opt_port_returns = returns_arr.T @ best_weights
    opt_sorted = np.sort(opt_port_returns)
    cutoff = max(1, int(np.ceil(alpha * len(opt_sorted))))
    var_alpha = float(opt_sorted[cutoff - 1])
    cvar_alpha = float(np.mean(opt_sorted[:cutoff]))

    sub_metrics = []
    for i, r in enumerate(sub_results):
        m = _calc_metrics(r["nav"], r["dates"])
        m["strategy"] = r["strategy"]
        m["code"] = r["code"]
        m["weight"] = round(weights_list[i], 4)
        # 單策略 CVaR
        strat_sorted = np.sort(returns_arr[i])
        sc = max(1, int(np.ceil(alpha * len(strat_sorted))))
        m["individual_cvar"] = round(float(np.mean(strat_sorted[:sc])) * 100, 4)
        sub_metrics.append(m)

    return {
        "portfolio": portfolio_metrics,
        "sub_strategies": sub_metrics,
        "portfolio_nav": portfolio_nav,
        "dates": [str(d) for d in common_dates],
        "optimal_weights": [round(w, 4) for w in weights_list],
        "optimal_cvar": round(cvar_alpha * 100, 4),
        "optimal_var": round(var_alpha * 100, 4),
        "equal_weight_cvar": round(eq_cvar * 100, 4),
        "alpha": alpha,
        "method": "cvar_optimize",
        "cash": cash,
    }


def multi_timeframe_signal(
    allocations: list[dict],
    windows: list = None,
    cash: float = None,
) -> dict:
    """
    多時間框架信號確認。
    對每個子策略在多個時間窗口（5天、20天、60天）計算信號方向，
    只有多數時間框架一致時才確認信號。

    Args:
        allocations: 子策略配置列表
        windows: 時間窗口列表，默認 [5, 20, 60]
        cash: 初始資金

    Returns:
        包含每個策略在各時間框架的信號和最終確認結果的字典
    """
    if cash is None:
        cash = settings.backtest_cash
    if windows is None:
        windows = [5, 20, 60]

    logger.info(f"多時間框架信號: 窗口={windows}")

    # 運行所有子策略
    sub_results = []
    for i, a in enumerate(allocations):
        try:
            r = _run_strategy_on_data(a["strategy"], a["code"], params=a.get("params"), cash=cash / len(allocations))
            sub_results.append(r)
        except Exception as e:
            logger.error(f"  [{i+1}] {a['strategy']}/{a['code']} 失敗: {e}")

    if not sub_results:
        return {"error": "所有子策略均失敗"}

    # 對齊
    common_dates, aligned_navs = _align_navs(sub_results)
    n = len(aligned_navs[0])

    results = []
    for si, r in enumerate(sub_results):
        nav = aligned_navs[si]
        label = f"{r['strategy']}/{r['code']}"

        # 計算各窗口的收益率和信號
        timeframe_signals = {}
        for w in windows:
            if n <= w:
                timeframe_signals[f"{w}d"] = {"signal": "hold", "return_pct": 0.0, "reason": "數據不足"}
                continue

            # 最近 w 天的收益
            recent_return = nav[-1] / nav[-w - 1] - 1 if nav[-w - 1] > 0 else 0
            # 最近 w 天的波動率
            recent_returns = [nav[i] / nav[i - 1] - 1 for i in range(max(1, n - w), n)]
            recent_vol = float(np.std(recent_returns)) if len(recent_returns) > 1 else 0

            # 信號判定
            if recent_return > 0.02 and recent_return / max(recent_vol, 1e-9) > 0.5:
                sig = "buy"
            elif recent_return < -0.02 and recent_return / max(recent_vol, 1e-9) < -0.5:
                sig = "sell"
            else:
                sig = "hold"

            timeframe_signals[f"{w}d"] = {
                "signal": sig,
                "return_pct": round(recent_return * 100, 4),
                "volatility": round(recent_vol * 100, 4),
            }

        # 多數投票確認
        votes = [v["signal"] for v in timeframe_signals.values()]
        buy_count = sum(1 for v in votes if v == "buy")
        sell_count = sum(1 for v in votes if v == "sell")
        hold_count = sum(1 for v in votes if v == "hold")
        total = len(votes)

        if buy_count > total / 2:
            confirmed_signal = "buy"
            agreement = buy_count / total
        elif sell_count > total / 2:
            confirmed_signal = "sell"
            agreement = sell_count / total
        else:
            confirmed_signal = "hold"
            agreement = hold_count / total

        results.append({
            "strategy": r["strategy"],
            "code": r["code"],
            "label": label,
            "timeframe_signals": timeframe_signals,
            "confirmed_signal": confirmed_signal,
            "agreement_score": round(agreement, 4),
            "buy_votes": buy_count,
            "sell_votes": sell_count,
            "hold_votes": hold_count,
        })

    # 整體組合信號
    all_confirmed = [r["confirmed_signal"] for r in results]
    overall_buy = sum(1 for s in all_confirmed if s == "buy")
    overall_sell = sum(1 for s in all_confirmed if s == "sell")
    overall_hold = sum(1 for s in all_confirmed if s == "hold")

    if overall_buy > overall_sell and overall_buy > overall_hold:
        overall_signal = "buy"
    elif overall_sell > overall_buy and overall_sell > overall_hold:
        overall_signal = "sell"
    else:
        overall_signal = "hold"

    return {
        "strategy_signals": results,
        "overall_signal": overall_signal,
        "overall_buy_count": overall_buy,
        "overall_sell_count": overall_sell,
        "overall_hold_count": overall_hold,
        "windows": windows,
        "method": "multi_timeframe",
    }


def dynamic_rebalance_trigger(
    allocations: list[dict],
    threshold_pct: float = 5.0,
    vol_window: int = 20,
    cash: float = None,
) -> dict:
    """
    動態再平衡觸發器。
    不按固定時間間隔再平衡，而是根據以下條件觸發：
    a) 任何策略權重偏離目標超過 threshold_pct
    b) 組合波動率短期（vol_window）相比歷史顯著變化（2倍）

    Args:
        allocations: 子策略配置列表
        threshold_pct: 權重偏移觸發閾值（百分比）
        vol_window: 波動率計算窗口
        cash: 初始資金

    Returns:
        包含再平衡歷史和觸發原因的字典
    """
    if cash is None:
        cash = settings.backtest_cash

    logger.info(f"動態再平衡觸發: 閾值={threshold_pct}%, 波動率窗口={vol_window}天")

    # 運行所有子策略
    sub_results = []
    for i, a in enumerate(allocations):
        try:
            r = _run_strategy_on_data(a["strategy"], a["code"], params=a.get("params"), cash=cash / len(allocations))
            sub_results.append(r)
        except Exception as e:
            logger.error(f"  [{i+1}] {a['strategy']}/{a['code']} 失敗: {e}")

    if len(sub_results) < 2:
        return {"error": "至少需要 2 個有效子策略"}

    # 對齊
    common_dates, aligned_navs = _align_navs(sub_results)
    n = len(aligned_navs[0])
    n_strats = len(sub_results)

    # 目標權重（等權）
    target_weights = np.ones(n_strats) / n_strats
    current_weights = target_weights.copy()

    # 計算每日收益
    daily_returns_matrix = []
    for nav in aligned_navs:
        dr = [0.0] + [nav[i] / nav[i - 1] - 1 for i in range(1, n)]
        daily_returns_matrix.append(dr)

    # 模擬組合
    portfolio_nav = [1.0]
    rebalance_history = []
    current_values = target_weights.copy()  # 各策略的價值佔比

    for i in range(1, n):
        # 各策略收益
        returns = np.array([daily_returns_matrix[j][i] for j in range(n_strats)])
        # 組合收益
        port_ret = float(current_weights @ returns)
        portfolio_nav.append(portfolio_nav[-1] * (1 + port_ret))

        # 更新各策略價值
        current_values = current_values * (1 + returns)
        total_val = np.sum(current_values)
        current_weights = current_values / total_val if total_val > 0 else target_weights.copy()

        # 檢查是否需要再平衡
        needs_rebalance = False
        trigger_reasons = []

        # 條件 a: 權重偏移檢查
        weight_drift = np.abs(current_weights - target_weights) * 100
        max_drift = float(np.max(weight_drift))
        if max_drift > threshold_pct:
            needs_rebalance = True
            drifted_idx = int(np.argmax(weight_drift))
            trigger_reasons.append(
                f"權重偏移: {sub_results[drifted_idx]['strategy']}/{sub_results[drifted_idx]['code']} "
                f"偏移 {max_drift:.1f}% > {threshold_pct}%"
            )

        # 條件 b: 波動率突變檢查
        if i >= vol_window * 2:
            # 短期波動率
            recent_port_returns = []
            for k in range(max(1, i - vol_window + 1), i + 1):
                rp = float(np.array([daily_returns_matrix[j][k] for j in range(n_strats)]) @ current_weights)
                recent_port_returns.append(rp)
            short_vol = float(np.std(recent_port_returns)) if len(recent_port_returns) > 1 else 0

            # 長期波動率
            long_port_returns = []
            for k in range(max(1, i - vol_window * 2 + 1), i + 1):
                lp = float(np.array([daily_returns_matrix[j][k] for j in range(n_strats)]) @ current_weights)
                long_port_returns.append(lp)
            long_vol = float(np.std(long_port_returns)) if len(long_port_returns) > 1 else 0

            if long_vol > 0 and short_vol > long_vol * 2:
                needs_rebalance = True
                trigger_reasons.append(
                    f"波動率突變: 短期 {short_vol:.4f} vs 長期 {long_vol:.4f} (比率 {short_vol/long_vol:.1f}x)"
                )

        if needs_rebalance:
            # 執行再平衡
            current_weights = target_weights.copy()
            current_values = target_weights.copy() * total_val
            rebalance_history.append({
                "day_index": i,
                "date": str(common_dates[i]) if i < len(common_dates) else str(i),
                "reasons": trigger_reasons,
                "max_drift_pct": round(max_drift, 2),
            })

    # 計算指標
    portfolio_metrics = _calc_metrics(portfolio_nav, common_dates)

    sub_metrics = []
    for i, r in enumerate(sub_results):
        m = _calc_metrics(r["nav"], r["dates"])
        m["strategy"] = r["strategy"]
        m["code"] = r["code"]
        m["target_weight"] = round(float(target_weights[i]), 4)
        sub_metrics.append(m)

    return {
        "portfolio": portfolio_metrics,
        "sub_strategies": sub_metrics,
        "portfolio_nav": portfolio_nav,
        "dates": [str(d) for d in common_dates],
        "rebalance_history": rebalance_history,
        "total_rebalances": len(rebalance_history),
        "threshold_pct": threshold_pct,
        "vol_window": vol_window,
        "method": "dynamic_rebalance",
        "cash": cash,
    }


def sector_exposure_limit(
    allocations: list[dict],
    max_sector_pct: float = 40.0,
    cash: float = None,
) -> dict:
    """
    板塊敞口限制。
    根據股票代碼前綴映射到板塊（上證/深證主板/創業板/科創板），
    強制限制單板塊最大佔比。

    Args:
        allocations: 子策略配置列表
        max_sector_pct: 單板塊最大佔比（百分比，默認 40%）
        cash: 初始資金

    Returns:
        包含調整後權重和板塊分佈的字典
    """
    if cash is None:
        cash = settings.backtest_cash

    logger.info(f"板塊敞口限制: 最大佔比={max_sector_pct}%")

    # 板塊映射函數
    def _map_sector(code: str) -> str:
        """根據股票代碼前綴映射板塊"""
        code = code.strip()
        if code.startswith("688"):
            return "科創板"
        elif code.startswith("300"):
            return "創業板"
        elif code.startswith("600") or code.startswith("601") or code.startswith("603") or code.startswith("605"):
            return "上證主板"
        elif code.startswith("000") or code.startswith("001") or code.startswith("002") or code.startswith("003"):
            return "深證主板"
        else:
            return "其他"

    # 為每個分配標記板塊
    sector_map = {}
    for a in allocations:
        label = f"{a['strategy']}/{a['code']}"
        sector_map[label] = _map_sector(a["code"])

    # 運行所有子策略
    sub_results = []
    for i, a in enumerate(allocations):
        try:
            r = _run_strategy_on_data(a["strategy"], a["code"], params=a.get("params"), cash=cash / len(allocations))
            sub_results.append(r)
        except Exception as e:
            logger.error(f"  [{i+1}] {a['strategy']}/{a['code']} 失敗: {e}")

    if not sub_results:
        return {"error": "所有子策略均失敗"}

    n_strats = len(sub_results)

    # 初始等權
    weights = np.ones(n_strats) / n_strats

    # 計算板塊敞口
    sector_exposure = {}
    for i, r in enumerate(sub_results):
        label = f"{r['strategy']}/{r['code']}"
        sector = sector_map.get(label, "其他")
        if sector not in sector_exposure:
            sector_exposure[sector] = 0.0
        sector_exposure[sector] += float(weights[i]) * 100

    # 限制板塊敞口（迭代調整）
    max_iter = 100
    for iteration in range(max_iter):
        # 找超標板塊
        over_limit = {s: e for s, e in sector_exposure.items() if e > max_sector_pct + 0.01}
        if not over_limit:
            break

        for sector, exposure in over_limit.items():
            # 找該板塊的所有策略
            sector_indices = []
            for i, r in enumerate(sub_results):
                label = f"{r['strategy']}/{r['code']}"
                if sector_map.get(label, "其他") == sector:
                    sector_indices.append(i)

            if not sector_indices:
                continue

            # 按比例縮減
            scale = max_sector_pct / exposure
            for idx in sector_indices:
                weights[idx] *= scale

        # 歸一化
        total_w = np.sum(weights)
        if total_w > 0:
            weights = weights / total_w

        # 重新計算板塊敞口
        sector_exposure = {}
        for i, r in enumerate(sub_results):
            label = f"{r['strategy']}/{r['code']}"
            sector = sector_map.get(label, "其他")
            if sector not in sector_exposure:
                sector_exposure[sector] = 0.0
            sector_exposure[sector] += float(weights[i]) * 100

    weights_list = [float(w) for w in weights]

    # 對齊
    common_dates, aligned_navs = _align_navs(sub_results)

    # 計算組合淨值
    portfolio_nav = _calc_portfolio_nav(aligned_navs, weights_list)
    portfolio_metrics = _calc_metrics(portfolio_nav, common_dates)

    sub_metrics = []
    for i, r in enumerate(sub_results):
        m = _calc_metrics(r["nav"], r["dates"])
        m["strategy"] = r["strategy"]
        m["code"] = r["code"]
        m["weight"] = round(weights_list[i], 4)
        label = f"{r['strategy']}/{r['code']}"
        m["sector"] = sector_map.get(label, "其他")
        sub_metrics.append(m)

    # 板塊分佈
    sector_breakdown = {}
    for i, r in enumerate(sub_results):
        label = f"{r['strategy']}/{r['code']}"
        sector = sector_map.get(label, "其他")
        if sector not in sector_breakdown:
            sector_breakdown[sector] = {
                "weight_pct": 0.0,
                "strategies": [],
                "count": 0,
            }
        sector_breakdown[sector]["weight_pct"] += round(weights_list[i] * 100, 2)
        sector_breakdown[sector]["strategies"].append(label)
        sector_breakdown[sector]["count"] += 1

    return {
        "portfolio": portfolio_metrics,
        "sub_strategies": sub_metrics,
        "portfolio_nav": portfolio_nav,
        "dates": [str(d) for d in common_dates],
        "optimal_weights": [round(w, 4) for w in weights_list],
        "sector_breakdown": sector_breakdown,
        "max_sector_pct": max_sector_pct,
        "method": "sector_exposure_limit",
        "cash": cash,
    }


def efficient_frontier(allocations: list[dict], n_points: int = 20) -> dict:
    """
    生成有效前沿點。
    通過隨機生成不同權重組合，計算各自的收益率和風險。
    
    Args:
        allocations: 子策略配置列表
        n_points: 生成點數
    
    Returns:
        {"points": [{"return": ..., "risk": ..., "sharpe": ..., "weights": [...]}], ...}
    """
    import numpy as np

    n_assets = len(allocations)
    if n_assets < 2:
        return {"points": [], "error": "至少需要 2 個子策略"}

    # 運行所有子策略
    sub_results = []
    for a in allocations:
        try:
            r = _run_strategy_on_data(a["strategy"], a["code"], params=a.get("params"))
            sub_results.append(r)
        except Exception as e:
            logger.error(f"有效前沿子策略 {a['strategy']}/{a['code']} 失敗: {e}")

    if len(sub_results) < 2:
        return {"points": [], "error": "可用子策略不足"}

    # 對齊
    date_sets = [set(r["dates"]) for r in sub_results]
    common_dates = sorted(set.intersection(*date_sets))
    if len(common_dates) < 20:
        return {"points": [], "error": "共同數據不足"}

    returns_matrix = []
    for r in sub_results:
        date_to_ret = dict(zip(r["dates"], r["daily_returns"]))
        returns_matrix.append([date_to_ret.get(d, 0.0) for d in common_dates])

    returns_arr = np.array(returns_matrix)
    mean_returns = np.mean(returns_arr, axis=1) * 252
    cov_matrix = np.cov(returns_arr) * 252

    labels = [f"{r['strategy']}/{r['code']}" for r in sub_results]

    # 生成隨機權重組合
    points = []
    for _ in range(n_points * 10):
        w = np.random.dirichlet(np.ones(n_assets))
        port_return = float(w @ mean_returns)
        port_risk = float(np.sqrt(w @ cov_matrix @ w))
        sharpe = (port_return - 0.03) / port_risk if port_risk > 0 else 0
        points.append({
            "return": round(port_return * 100, 4),
            "risk": round(port_risk * 100, 4),
            "sharpe": round(sharpe, 4),
            "weights": [round(float(x), 4) for x in w],
        })

    # 按風險排序並取 n_points 個均勻分佈的點
    points.sort(key=lambda x: x["risk"])
    step = max(1, len(points) // n_points)
    frontier_points = points[::step][:n_points]

    # 最大夏普
    max_sharpe = max(points, key=lambda x: x["sharpe"])
    # 最小風險
    min_risk = min(points, key=lambda x: x["risk"])

    return {
        "points": frontier_points,
        "max_sharpe": max_sharpe,
        "min_risk": min_risk,
        "labels": labels,
    }


# ============================================================
# 策略組合進階 — 第三批功能（新策略組合方法）
# ============================================================


def strategy_voting_portfolio(
    allocations: list[dict],
    min_votes: int = 2,
    cash: float = None,
) -> dict:
    """
    投票式組合回測。
    運行所有子策略，每日統計買賣信號票數，
    只有 >= min_votes 個策略同意時才執行交易，權重在同意的策略間平均分配。

    Args:
        allocations: 子策略配置列表 [{"strategy": ..., "code": ..., "params": ...}]
        min_votes: 最低同意票數（默認 2）
        cash: 初始資金

    Returns:
        包含投票軌跡和組合指標的字典
    """
    if cash is None:
        cash = settings.backtest_cash

    logger.info(f"投票式組合: {len(allocations)} 個子策略, 最低票數={min_votes}")

    # 運行所有子策略
    sub_results = []
    for i, a in enumerate(allocations):
        try:
            r = _run_strategy_on_data(
                a["strategy"], a["code"],
                params=a.get("params"),
                cash=cash / len(allocations),
            )
            sub_results.append(r)
            logger.info(f"  [{i+1}] {a['strategy']}/{a['code']}: {r['total_return_pct']:.2f}%")
        except Exception as e:
            logger.error(f"  [{i+1}] {a['strategy']}/{a['code']} 失敗: {e}")

    if not sub_results:
        return {"error": "所有子策略均失敗"}

    # 對齊日期
    common_dates, aligned_navs = _align_navs(sub_results)
    n_periods = len(aligned_navs[0])
    n_strats = len(sub_results)

    # 計算每日收益率
    daily_returns_matrix = []
    for nav in aligned_navs:
        dr = [0.0] + [nav[i] / nav[i - 1] - 1 for i in range(1, n_periods)]
        daily_returns_matrix.append(dr)

    # 投票式組合淨值計算
    # 信號判定：當日收益率 > 0 視為「看多」，< 0 視為「看空」
    portfolio_nav = [1.0]
    vote_history = []  # 記錄每日投票結果
    in_position = False  # 當前是否持倉

    for i in range(1, n_periods):
        # 統計各策略前一日的信號（用前一日收益判定方向）
        buy_votes = 0
        sell_votes = 0
        for j in range(n_strats):
            prev_ret = daily_returns_matrix[j][i - 1] if i > 0 else 0
            # 前一日正收益 → 看多信號
            if prev_ret > 0:
                buy_votes += 1
            elif prev_ret < 0:
                sell_votes += 1

        vote_record = {
            "buy_votes": buy_votes,
            "sell_votes": sell_votes,
            "action": "hold",
        }

        # 決定動作
        if buy_votes >= min_votes and not in_position:
            vote_record["action"] = "buy"
            in_position = True
        elif sell_votes >= min_votes and in_position:
            vote_record["action"] = "sell"
            in_position = False

        vote_history.append(vote_record)

        # 計算組合收益
        if in_position:
            # 持倉時：等權持有同意買入的策略
            port_ret = 0.0
            contributing = 0
            for j in range(n_strats):
                prev_ret = daily_returns_matrix[j][i - 1] if i > 0 else 0
                if prev_ret > 0:
                    port_ret += daily_returns_matrix[j][i]
                    contributing += 1
            if contributing > 0:
                port_ret /= contributing
        else:
            port_ret = 0.0

        portfolio_nav.append(portfolio_nav[-1] * (1 + port_ret))

    # 計算指標
    portfolio_metrics = _calc_metrics(portfolio_nav, common_dates)

    sub_metrics = []
    for i, r in enumerate(sub_results):
        m = _calc_metrics(r["nav"], r["dates"])
        m["strategy"] = r["strategy"]
        m["code"] = r["code"]
        sub_metrics.append(m)

    # 投票統計
    buy_days = sum(1 for v in vote_history if v["action"] == "buy")
    sell_days = sum(1 for v in vote_history if v["action"] == "sell")
    hold_days = sum(1 for v in vote_history if v["action"] == "hold")

    return {
        "portfolio": portfolio_metrics,
        "sub_strategies": sub_metrics,
        "portfolio_nav": portfolio_nav,
        "dates": [str(d) for d in common_dates],
        "min_votes": min_votes,
        "vote_summary": {
            "buy_days": buy_days,
            "sell_days": sell_days,
            "hold_days": hold_days,
            "total_days": len(vote_history),
        },
        "vote_history": vote_history[-50:],  # 最近 50 天投票記錄
        "cash": cash,
    }


def momentum_of_momentum(
    allocations: list[dict],
    lookback: int = 60,
    cash: float = None,
) -> dict:
    """
    動量的動量（二階動量）組合。
    計算每個策略近期 Sharpe（一階動量），再計算 Sharpe 的變化趨勢（二階動量），
    正向二階動量的策略獲得更高權重。

    Args:
        allocations: 子策略配置列表
        lookback: 動量計算回看天數（默認 60）
        cash: 初始資金

    Returns:
        包含動量軌跡和組合指標的字典
    """
    if cash is None:
        cash = settings.backtest_cash

    logger.info(f"動量的動量: {len(allocations)} 個子策略, 回看={lookback}天")

    # 運行所有子策略
    sub_results = []
    for i, a in enumerate(allocations):
        try:
            r = _run_strategy_on_data(
                a["strategy"], a["code"],
                params=a.get("params"),
                cash=cash / len(allocations),
            )
            sub_results.append(r)
            logger.info(f"  [{i+1}] {a['strategy']}/{a['code']}: {r['total_return_pct']:.2f}%")
        except Exception as e:
            logger.error(f"  [{i+1}] {a['strategy']}/{a['code']} 失敗: {e}")

    if not sub_results:
        return {"error": "所有子策略均失敗"}

    # 對齊日期
    common_dates, aligned_navs = _align_navs(sub_results)
    n_periods = len(aligned_navs[0])
    n_strats = len(sub_results)

    # 計算每日收益率
    daily_returns_matrix = []
    for nav in aligned_navs:
        dr = [0.0] + [nav[i] / nav[i - 1] - 1 for i in range(1, n_periods)]
        daily_returns_matrix.append(dr)

    # 動量的動量組合淨值
    default_weight = 1.0 / n_strats
    current_weights = [default_weight] * n_strats
    weight_history = [[default_weight] * n_strats]
    portfolio_nav = [1.0]
    momentum_history = []  # 記錄每個策略的一階和二階動量

    for i in range(1, n_periods):
        # 計算組合收益
        port_ret = sum(
            current_weights[j] * daily_returns_matrix[j][i]
            for j in range(n_strats)
        )
        portfolio_nav.append(portfolio_nav[-1] * (1 + port_ret))

        # 每 lookback/2 天重新計算權重
        if i % (lookback // 2) == 0 and i >= lookback:
            first_momentum = []   # 一階動量：近期 Sharpe
            second_momentum = []  # 二階動量：Sharpe 的變化

            for j in range(n_strats):
                # 計算近期 Sharpe（一階動量）
                recent = daily_returns_matrix[j][max(0, i - lookback + 1):i + 1]
                half = lookback // 2

                if len(recent) >= half:
                    # 前半段 Sharpe
                    front = recent[:half]
                    front_sharpe = (np.mean(front) / np.std(front) * np.sqrt(252)) if np.std(front) > 0 else 0

                    # 後半段 Sharpe
                    back = recent[half:]
                    back_sharpe = (np.mean(back) / np.std(back) * np.sqrt(252)) if np.std(back) > 0 else 0

                    # 一階動量 = 當前 Sharpe
                    current_sharpe = back_sharpe
                    first_momentum.append(current_sharpe)

                    # 二階動量 = Sharpe 的變化（改善或惡化）
                    second_order = back_sharpe - front_sharpe
                    second_momentum.append(second_order)
                else:
                    first_momentum.append(0.0)
                    second_momentum.append(0.0)

            # 根據二階動量分配權重
            # 二階動量 > 0 表示策略在改善，獲得更高權重
            mom_arr = np.array(second_momentum)
            # 將二階動量轉為正權重（最低 0.1）
            shifted = mom_arr - mom_arr.min() + 0.1
            total = float(np.sum(shifted))
            if total > 0:
                current_weights = [float(s / total) for s in shifted]
            else:
                current_weights = [default_weight] * n_strats

            momentum_history.append({
                "day": i,
                "first_momentum": [round(m, 4) for m in first_momentum],
                "second_momentum": [round(m, 4) for m in second_momentum],
                "weights": [round(w, 4) for w in current_weights],
            })

        weight_history.append(list(current_weights))

    # 計算指標
    portfolio_metrics = _calc_metrics(portfolio_nav, common_dates)

    sub_metrics = []
    for i, r in enumerate(sub_results):
        m = _calc_metrics(r["nav"], r["dates"])
        m["strategy"] = r["strategy"]
        m["code"] = r["code"]
        sub_metrics.append(m)

    return {
        "portfolio": portfolio_metrics,
        "sub_strategies": sub_metrics,
        "portfolio_nav": portfolio_nav,
        "dates": [str(d) for d in common_dates],
        "weight_history": weight_history,
        "momentum_history": momentum_history[-20:],  # 最近 20 次動量記錄
        "lookback": lookback,
        "cash": cash,
    }


def adaptive_regime_portfolio(
    allocations: list[dict],
    cash: float = None,
) -> dict:
    """
    自適應市場狀態組合。
    通過等權組合的滾動波動率判定市場狀態：
    - 低波動狀態 → 加重趨勢型策略（turtle, dual_ma, momentum）
    - 高波動狀態 → 加重均值回歸型策略（bollinger, rsi, mean_reversion）

    Args:
        allocations: 子策略配置列表
        cash: 初始資金

    Returns:
        包含狀態軌跡、各狀態權重和組合指標的字典
    """
    if cash is None:
        cash = settings.backtest_cash

    logger.info(f"自適應狀態組合: {len(allocations)} 個子策略")

    # 運行所有子策略
    sub_results = []
    for i, a in enumerate(allocations):
        try:
            r = _run_strategy_on_data(
                a["strategy"], a["code"],
                params=a.get("params"),
                cash=cash / len(allocations),
            )
            sub_results.append(r)
            logger.info(f"  [{i+1}] {a['strategy']}/{a['code']}: {r['total_return_pct']:.2f}%")
        except Exception as e:
            logger.error(f"  [{i+1}] {a['strategy']}/{a['code']} 失敗: {e}")

    if not sub_results:
        return {"error": "所有子策略均失敗"}

    # 對齊日期
    common_dates, aligned_navs = _align_navs(sub_results)
    n_periods = len(aligned_navs[0])
    n_strats = len(sub_results)

    # 計算每日收益率
    daily_returns_matrix = []
    for nav in aligned_navs:
        dr = [0.0] + [nav[i] / nav[i - 1] - 1 for i in range(1, n_periods)]
        daily_returns_matrix.append(dr)

    # 策略分類
    trend_strategies = {"dual_ma", "macd", "turtle", "dual_thrust", "momentum", "breakout"}
    mean_revert_strategies = {"bollinger", "rsi", "kdj", "mean_reversion"}

    # 為每個策略計算類型標籤
    strat_types = []
    for r in sub_results:
        if r["strategy"] in trend_strategies:
            strat_types.append("trend")
        elif r["strategy"] in mean_revert_strategies:
            strat_types.append("mean_revert")
        else:
            strat_types.append("neutral")

    # 動態權重計算
    default_weight = 1.0 / n_strats
    current_weights = [default_weight] * n_strats
    weight_history = [[default_weight] * n_strats]
    regime_history = []
    portfolio_nav = [1.0]
    lookback_days = 60  # 狀態判定窗口

    for i in range(1, n_periods):
        # 計算組合收益
        port_ret = sum(
            current_weights[j] * daily_returns_matrix[j][i]
            for j in range(n_strats)
        )
        portfolio_nav.append(portfolio_nav[-1] * (1 + port_ret))

        # 每 lookback_days 天重新判定狀態
        if i % lookback_days == 0 and i >= lookback_days:
            # 計算等權組合近期波動率
            eq_returns = []
            for k in range(max(0, i - lookback_days + 1), i + 1):
                eq_ret = sum(daily_returns_matrix[j][k] for j in range(n_strats)) / n_strats
                eq_returns.append(eq_ret)

            realized_vol = float(np.std(eq_returns) * np.sqrt(252)) if len(eq_returns) > 5 else 0.20

            # 狀態判定
            vol_threshold_low = 0.15   # 低波動閾值
            vol_threshold_high = 0.25  # 高波動閾值

            if realized_vol < vol_threshold_low:
                regime = "low_vol"
                # 低波動 → 加重趨勢策略
                for j in range(n_strats):
                    if strat_types[j] == "trend":
                        current_weights[j] = 2.0
                    elif strat_types[j] == "mean_revert":
                        current_weights[j] = 0.3
                    else:
                        current_weights[j] = 1.0
            elif realized_vol > vol_threshold_high:
                regime = "high_vol"
                # 高波動 → 加重均值回歸策略
                for j in range(n_strats):
                    if strat_types[j] == "mean_revert":
                        current_weights[j] = 2.0
                    elif strat_types[j] == "trend":
                        current_weights[j] = 0.3
                    else:
                        current_weights[j] = 1.0
            else:
                regime = "neutral"
                current_weights = [default_weight] * n_strats

            # 歸一化
            total_w = sum(current_weights)
            current_weights = [w / total_w for w in current_weights]
            regime_history.append({
                "day": i,
                "regime": regime,
                "realized_vol": round(realized_vol, 4),
                "weights": [round(w, 4) for w in current_weights],
            })

        weight_history.append(list(current_weights))

    # 計算指標
    portfolio_metrics = _calc_metrics(portfolio_nav, common_dates)

    sub_metrics = []
    for i, r in enumerate(sub_results):
        m = _calc_metrics(r["nav"], r["dates"])
        m["strategy"] = r["strategy"]
        m["code"] = r["code"]
        m["type"] = strat_types[i]
        sub_metrics.append(m)

    # 狀態統計
    from collections import Counter
    regime_counts = dict(Counter(r["regime"] for r in regime_history)) if regime_history else {}

    # 計算各狀態下的平均權重
    regime_weight_summary = {}
    for regime_name in regime_counts:
        regime_weights = [r["weights"] for r in regime_history if r["regime"] == regime_name]
        if regime_weights:
            avg_w = [round(float(np.mean([w[j] for w in regime_weights])), 4) for j in range(n_strats)]
            regime_weight_summary[regime_name] = {
                "avg_weights": avg_w,
                "count": regime_counts[regime_name],
            }

    return {
        "portfolio": portfolio_metrics,
        "sub_strategies": sub_metrics,
        "portfolio_nav": portfolio_nav,
        "dates": [str(d) for d in common_dates],
        "weight_history": weight_history,
        "regime_history": regime_history,
        "regime_counts": regime_counts,
        "regime_weight_summary": regime_weight_summary,
        "vol_thresholds": {"low": 0.15, "high": 0.25},
        "lookback_days": lookback_days,
        "cash": cash,
    }
