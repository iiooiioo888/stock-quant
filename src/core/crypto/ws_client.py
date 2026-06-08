"""
幣安 WebSocket Streams 客戶端 — 異步、自動重連、數據驗證。

支持串流：trade / kline_* / ticker / depth@100ms
無需 API Key（公開市場數據）。

符合幣安規範：
- ping/pong 心跳（每 20 秒 ping，1 分鐘內需回覆 pong）
- 24 小時強制斷線前監聽 serverShutdown 事件
- 每 IP 每 5 分鐘最多 300 次連接
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Optional

from src.utils.logger import logger

# ── 常量 ──────────────────────────────────────────────────────

BINANCE_WS_BASE = "wss://stream.binance.com:9443/ws"
BINANCE_WS_COMBINED = "wss://stream.binance.com:9443/stream?streams="

# 默認配置（可被 settings 覆蓋）
DEFAULT_RECONNECT_BASE_SEC = 5
DEFAULT_RECONNECT_MAX_SEC = 60
DEFAULT_PING_INTERVAL_SEC = 20
DEFAULT_CONNECT_TIMEOUT_SEC = 10
DEFAULT_MESSAGE_TIMEOUT_SEC = 65  # 幣安 1 分鐘無 pong 斷線

# 數據驗證常量
MAX_TIMESTAMP_DRIFT_MS = 5000  # ±5 秒


# ── 回調類型 ──────────────────────────────────────────────────

TradeCallback = Callable[[dict], Coroutine[Any, Any, None]]
KlineCallback = Callable[[dict], Coroutine[Any, Any, None]]
TickerCallback = Callable[[dict], Coroutine[Any, Any, None]]
DepthCallback = Callable[[dict], Coroutine[Any, Any, None]]
ErrorCallback = Callable[[str, Exception], Coroutine[Any, Any, None]]


@dataclass
class StreamConfig:
    """單個串流的訂閱配置。"""

    symbol: str  # 如 "BTCUSDT"
    stream_types: list[str] = field(default_factory=lambda: ["trade", "ticker"])
    kline_intervals: list[str] = field(default_factory=lambda: ["1m"])


@dataclass
class WSClientStats:
    """連接統計。"""

    total_connections: int = 0
    total_reconnects: int = 0
    total_messages: int = 0
    total_errors: int = 0
    total_validated: int = 0
    total_rejected: int = 0
    last_message_ts: float = 0.0
    connected_at: float = 0.0
    disconnected_at: float = 0.0
    state: str = "idle"  # idle / connecting / connected / reconnecting / stopped


class BinanceStreamClient:
    """
    幣安 WebSocket Streams 異步客戶端。

    特性：
    - 多串流訂閱：trade / kline_* / ticker / depth@100ms
    - 自動重連：指數退避（5s → 10s → 30s → 60s，可配置）
    - 心跳處理：幣安每 20s ping，自動回覆 pong
    - 24h 強制斷線前監聽 serverShutdown 事件
    - 數據驗證：時間戳 / 價格 / 必要字段
    - 限流保護：連接間隔控制
    - 異步回調分發
    """

    def __init__(
        self,
        reconnect_base_sec: int = DEFAULT_RECONNECT_BASE_SEC,
        reconnect_max_sec: int = DEFAULT_RECONNECT_MAX_SEC,
        ping_interval_sec: int = DEFAULT_PING_INTERVAL_SEC,
        connect_timeout_sec: int = DEFAULT_CONNECT_TIMEOUT_SEC,
        message_timeout_sec: int = DEFAULT_MESSAGE_TIMEOUT_SEC,
    ):
        self._reconnect_base = reconnect_base_sec
        self._reconnect_max = reconnect_max_sec
        self._ping_interval = ping_interval_sec
        self._connect_timeout = connect_timeout_sec
        self._msg_timeout = message_timeout_sec

        # 訂閱管理
        self._subscriptions: list[str] = []  # stream names
        self._stream_configs: dict[str, StreamConfig] = {}

        # 回調
        self._on_trade: Optional[TradeCallback] = None
        self._on_kline: Optional[KlineCallback] = None
        self._on_ticker: Optional[TickerCallback] = None
        self._on_depth: Optional[DepthCallback] = None
        self._on_error: Optional[ErrorCallback] = None

        # 狀態
        self.stats = WSClientStats()
        self._ws = None
        self._running = False
        self._reconnect_attempts = 0
        self._task: Optional[asyncio.Task] = None
        self._last_connect_time: float = 0.0

    # ── 回調註冊 ──────────────────────────────────────────────

    def on_trade(self, cb: TradeCallback):
        self._on_trade = cb
        return self

    def on_kline(self, cb: KlineCallback):
        self._on_kline = cb
        return self

    def on_ticker(self, cb: TickerCallback):
        self._on_ticker = cb
        return self

    def on_depth(self, cb: DepthCallback):
        self._on_depth = cb
        return self

    def on_error(self, cb: ErrorCallback):
        self._on_error = cb
        return self

    # ── 訂閱管理 ──────────────────────────────────────────────

    def add_subscription(
        self,
        symbol: str,
        stream_types: list[str] = None,
        kline_intervals: list[str] = None,
    ) -> list[str]:
        """
        添加訂閱。返回新增的 stream names。

        stream_types: ["trade", "ticker", "depth"] 等
        kline_intervals: ["1m", "5m", "15m", "1h"] 等（僅 stream_types 含 "kline" 時生效）
        """
        symbol = symbol.lower()
        types = stream_types or ["trade", "ticker"]
        intervals = kline_intervals or ["1m"]
        new_streams = []

        for st in types:
            if st == "kline":
                for interval in intervals:
                    name = f"{symbol}@kline_{interval}"
                    if name not in self._subscriptions:
                        self._subscriptions.append(name)
                        new_streams.append(name)
            elif st == "depth":
                name = f"{symbol}@depth@100ms"
                if name not in self._subscriptions:
                    self._subscriptions.append(name)
                    new_streams.append(name)
            else:
                name = f"{symbol}@{st}"
                if name not in self._subscriptions:
                    self._subscriptions.append(name)
                    new_streams.append(name)

        self._stream_configs[symbol] = StreamConfig(
            symbol=symbol.upper(),
            stream_types=types,
            kline_intervals=intervals,
        )
        return new_streams

    def remove_subscription(self, symbol: str) -> list[str]:
        """移除某交易對的所有訂閱。返回被移除的 stream names。"""
        symbol = symbol.lower()
        removed = [s for s in self._subscriptions if s.startswith(f"{symbol}@")]
        self._subscriptions = [
            s for s in self._subscriptions if not s.startswith(f"{symbol}@")
        ]
        self._stream_configs.pop(symbol, None)
        return removed

    @property
    def subscriptions(self) -> list[str]:
        return list(self._subscriptions)

    # ── 連接控制 ──────────────────────────────────────────────

    async def connect(self):
        """啟動 WebSocket 連接（後台任務）。"""
        if self._running:
            logger.warning("[BinanceWS] 已在運行中")
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("[BinanceWS] 啟動連接循環")

    async def disconnect(self):
        """停止連接。"""
        self._running = False
        self.stats.state = "stopped"
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        logger.info("[BinanceWS] 已停止")

    # ── 主循環 ────────────────────────────────────────────────

    async def _run_loop(self):
        """主循環：連接 → 接收 → 斷線 → 重連。"""
        while self._running:
            try:
                await self._connect_and_listen()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.stats.total_errors += 1
                logger.error(f"[BinanceWS] 連接異常: {e}")
                if self._on_error:
                    try:
                        await self._on_error("connection_error", e)
                    except Exception:
                        pass

            if not self._running:
                break

            # 重連邏輯
            self.stats.state = "reconnecting"
            self.stats.total_reconnects += 1
            self._reconnect_attempts += 1
            delay = min(
                self._reconnect_base * (2 ** (self._reconnect_attempts - 1)),
                self._reconnect_max,
            )
            logger.info(
                f"[BinanceWS] {delay}s 後重連（第 {self._reconnect_attempts} 次）"
            )
            await asyncio.sleep(delay)

    async def _connect_and_listen(self):
        """單次連接生命週期。"""
        if not self._subscriptions:
            logger.warning("[BinanceWS] 無訂閱，等待中...")
            await asyncio.sleep(5)
            return

        # 限流保護：距上次連接至少 1 秒
        now = time.time()
        elapsed = now - self._last_connect_time
        if elapsed < 1.0:
            await asyncio.sleep(1.0 - elapsed)

        # 構建 URL
        if len(self._subscriptions) == 1:
            url = f"{BINANCE_WS_BASE}/{self._subscriptions[0]}"
        else:
            streams = "/".join(self._subscriptions)
            url = f"{BINANCE_WS_COMBINED}{streams}"

        self.stats.state = "connecting"
        self.stats.total_connections += 1
        self._last_connect_time = time.time()

        logger.info(f"[BinanceWS] 連接中... ({len(self._subscriptions)} 個串流)")
        logger.debug(f"[BinanceWS] URL: {url[:120]}...")

        try:
            import websockets
        except ImportError:
            logger.error("[BinanceWS] websockets 庫未安裝，請 pip install websockets")
            raise

        async with websockets.connect(
            url,
            ping_interval=None,  # 幣安自帶 ping
            close_timeout=5,
            open_timeout=self._connect_timeout,
        ) as ws:
            self._ws = ws
            self.stats.state = "connected"
            self.stats.connected_at = time.time()
            self._reconnect_attempts = 0
            logger.info(f"[BinanceWS] 已連接（{len(self._subscriptions)} 個串流）")

            async for raw_msg in ws:
                if not self._running:
                    break

                self.stats.total_messages += 1
                self.stats.last_message_ts = time.time()

                try:
                    await self._handle_message(raw_msg)
                except Exception as e:
                    self.stats.total_errors += 1
                    logger.debug(f"[BinanceWS] 消息處理異常: {e}")
                    if self._on_error:
                        try:
                            await self._on_error("message_error", e)
                        except Exception:
                            pass

            logger.info("[BinanceWS] 連接已關閉")

    # ── 消息處理 ──────────────────────────────────────────────

    async def _handle_message(self, raw: str):
        """解析並分發消息。"""
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return

        # 組合流格式：{"stream": "btcusdt@trade", "data": {...}}
        if "stream" in msg and "data" in msg:
            msg["stream"]
            data = msg["data"]
        elif "e" in msg:
            # 單流格式
            data = msg
        else:
            # 可能是 pong 或其他控制消息
            return

        event_type = data.get("e", "")

        # serverShutdown 事件（24h 斷線前通知）
        if event_type == "serverShutdown":
            logger.warning("[BinanceWS] 收到 serverShutdown 事件，準備重連")
            if self._ws:
                await self._ws.close()
            return

        # 數據驗證
        if not self._validate_message(data):
            self.stats.total_rejected += 1
            return
        self.stats.total_validated += 1

        # 分發到對應回調
        if event_type == "trade":
            parsed = self._parse_trade(data)
            if self._on_trade and parsed:
                await self._on_trade(parsed)

        elif event_type == "kline":
            parsed = self._parse_kline(data)
            if self._on_kline and parsed:
                await self._on_kline(parsed)

        elif event_type == "24hrTicker":
            parsed = self._parse_ticker(data)
            if self._on_ticker and parsed:
                await self._on_ticker(parsed)

        elif event_type == "depthUpdate":
            parsed = self._parse_depth(data)
            if self._on_depth and parsed:
                await self._on_depth(parsed)

    # ── 數據驗證 ──────────────────────────────────────────────

    def _validate_message(self, data: dict) -> bool:
        """驗證消息完整性。"""
        event_type = data.get("e", "")
        event_time = data.get("E", 0)

        # 時間戳校驗（±5 秒）
        if event_time:
            now_ms = int(time.time() * 1000)
            if abs(now_ms - event_time) > MAX_TIMESTAMP_DRIFT_MS:
                return False

        # 事件特定驗證
        if event_type == "trade":
            price = float(data.get("p", 0))
            qty = float(data.get("q", 0))
            if price <= 0 or qty < 0:
                return False
            required = {"e", "E", "s", "p", "q", "T"}
            if not required.issubset(data.keys()):
                return False

        elif event_type == "kline":
            k = data.get("k", {})
            if not k:
                return False
            if float(k.get("c", 0)) <= 0:
                return False

        elif event_type == "24hrTicker":
            price = float(data.get("c", 0))  # close price
            if price <= 0:
                return False

        return True

    # ── 數據解析 ──────────────────────────────────────────────

    def _parse_trade(self, data: dict) -> Optional[dict]:
        """解析 trade 串流。"""
        try:
            return {
                "event": "trade",
                "symbol": data["s"],
                "price": float(data["p"]),
                "qty": float(data["q"]),
                "quote_qty": float(data["p"]) * float(data["q"]),
                "trade_time": data["T"],  # 毫秒時間戳
                "is_buyer_maker": data.get("m", False),
                "trade_id": data.get("t", 0),
                "event_time": data.get("E", 0),
                "timestamp": time.time(),
            }
        except (KeyError, ValueError) as e:
            logger.debug(f"[BinanceWS] trade 解析失敗: {e}")
            return None

    def _parse_kline(self, data: dict) -> Optional[dict]:
        """解析 kline 串流。"""
        try:
            k = data["k"]
            return {
                "event": "kline",
                "symbol": data["s"],
                "interval": k["i"],
                "open_time": k["t"],
                "close_time": k["T"],
                "open": float(k["o"]),
                "high": float(k["h"]),
                "low": float(k["l"]),
                "close": float(k["c"]),
                "volume": float(k["v"]),
                "quote_volume": float(k["q"]),
                "trades_count": k["n"],
                "is_closed": k["x"],  # K 線是否已收盤
                "event_time": data.get("E", 0),
                "timestamp": time.time(),
            }
        except (KeyError, ValueError) as e:
            logger.debug(f"[BinanceWS] kline 解析失敗: {e}")
            return None

    def _parse_ticker(self, data: dict) -> Optional[dict]:
        """解析 24hrTicker 串流。"""
        try:
            return {
                "event": "ticker",
                "symbol": data["s"],
                "price": float(data["c"]),
                "open": float(data["o"]),
                "high": float(data["h"]),
                "low": float(data["l"]),
                "volume": float(data["v"]),
                "quote_volume": float(data["q"]),
                "change": float(data["p"]),
                "change_pct": float(data["P"]),
                "weighted_avg_price": float(data["w"]),
                "first_trade_price": float(data.get("l", 0)),
                "trade_count": int(data.get("n", 0)),
                "event_time": data.get("E", 0),
                "timestamp": time.time(),
            }
        except (KeyError, ValueError) as e:
            logger.debug(f"[BinanceWS] ticker 解析失敗: {e}")
            return None

    def _parse_depth(self, data: dict) -> Optional[dict]:
        """解析 depth 串流。"""
        try:
            bids = [[float(p), float(q)] for p, q in data.get("b", [])]
            asks = [[float(p), float(q)] for p, q in data.get("a", [])]
            return {
                "event": "depth",
                "symbol": data.get("s", ""),
                "bids": bids,
                "asks": asks,
                "bid_total": sum(q for _, q in bids),
                "ask_total": sum(q for _, q in asks),
                "best_bid": bids[0][0] if bids else 0,
                "best_ask": asks[0][0] if asks else 0,
                "spread": (asks[0][0] - bids[0][0]) if bids and asks else 0,
                "spread_pct": (
                    ((asks[0][0] - bids[0][0]) / bids[0][0] * 100)
                    if bids and asks and bids[0][0] > 0
                    else 0
                ),
                "event_time": data.get("E", 0),
                "timestamp": time.time(),
            }
        except (KeyError, ValueError, IndexError) as e:
            logger.debug(f"[BinanceWS] depth 解析失敗: {e}")
            return None

    # ── 狀態查詢 ──────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        return self.stats.state == "connected"

    @property
    def is_running(self) -> bool:
        return self._running

    def get_status(self) -> dict:
        """返回客戶端狀態摘要。"""
        return {
            "state": self.stats.state,
            "is_connected": self.is_connected,
            "is_running": self._running,
            "subscriptions": self._subscriptions,
            "stream_count": len(self._subscriptions),
            "total_connections": self.stats.total_connections,
            "total_reconnects": self.stats.total_reconnects,
            "total_messages": self.stats.total_messages,
            "total_errors": self.stats.total_errors,
            "total_validated": self.stats.total_validated,
            "total_rejected": self.stats.total_rejected,
            "last_message_ago_sec": (
                round(time.time() - self.stats.last_message_ts, 1)
                if self.stats.last_message_ts > 0
                else None
            ),
            "connected_since": (
                time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(self.stats.connected_at)
                )
                if self.stats.connected_at > 0
                else None
            ),
        }
