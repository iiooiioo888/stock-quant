"""
多因子選股引擎 — 價值/動量/質量/波動因子

功能：
- 因子計算：PE/PB/ROE/動量/波動率/成交量等
- IC 分析（Information Coefficient）：因子與未來收益的相關性
- 因子正交化：消除因子間多重共線性
- 因子選股：綜合打分排名
"""
from __future__ import annotations

import math
from typing import Any, Optional

import numpy as np
import pandas as pd

from src.utils.logger import logger


# ============================================================
# 因子定義
# ============================================================

FACTOR_DEFINITIONS = {
    # 價值因子
    "pe_ttm": {"label": "市盈率(TTM)", "category": "value", "direction": -1, "description": "越低越好"},
    "pb": {"label": "市淨率", "category": "value", "direction": -1, "description": "越低越好"},
    "dividend_yield": {"label": "股息率", "category": "value", "direction": 1, "description": "越高越好"},
    # 質量因子
    "roe": {"label": "ROE", "category": "quality", "direction": 1, "description": "越高越好"},
    "gross_margin": {"label": "毛利率", "category": "quality", "direction": 1, "description": "越高越好"},
    "net_margin": {"label": "淨利率", "category": "quality", "direction": 1, "description": "越高越好"},
    "debt_ratio": {"label": "資產負債率", "category": "quality", "direction": -1, "description": "越低越好"},
    # 成長因子
    "revenue_yoy": {"label": "營收同比", "category": "growth", "direction": 1, "description": "越高越好"},
    "profit_yoy": {"label": "利潤同比", "category": "growth", "direction": 1, "description": "越高越好"},
    # 動量因子（從 K 線計算）
    "momentum_20d": {"label": "20日動量", "category": "momentum", "direction": 1, "description": "20日收益率"},
    "momentum_60d": {"label": "60日動量", "category": "momentum", "direction": 1, "description": "60日收益率"},
    # 波動因子
    "volatility_20d": {"label": "20日波動率", "category": "volatility", "direction": -1, "description": "越低越好"},
    "atr_ratio": {"label": "ATR比率", "category": "volatility", "direction": -1, "description": "ATR/價格"},
    # 量價因子
    "turnover_avg": {"label": "平均換手率", "category": "liquidity", "direction": 0, "description": "中性"},
    "volume_ratio": {"label": "量比", "category": "liquidity", "direction": 0, "description": "當前量/均量"},
}


def list_factor_definitions() -> list[dict]:
    """列出所有因子定義。"""
    out = []
    for key, meta in FACTOR_DEFINITIONS.items():
        out.append({"key": key, **meta})
    return out


def list_factor_categories() -> dict[str, list[str]]:
    """按類別分組列出因子。"""
    cats: dict[str, list[str]] = {}
    for key, meta in FACTOR_DEFINITIONS.items():
        cat = meta["category"]
        cats.setdefault(cat, []).append(key)
    return cats


# ============================================================
# 因子計算
# ============================================================

def compute_value_quality_factors(fundamentals: dict) -> dict[str, Optional[float]]:
    """從基本面數據計算價值/質量/成長因子。"""
    factors = {}
    for key in ("pe_ttm", "pb", "roe", "gross_margin", "net_margin",
                "debt_ratio", "dividend_yield", "revenue_yoy", "profit_yoy",
                "ps_ttm", "eps", "bvps"):
        factors[key] = fundamentals.get(key)
    return factors


def compute_momentum_factors(closes: list[float], dates: list[str] = None) -> dict[str, Optional[float]]:
    """從收盤價序列計算動量因子。"""
    if not closes or len(closes) < 2:
        return {"momentum_20d": None, "momentum_60d": None}

    n = len(closes)
    last = closes[-1]
    if last == 0:
        return {"momentum_20d": None, "momentum_60d": None}

    mom_20 = (last / closes[max(0, n - 21)] - 1) * 100 if n >= 21 else None
    mom_60 = (last / closes[max(0, n - 61)] - 1) * 100 if n >= 61 else None

    return {
        "momentum_20d": round(mom_20, 4) if mom_20 is not None else None,
        "momentum_60d": round(mom_60, 4) if mom_60 is not None else None,
    }


def compute_volatility_factors(closes: list[float], highs: list[float] = None,
                                lows: list[float] = None) -> dict[str, Optional[float]]:
    """從價格序列計算波動因子。"""
    if not closes or len(closes) < 20:
        return {"volatility_20d": None, "atr_ratio": None}

    arr = np.array(closes[-20:], dtype=float)
    returns = np.diff(arr) / arr[:-1]
    vol = float(np.std(returns) * np.sqrt(252) * 100) if len(returns) > 1 else None

    # ATR ratio
    atr_ratio = None
    if highs and lows and len(highs) >= 14 and len(lows) >= 14:
        h = np.array(highs[-14:], dtype=float)
        l = np.array(lows[-14:], dtype=float)
        c = np.array(closes[-14:], dtype=float)
        tr = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
        atr = float(np.mean(tr))
        if closes[-1] > 0:
            atr_ratio = round(atr / closes[-1] * 100, 4)

    return {
        "volatility_20d": round(vol, 4) if vol is not None else None,
        "atr_ratio": atr_ratio,
    }


def compute_liquidity_factors(volumes: list[float], turnovers: list[float] = None) -> dict[str, Optional[float]]:
    """從成交量序列計算流動性因子。"""
    if not volumes or len(volumes) < 5:
        return {"turnover_avg": None, "volume_ratio": None}

    vol_arr = np.array(volumes[-20:], dtype=float) if len(volumes) >= 20 else np.array(volumes, dtype=float)
    vol_avg = float(np.mean(vol_arr))
    vol_ratio = round(volumes[-1] / vol_avg, 4) if vol_avg > 0 else None

    turnover_avg = None
    if turnovers and len(turnovers) >= 5:
        t_arr = np.array(turnovers[-20:], dtype=float) if len(turnovers) >= 20 else np.array(turnovers, dtype=float)
        turnover_avg = round(float(np.mean(t_arr)), 4)

    return {
        "turnover_avg": turnover_avg,
        "volume_ratio": vol_ratio,
    }


def compute_all_factors(fundamentals: dict = None, closes: list[float] = None,
                         highs: list[float] = None, lows: list[float] = None,
                         volumes: list[float] = None, turnovers: list[float] = None) -> dict[str, Any]:
    """計算所有可用因子。"""
    factors = {}
    if fundamentals:
        factors.update(compute_value_quality_factors(fundamentals))
    if closes:
        factors.update(compute_momentum_factors(closes))
        factors.update(compute_volatility_factors(closes, highs, lows))
    if volumes:
        factors.update(compute_liquidity_factors(volumes, turnovers))
    return factors


# ============================================================
# 因子標準化（Z-Score）
# ============================================================

def zscore_normalize(values: list[Optional[float]]) -> list[Optional[float]]:
    """Z-Score 標準化：(x - mean) / std。"""
    valid = [v for v in values if v is not None and not math.isnan(v)]
    if len(valid) < 2:
        return values

    mean = np.mean(valid)
    std = np.std(valid)
    if std == 0:
        return [0.0 if v is not None else None for v in values]

    return [round((v - mean) / std, 4) if v is not None else None for v in values]


def rank_normalize(values: list[Optional[float]], ascending: bool = True) -> list[Optional[float]]:
    """排名百分位標準化（0~1）。"""
    n = len(values)
    valid_indices = [(i, v) for i, v in enumerate(values) if v is not None and not math.isnan(v)]
    if not valid_indices:
        return values

    sorted_items = sorted(valid_indices, key=lambda x: x[1], reverse=not ascending)
    result = [None] * n
    for rank, (idx, _) in enumerate(sorted_items):
        result[idx] = round(rank / max(len(sorted_items) - 1, 1), 4)

    return result


# ============================================================
# IC 分析（Information Coefficient）
# ============================================================

def compute_ic(factor_values: list[float], forward_returns: list[float]) -> dict[str, float]:
    """
    計算因子 IC（Information Coefficient）。
    
    IC = spearman_rank_correlation(factor, forward_return)
    
    Args:
        factor_values: 因子值序列
        forward_returns: 對應的未來收益率
    
    Returns:
        {"ic": float, "rank_ic": float, "ic_ir": float, "n": int}
    """
    n = min(len(factor_values), len(forward_returns))
    if n < 5:
        return {"ic": 0.0, "rank_ic": 0.0, "ic_ir": 0.0, "n": n}

    fv = np.array(factor_values[:n], dtype=float)
    fr = np.array(forward_returns[:n], dtype=float)

    # 去除 NaN
    mask = ~(np.isnan(fv) | np.isnan(fr))
    fv, fr = fv[mask], fr[mask]
    if len(fv) < 5:
        return {"ic": 0.0, "rank_ic": 0.0, "ic_ir": 0.0, "n": len(fv)}

    # Pearson IC
    ic = float(np.corrcoef(fv, fr)[0, 1]) if np.std(fv) > 0 and np.std(fr) > 0 else 0.0

    # Spearman Rank IC
    from scipy import stats
    try:
        rank_ic, _ = stats.spearmanr(fv, fr)
        rank_ic = float(rank_ic) if not np.isnan(rank_ic) else 0.0
    except Exception:
        rank_ic = 0.0

    return {
        "ic": round(ic, 4),
        "rank_ic": round(rank_ic, 4),
        "ic_ir": round(ic, 4),  # 簡化版，實際應為 mean(IC)/std(IC)
        "n": len(fv),
    }


def compute_ic_series(factor_df: pd.DataFrame, return_df: pd.DataFrame,
                       factor_col: str, return_col: str, window: int = 20) -> pd.DataFrame:
    """
    計算滾動 IC 時間序列。
    
    Args:
        factor_df: 因子數據（columns=[date, code, factor]）
        return_df: 收益數據（columns=[date, code, return]）
        factor_col: 因子列名
        return_col: 收益列名
        window: 滾動窗口
    
    Returns:
        DataFrame with columns=[date, ic, rank_ic]
    """
    merged = pd.merge(factor_df, return_df, on=["date", "code"], how="inner")
    if merged.empty:
        return pd.DataFrame(columns=["date", "ic", "rank_ic"])

    results = []
    for date, group in merged.groupby("date"):
        fv = group[factor_col].dropna().values
        fr = group[return_col].dropna().values
        n = min(len(fv), len(fr))
        if n < 5:
            results.append({"date": date, "ic": 0.0, "rank_ic": 0.0})
            continue

        ic_result = compute_ic(list(fv[:n]), list(fr[:n]))
        results.append({"date": date, "ic": ic_result["ic"], "rank_ic": ic_result["rank_ic"]})

    return pd.DataFrame(results)


# ============================================================
# 因子正交化
# ============================================================

def orthogonalize_factors(factor_matrix: pd.DataFrame) -> pd.DataFrame:
    """
    因子正交化（Gram-Schmidt）：消除因子間多重共線性。
    
    按列順序依次正交化（前面的因子優先級高）。
    
    Args:
        factor_matrix: DataFrame，每列為一個因子
    
    Returns:
        正交化後的 DataFrame
    """
    cols = list(factor_matrix.columns)
    mat = factor_matrix.values.astype(float)
    n_rows, n_cols = mat.shape

    # 填充 NaN 為列均值
    for j in range(n_cols):
        col = mat[:, j]
        nan_mask = np.isnan(col)
        if nan_mask.any():
            col_mean = np.nanmean(col)
            col[nan_mask] = col_mean

    # Gram-Schmidt 正交化
    orthogonal = np.zeros_like(mat)
    for j in range(n_cols):
        v = mat[:, j].copy()
        for k in range(j):
            proj = np.dot(orthogonal[:, k], v) / (np.dot(orthogonal[:, k], orthogonal[:, k]) + 1e-10)
            v -= proj * orthogonal[:, k]
        orthogonal[:, j] = v

    # 重新標準化
    for j in range(n_cols):
        std = np.std(orthogonal[:, j])
        if std > 0:
            orthogonal[:, j] = (orthogonal[:, j] - np.mean(orthogonal[:, j])) / std

    return pd.DataFrame(orthogonal, columns=cols, index=factor_matrix.index)


# ============================================================
# 因子選股打分
# ============================================================

def score_stocks(stock_factors: dict[str, dict[str, Optional[float]]],
                  weights: dict[str, float] = None,
                  top_n: int = 20) -> list[dict]:
    """
    多因子綜合打分選股。
    
    Args:
        stock_factors: {code: {factor_name: value, ...}, ...}
        weights: 因子權重（默認等權）
        top_n: 返回前 N 名
    
    Returns:
        [{"code": str, "score": float, "factors": dict, "rank": int}, ...]
    """
    if not stock_factors:
        return []

    # 收集所有因子值
    all_codes = list(stock_factors.keys())
    all_factors = set()
    for f_dict in stock_factors.values():
        all_factors.update(f_dict.keys())

    # 默認等權
    if not weights:
        active_factors = [f for f in all_factors if f in FACTOR_DEFINITIONS]
        weights = {f: 1.0 / max(len(active_factors), 1) for f in active_factors}

    # 標準化每個因子
    normalized: dict[str, dict[str, Optional[float]]] = {}
    for factor_name in weights:
        values = [stock_factors.get(c, {}).get(factor_name) for c in all_codes]
        direction = FACTOR_DEFINITIONS.get(factor_name, {}).get("direction", 1)

        # Z-Score 標準化
        normed = zscore_normalize(values)

        # 方向調整（direction=-1 表示越低越好，取反）
        if direction < 0:
            normed = [-v if v is not None else None for v in normed]

        for i, code in enumerate(all_codes):
            normalized.setdefault(code, {})[factor_name] = normed[i]

    # 綜合打分
    scored = []
    for code in all_codes:
        total = 0.0
        weight_sum = 0.0
        factors = normalized.get(code, {})
        for factor_name, w in weights.items():
            v = factors.get(factor_name)
            if v is not None and not math.isnan(v):
                total += v * w
                weight_sum += w

        score = total / weight_sum if weight_sum > 0 else 0.0
        scored.append({
            "code": code,
            "score": round(score, 4),
            "factors": stock_factors.get(code, {}),
        })

    # 排序
    scored.sort(key=lambda x: x["score"], reverse=True)
    for i, item in enumerate(scored):
        item["rank"] = i + 1

    return scored[:top_n]


# ============================================================
# 便捷 API
# ============================================================

def screen_by_factors(codes: list[str], fundamentals_map: dict[str, dict],
                       kline_map: dict[str, pd.DataFrame] = None,
                       weights: dict[str, float] = None,
                       top_n: int = 20) -> list[dict]:
    """
    多因子選股便捷接口。
    
    Args:
        codes: 股票代碼列表
        fundamentals_map: {code: fundamentals_dict}
        kline_map: {code: DataFrame with columns [close, high, low, volume, turnover]}
        weights: 因子權重
        top_n: 返回前 N 名
    
    Returns:
        打分排名結果
    """
    stock_factors = {}

    for code in codes:
        fund = fundamentals_map.get(code, {})
        factors = compute_value_quality_factors(fund)

        if kline_map and code in kline_map:
            df = kline_map[code]
            closes = df["close"].tolist() if "close" in df.columns else None
            highs = df["high"].tolist() if "high" in df.columns else None
            lows = df["low"].tolist() if "low" in df.columns else None
            volumes = df["volume"].tolist() if "volume" in df.columns else None
            turnovers = df["turnover"].tolist() if "turnover" in df.columns else None

            if closes:
                factors.update(compute_momentum_factors(closes))
                factors.update(compute_volatility_factors(closes, highs, lows))
            if volumes:
                factors.update(compute_liquidity_factors(volumes, turnovers))

        stock_factors[code] = factors

    return score_stocks(stock_factors, weights=weights, top_n=top_n)