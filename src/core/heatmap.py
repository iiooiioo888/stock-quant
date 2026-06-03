"""
策略熱力圖 — 參數敏感度分析
"""
import numpy as np

from src.core.backtest import STRATEGIES
from src.core.optimize import _run_single, _score
from src.utils.logger import logger


def _params_valid(params: dict) -> bool:
    if "fast" in params and "slow" in params and params["fast"] >= params["slow"]:
        return False
    if "entry_period" in params and "exit_period" in params and params["entry_period"] <= params["exit_period"]:
        return False
    if "overbought" in params and "oversold" in params and params["overbought"] <= params["oversold"]:
        return False
    return True


def _eval_heatmap_point(
    code: str,
    strategy_name: str,
    default_params: dict,
    param_x: str,
    param_y: str,
    x_val,
    y_val,
    objective: str,
):
    params = dict(default_params)
    params[param_x] = x_val
    params[param_y] = y_val
    if not _params_valid(params):
        return None, None, None
    try:
        r = _run_single(code, strategy_name, params)
        score = _score(r, objective)
        return round(score, 4), score, {param_x: x_val, param_y: y_val}
    except Exception as e:
        logger.debug(f"熱力圖點 ({x_val}, {y_val}) 失敗: {e}")
        return None, None, None


def _get_default_params(strategy_name: str) -> dict:
    """從策略類獲取默認參數"""
    cls = STRATEGIES[strategy_name]
    return dict(cls.params._getpairs())


def param_heatmap(
    code: str,
    strategy_name: str,
    param_x: str,
    param_y: str,
    x_range: tuple = None,
    y_range: tuple = None,
    grid_size: int = 10,
    objective: str = "sharpe",
) -> dict:
    """
    生成兩維參數的熱力圖數據。

    Args:
        code: 股票代碼
        strategy_name: 策略名稱
        param_x: X 軸參數名
        param_y: Y 軸參數名
        x_range: X 軸範圍 (min, max)
        y_range: Y 軸範圍 (min, max)
        grid_size: 網格大小
        objective: 評分指標 (sharpe/return/calmar/win_rate)

    Returns:
        熱力圖數據字典
    """
    if strategy_name not in STRATEGIES:
        raise ValueError(f"未知策略: {strategy_name}，可選: {list(STRATEGIES.keys())}")

    from src.core.optimize import PARAM_RANGES
    ranges = PARAM_RANGES.get(strategy_name, {})
    default_params = _get_default_params(strategy_name)

    if param_x not in default_params:
        raise ValueError(f"策略 {strategy_name} 沒有參數 {param_x}，可選: {list(default_params.keys())}")
    if param_y not in default_params:
        raise ValueError(f"策略 {strategy_name} 沒有參數 {param_y}，可選: {list(default_params.keys())}")

    # 確定 X, Y 範圍
    def _resolve_range(param_name, user_range):
        if user_range:
            return user_range
        if param_name in ranges:
            return ranges[param_name]
        default_val = default_params[param_name]
        if isinstance(default_val, int):
            return (max(1, default_val // 2), default_val * 3)
        else:
            return (default_val * 0.2, default_val * 3)

    x_min, x_max = _resolve_range(param_x, x_range)
    y_min, y_max = _resolve_range(param_y, y_range)

    # 生成值列表
    def _make_values(lo, hi, n):
        if isinstance(lo, int) and isinstance(hi, int):
            step = max(1, (hi - lo) // (n - 1)) if n > 1 else 1
            vals = list(range(lo, hi + 1, step))[:n]
            if not vals:
                vals = [lo]
            return vals
        else:
            return [round(v, 4) for v in np.linspace(lo, hi, n)]

    x_values = _make_values(x_min, x_max, grid_size)
    y_values = _make_values(y_min, y_max, grid_size)

    # 運行網格（可並行）
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from src.config import settings
    from src.core.compute_budget import get_thread_workers

    matrix = [[None for _ in x_values] for _ in y_values]
    best_score = float("-inf")
    best_params = {}
    total = len(x_values) * len(y_values)
    count = 0

    jobs = [
        (yi, xi, y_val, x_val)
        for yi, y_val in enumerate(y_values)
        for xi, x_val in enumerate(x_values)
    ]

    def _run_job(job):
        yi, xi, y_val, x_val = job
        cell, score, bp = _eval_heatmap_point(
            code, strategy_name, default_params, param_x, param_y, x_val, y_val, objective,
        )
        return yi, xi, cell, score, bp

    parallel = bool(getattr(settings, "heatmap_parallel", True)) and total > 4
    max_workers = get_thread_workers(
        getattr(settings, "heatmap_max_workers", 4),
        min_workers=1,
    )

    if parallel:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_run_job, j): j for j in jobs}
            for fut in as_completed(futures):
                yi, xi, cell, score, bp = fut.result()
                matrix[yi][xi] = cell
                if score is not None and score > best_score:
                    best_score = score
                    best_params = bp or {}
                count += 1
                if count % 50 == 0:
                    logger.info(f"  熱力圖進度: {count}/{total}")
    else:
        for yi, xi, y_val, x_val in jobs:
            yi, xi, cell, score, bp = _run_job((yi, xi, y_val, x_val))
            matrix[yi][xi] = cell
            if score is not None and score > best_score:
                best_score = score
                best_params = bp or {}
            count += 1
            if count % 50 == 0:
                logger.info(f"  熱力圖進度: {count}/{total}")

    # 替換 None 為 None (JSON null)
    result = {
        "param_x": param_x,
        "param_y": param_y,
        "x_values": x_values,
        "y_values": y_values,
        "matrix": matrix,
        "objective": objective,
        "best_params": best_params,
        "best_score": round(best_score, 4) if best_score > float("-inf") else None,
    }

    logger.info(
        f"熱力圖完成: {code}/{strategy_name} "
        f"[{param_x}×{param_y}] {grid_size}×{grid_size} "
        f"最佳={best_params} score={best_score:.4f}"
    )

    return result
