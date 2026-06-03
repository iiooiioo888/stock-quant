"""
Interactive Brokers 行情 — 可選 ib_insync + TWS / IB Gateway

需本地運行 TWS 或 IB Gateway，並在 .env 啟用：
  SQ_IB_ENABLED=true
  SQ_IB_HOST=127.0.0.1
  SQ_IB_PORT=7497
  SQ_IB_CLIENT_ID=10
"""
from __future__ import annotations

import asyncio
import threading
import time
from datetime import datetime
from typing import Any

import pandas as pd

from src.utils.logger import logger

_lock = threading.Lock()
_ib = None
_last_connect_attempt = 0.0
_CONNECT_COOLDOWN = 60.0
_connected = False

# Windows + uvicorn 下 ib_insync 容易遇到「不同 event loop」問題；
# 改為在專用背景執行緒內持有單一 asyncio loop 與 IB 實例。
_ib_thread: threading.Thread | None = None
_ib_loop: asyncio.AbstractEventLoop | None = None
_ib_thread_ready = threading.Event()
_ib_thread_stop = threading.Event()


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
    """懶連線單例；失敗後冷卻重試（IB 僅在專用執行緒操作）。"""
    global _ib, _last_connect_attempt, _connected

    if not ib_available():
        return None

    with _lock:
        _ensure_ib_thread()
        if _ib is not None:
            try:
                if _ib.isConnected():
                    _connected = True
                    return _ib
            except Exception:
                pass

        now = time.time()
        if now - _last_connect_attempt < _CONNECT_COOLDOWN:
            return None
        _last_connect_attempt = now

        try:
            s = _settings()
            host = getattr(s, "ib_host", "127.0.0.1")
            port = int(getattr(s, "ib_port", 7497))
            cid = int(getattr(s, "ib_client_id", 10))

            ok = _ib_connect_threadsafe(host, port, cid, timeout=5)
            if ok and _ib is not None and _ib.isConnected():
                _connected = True
                logger.info("IB TWS/Gateway 已連接")
                return _ib
            _connected = False
            return None
        except Exception as e:
            _connected = False
            logger.warning(f"IB 連接異常：{e}，將在 {_CONNECT_COOLDOWN} 秒後重試")


def _ensure_ib_thread() -> None:
    global _ib_thread, _ib_loop, _ib
    if _ib_thread and _ib_loop and _ib_thread.is_alive():
        return

    _ib_thread_ready.clear()
    _ib_thread_stop.clear()

    def _runner():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            _ib_loop_local = loop
            # store
            globals()["_ib_loop"] = _ib_loop_local
            from ib_insync import IB
            globals()["_ib"] = IB()
            _ib_thread_ready.set()
            # run until stop
            while not _ib_thread_stop.is_set():
                loop.run_until_complete(asyncio.sleep(0.1))
            # graceful cleanup
            try:
                if globals().get("_ib") and globals()["_ib"].isConnected():
                    globals()["_ib"].disconnect()
            except Exception:
                pass
            try:
                loop.stop()
            except Exception:
                pass
            try:
                loop.close()
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"IB loop thread failed: {e}")
            _ib_thread_ready.set()

    t = threading.Thread(target=_runner, name="ib-loop", daemon=True)
    _ib_thread = t
    t.start()
    _ib_thread_ready.wait(timeout=3)


def _ib_connect_threadsafe(host: str, port: int, client_id: int, timeout: int = 5) -> bool:
    """在 IB 專用 loop 內執行 connectAsync，避免跨 loop future。"""
    if _ib_loop is None or _ib is None:
        return False
    if _ib.isConnected():
        return True

    async def _coro():
        try:
            await _ib.connectAsync(host, port, clientId=client_id, timeout=timeout)
            return True
        except Exception as e:
            logger.debug(f"IB connectAsync failed: {e}")
            try:
                _ib.disconnect()
            except Exception:
                pass
            return False

    fut = asyncio.run_coroutine_threadsafe(_coro(), _ib_loop)
    try:
        return bool(fut.result(timeout=timeout + 1))
    except Exception as e:
        logger.debug(f"IB connect future failed: {e}")
        return False


def _ib_call(fn, *args, **kwargs):
    """在 IB 專用執行緒執行阻塞 ib_insync 操作。"""
    if _ib_loop is None:
        raise RuntimeError("IB loop not ready")
    done = threading.Event()
    out = {"ok": False, "value": None, "err": None}

    def _run():
        try:
            out["value"] = fn(*args, **kwargs)
            out["ok"] = True
        except Exception as e:
            out["err"] = e
        finally:
            done.set()

    _ib_loop.call_soon_threadsafe(_run)
    done.wait(timeout=15)
    if not out["ok"]:
        if out["err"] is not None:
            raise out["err"]
        raise TimeoutError("IB call timeout")
    return out["value"]


def fetch_ib_quote(spec: dict[str, Any]) -> dict:
    """IB 延遲/快照報價。"""
    ib = _get_ib()
    if not ib or not spec:
        return {}

    try:
        contract = _contract_from_spec(spec)
        _ib_call(ib.qualifyContracts, contract)
        tickers = _ib_call(ib.reqTickers, contract)
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
        _ib_call(ib.qualifyContracts, contract)
        bars = _ib_call(
            ib.reqHistoricalData,
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
    global _ib, _connected, _ib_thread, _ib_loop
    with _lock:
        try:
            _ib_thread_stop.set()
        except Exception:
            pass
        _connected = False
        _ib = None
        _ib_loop = None
        _ib_thread = None


def ib_reconnect():
    """
    手動觸發 IB 重連（Phase 1 P1-3）
    
    重置冷卻計時器，立即嘗試重新連接。
    返回連接狀態。
    """
    global _last_connect_attempt, _connected

    if not ib_available():
        return {"status": "disabled", "reason": "IB 未啟用或缺少依賴"}

    # 重置冷卻計時器
    with _lock:
        _last_connect_attempt = 0.0
        _connected = False

    # 嘗試連接
    ib = _get_ib()
    connected = bool(ib and ib.isConnected())

    return {
        "status": "connected" if connected else "failed",
        "connected": connected,
        "host": getattr(_settings(), "ib_host", "127.0.0.1"),
        "port": getattr(_settings(), "ib_port", 7497),
    }
