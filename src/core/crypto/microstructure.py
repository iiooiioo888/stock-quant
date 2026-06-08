"""
加密貨幣市場微結構分析。

從 trade 流和 depth 流分析：
- 成交流分析：買賣壓力比、大單偵測、淨流入/流出、成交密度
- 盤口分析：Spread、深度不平衡、支撐/阻力偵測
- 波動率分析：實現波動率（多週期）、波動率百分位
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np


class CryptoMicrostructureAnalyzer:
    """
    市場微結構分析器。

    從 StreamManager 的 trade 窗口和 depth 快照計算深度市場洞察。
    """

    def __init__(
        self,
        large_order_multiplier: float = 10.0,
        large_order_usd: float = 100_000.0,
        depth_levels: int = 20,
    ):
        self._large_order_mult = large_order_multiplier
        self._large_order_usd = large_order_usd
        self._depth_levels = depth_levels

        # 緩存上次分析結果（避免重複計算）
        self._cache: dict[str, dict] = {}
        self._cache_ts: dict[str, float] = {}
        self._cache_ttl: float = 1.0  # 1 秒緩存

    # ============================================================
    # 成交流分析
    # ============================================================

    def analyze_trades(self, trades: list[dict]) -> dict[str, Any]:
        """
        從 trade 列表分析微結構。

        trades: [{"price", "qty", "is_buyer_maker", "quote_qty", "trade_time"}, ...]
        """
        if not trades:
            return self._empty_analysis()

        n = len(trades)
        prices = np.array([t["price"] for t in trades], dtype=np.float64)
        qtys = np.array([t["qty"] for t in trades], dtype=np.float64)
        quote_qtys = np.array(
            [t.get("quote_qty", p * q) for t, p, q in zip(trades, prices, qtys)],
            dtype=np.float64,
        )

        # ── 買賣壓力 ──
        buy_mask = np.array([not t.get("is_buyer_maker", False) for t in trades])
        sell_mask = ~buy_mask

        buy_vol = float(np.sum(qtys[buy_mask])) if buy_mask.any() else 0.0
        sell_vol = float(np.sum(qtys[sell_mask])) if sell_mask.any() else 0.0
        total_vol = buy_vol + sell_vol

        buy_quote = float(np.sum(quote_qtys[buy_mask])) if buy_mask.any() else 0.0
        sell_quote = float(np.sum(quote_qtys[sell_mask])) if sell_mask.any() else 0.0
        buy_quote + sell_quote

        buy_count = int(np.sum(buy_mask))
        sell_count = int(np.sum(sell_mask))

        # ── 大單偵測 ──
        avg_qty = float(np.mean(qtys)) if n > 0 else 0.0
        qty_threshold = avg_qty * self._large_order_mult
        usd_threshold = self._large_order_usd

        large_mask = (qtys >= qty_threshold) | (quote_qtys >= usd_threshold)
        large_trades = [trades[i] for i in range(n) if large_mask[i]]
        large_buy_vol = (
            float(np.sum(qtys[large_mask & buy_mask]))
            if (large_mask & buy_mask).any()
            else 0.0
        )
        large_sell_vol = (
            float(np.sum(qtys[large_mask & sell_mask]))
            if (large_mask & sell_mask).any()
            else 0.0
        )

        # ── 淨流入/流出 ──
        net_volume = buy_vol - sell_vol
        net_quote = buy_quote - sell_quote
        net_direction = (
            "inflow" if net_volume > 0 else "outflow" if net_volume < 0 else "neutral"
        )

        # ── 成交密度（每分鐘筆數） ──
        trade_density = self._compute_trade_density(trades)

        # ── 價格衝擊 ──
        vwap_buy = buy_quote / buy_vol if buy_vol > 0 else 0.0
        vwap_sell = sell_quote / sell_vol if sell_vol > 0 else 0.0
        price_impact = (
            abs(vwap_buy - vwap_sell) / ((vwap_buy + vwap_sell) / 2) * 100
            if (vwap_buy + vwap_sell) > 0
            else 0.0
        )

        return {
            "timestamp": time.time(),
            "trade_count": n,
            "buy_sell_pressure": {
                "buy_volume": round(buy_vol, 4),
                "sell_volume": round(sell_vol, 4),
                "total_volume": round(total_vol, 4),
                "buy_ratio": (
                    round(buy_vol / total_vol * 100, 2) if total_vol > 0 else 50.0
                ),
                "sell_ratio": (
                    round(sell_vol / total_vol * 100, 2) if total_vol > 0 else 50.0
                ),
                "buy_quote": round(buy_quote, 2),
                "sell_quote": round(sell_quote, 2),
                "buy_count": buy_count,
                "sell_count": sell_count,
            },
            "net_flow": {
                "net_volume": round(net_volume, 4),
                "net_quote": round(net_quote, 2),
                "direction": net_direction,
                "strength": (
                    round(abs(net_volume) / total_vol * 100, 2)
                    if total_vol > 0
                    else 0.0
                ),
            },
            "large_orders": {
                "count": len(large_trades),
                "buy_volume": round(large_buy_vol, 4),
                "sell_volume": round(large_sell_vol, 4),
                "total_volume": round(large_buy_vol + large_sell_vol, 4),
                "pct_of_total": (
                    round((large_buy_vol + large_sell_vol) / total_vol * 100, 2)
                    if total_vol > 0
                    else 0.0
                ),
                "threshold_qty": round(qty_threshold, 4),
                "threshold_usd": usd_threshold,
                "recent": [
                    {
                        "price": round(t["price"], 8),
                        "qty": round(t["qty"], 4),
                        "usd": round(t.get("quote_qty", t["price"] * t["qty"]), 2),
                        "direction": (
                            "sell" if t.get("is_buyer_maker", False) else "buy"
                        ),
                        "time": t.get("trade_time", 0),
                    }
                    for t in large_trades[-10:]  # 最近 10 筆大單
                ],
            },
            "trade_density": trade_density,
            "price_impact": {
                "vwap_buy": round(vwap_buy, 8),
                "vwap_sell": round(vwap_sell, 8),
                "impact_pct": round(price_impact, 4),
            },
        }

    # ============================================================
    # 盤口分析
    # ============================================================

    def analyze_depth(self, depth_data: dict) -> dict[str, Any]:
        """
        從 depth 數據分析盤口。

        depth_data: {"bids": [[price, qty], ...], "asks": [[price, qty], ...], ...}
        """
        bids = depth_data.get("bids", [])
        asks = depth_data.get("asks", [])

        if not bids or not asks:
            return {"error": "depth data unavailable"}

        bid_prices = np.array(
            [b[0] for b in bids[: self._depth_levels]], dtype=np.float64
        )
        bid_qtys = np.array(
            [b[1] for b in bids[: self._depth_levels]], dtype=np.float64
        )
        ask_prices = np.array(
            [a[0] for a in asks[: self._depth_levels]], dtype=np.float64
        )
        ask_qtys = np.array(
            [a[1] for a in asks[: self._depth_levels]], dtype=np.float64
        )

        # ── Spread ──
        best_bid = float(bid_prices[0])
        best_ask = float(ask_prices[0])
        spread = best_ask - best_bid
        spread_pct = spread / best_bid * 100 if best_bid > 0 else 0.0
        mid_price = (best_bid + best_ask) / 2.0

        # ── 深度不平衡 ──
        bid_total = float(np.sum(bid_qtys))
        ask_total = float(np.sum(ask_qtys))
        depth_imbalance = (
            (bid_total - ask_total) / (bid_total + ask_total)
            if (bid_total + ask_total) > 0
            else 0.0
        )

        # ── 各層深度 ──
        levels = min(self._depth_levels, len(bids), len(asks))
        level_data = []
        for i in range(levels):
            level_data.append(
                {
                    "level": i + 1,
                    "bid_price": round(float(bid_prices[i]), 8),
                    "bid_qty": round(float(bid_qtys[i]), 4),
                    "ask_price": round(float(ask_prices[i]), 8),
                    "ask_qty": round(float(ask_qtys[i]), 4),
                    "imbalance": round(
                        (
                            (float(bid_qtys[i]) - float(ask_qtys[i]))
                            / (float(bid_qtys[i]) + float(ask_qtys[i]))
                            if (float(bid_qtys[i]) + float(ask_qtys[i])) > 0
                            else 0.0
                        ),
                        4,
                    ),
                }
            )

        # ── 支撐/阻力偵測（大額掛單聚集） ──
        support_levels = self._detect_cluster_levels(bid_prices, bid_qtys, "support")
        resistance_levels = self._detect_cluster_levels(
            ask_prices, ask_qtys, "resistance"
        )

        # ── 撤單壓力估算（掛單量 vs 成交密度） ──
        wall_bid = float(np.max(bid_qtys)) if len(bid_qtys) > 0 else 0.0
        wall_ask = float(np.max(ask_qtys)) if len(ask_qtys) > 0 else 0.0

        return {
            "timestamp": time.time(),
            "best_bid": round(best_bid, 8),
            "best_ask": round(best_ask, 8),
            "mid_price": round(mid_price, 8),
            "spread": round(spread, 8),
            "spread_pct": round(spread_pct, 6),
            "bid_depth_total": round(bid_total, 4),
            "ask_depth_total": round(ask_total, 4),
            "depth_imbalance": round(depth_imbalance, 4),  # +1=全買, -1=全賣, 0=平衡
            "imbalance_signal": (
                "strong_buy"
                if depth_imbalance > 0.5
                else (
                    "buy"
                    if depth_imbalance > 0.2
                    else (
                        "strong_sell"
                        if depth_imbalance < -0.5
                        else "sell" if depth_imbalance < -0.2 else "neutral"
                    )
                )
            ),
            "bid_wall": round(wall_bid, 4),
            "ask_wall": round(wall_ask, 4),
            "support_levels": support_levels,
            "resistance_levels": resistance_levels,
            "levels": level_data,
        }

    # ============================================================
    # 波動率分析
    # ============================================================

    def analyze_volatility(
        self, trades: list[dict], windows: list[int] = None
    ) -> dict[str, Any]:
        """
        從 trade 序列計算實現波動率（多週期）。

        windows: 分鐘窗口列表，如 [5, 15, 60]
        """
        windows = windows or [5, 15, 60]

        if len(trades) < 10:
            return {"error": "insufficient trades"}

        prices = np.array([t["price"] for t in trades], dtype=np.float64)
        np.array([t.get("timestamp", 0) for t in trades], dtype=np.float64)

        result: dict[str, Any] = {"timestamp": time.time()}

        # 對數收益率
        log_returns = np.diff(np.log(prices))
        if len(log_returns) < 2:
            return {"error": "insufficient returns"}

        # 整體實現波動率（年化）
        overall_vol = float(np.std(log_returns) * np.sqrt(252 * 24 * 60))  # 分鐘級年化
        result["realized_vol_annualized"] = round(overall_vol * 100, 4)

        # 各窗口波動率
        window_vols = {}
        total_len = len(log_returns)
        for w in windows:
            if total_len >= w:
                recent = log_returns[-w:]
                vol = float(np.std(recent) * np.sqrt(252 * 24 * 60))
                window_vols[f"{w}_trades"] = round(vol * 100, 4)
        result["window_volatility"] = window_vols

        # 波動率聚類偵測
        if total_len >= 60:
            recent_20 = np.std(log_returns[-20:])
            prev_20 = np.std(log_returns[-40:-20])
            vol_ratio = recent_20 / prev_20 if prev_20 > 0 else 1.0
            result["vol_clustering"] = {
                "recent_vol": round(float(recent_20) * 100, 4),
                "prev_vol": round(float(prev_20) * 100, 4),
                "ratio": round(float(vol_ratio), 4),
                "signal": (
                    "expanding"
                    if vol_ratio > 1.5
                    else "contracting" if vol_ratio < 0.67 else "stable"
                ),
            }

        # 最大價格變動
        max_move = float(np.max(np.abs(log_returns)))
        max_move_pct = (np.exp(max_move) - 1) * 100
        result["max_single_move_pct"] = round(max_move_pct, 4)

        return result

    # ============================================================
    # 綜合分析
    # ============================================================

    def full_analysis(
        self,
        symbol: str,
        trades: list[dict],
        depth_data: dict = None,
    ) -> dict[str, Any]:
        """
        完整微結構分析。

        symbol: 交易對
        trades: 最近的 trade 列表
        depth_data: depth 串流數據（可選）
        """
        # 緩存檢查
        now = time.time()
        cache_key = symbol.upper()
        if (
            cache_key in self._cache
            and now - self._cache_ts.get(cache_key, 0) < self._cache_ttl
        ):
            return self._cache[cache_key]

        result = {
            "symbol": symbol.upper(),
            "timestamp": now,
            "trade_analysis": self.analyze_trades(trades),
            "volatility_analysis": self.analyze_volatility(trades),
        }

        if depth_data:
            result["depth_analysis"] = self.analyze_depth(depth_data)

        # 更新緩存
        self._cache[cache_key] = result
        self._cache_ts[cache_key] = now

        return result

    # ============================================================
    # 內部方法
    # ============================================================

    def _compute_trade_density(self, trades: list[dict]) -> dict:
        """計算成交密度。"""
        if len(trades) < 2:
            return {"trades_per_minute": 0, "trend": "unknown"}

        times = [t.get("timestamp", 0) for t in trades]
        if times[-1] - times[0] <= 0:
            return {"trades_per_minute": 0, "trend": "unknown"}

        duration_min = (times[-1] - times[0]) / 60.0
        tpm = len(trades) / duration_min if duration_min > 0 else 0

        # 前半 vs 後半密度趨勢
        mid = len(trades) // 2
        if mid > 0:
            first_half_dur = (
                (times[mid] - times[0]) / 60.0 if times[mid] > times[0] else 1.0
            )
            second_half_dur = (
                (times[-1] - times[mid]) / 60.0 if times[-1] > times[mid] else 1.0
            )
            first_tpm = mid / first_half_dur
            second_tpm = (len(trades) - mid) / second_half_dur
            trend = (
                "accelerating"
                if second_tpm > first_tpm * 1.2
                else "decelerating" if second_tpm < first_tpm * 0.8 else "stable"
            )
        else:
            trend = "unknown"

        return {
            "trades_per_minute": round(tpm, 2),
            "trend": trend,
            "total_trades": len(trades),
            "duration_seconds": round(times[-1] - times[0], 1),
        }

    def _detect_cluster_levels(
        self,
        prices: np.ndarray,
        qtys: np.ndarray,
        level_type: str,
    ) -> list[dict]:
        """偵測大額掛單聚集價格。"""
        if len(prices) == 0:
            return []

        avg_qty = float(np.mean(qtys))
        threshold = avg_qty * 2.5  # 2.5 倍平均

        clusters = []
        for i in range(len(qtys)):
            if float(qtys[i]) >= threshold:
                clusters.append(
                    {
                        "price": round(float(prices[i]), 8),
                        "qty": round(float(qtys[i]), 4),
                        "type": level_type,
                        "strength": round(float(qtys[i]) / avg_qty, 2),
                    }
                )

        return sorted(clusters, key=lambda x: x["qty"], reverse=True)[:5]

    def _empty_analysis(self) -> dict:
        """空分析結果。"""
        return {
            "timestamp": time.time(),
            "trade_count": 0,
            "buy_sell_pressure": {
                "buy_volume": 0,
                "sell_volume": 0,
                "total_volume": 0,
                "buy_ratio": 50.0,
                "sell_ratio": 50.0,
                "buy_quote": 0,
                "sell_quote": 0,
                "buy_count": 0,
                "sell_count": 0,
            },
            "net_flow": {
                "net_volume": 0,
                "net_quote": 0,
                "direction": "neutral",
                "strength": 0.0,
            },
            "large_orders": {"count": 0, "recent": []},
            "trade_density": {"trades_per_minute": 0, "trend": "unknown"},
        }
