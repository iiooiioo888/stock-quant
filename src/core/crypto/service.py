"""
加密貨幣業務服務層 — REST + WebSocket 整合入口。

整合：
- 原有 REST 數據源（Binance REST + CoinGecko + CoinCap）
- 新增 WebSocket 實時串流（BinanceStreamClient + CryptoStreamManager）
- 技術指標引擎（CryptoIndicatorEngine）
- 微結構分析（CryptoMicrostructureAnalyzer）
- 告警引擎（CryptoAlertEngine）
"""
from __future__ import annotations

import asyncio
from typing import Optional

import numpy as np

from src.config import settings
from src.core.crypto.alerts import CryptoAlertEngine
from src.core.crypto.client import (
    download_crypto_kline,
    get_crypto_realtime,
    get_crypto_symbols,
)
from src.core.crypto.indicators import compute_all_crypto_indicators
from src.core.crypto.microstructure import CryptoMicrostructureAnalyzer
from src.core.crypto.stream_manager import CryptoStreamManager
from src.core.crypto.ws_client import BinanceStreamClient
from src.utils.logger import logger

_service_instance: Optional["CryptoService"] = None


class CryptoDisabledError(RuntimeError):
    """功能關閉時拋出。"""


class CryptoService:
    """
    加密貨幣數據服務。

    數據源優先級：WebSocket 快照 → REST API
    """

    def __init__(self):
        self._ws_client: Optional[BinanceStreamClient] = None
        self._stream_manager: Optional[CryptoStreamManager] = None
        self._micro_analyzer: Optional[CryptoMicrostructureAnalyzer] = None
        self._alert_engine: Optional[CryptoAlertEngine] = None
        self._initialized = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _ensure_enabled(self) -> None:
        if not settings.crypto_enabled:
            raise CryptoDisabledError("加密貨幣功能已關閉（SQ_CRYPTO_ENABLED=false）")

    def _ensure_ws_components(self):
        """懶初始化 WS 組件。"""
        if self._initialized:
            return

        if settings.crypto_ws_enabled:
            self._stream_manager = CryptoStreamManager(
                trade_window_size=settings.crypto_ws_trade_window_size,
                large_order_multiplier=settings.crypto_micro_large_order_multiplier,
            )
            self._ws_client = BinanceStreamClient(
                reconnect_base_sec=settings.crypto_ws_reconnect_base_sec,
                reconnect_max_sec=settings.crypto_ws_reconnect_max_sec,
            )
            # 註冊回調
            self._ws_client.on_trade(self._stream_manager.on_trade)
            self._ws_client.on_kline(self._stream_manager.on_kline)
            self._ws_client.on_ticker(self._stream_manager.on_ticker)
            self._ws_client.on_depth(self._stream_manager.on_depth)

        if settings.crypto_alerts_enabled:
            self._alert_engine = CryptoAlertEngine(
                rsi_overbought=settings.crypto_alert_rsi_overbought,
                rsi_oversold=settings.crypto_alert_rsi_oversold,
                price_change_pct=settings.crypto_alert_price_change_pct,
                volume_surge_multiplier=settings.crypto_alert_volume_surge_multiplier,
                large_order_usd=settings.crypto_alert_large_order_usd,
                default_cooldown_sec=settings.crypto_alert_cooldown_sec,
            )

        self._micro_analyzer = CryptoMicrostructureAnalyzer(
            large_order_multiplier=settings.crypto_micro_large_order_multiplier,
            large_order_usd=settings.crypto_alert_large_order_usd,
            depth_levels=settings.crypto_micro_depth_levels,
        )

        self._initialized = True

    # ── WebSocket 生命周期 ────────────────────────────────────

    async def start_ws(self):
        """啟動 WebSocket 連接。"""
        self._ensure_ws_components()
        if not self._ws_client:
            logger.warning("[CryptoService] WS 未啟用")
            return

        # 默認訂閱 watchlist
        stream_types = settings.crypto_ws_streams
        kline_intervals = settings.crypto_ws_kline_intervals

        for sym in settings.crypto_watchlist:
            self._ws_client.add_subscription(
                sym,
                stream_types=stream_types,
                kline_intervals=kline_intervals,
            )

        await self._ws_client.connect()
        logger.info(f"[CryptoService] WS 已啟動，訂閱 {len(settings.crypto_watchlist)} 個交易對")

    async def stop_ws(self):
        """停止 WebSocket 連接。"""
        if self._ws_client:
            await self._ws_client.disconnect()

    # ── 原有接口（向後兼容） ──────────────────────────────────

    def list_symbols(self) -> dict:
        self._ensure_enabled()
        return get_crypto_symbols()

    def get_watchlist(self) -> list[str]:
        self._ensure_enabled()
        return list(settings.crypto_watchlist)

    def get_realtime(self, symbols: list[str] = None) -> list[dict]:
        """
        獲取實時行情（WS 快照優先，REST 降級）。
        """
        self._ensure_enabled()
        self._ensure_ws_components()

        sym_list = symbols or list(settings.crypto_watchlist)
        results = []

        for sym in sym_list:
            sym_upper = sym.upper().replace("-", "").replace("/", "")

            # 嘗試 WS 快照
            if self._stream_manager:
                snap = self._stream_manager.get_snapshot(sym_upper)
                if snap and snap.get("price", 0) > 0:
                    snap["name"] = get_crypto_symbols().get(sym_upper, sym_upper)
                    results.append(snap)
                    continue

            # 降級 REST
            try:
                data = get_crypto_realtime(sym_upper)
                if data and data.get("price", 0) > 0:
                    data["name"] = get_crypto_symbols().get(sym_upper, sym_upper)
                    results.append(data)
            except Exception as e:
                logger.debug(f"[CryptoService] REST 降級失敗 {sym_upper}: {e}")

        return results

    def get_realtime_one(self, symbol: str) -> dict:
        self._ensure_enabled()
        self._ensure_ws_components()
        sym = symbol.upper().replace("-", "").replace("/", "")

        # WS 優先
        if self._stream_manager:
            snap = self._stream_manager.get_snapshot(sym)
            if snap and snap.get("price", 0) > 0:
                return snap

        return get_crypto_realtime(sym)

    def get_kline(
        self,
        symbol: str = "BTCUSDT",
        days: int = 30,
        interval: str = "1d",
    ) -> dict:
        self._ensure_enabled()
        self._ensure_ws_components()
        from datetime import datetime, timedelta

        sym = symbol.upper().replace("-", "").replace("/", "")

        # 嘗試 WS 實時 K 線（僅短週期）
        if self._stream_manager and interval in ("1m", "3m", "5m", "15m", "30m", "1h"):
            kl = self._stream_manager.get_kline(sym, interval)
            if kl:
                return {"symbol": sym, "klines": [kl], "total": 1, "source": "ws"}

        # 降級 REST
        start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        try:
            df = download_crypto_kline(symbol=sym, interval=interval, start_date=start)
            if df.empty:
                return {"symbol": sym, "klines": [], "message": "無數據", "total": 0}
            klines = df.to_dict(orient="records")
            return {"symbol": sym, "klines": klines, "total": len(klines), "source": "rest"}
        except Exception as e:
            logger.error(f"加密 K 線失敗 {sym}: {e}")
            raise

    # ── 新增接口：技術指標 ────────────────────────────────────

    def get_indicators(self, symbol: str = "BTCUSDT", days: int = 90) -> dict:
        """
        計算完整技術指標。

        從歷史 K 線 + WS 實時數據計算。
        """
        self._ensure_enabled()
        self._ensure_ws_components()
        sym = symbol.upper().replace("-", "").replace("/", "")

        # 獲取歷史 K 線
        from datetime import datetime, timedelta
        start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        try:
            df = download_crypto_kline(symbol=sym, interval="1d", start_date=start)
        except Exception as e:
            logger.error(f"[CryptoService] 獲取 K 線失敗 {sym}: {e}")
            return {"error": str(e)}

        if df.empty:
            return {"symbol": sym, "indicators": {}, "message": "數據不足"}

        closes = df["close"].values
        highs = df["high"].values
        lows = df["low"].values
        volumes = df["volume"].values

        # 構建指標配置
        config = {
            "rsi_period": settings.crypto_indicator_rsi_period,
            "macd_fast": settings.crypto_indicator_macd_fast,
            "macd_slow": settings.crypto_indicator_macd_slow,
            "macd_signal": settings.crypto_indicator_macd_signal,
            "bb_period": settings.crypto_indicator_bb_period,
            "bb_std": settings.crypto_indicator_bb_std,
            "ema_periods": settings.crypto_indicator_ema_periods,
            "atr_period": settings.crypto_indicator_atr_period,
            "mfi_period": settings.crypto_indicator_mfi_period,
            "stoch_rsi_period": settings.crypto_indicator_stoch_rsi_period,
            "cci_period": settings.crypto_indicator_cci_period,
        }

        indicators = compute_all_crypto_indicators(
            closes=closes,
            highs=highs,
            lows=lows,
            volumes=volumes,
            config=config,
        )

        # 清理 numpy 陣列（不可 JSON 序列化）
        serializable = {}
        for k, v in indicators.items():
            if isinstance(v, np.ndarray):
                continue  # 跳過序列
            serializable[k] = v

        return {
            "symbol": sym,
            "indicators": serializable,
            "data_points": len(closes),
            "last_price": round(float(closes[-1]), 8),
            "last_date": str(df["date"].iloc[-1]) if "date" in df.columns else None,
        }

    # ── 新增接口：微結構分析 ──────────────────────────────────

    def get_microstructure(self, symbol: str = "BTCUSDT") -> dict:
        """
        獲取微結構分析（需 WS 數據）。
        """
        self._ensure_enabled()
        self._ensure_ws_components()
        sym = symbol.upper().replace("-", "").replace("/", "")

        if not self._stream_manager:
            return {"error": "WebSocket 未啟用", "symbol": sym}

        trades = self._stream_manager.get_recent_trades(sym, limit=5000)
        if not trades:
            return {
                "symbol": sym,
                "message": "尚無交易數據（WS 可能未連接）",
                "trade_analysis": None,
                "depth_analysis": None,
                "volatility_analysis": None,
            }

        # 獲取 depth 快照
        snap = self._stream_manager.get_snapshot(sym) or {}

        analysis = self._micro_analyzer.full_analysis(
            symbol=sym,
            trades=trades,
            depth_data=snap if snap.get("best_bid") else None,
        )

        # 添加交易統計
        trade_stats = self._stream_manager.get_trade_stats(sym)
        analysis["trade_stats"] = trade_stats

        return analysis

    # ── 新增接口：告警 ────────────────────────────────────────

    def get_alerts(self) -> list[dict]:
        """獲取活躍告警。"""
        self._ensure_ws_components()
        if not self._alert_engine:
            return []
        return self._alert_engine.get_active_alerts()

    def get_alert_history(self, symbol: str = None, limit: int = 50) -> list[dict]:
        """獲取告警歷史。"""
        self._ensure_ws_components()
        if not self._alert_engine:
            return []
        return self._alert_engine.get_alert_history(symbol, limit)

    def get_alert_rules(self, symbol: str = None) -> list[dict]:
        """獲取告警規則。"""
        self._ensure_ws_components()
        if not self._alert_engine:
            return []
        return self._alert_engine.get_rules(symbol)

    def update_alert_config(self, config: dict) -> dict:
        """更新告警配置。"""
        self._ensure_ws_components()
        if not self._alert_engine:
            return {"error": "告警引擎未啟用"}
        self._alert_engine.update_config(config)
        return self._alert_engine.get_config()

    def create_alert_rules(self, symbol: str) -> list[str]:
        """為交易對創建默認告警規則。"""
        self._ensure_ws_components()
        if not self._alert_engine:
            return []
        return self._alert_engine.create_default_rules(symbol)

    # ── 新增接口：WS 狀態 ─────────────────────────────────────

    def get_ws_status(self) -> dict:
        """獲取 WebSocket 連接狀態。"""
        self._ensure_ws_components()

        status = {
            "ws_enabled": settings.crypto_ws_enabled,
            "ws_client": None,
            "stream_manager": None,
            "alert_engine": None,
        }

        if self._ws_client:
            status["ws_client"] = self._ws_client.get_status()

        if self._stream_manager:
            status["stream_manager"] = self._stream_manager.get_manager_stats()

        if self._alert_engine:
            status["alert_engine"] = self._alert_engine.get_stats()

        return status

    async def subscribe(self, symbols: list[str]) -> dict:
        """動態訂閱新交易對。"""
        self._ensure_ws_components()
        if not self._ws_client:
            return {"error": "WebSocket 未啟用"}

        stream_types = settings.crypto_ws_streams
        kline_intervals = settings.crypto_ws_kline_intervals
        added = []

        for sym in symbols:
            new = self._ws_client.add_subscription(
                sym, stream_types=stream_types, kline_intervals=kline_intervals
            )
            added.extend(new)

            # 創建默認告警規則
            if self._alert_engine:
                self._alert_engine.create_default_rules(sym)

        # 如果已連接，需要重連以訂閱新串流
        if self._ws_client.is_connected and added:
            logger.info(f"[CryptoService] 新增 {len(added)} 個串流，重連中...")
            await self._ws_client.disconnect()
            await self._ws_client.connect()

        return {
            "added_streams": added,
            "total_subscriptions": len(self._ws_client.subscriptions),
        }

    async def unsubscribe(self, symbols: list[str]) -> dict:
        """取消訂閱。"""
        self._ensure_ws_components()
        if not self._ws_client:
            return {"error": "WebSocket 未啟用"}

        removed = []
        for sym in symbols:
            r = self._ws_client.remove_subscription(sym)
            removed.extend(r)

        return {
            "removed_streams": removed,
            "total_subscriptions": len(self._ws_client.subscriptions),
        }


def get_crypto_service() -> CryptoService:
    global _service_instance
    if _service_instance is None:
        _service_instance = CryptoService()
    return _service_instance
