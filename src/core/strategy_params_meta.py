"""
策略參數元數據 — 中文標籤、類型、優化網格（供 API / 前端共用）
"""

from src.config import settings
from src.core.optimize import PARAM_GRIDS, PARAM_RANGES

# 參數中文標籤（可選，前端展示用）
PARAM_LABELS = {
    "fast": "快線週期",
    "slow": "慢線週期",
    "signal": "信號線",
    "period": "週期",
    "devfactor": "標準差倍數",
    "overbought": "超買閾值",
    "oversold": "超賣閾值",
    "entry_period": "入場週期",
    "exit_period": "出場週期",
    "atr_period": "ATR週期",
    "risk_pct": "風險比例%",
    "lookback": "回看週期",
    "hold_period": "持有週期",
    "grid_pct": "網格間距%",
    "position_pct": "單格倉位",
    "k_up": "上軌係數",
    "k_down": "下軌係數",
    "entry_zscore": "入場Z分",
    "exit_zscore": "出場Z分",
    "price_ma": "價格均線",
    "volume_ma": "成交量均線",
    "volume_ratio": "量比閾值",
    "deviation_pct": "偏離%",
    "atr_multiplier": "ATR倍數",
    "adx_period": "ADX週期",
    "adx_threshold": "ADX閾值",
    "di_period": "DI週期",
    "af_start": "加速因子初值",
    "af_step": "加速因子步長",
    "af_max": "加速因子上限",
    "squeeze_threshold": "擠壓閾值",
    "squeeze_lookback": "擠壓回看",
    "obv_ma_period": "OBV均線",
    "price_ma_period": "價格均線週期",
    "min_agreement": "最少一致數",
    "ma_fast": "組合快線",
    "ma_slow": "組合慢線",
    "macd_fast": "MACD快線",
    "macd_slow": "MACD慢線",
    "macd_signal": "MACD信號",
    "rsi_period": "RSI週期",
    "rsi_overbought": "RSI超買",
    "rsi_oversold": "RSI超賣",
    "boll_period": "布林週期",
    "boll_dev": "布林倍數",
    "period_dfast": "K值平滑",
    "period_dslow": "D值平滑",
}


def get_all_strategy_params() -> dict:
    """返回全部策略的默認參數、優化網格與 Optuna 範圍"""
    from src.core.backtest import STRATEGIES

    out = {}
    for name in sorted(STRATEGIES.keys()):
        defaults = settings.get_strategy_defaults(name) or {}
        grid = PARAM_GRIDS.get(name, {})
        ranges = PARAM_RANGES.get(name, {})
        out[name] = {
            "defaults": defaults,
            "param_keys": list(defaults.keys()),
            "grid_values": grid,
            "optuna_ranges": {k: list(v) for k, v in ranges.items()},
            "labels": {k: PARAM_LABELS.get(k, k) for k in defaults.keys()},
        }
    return out
