"""WebSocket 實時推送"""
import asyncio
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.config import settings
from src.utils.logger import logger

router = APIRouter(tags=["websocket"])


class ConnectionManager:
    MAX_CONNECTIONS = 50

    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        if len(self.active) >= self.MAX_CONNECTIONS:
            await ws.close(code=4003, reason="連接數已達上限")
            logger.warning(f"WebSocket 連接拒絕：已達上限 {self.MAX_CONNECTIONS}")
            return
        await ws.accept()
        self.active.append(ws)
        logger.info(f"WebSocket 連接: {len(self.active)} 個客戶端")

    def disconnect(self, ws: WebSocket):
        try:
            self.active.remove(ws)
        except ValueError:
            pass
        logger.info(f"WebSocket 斷開: {len(self.active)} 個客戶端")

    async def broadcast(self, data: dict):
        text = json.dumps(data, ensure_ascii=False)
        failed = []
        for ws in self.active[:]:
            try:
                await ws.send_text(text)
            except Exception:
                failed.append(ws)
        for ws in failed:
            self.disconnect(ws)


manager = ConnectionManager()

# ── 同步廣播（供線程池中的任務管理器調用） ──────────────────────
_loop: asyncio.AbstractEventLoop = None


def set_event_loop(loop: asyncio.AbstractEventLoop):
    """在 lifespan 啟動時設置事件循環引用。"""
    global _loop
    _loop = loop


def sync_broadcast(data: dict):
    """同步版廣播，安全地從任意線程調用。"""
    if _loop is None or not manager.active:
        return
    try:
        asyncio.run_coroutine_threadsafe(manager.broadcast(data), _loop)
    except Exception as e:
        logger.debug(f"同步廣播失敗: {e}")


def _is_trading_time() -> bool:
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.hour * 100 + now.minute
    return (915 <= t <= 1130) or (1300 <= t <= 1500)


async def ws_realtime_push():
    """後台任務: 向 WebSocket 客戶端推送行情與信號"""
    import asyncio
    from src.core.realtime import fetch_realtime
    from src.core.signals import SignalEngine, compute_and_push_signals

    signal_engine = SignalEngine()
    try:
        signal_engine.update_weights_from_backtest()
    except Exception:
        pass
    signal_push_counter = 0
    signal_push_interval = 6
    while True:
        await asyncio.sleep(settings.poll_interval_sec)
        if not manager.active:
            continue
        if not _is_trading_time():
            continue
        try:
            df = fetch_realtime(settings.watchlist)
            if not df.empty:
                await manager.broadcast({
                    "type": "quotes",
                    "data": df.to_dict(orient="records"),
                    "timestamp": datetime.now().isoformat(),
                })
        except Exception as e:
            logger.debug(f"WebSocket 推送失敗: {e}")

        signal_push_counter += 1
        if signal_push_counter >= signal_push_interval:
            signal_push_counter = 0
            try:
                signals_data = compute_and_push_signals(signal_engine, settings.watchlist)
                if signals_data:
                    await manager.broadcast({
                        "type": "signals",
                        "data": signals_data,
                        "timestamp": datetime.now().isoformat(),
                    })
            except Exception as e:
                logger.debug(f"WebSocket 信號推送失敗: {e}")


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str = None):
    """WebSocket 實時行情推送（依 effective_ws_auth_required 決定是否強制認證）"""
    auth_required = settings.effective_ws_auth_required

    if auth_required:
        if not token:
            await ws.close(code=4001, reason="需要認證：請在 URL 中添加 ?token=xxx")
            logger.warning("WebSocket 連接被拒絕：缺少 token")
            return

        from src.core.auth import classify_token, verify_token

        state = classify_token(token)
        if state == "expired":
            await ws.close(code=4001, reason="Token 已過期，請重新登錄")
            logger.warning("WebSocket 連接被拒絕：token 已過期")
            return
        if state != "ok":
            await ws.close(code=4001, reason="Token 無效")
            logger.warning("WebSocket 連接被拒絕：token 無效")
            return

        payload = verify_token(token)
        if not payload:
            await ws.close(code=4001, reason="Token 無效或已過期")
            return
    elif token:
        from src.core.auth import verify_token
        if not verify_token(token):
            await ws.close(code=4001, reason="Token 無效或已過期")
            logger.warning("WebSocket 連接被拒絕：提供了無效 token")
            return

    await manager.connect(ws)
    try:
        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        manager.disconnect(ws)
