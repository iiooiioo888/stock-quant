"""
加密貨幣串流管理器 — 多交易對生命周期管理、數據融合、快照緩存。

功能：
- 管理多交易對的 WebSocket 連接
- 多串流數據融合（trade 微結構 + kline 趨勢 + ticker 波動 + depth 盤口）
- 最新行情快照緩存（線程安全，供 REST API / WebSocket 推送讀取）
- 歷史 trade 滾動窗口
- K 線聚合器：從 trade 流實時聚合出 1m/5m/15m/1h K 線
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

# ── 數據結構 ──────────────────────────────────────────────────

@dataclass
class CryptoSnapshot:
    """單交易對實時快照。"""
    symbol: str
    price: float = 0.0
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    volume: float = 0.0
    quote_volume: float = 0.0
    change: float = 0.0
    change_pct: float = 0.0
    trade_count: int = 0
    best_bid: float = 0.0
    best_ask: float = 0.0
    spread: float = 0.0
    spread_pct: float = 0.0
    bid_total: float = 0.0
    ask_total: float = 0.0
    last_trade_price: float = 0.0
    last_trade_qty: float = 0.0
    last_trade_time: float = 0.0
    is_buyer_maker: bool = False
    updated_at: float = field(default_factory=time.time)

    # 交易統計（從 trade 流累積）
    buy_volume: float = 0.0
    sell_volume: float = 0.0
    buy_count: int = 0
    sell_count: int = 0
    large_orders: int = 0       # 大單筆數
    large_order_volume: float = 0.0  # 大單成交量

    def to_dict(self) -> dict:
        """轉換為 API 友好格式。"""
        return {
            "symbol": self.symbol,
            "price": round(self.price, 8),
            "open": round(self.open, 8),
            "high": round(self.high, 8),
            "low": round(self.low, 8),
            "volume": round(self.volume, 4),
            "quote_volume": round(self.quote_volume, 2),
            "change": round(self.change, 8),
            "change_pct": round(self.change_pct, 4),
            "trade_count": self.trade_count,
            "best_bid": round(self.best_bid, 8),
            "best_ask": round(self.best_ask, 8),
            "spread": round(self.spread, 8),
            "spread_pct": round(self.spread_pct, 6),
            "bid_total": round(self.bid_total, 4),
            "ask_total": round(self.ask_total, 4),
            "last_trade_price": round(self.last_trade_price, 8),
            "last_trade_qty": round(self.last_trade_qty, 8),
            "buy_volume": round(self.buy_volume, 4),
            "sell_volume": round(self.sell_volume, 4),
            "buy_count": self.buy_count,
            "sell_count": self.sell_count,
            "large_orders": self.large_orders,
            "market": "crypto",
            "source": "binance_ws",
            "updated_at": datetime.fromtimestamp(self.updated_at).isoformat(),
        }


@dataclass
class AggregatedKline:
    """聚合 K 線。"""
    symbol: str
    interval: str
    open_time: int  # 毫秒
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: float = 0.0
    quote_volume: float = 0.0
    trades_count: int = 0
    is_closed: bool = False
    last_update: float = 0.0

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "open_time": self.open_time,
            "open": round(self.open, 8),
            "high": round(self.high, 8),
            "low": round(self.low, 8),
            "close": round(self.close, 8),
            "volume": round(self.volume, 4),
            "quote_volume": round(self.quote_volume, 2),
            "trades_count": self.trades_count,
            "is_closed": self.is_closed,
            "date": datetime.fromtimestamp(self.open_time / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M"),
        }


class CryptoStreamManager:
    """
    多交易對串流管理器。

    職責：
    - 管理多交易對的實時快照
    - 從 trade 流聚合 K 線（1m/5m/15m/1h）
    - 維護歷史 trade 滾動窗口
    - 提供最新數據查詢接口
    """

    def __init__(
        self,
        trade_window_size: int = 10000,
        large_order_multiplier: float = 10.0,
    ):
        self._trade_window_size = trade_window_size
        self._large_order_multiplier = large_order_multiplier

        # 快照緩存（線程安全）
        self._snapshots: dict[str, CryptoSnapshot] = {}

        # 歷史 trade 滾動窗口（每交易對）
        self._trade_windows: dict[str, deque] = {}

        # K 線緩存（key: "symbol@interval"）
        self._kline_cache: dict[str, AggregatedKline] = {}

        # 本分鐘的 trade 統計（用於 K 線聚合）
        self._current_klines: dict[str, dict] = {}  # key: "symbol@interval"

        # 從 server 端收到的 kline 數據（非聚合，直接來自幣安 kline 串流）
        self._server_klines: dict[str, AggregatedKline] = {}

        # 統計
        self._total_trades_processed: int = 0
        self._total_klines_aggregated: int = 0

    # ── 回調處理器（供 BinanceStreamClient 註冊） ──────────────

    async def on_trade(self, data: dict):
        """處理 trade 串流數據。"""
        symbol = data.get("symbol", "")
        if not symbol:
            return

        self._total_trades_processed += 1

        # 更新快照
        snap = self._get_or_create_snapshot(symbol)
        price = data["price"]
        qty = data["qty"]
        is_buyer_maker = data.get("is_buyer_maker", False)

        snap.last_trade_price = price
        snap.last_trade_qty = qty
        snap.last_trade_time = data.get("timestamp", time.time())
        snap.is_buyer_maker = is_buyer_maker
        snap.price = price
        snap.updated_at = time.time()

        # 買賣量統計
        if is_buyer_maker:
            snap.sell_volume += qty
            snap.sell_count += 1
        else:
            snap.buy_volume += qty
            snap.buy_count += 1

        # 大單偵測（後續由 microstructure 模塊計算閾值）
        snap.trade_count += 1

        # 更新高/低
        if snap.high == 0 or price > snap.high:
            snap.high = price
        if snap.low == 0 or price < snap.low:
            snap.low = price

        # 滾動窗口
        window = self._get_or_create_trade_window(symbol)
        window.append(data)

        # 聚合 K 線
        self._aggregate_trade_to_kline(symbol, data)

    async def on_kline(self, data: dict):
        """處理 kline 串流數據（來自幣安服務器端 K 線）。"""
        symbol = data.get("symbol", "")
        interval = data.get("interval", "1m")
        key = f"{symbol}@{interval}"

        kl = AggregatedKline(
            symbol=symbol,
            interval=interval,
            open_time=data.get("open_time", 0),
            open=data["open"],
            high=data["high"],
            low=data["low"],
            close=data["close"],
            volume=data["volume"],
            quote_volume=data.get("quote_volume", 0),
            trades_count=data.get("trades_count", 0),
            is_closed=data.get("is_closed", False),
            last_update=time.time(),
        )
        self._server_klines[key] = kl

        # 同步更新快照
        snap = self._get_or_create_snapshot(symbol)
        snap.price = data["close"]
        snap.volume = data["volume"]
        snap.quote_volume = data.get("quote_volume", 0)
        snap.updated_at = time.time()
        if snap.high == 0 or data["high"] > snap.high:
            snap.high = data["high"]
        if snap.low == 0 or data["low"] < snap.low:
            snap.low = data["low"]

    async def on_ticker(self, data: dict):
        """處理 ticker 串流數據。"""
        symbol = data.get("symbol", "")
        if not symbol:
            return

        snap = self._get_or_create_snapshot(symbol)
        snap.price = data["price"]
        snap.open = data["open"]
        snap.high = data["high"]
        snap.low = data["low"]
        snap.volume = data["volume"]
        snap.quote_volume = data.get("quote_volume", 0)
        snap.change = data["change"]
        snap.change_pct = data["change_pct"]
        snap.trade_count = data.get("trade_count", 0)
        snap.updated_at = time.time()

    async def on_depth(self, data: dict):
        """處理 depth 串流數據。"""
        symbol = data.get("symbol", "")
        if not symbol:
            return

        snap = self._get_or_create_snapshot(symbol)
        snap.best_bid = data["best_bid"]
        snap.best_ask = data["best_ask"]
        snap.spread = data["spread"]
        snap.spread_pct = data["spread_pct"]
        snap.bid_total = data["bid_total"]
        snap.ask_total = data["ask_total"]
        snap.updated_at = time.time()

    # ── 查詢接口 ──────────────────────────────────────────────

    def get_snapshot(self, symbol: str) -> Optional[dict]:
        """獲取單交易對快照。"""
        snap = self._snapshots.get(symbol.upper())
        return snap.to_dict() if snap else None

    def get_all_snapshots(self) -> list[dict]:
        """獲取所有交易對快照。"""
        return [snap.to_dict() for snap in self._snapshots.values()]

    def get_snapshot_symbols(self) -> list[str]:
        """返回已有快照的交易對列表。"""
        return list(self._snapshots.keys())

    def get_kline(self, symbol: str, interval: str = "1m") -> Optional[dict]:
        """獲取 K 線（優先 server 端，回退本地聚合）。"""
        key = f"{symbol.upper()}@{interval}"
        # 優先 server 端 kline
        kl = self._server_klines.get(key)
        if kl:
            return kl.to_dict()
        # 回退本地聚合
        kl = self._kline_cache.get(key)
        return kl.to_dict() if kl else None

    def get_recent_trades(self, symbol: str, limit: int = 100) -> list[dict]:
        """獲取最近 N 筆交易。"""
        window = self._trade_windows.get(symbol.upper(), deque())
        items = list(window)[-limit:]
        return items

    def get_trade_stats(self, symbol: str) -> dict:
        """獲取交易統計。"""
        snap = self._snapshots.get(symbol.upper())
        if not snap:
            return {}

        total = snap.buy_volume + snap.sell_volume
        return {
            "symbol": snap.symbol,
            "buy_volume": round(snap.buy_volume, 4),
            "sell_volume": round(snap.sell_volume, 4),
            "total_volume": round(total, 4),
            "buy_ratio": round(snap.buy_volume / total * 100, 2) if total > 0 else 0,
            "sell_ratio": round(snap.sell_volume / total * 100, 2) if total > 0 else 0,
            "net_volume": round(snap.buy_volume - snap.sell_volume, 4),
            "buy_count": snap.buy_count,
            "sell_count": snap.sell_count,
            "total_trades": snap.buy_count + snap.sell_count,
            "large_orders": snap.large_orders,
            "large_order_volume": round(snap.large_order_volume, 4),
        }

    def get_manager_stats(self) -> dict:
        """返回管理器統計。"""
        return {
            "symbols_tracked": len(self._snapshots),
            "total_trades_processed": self._total_trades_processed,
            "total_klines_aggregated": self._total_klines_aggregated,
            "server_klines_count": len(self._server_klines),
            "aggregated_klines_count": len(self._kline_cache),
            "trade_window_symbols": len(self._trade_windows),
        }

    # ── 內部方法 ──────────────────────────────────────────────

    def _get_or_create_snapshot(self, symbol: str) -> CryptoSnapshot:
        """獲取或創建快照。"""
        symbol = symbol.upper()
        if symbol not in self._snapshots:
            self._snapshots[symbol] = CryptoSnapshot(symbol=symbol)
        return self._snapshots[symbol]

    def _get_or_create_trade_window(self, symbol: str) -> deque:
        """獲取或創建交易窗口。"""
        symbol = symbol.upper()
        if symbol not in self._trade_windows:
            self._trade_windows[symbol] = deque(maxlen=self._trade_window_size)
        return self._trade_windows[symbol]

    def _aggregate_trade_to_kline(self, symbol: str, trade: dict):
        """從 trade 數據聚合 K 線。"""
        now_ms = int(trade.get("timestamp", time.time()) * 1000)
        price = trade["price"]
        qty = trade["qty"]

        for interval, window_ms in _INTERVAL_MS.items():
            key = f"{symbol}@{interval}"
            bucket_start = (now_ms // window_ms) * window_ms

            current = self._current_klines.get(key)
            if current is None or current["open_time"] != bucket_start:
                # 關閉上一根 K 線
                if current is not None:
                    kl = AggregatedKline(
                        symbol=symbol,
                        interval=interval,
                        open_time=current["open_time"],
                        open=current["open"],
                        high=current["high"],
                        low=current["low"],
                        close=current["close"],
                        volume=current["volume"],
                        quote_volume=current["quote_volume"],
                        trades_count=current["trades_count"],
                        is_closed=True,
                        last_update=time.time(),
                    )
                    cache_key = f"{symbol}@{interval}"
                    self._kline_cache[cache_key] = kl
                    self._total_klines_aggregated += 1

                # 開始新 K 線
                self._current_klines[key] = {
                    "open_time": bucket_start,
                    "open": price,
                    "high": price,
                    "low": price,
                    "close": price,
                    "volume": qty,
                    "quote_volume": price * qty,
                    "trades_count": 1,
                }
            else:
                # 更新當前 K 線
                current["high"] = max(current["high"], price)
                current["low"] = min(current["low"], price)
                current["close"] = price
                current["volume"] += qty
                current["quote_volume"] += price * qty
                current["trades_count"] += 1

    def reset(self):
        """重置所有數據。"""
        self._snapshots.clear()
        self._trade_windows.clear()
        self._kline_cache.clear()
        self._current_klines.clear()
        self._server_klines.clear()
        self._total_trades_processed = 0
        self._total_klines_aggregated = 0


# ── K 線週期映射 ──────────────────────────────────────────────

_INTERVAL_MS = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}
