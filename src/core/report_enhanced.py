"""
增強報告模塊 — 全面回測分析報告、多股對比報告、策略分析報告
"""
import numpy as np
from datetime import datetime
from src.core.backtest import (
    run_backtest, run_multi_strategy, STRATEGIES,
    trade_analysis, monte_carlo_simulation, rolling_metrics,
    benchmark_comparison_detail, analyze_equity_curve,
)
from src.core.db import get_alert_logs, load_daily_kline
from src.config import settings
from src.utils.logger import logger


def generate_full_report(code: str, strategy: str, params: dict = None) -> dict:
    """
    生成單股全面回測報告。

    包含：
      - 標準回測指標
      - 交易深度分析
      - 蒙特卡羅模擬
      - 滾動指標
      - 基準對比
      - 信號歷史

    返回：
        結構化 dict，適合 API/CLI 消費
    """
    # 執行回測
    bt_result = run_backtest(code, strategy_name=strategy, params=params)

    # 交易分析
    ta = trade_analysis(bt_result.get("trade_details", []))

    # 蒙特卡羅模擬
    mc = monte_carlo_simulation(bt_result.get("daily_returns", []))

    # 滾動指標
    rm = rolling_metrics(bt_result.get("daily_returns", []), bt_result.get("dates", []))

    # 詳細基準對比
    bc = benchmark_comparison_detail(bt_result)

    # 權益曲線分析
    ea = bt_result.get("equity_analysis", {})

    # 組裝報告
    report = {
        "meta": {
            "code": code,
            "strategy": strategy,
            "params": params or {},
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        # 標準指標
        "performance": {
            "total_return_pct": bt_result.get("total_return_pct", 0),
            "annual_return_pct": bt_result.get("annual_return_pct", 0),
            "sharpe_ratio": bt_result.get("sharpe_ratio", 0),
            "sortino_ratio": bt_result.get("sortino_ratio", 0),
            "calmar_ratio": bt_result.get("calmar_ratio", 0),
            "max_drawdown_pct": bt_result.get("max_drawdown_pct", 0),
            "annual_volatility": bt_result.get("annual_volatility", 0),
            "var_95": bt_result.get("var_95", 0),
            "cvar_95": bt_result.get("cvar_95", 0),
        },
        # 交易統計
        "trades": {
            "total": bt_result.get("total_trades", 0),
            "won": bt_result.get("won_trades", 0),
            "lost": bt_result.get("lost_trades", 0),
            "win_rate_pct": bt_result.get("win_rate_pct", 0),
            "profit_loss_ratio": bt_result.get("profit_loss_ratio", 0),
            "monthly_win_rate": bt_result.get("monthly_win_rate", 0),
            "details": bt_result.get("trade_details", []),
        },
        # 深度分析
        "trade_analysis": ta,
        "monte_carlo": mc,
        "rolling_metrics": {
            "summary": rm.get("summary", {}),
            "window": rm.get("window", 60),
            "data_points": len(rm.get("rolling_sharpe", [])),
            "sharpe_series": rm.get("rolling_sharpe", []),
            "sortino_series": rm.get("rolling_sortino", []),
            "max_dd_series": rm.get("rolling_max_dd", []),
            "volatility_series": rm.get("rolling_volatility", []),
            "dates": rm.get("dates", []),
        },
        "benchmark_comparison": bc,
        "equity_analysis": ea,
        # 信號歷史
        "signals": bt_result.get("signals", []),
        # K 線（可選，前端繪圖用）
        "kline": bt_result.get("kline", []),
        # 淨值曲線
        "nav": bt_result.get("nav", []),
        "dates": bt_result.get("dates", []),
        "daily_returns": bt_result.get("daily_returns", []),
    }

    logger.info(f"全面報告生成: {code}/{strategy}")
    return report


def generate_comparison_report(codes: list, strategy: str) -> dict:
    """
    多股對比報告。

    對多隻股票跑同一策略，對比關鍵指標，按風險調整收益排名。

    參數：
        codes: 股票代碼列表
        strategy: 策略名稱

    返回：
        - results: 各股票的回測摘要
        - ranking: 按夏普排名
        - best/worst: 最佳/最差表現者
    """
    if not codes:
        return {"results": [], "ranking": [], "best": None, "worst": None}

    results = []
    for code in codes:
        try:
            bt = run_backtest(code, strategy_name=strategy)
            ta = trade_analysis(bt.get("trade_details", []))
            results.append({
                "code": code,
                "total_return_pct": bt.get("total_return_pct", 0),
                "annual_return_pct": bt.get("annual_return_pct", 0),
                "sharpe_ratio": bt.get("sharpe_ratio", 0),
                "sortino_ratio": bt.get("sortino_ratio", 0),
                "calmar_ratio": bt.get("calmar_ratio", 0),
                "max_drawdown_pct": bt.get("max_drawdown_pct", 0),
                "annual_volatility": bt.get("annual_volatility", 0),
                "win_rate_pct": bt.get("win_rate_pct", 0),
                "total_trades": bt.get("total_trades", 0),
                "profit_factor": ta.get("profit_factor", 0),
                "expectancy": ta.get("expectancy", 0),
                "var_95": bt.get("var_95", 0),
                "nav": bt.get("nav", []),
                "dates": bt.get("dates", []),
            })
        except Exception as e:
            logger.error(f"對比報告 {code} 失敗: {e}")
            results.append({
                "code": code,
                "error": str(e),
            })

    # 排除失敗的
    valid = [r for r in results if "error" not in r]

    # 按夏普排名
    ranking = sorted(valid, key=lambda x: x.get("sharpe_ratio", 0), reverse=True)
    for i, r in enumerate(ranking):
        r["rank"] = i + 1

    best = ranking[0] if ranking else None
    worst = ranking[-1] if ranking else None

    # 計算一致性分數（所有股票夏普的均值/標準差）
    sharpes = [r.get("sharpe_ratio", 0) for r in valid]
    if len(sharpes) > 1:
        consistency = round(float(np.mean(sharpes) / (np.std(sharpes) + 1e-9)), 4)
    else:
        consistency = 0

    # 計算平均指標
    avg_metrics = {}
    if valid:
        for key in ["total_return_pct", "annual_return_pct", "sharpe_ratio",
                     "sortino_ratio", "max_drawdown_pct", "win_rate_pct"]:
            vals = [r.get(key, 0) for r in valid]
            avg_metrics[f"avg_{key}"] = round(float(np.mean(vals)), 4)

    return {
        "strategy": strategy,
        "total_stocks": len(codes),
        "success_stocks": len(valid),
        "results": results,
        "ranking": ranking,
        "best": best,
        "worst": worst,
        "consistency_score": consistency,
        "avg_metrics": avg_metrics,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def generate_strategy_report(strategy_name: str, codes: list = None) -> dict:
    """
    策略分析報告 — 測試一個策略在多隻股票上的表現。

    參數：
        strategy_name: 策略名稱
        codes: 股票代碼列表（默認使用 watchlist）

    返回：
        - strategy: 策略信息
        - stock_results: 各股票表現
        - avg_metrics: 平均指標
        - consistency_score: 一致性分數
        - best_stock/worst_stock: 最佳/最差股票
        - param_suggestions: 參數調整建議
    """
    if codes is None:
        codes = settings.watchlist

    if strategy_name not in STRATEGIES:
        return {
            "error": f"未知策略: {strategy_name}，可選: {list(STRATEGIES.keys())}",
        }

    # 策略描述
    strategy_cls = STRATEGIES[strategy_name]
    desc = (strategy_cls.__doc__ or "").strip().split("\n")[0]

    # 獲取策略默認參數
    default_params = {}
    if hasattr(strategy_cls, 'params'):
        default_params = dict(strategy_cls.params._getpairs())

    stock_results = []
    for code in codes:
        try:
            bt = run_backtest(code, strategy_name=strategy_name)
            ta = trade_analysis(bt.get("trade_details", []))
            stock_results.append({
                "code": code,
                "total_return_pct": bt.get("total_return_pct", 0),
                "annual_return_pct": bt.get("annual_return_pct", 0),
                "sharpe_ratio": bt.get("sharpe_ratio", 0),
                "sortino_ratio": bt.get("sortino_ratio", 0),
                "calmar_ratio": bt.get("calmar_ratio", 0),
                "max_drawdown_pct": bt.get("max_drawdown_pct", 0),
                "win_rate_pct": bt.get("win_rate_pct", 0),
                "total_trades": bt.get("total_trades", 0),
                "profit_factor": ta.get("profit_factor", 0),
                "expectancy": ta.get("expectancy", 0),
            })
        except Exception as e:
            logger.error(f"策略報告 {code}/{strategy_name} 失敗: {e}")
            stock_results.append({"code": code, "error": str(e)})

    # 過濾成功的
    valid = [r for r in stock_results if "error" not in r]

    # 計算平均指標
    avg_metrics = {}
    if valid:
        for key in ["total_return_pct", "annual_return_pct", "sharpe_ratio",
                     "sortino_ratio", "calmar_ratio", "max_drawdown_pct",
                     "win_rate_pct", "total_trades", "profit_factor", "expectancy"]:
            vals = [r.get(key, 0) for r in valid]
            avg_metrics[f"avg_{key}"] = round(float(np.mean(vals)), 4)
            avg_metrics[f"std_{key}"] = round(float(np.std(vals)), 4)
            avg_metrics[f"min_{key}"] = round(float(np.min(vals)), 4)
            avg_metrics[f"max_{key}"] = round(float(np.max(vals)), 4)

    # 一致性分數
    sharpes = [r.get("sharpe_ratio", 0) for r in valid]
    if len(sharpes) > 1:
        consistency = round(float(np.mean(sharpes) / (np.std(sharpes) + 1e-9)), 4)
    else:
        consistency = 0

    # 排名
    by_sharpe = sorted(valid, key=lambda x: x.get("sharpe_ratio", 0), reverse=True)
    by_return = sorted(valid, key=lambda x: x.get("total_return_pct", 0), reverse=True)

    best_stock = by_sharpe[0] if by_sharpe else None
    worst_stock = by_sharpe[-1] if by_sharpe else None

    # 參數調整建議
    param_suggestions = _generate_param_suggestions(strategy_name, valid)

    return {
        "strategy": strategy_name,
        "description": desc,
        "default_params": default_params,
        "total_stocks": len(codes),
        "success_stocks": len(valid),
        "stock_results": stock_results,
        "avg_metrics": avg_metrics,
        "consistency_score": consistency,
        "best_stock": best_stock,
        "worst_stock": worst_stock,
        "ranking_by_sharpe": by_sharpe,
        "ranking_by_return": by_return,
        "param_suggestions": param_suggestions,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _generate_param_suggestions(strategy_name: str, valid_results: list) -> list:
    """
    根據策略表現生成參數調整建議。

    邏輯：
      - 高回撤 → 建議加大止損
      - 低勝率 → 建議調整進場條件
      - 低夏普 → 建議優化參數
    """
    suggestions = []

    if not valid_results:
        return suggestions

    avg_dd = np.mean([r.get("max_drawdown_pct", 0) for r in valid_results])
    avg_wr = np.mean([r.get("win_rate_pct", 0) for r in valid_results])
    avg_sharpe = np.mean([r.get("sharpe_ratio", 0) for r in valid_results])
    avg_pf = np.mean([r.get("profit_factor", 0) for r in valid_results])

    if avg_dd > 20:
        suggestions.append({
            "type": "risk",
            "level": "high",
            "message": f"平均最大回撤 {avg_dd:.1f}% 偏高，建議設置 10-15% 止損或使用移動止損",
        })

    if avg_wr < 35:
        suggestions.append({
            "type": "win_rate",
            "level": "medium",
            "message": f"平均勝率 {avg_wr:.1f}% 偏低，建議加入趨勢過濾器（如 MA200）減少假信號",
        })

    if avg_sharpe < 0.5:
        suggestions.append({
            "type": "performance",
            "level": "medium",
            "message": f"平均夏普 {avg_sharpe:.2f} 不理想，建議運行參數優化: python main.py optimize <code> {strategy_name}",
        })

    if avg_pf < 1.0:
        suggestions.append({
            "type": "profit_factor",
            "level": "high",
            "message": f"平均盈虧比 {avg_pf:.2f} < 1，策略整體虧損，需要重新設計進出場邏輯",
        })
    elif avg_pf < 1.5:
        suggestions.append({
            "type": "profit_factor",
            "level": "low",
            "message": f"平均盈虧比 {avg_pf:.2f} 尚可，建議加大盈利倉位或縮小止損以提升盈虧比",
        })

    # 策略特定建議
    param_grids = {
        "dual_ma": "fast (5-20), slow (20-60)",
        "macd": "fast (8-16), slow (20-30), signal (7-12)",
        "bollinger": "period (15-30), devfactor (1.5-3.0)",
        "kdj": "period (7-14), overbought (70-90), oversold (10-30)",
        "rsi": "period (10-20), overbought (65-80), oversold (20-35)",
    }
    if strategy_name in param_grids and avg_sharpe < 1.0:
        suggestions.append({
            "type": "optimize",
            "level": "info",
            "message": f"建議搜索參數空間: {param_grids[strategy_name]}",
        })

    return suggestions
