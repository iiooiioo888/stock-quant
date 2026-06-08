"""
Backtrader 回測執行期工具 — 記憶體釋放、滑點模型
"""

from __future__ import annotations

import gc
from typing import Any


def dispose_cerebro(cerebro: Any = None, results: Any = None) -> None:
    """
    回測結束後釋放 Cerebro / 結果引用，降低網格搜索與 Walk-Forward 的記憶體累積。
    """
    try:
        if results is not None:
            try:
                if hasattr(results, "clear"):
                    results.clear()
            except Exception:
                pass
        if cerebro is not None:
            for attr in ("datas", "strats", "runstrats", "optcbs", "optstrats"):
                coll = getattr(cerebro, attr, None)
                if coll is not None and hasattr(coll, "clear"):
                    try:
                        coll.clear()
                    except Exception:
                        pass
            try:
                del cerebro
            except Exception:
                pass
    finally:
        gc.collect()


def compute_volume_impact_slippage_pct(
    base_slippage_pct: float,
    order_shares: float,
    bar_volume: float,
    *,
    participation_cap: float = 0.05,
    impact_exponent: float = 2.0,
) -> float:
    """
    依訂單量佔 K 線成交量比例放大滑點（衝擊成本近似）。

    當訂單量 <= participation_cap * bar_volume 時維持 base；
    超過後按 (participation / cap) ** exponent 放大。
    """
    base = max(float(base_slippage_pct or 0), 0.0)
    if base <= 0 or order_shares <= 0 or bar_volume <= 0:
        return base
    participation = order_shares / bar_volume
    if participation <= participation_cap:
        return base
    ratio = participation / participation_cap
    return base * (ratio**impact_exponent)


def trim_ohlcv_dataframe(df):
    """餵給 Backtrader 前僅保留 OHLCV 數值欄，減少 object 欄位佔用。"""
    import pandas as pd

    if df is None or getattr(df, "empty", True):
        return df
    col_map = {}
    for c in df.columns:
        cl = str(c).lower()
        if cl in ("open", "high", "low", "close", "volume"):
            col_map[c] = cl.capitalize() if cl != "volume" else "Volume"
    if not col_map:
        return df
    out = df[list(col_map.keys())].copy()
    out.columns = [col_map[c] for c in out.columns]
    for c in out.columns:
        if c != "Volume":
            out[c] = pd.to_numeric(out[c], errors="coerce")
        else:
            out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0).astype("float64")
    return out.dropna(subset=["Close"])
