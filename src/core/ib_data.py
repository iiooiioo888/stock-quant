"""
Interactive Brokers 行情 — 可選 ib_insync + TWS / IB Gateway

需本地運行 TWS 或 IB Gateway，並在 .env 啟用：
  SQ_IB_ENABLED=true
  SQ_IB_HOST=127.0.0.1
  SQ_IB_PORT=7497
  SQ_IB_CLIENT_ID=10
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta
from typing import Any, Optional

import pandas as pd

from src.utils.logger import logger

_lock = threading.Lock()
_ib = None
_last_connect_attempt = 0.0
_CONNECT_COOLDOWN = 60.0
_connected = False


def _settings():
    from src.config import settings
    return settings


def ib_available() -> bool:
    """IB 是否已配置且可選依賴存在。"""
    try:
        s = _settings()
        if not getattr(s, "ib_enabled", False):
            return False
        import ib_insync  # noqa: F401
        return True
    except ImportError:
        return False
    except Exception:
        return False


def ib_status(*, probe: bool = False) -> dict:
    """連線狀態摘要（供 API / UI）。probe=True 時嘗試連接 TWS/Gateway。"""
    s = _settings()
    enabled = getattr(s, "ib_enabled", False)
    try:
        import ib_insync  # noqa: F401
        lib_ok = True
    except ImportError:
        lib_ok = False

    connected = _connected
    if probe and enabled and lib_ok:
        ib = _get_ib()
        connected = bool(ib and ib.isConnected())

    st = {
        "enabled": enabled,
        "library": lib_ok,
        "connected": connected,
        "ok": connected,
        "host": getattr(s, "ib_host", "127.0.0.1"),
        "port": getattr(s, "ib_port", 7497),
        "client_id": int(getattr(s, "ib_client_id", 10)),
    }
    if not enabled:
        st["reason"] = "disabled"
        st["ok"] = False
    elif not lib_ok:
        st["reason"] = "ib_insync_not_installed"
        st["ok"] = False
    elif not connected:
        st["reason"] = "not_connected"
        st["ok"] = False
    else:
        st["reason"] = "ok"
        st["ok"] = True
    return st


def _contract_from_spec(spec: dict[str, Any]):
    from ib_insync import Contract, Forex, Index, Stock

    sec = str(spec.get("secType", "STK")).upper()
    symbol = spec.get("symbol", "")
    exchange = spec.get("exchange", "SMART")
    currency = spec.get("currency", "USD")

    if sec == "CASH":
        return Forex(symbol + currency if len(symbol) == 3 else symbol)
    if sec == "IND":
        return Index(symbol, exchange, currency)
    if sec == "CMDTY":
        return Contract(secType="CMDTY", symbol=symbol, exchange=exchange, currency=currency)
    return Stock(symbol, exchange, currency)


def _get_ib():
    """懶連線單例；失敗後冷卻重試。"""
    global _ib, _last_connect_attempt, _connected

    if not ib_available():
        return None

    with _lock:
        if _ib is not None and _ib.isConnected():
            _connected = True
            return _ib

        now = time.time()
        if now - _last_connect_attempt < _CONNECT_COOLDOWN:
            return None
        _last_connect_attempt = now

        try:
            from ib_insync import IB

            s = _settings()
            ib = IB()
            ib.connect(
                getattr(s, "ib_host", "127.0.0.1"),
                int(getattr(s, "ib_port", 7497)),
                clientId=int(getattr(s, "ib_client_id", 10)),
                timeout=5,
            )
            _ib = ib
            _connected = True
            logger.info("IB TWS/Gateway 已連接")
            return _ib
        except Exception as e:
            _connected = False
            _ib = None
            logger.debug(f"IB 連接失敗: {e}")
            return None


def fetch_ib_quote(spec: dict[str, Any]) -> dict:
    """IB 延遲/快照報價。"""
    ib = _get_ib()
    if not ib or not spec:
        return {}

    try:
        contract = _contract_from_spec(spec)
        ib.qualifyContracts(contract)
        tickers = ib.reqTickers(contract)
        if not tickers:
            return {}

        t = tickers[0]
        price = t.last or t.close or t.marketPrice()
        if not price or price <= 0:
            return {}

        prev = t.close or price
        change = price - prev if prev else 0
        change_pct = (change / prev * 100) if prev else 0

        return {
            "symbol": spec.get("symbol", ""),
            "name": spec.get("symbol", ""),
            "price": round(float(price), 6),
            "change": round(float(change), 6),
            "change_pct": round(float(change_pct), 4),
            "currency": spec.get("currency", "USD"),
            "source": "ib",
        }
    except Exception as e:
        logger.debug(f"IB quote {spec} 失敗: {e}")
        return {}


def fetch_ib_history(spec: dict[str, Any], days: int = 90) -> pd.DataFrame:
    """IB 日 K 歷史。"""
    ib = _get_ib()
    if not ib or not spec:
        return pd.DataFrame()

    days = max(2, int(days))
    duration = f"{min(days + 30, 365)} D"
    try:
        contract = _contract_from_spec(spec)
        ib.qualifyContracts(contract)
        bars = ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr=duration,
            barSizeSetting="1 day",
            whatToShow="TRADES",
            useRTH=True,
            formatDate=1,
        )
        if not bars or len(bars) < 2:
            return pd.DataFrame()

        rows = []
        for b in bars:
            dt = b.date
            if isinstance(dt, datetime):
                ds = dt.strftime("%Y-%m-%d")
            else:
                ds = str(dt)[:10]
            rows.append({
                "date": ds,
                "open": float(b.open),
                "high": float(b.high),
                "low": float(b.low),
                "close": float(b.close),
                "volume": float(b.volume or 0),
            })
        df = pd.DataFrame(rows)
        return df.tail(days).reset_index(drop=True)
    except Exception as e:
        logger.debug(f"IB history {spec} 失敗: {e}")
        return pd.DataFrame()


def fetch_ib_bundle(
    spec: dict[str, Any],
    days: int,
) -> tuple[pd.DataFrame, dict, str]:
    df = fetch_ib_history(spec, days)
    quote = fetch_ib_quote(spec)
    if df.empty and not quote:
        return pd.DataFrame(), {}, ""
    if quote:
        quote.setdefault("source", "ib")
    return df, quote, "ib"


def disconnect_ib():
    global _ib, _connected
    with _lock:
        if _ib and _ib.isConnected():
            try:
                _ib.disconnect()
            except Exception:
                pass
        _ib = None
        _connected = False
