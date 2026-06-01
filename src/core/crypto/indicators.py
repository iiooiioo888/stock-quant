"""
加密貨幣專用技術指標引擎。

復用 src/core/indicators/fast_indicators.py 的 RSI/MACD/ATR/SMA（Numba 加速），
額外新增加密專用指標：
- EMA 多週期、Supertrend、Ichimoku Cloud
- Stochastic RSI、Williams %R、CCI
- Bollinger Bands、Keltner Channel
- OBV、VWAP、MFI、ADOSC
- Taker Buy/Sell Ratio、大單偵測
- 波動率百分位
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np

from src.core.indicators.fast_indicators import (
    compute_atr,
    compute_macd,
    compute_rsi,
    compute_sma,
)
from src.utils.logger import logger


# ============================================================
# 趨勢指標
# ============================================================

def compute_ema(close: np.ndarray, period: int) -> np.ndarray:
    """指數移動平均線（EMA）。"""
    c = np.asarray(close, dtype=np.float64).ravel()
    n = len(c)
    out = np.full(n, np.nan)
    if n < period or period < 1:
        return out
    alpha = 2.0 / (period + 1.0)
    # 用 SMA 作為種子值
    out[period - 1] = np.mean(c[:period])
    for i in range(period, n):
        out[i] = alpha * c[i] + (1.0 - alpha) * out[i - 1]
    return out


def compute_ema_multi(close: np.ndarray, periods: list[int] = None) -> dict[str, np.ndarray]:
    """多週期 EMA。"""
    periods = periods or [9, 21, 55, 200]
    return {f"ema_{p}": compute_ema(close, p) for p in periods}


def compute_supertrend(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    atr_period: int = 10,
    multiplier: float = 3.0,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Supertrend 指標。
    返回：(supertrend_line, direction) — direction: 1=上升, -1=下降
    """
    h = np.asarray(high, dtype=np.float64).ravel()
    l = np.asarray(low, dtype=np.float64).ravel()
    c = np.asarray(close, dtype=np.float64).ravel()
    n = len(c)

    atr = compute_atr(h, l, c, atr_period)
    hl2 = (h + l) / 2.0

    upper_band = hl2 + multiplier * atr
    lower_band = hl2 - multiplier * atr

    st = np.full(n, np.nan)
    direction = np.zeros(n)

    for i in range(1, n):
        if np.isnan(atr[i]):
            continue

        # 上軌調整（只能下降）
        if upper_band[i] < upper_band[i - 1] or c[i - 1] > upper_band[i - 1]:
            pass
        else:
            upper_band[i] = upper_band[i - 1]

        # 下軌調整（只能上升）
        if lower_band[i] > lower_band[i - 1] or c[i - 1] < lower_band[i - 1]:
            pass
        else:
            lower_band[i] = lower_band[i - 1]

        # 方向判定
        if i == 1:
            direction[i] = 1
            st[i] = lower_band[i]
        else:
            prev_dir = direction[i - 1]
            if prev_dir == 1:
                if c[i] < lower_band[i]:
                    direction[i] = -1
                    st[i] = upper_band[i]
                else:
                    direction[i] = 1
                    st[i] = lower_band[i]
            else:
                if c[i] > upper_band[i]:
                    direction[i] = 1
                    st[i] = lower_band[i]
                else:
                    direction[i] = -1
                    st[i] = upper_band[i]

    return st, direction


def compute_ichimoku(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    tenkan: int = 9,
    kijun: int = 26,
    senkou_b: int = 52,
) -> dict[str, np.ndarray]:
    """
    Ichimoku Cloud。
    返回：tenkan_sen, kijun_sen, senkou_a, senkou_b, chikou
    """
    h = np.asarray(high, dtype=np.float64).ravel()
    l = np.asarray(low, dtype=np.float64).ravel()
    c = np.asarray(close, dtype=np.float64).ravel()
    n = len(c)

    def _donchian(data: np.ndarray, period: int) -> np.ndarray:
        out = np.full(n, np.nan)
        for i in range(period - 1, n):
            out[i] = (np.max(data[i - period + 1:i + 1]) + np.min(data[i - period + 1:i + 1])) / 2.0
        return out

    tenkan_sen = _donchian((h + l) / 2.0, tenkan)
    kijun_sen = _donchian((h + l) / 2.0, kijun)

    senkou_a = np.full(n, np.nan)
    for i in range(max(tenkan, kijun) - 1, n):
        if not np.isnan(tenkan_sen[i]) and not np.isnan(kijun_sen[i]):
            senkou_a[i] = (tenkan_sen[i] + kijun_sen[i]) / 2.0

    senkou_b_line = _donchian((h + l) / 2.0, senkou_b)

    chikou = np.full(n, np.nan)
    if n > kijun:
        chikou[:n - kijun] = c[kijun:]

    return {
        "tenkan_sen": tenkan_sen,
        "kijun_sen": kijun_sen,
        "senkou_a": senkou_a,
        "senkou_b": senkou_b_line,
        "chikou": chikou,
    }


# ============================================================
# 動量指標
# ============================================================

def compute_stoch_rsi(
    close: np.ndarray,
    rsi_period: int = 14,
    stoch_period: int = 14,
    k_smooth: int = 3,
    d_smooth: int = 3,
) -> tuple[np.ndarray, np.ndarray]:
    """Stochastic RSI。返回：(K, D)"""
    c = np.asarray(close, dtype=np.float64).ravel()
    rsi = compute_rsi(c, rsi_period)
    n = len(rsi)

    stoch = np.full(n, np.nan)
    for i in range(stoch_period - 1, n):
        window = rsi[i - stoch_period + 1:i + 1]
        valid = window[~np.isnan(window)]
        if len(valid) > 0:
            r_min = np.min(valid)
            r_max = np.max(valid)
            if r_max != r_min:
                stoch[i] = (rsi[i] - r_min) / (r_max - r_min) * 100
            else:
                stoch[i] = 50.0

    k = _sma_nan(stoch, k_smooth)
    d = _sma_nan(k, d_smooth)
    return k, d


def compute_williams_r(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    period: int = 14,
) -> np.ndarray:
    """Williams %R。"""
    h = np.asarray(high, dtype=np.float64).ravel()
    l = np.asarray(low, dtype=np.float64).ravel()
    c = np.asarray(close, dtype=np.float64).ravel()
    n = len(c)
    out = np.full(n, np.nan)
    for i in range(period - 1, n):
        hh = np.max(h[i - period + 1:i + 1])
        ll = np.min(l[i - period + 1:i + 1])
        if hh != ll:
            out[i] = (hh - c[i]) / (hh - ll) * -100
        else:
            out[i] = -50.0
    return out


def compute_cci(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    period: int = 20,
) -> np.ndarray:
    """CCI（Commodity Channel Index）。"""
    h = np.asarray(high, dtype=np.float64).ravel()
    l = np.asarray(low, dtype=np.float64).ravel()
    c = np.asarray(close, dtype=np.float64).ravel()
    tp = (h + l + c) / 3.0
    n = len(tp)
    out = np.full(n, np.nan)
    for i in range(period - 1, n):
        window = tp[i - period + 1:i + 1]
        mean = np.mean(window)
        mad = np.mean(np.abs(window - mean))
        if mad > 0:
            out[i] = (tp[i] - mean) / (0.015 * mad)
        else:
            out[i] = 0.0
    return out


# ============================================================
# 波動指標
# ============================================================

def compute_bollinger_bands(
    close: np.ndarray,
    period: int = 20,
    std_dev: float = 2.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Bollinger Bands。返回：(upper, middle, lower)"""
    c = np.asarray(close, dtype=np.float64).ravel()
    n = len(c)
    middle = compute_sma(c, period)
    upper = np.full(n, np.nan)
    lower = np.full(n, np.nan)
    for i in range(period - 1, n):
        window = c[i - period + 1:i + 1]
        std = np.std(window, ddof=0)
        upper[i] = middle[i] + std_dev * std
        lower[i] = middle[i] - std_dev * std
    return upper, middle, lower


def compute_keltner_channel(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    ema_period: int = 20,
    atr_period: int = 10,
    multiplier: float = 2.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Keltner Channel。返回：(upper, middle, lower)"""
    c = np.asarray(close, dtype=np.float64).ravel()
    h = np.asarray(high, dtype=np.float64).ravel()
    l = np.asarray(low, dtype=np.float64).ravel()
    n = len(c)
    middle = compute_ema(c, ema_period)
    atr = compute_atr(h, l, c, atr_period)
    upper = np.full(n, np.nan)
    lower = np.full(n, np.nan)
    for i in range(n):
        if not np.isnan(middle[i]) and not np.isnan(atr[i]):
            upper[i] = middle[i] + multiplier * atr[i]
            lower[i] = middle[i] - multiplier * atr[i]
    return upper, middle, lower


def compute_volatility_percentile(closes: np.ndarray, window: int = 30) -> float:
    """
    當前波動率在近 N 日中的百分位。
    返回 0~100 的浮點數。
    """
    c = np.asarray(closes, dtype=np.float64).ravel()
    if len(c) < window + 1:
        return 50.0

    returns = np.diff(np.log(c))
    if len(returns) < window:
        return 50.0

    current_vol = np.std(returns[-20:]) * np.sqrt(252)
    historical_vols = []
    for i in range(len(returns) - window, -1, -1):
        hist_ret = returns[i:i + 20]
        if len(hist_ret) == 20:
            historical_vols.append(np.std(hist_ret) * np.sqrt(252))

    if not historical_vols:
        return 50.0

    count_below = sum(1 for v in historical_vols if v < current_vol)
    return round(count_below / len(historical_vols) * 100, 2)


# ============================================================
# 量價指標
# ============================================================

def compute_obv(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    """OBV（On-Balance Volume）。"""
    c = np.asarray(close, dtype=np.float64).ravel()
    v = np.asarray(volume, dtype=np.float64).ravel()
    n = len(c)
    out = np.zeros(n)
    if n < 2:
        return out
    out[0] = v[0]
    for i in range(1, n):
        if c[i] > c[i - 1]:
            out[i] = out[i - 1] + v[i]
        elif c[i] < c[i - 1]:
            out[i] = out[i - 1] - v[i]
        else:
            out[i] = out[i - 1]
    return out


def compute_vwap(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
) -> np.ndarray:
    """VWAP（成交量加權平均價格）。"""
    h = np.asarray(high, dtype=np.float64).ravel()
    l = np.asarray(low, dtype=np.float64).ravel()
    c = np.asarray(close, dtype=np.float64).ravel()
    v = np.asarray(volume, dtype=np.float64).ravel()
    tp = (h + l + c) / 3.0
    cumulative_tp_vol = np.cumsum(tp * v)
    cumulative_vol = np.cumsum(v)
    n = len(c)
    out = np.full(n, np.nan)
    for i in range(n):
        if cumulative_vol[i] > 0:
            out[i] = cumulative_tp_vol[i] / cumulative_vol[i]
    return out


def compute_mfi(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
    period: int = 14,
) -> np.ndarray:
    """MFI（Money Flow Index）。"""
    h = np.asarray(high, dtype=np.float64).ravel()
    l = np.asarray(low, dtype=np.float64).ravel()
    c = np.asarray(close, dtype=np.float64).ravel()
    v = np.asarray(volume, dtype=np.float64).ravel()
    tp = (h + l + c) / 3.0
    mf = tp * v
    n = len(c)
    out = np.full(n, np.nan)

    for i in range(period, n):
        pos = 0.0
        neg = 0.0
        for j in range(i - period + 1, i + 1):
            if tp[j] > tp[j - 1]:
                pos += mf[j]
            elif tp[j] < tp[j - 1]:
                neg += mf[j]
        if neg == 0:
            out[i] = 100.0
        else:
            ratio = pos / neg
            out[i] = 100.0 - (100.0 / (1.0 + ratio))
    return out


def compute_adosc(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
    fast: int = 3,
    slow: int = 10,
) -> np.ndarray:
    """ADOSC（Accumulation/Distribution Oscillator）。"""
    h = np.asarray(high, dtype=np.float64).ravel()
    l = np.asarray(low, dtype=np.float64).ravel()
    c = np.asarray(close, dtype=np.float64).ravel()
    v = np.asarray(volume, dtype=np.float64).ravel()
    n = len(c)

    clv = np.zeros(n)
    for i in range(n):
        hl = h[i] - l[i]
        if hl > 0:
            clv[i] = ((c[i] - l[i]) - (h[i] - c[i])) / hl * v[i]

    ad = np.cumsum(clv)
    fast_ema = compute_ema(ad, fast)
    slow_ema = compute_ema(ad, slow)

    out = np.full(n, np.nan)
    for i in range(n):
        if not np.isnan(fast_ema[i]) and not np.isnan(slow_ema[i]):
            out[i] = fast_ema[i] - slow_ema[i]
    return out


# ============================================================
# 加密專用指標
# ============================================================

def compute_taker_buy_sell_ratio(trades: list[dict]) -> dict:
    """
    從 trade 列表計算 Taker Buy/Sell Ratio。
    trades: [{"price", "qty", "is_buyer_maker"}, ...]
    """
    buy_vol = 0.0
    sell_vol = 0.0
    buy_count = 0
    sell_count = 0

    for t in trades:
        qty = t.get("qty", 0)
        if t.get("is_buyer_maker", False):
            sell_vol += qty
            sell_count += 1
        else:
            buy_vol += qty
            buy_count += 1

    total = buy_vol + sell_vol
    return {
        "buy_volume": round(buy_vol, 4),
        "sell_volume": round(sell_vol, 4),
        "total_volume": round(total, 4),
        "buy_ratio": round(buy_vol / total * 100, 2) if total > 0 else 50.0,
        "sell_ratio": round(sell_vol / total * 100, 2) if total > 0 else 50.0,
        "ratio": round(buy_vol / sell_vol, 4) if sell_vol > 0 else float("inf"),
        "buy_count": buy_count,
        "sell_count": sell_count,
    }


def detect_large_orders(
    trades: list[dict],
    multiplier: float = 10.0,
) -> list[dict]:
    """
    偵測大單。
    閾值 = multiplier × 平均成交量
    """
    if not trades:
        return []

    qtys = [t.get("qty", 0) for t in trades]
    avg_qty = np.mean(qtys) if qtys else 0
    threshold = avg_qty * multiplier

    large = []
    for t in trades:
        if t.get("qty", 0) >= threshold:
            large.append({
                "price": t.get("price", 0),
                "qty": t.get("qty", 0),
                "quote_qty": t.get("quote_qty", 0),
                "is_buyer_maker": t.get("is_buyer_maker", False),
                "trade_time": t.get("trade_time", 0),
                "direction": "sell" if t.get("is_buyer_maker", False) else "buy",
            })
    return large


# ============================================================
# 綜合計算接口
# ============================================================

def compute_all_crypto_indicators(
    closes: np.ndarray,
    highs: np.ndarray = None,
    lows: np.ndarray = None,
    volumes: np.ndarray = None,
    config: dict = None,
) -> dict[str, Any]:
    """
    計算所有可用的加密貨幣技術指標。

    config 參數（可選）：
    - rsi_period, macd_fast, macd_slow, macd_signal
    - bb_period, bb_std
    - ema_periods
    - atr_period, mfi_period
    - stoch_rsi_period, cci_period
    """
    cfg = config or {}
    c = np.asarray(closes, dtype=np.float64).ravel()
    result: dict[str, Any] = {}

    if len(c) < 2:
        return result

    # ── 趨勢 ──
    rsi_period = cfg.get("rsi_period", 14)
    rsi = compute_rsi(c, rsi_period)
    result["rsi"] = _latest(rsi)
    result["rsi_series"] = rsi

    macd_fast = cfg.get("macd_fast", 12)
    macd_slow = cfg.get("macd_slow", 26)
    macd_signal = cfg.get("macd_signal", 9)
    macd_line, macd_sig, macd_hist = compute_macd(c, macd_fast, macd_slow, macd_signal)
    result["macd_line"] = _latest(macd_line)
    result["macd_signal"] = _latest(macd_sig)
    result["macd_histogram"] = _latest(macd_hist)

    ema_periods = cfg.get("ema_periods", [9, 21, 55, 200])
    emas = compute_ema_multi(c, ema_periods)
    for key, arr in emas.items():
        result[key] = _latest(arr)

    # ── 波動 ──
    bb_period = cfg.get("bb_period", 20)
    bb_std = cfg.get("bb_std", 2.0)
    bb_upper, bb_middle, bb_lower = compute_bollinger_bands(c, bb_period, bb_std)
    result["bb_upper"] = _latest(bb_upper)
    result["bb_middle"] = _latest(bb_middle)
    result["bb_lower"] = _latest(bb_lower)
    result["bb_width"] = (
        round((result["bb_upper"] - result["bb_lower"]) / result["bb_middle"] * 100, 4)
        if result.get("bb_middle") and result["bb_middle"] > 0
        else None
    )

    if highs is not None and lows is not None:
        h = np.asarray(highs, dtype=np.float64).ravel()
        l = np.asarray(lows, dtype=np.float64).ravel()

        atr_period = cfg.get("atr_period", 14)
        atr = compute_atr(h, l, c, atr_period)
        result["atr"] = _latest(atr)
        result["atr_pct"] = (
            round(result["atr"] / c[-1] * 100, 4)
            if result.get("atr") and c[-1] > 0
            else None
        )

        # Supertrend
        st, st_dir = compute_supertrend(h, l, c)
        result["supertrend"] = _latest(st)
        result["supertrend_direction"] = _latest(st_dir)

        # Ichimoku
        ichi = compute_ichimoku(h, l, c)
        for key, arr in ichi.items():
            result[f"ichimoku_{key}"] = _latest(arr)

        # Keltner
        kc_upper, kc_mid, kc_lower = compute_keltner_channel(h, l, c)
        result["kc_upper"] = _latest(kc_upper)
        result["kc_middle"] = _latest(kc_mid)
        result["kc_lower"] = _latest(kc_lower)

        # Stochastic RSI
        sr_period = cfg.get("stoch_rsi_period", 14)
        stoch_k, stoch_d = compute_stoch_rsi(c, sr_period)
        result["stoch_rsi_k"] = _latest(stoch_k)
        result["stoch_rsi_d"] = _latest(stoch_d)

        # Williams %R
        result["williams_r"] = _latest(compute_williams_r(h, l, c))

        # CCI
        cci_period = cfg.get("cci_period", 20)
        result["cci"] = _latest(compute_cci(h, l, c, cci_period))

        # MFI
        if volumes is not None:
            v = np.asarray(volumes, dtype=np.float64).ravel()
            mfi_period = cfg.get("mfi_period", 14)
            result["mfi"] = _latest(compute_mfi(h, l, c, v, mfi_period))
            result["adosc"] = _latest(compute_adosc(h, l, c, v))

    # ── 量價 ──
    if volumes is not None:
        v = np.asarray(volumes, dtype=np.float64).ravel()
        result["obv"] = _latest(compute_obv(c, v))
        if highs is not None and lows is not None:
            result["vwap"] = _latest(compute_vwap(h, l, c, v))

    # ── 波動率百分位 ──
    result["volatility_percentile"] = compute_volatility_percentile(c)

    # 清理 numpy 類型
    return {k: _to_native(v) for k, v in result.items()}


# ============================================================
# 輔助函數
# ============================================================

def _sma_nan(arr: np.ndarray, period: int) -> np.ndarray:
    """帶 NaN 的簡單移動平均。"""
    n = len(arr)
    out = np.full(n, np.nan)
    for i in range(period - 1, n):
        window = arr[i - period + 1:i + 1]
        valid = window[~np.isnan(window)]
        if len(valid) > 0:
            out[i] = np.mean(valid)
    return out


def _latest(arr: np.ndarray) -> Optional[float]:
    """取數組最後一個非 NaN 值。"""
    for i in range(len(arr) - 1, -1, -1):
        v = arr[i]
        if not np.isnan(v):
            return round(float(v), 6)
    return None


def _to_native(v):
    """將 numpy 類型轉為 Python 原生類型。"""
    if isinstance(v, np.floating):
        return round(float(v), 6)
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.ndarray):
        return v  # 保留數組
    return v