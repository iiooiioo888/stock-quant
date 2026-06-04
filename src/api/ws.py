"""WebSocket 實時推送"""
import asyncio
import json
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.config import settings
from src.utils.logger import logger

router = APIRouter(tags=["websocket"])

# 每用戶最大 WebSocket 連接數
_PER_USER_MAX_CONNECTIONS = 5


class ConnectionManager:
    MAX_CONNECTIONS = 50

    def __init__(self):
        self.active: list[WebSocket] = []
        self._user_conns: dict[int, list[WebSocket]] = {}  # user_id -> [ws, ...]
        self._ws_user: dict[int, int] = {}  # id(ws) -> user_id

    async def connect(self, ws: WebSocket, user_id: Optional[int] = None):
        # 全局連接數限制
        if len(self.active) >= self.MAX_CONNECTIONS:
            await ws.close(code=4003, reason="連接數已達上限")
            logger.warning(f"WebSocket 連接拒絕：已達上限 {self.MAX_CONNECTIONS}")
            return
        # 每用戶連接數限制
        if user_id is not None:
            user_conns = self._user_conns.get(user_id, [])
            if len(user_conns) >= _PER_USER_MAX_CONNECTIONS:
                await ws.close(code=4003, reason="該用戶連接數已達上限")
                logger.warning(f"WebSocket 連接拒絕：用戶 {user_id} 達上限 {_PER_USER_MAX_CONNECTIONS}")
                return
        await ws.accept()
        self.active.append(ws)
        if user_id is not None:
            self._user_conns.setdefault(user_id, []).append(ws)
            self._ws_user[id(ws)] = user_id
        logger.info(f"WebSocket 連接: {len(self.active)} 個客戶端 (user={user_id})")

    def disconnect(self, ws: WebSocket):
        try:
            self.active.remove(ws)
        except ValueError:
            pass
        # 清理 per-user 追蹤
        uid = self._ws_user.pop(id(ws), None)
        if uid is not None:
            conns = self._user_conns.get(uid)
            if conns:
                try:
                    conns.remove(ws)
                except ValueError:
                    pass
                if not conns:
                    self._user_conns.pop(uid, None)
        logger.info(f"WebSocket 斷開: {len(self.active)} 個客戶端")

    def count_for_user(self, user_id: int) -> int:
        return len(self._user_conns.get(user_id, []))

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

    # 加密貨幣 WS 初始化
    crypto_push_counter = 0
    crypto_push_interval = max(1, settings.crypto_push_interval_sec // settings.poll_interval_sec)
    crypto_ws_started = False

    while True:
        await asyncio.sleep(settings.poll_interval_sec)
        if not manager.active:
            continue

        # ── A 股行情推送（僅交易時間） ──
        if _is_trading_time():
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

        # ── 加密貨幣行情推送（24/7，不受交易時間限制） ──
        if settings.crypto_enabled and settings.crypto_ws_enabled:
            # 懶啟動 WS 連接
            if not crypto_ws_started:
                try:
                    from src.core.crypto.service import get_crypto_service
                    svc = get_crypto_service()
                    await svc.start_ws()
                    crypto_ws_started = True
                except Exception as e:
                    logger.debug(f"[CryptoWS] 啟動失敗: {e}")

            crypto_push_counter += 1
            if crypto_push_counter >= crypto_push_interval:
                crypto_push_counter = 0
                try:
                    from src.core.crypto.service import get_crypto_service
                    svc = get_crypto_service()

                    push_types = settings.crypto_push_types

                    # 實時行情快照
                    if "quotes" in push_types:
                        snapshots = svc._stream_manager.get_all_snapshots() if svc._stream_manager else []
                        if snapshots:
                            await manager.broadcast({
                                "type": "crypto_quotes",
                                "data": snapshots,
                                "timestamp": datetime.now().isoformat(),
                            })

                    # 告警推送
                    if "alerts" in push_types:
                        alerts = svc.get_alerts()
                        if alerts:
                            await manager.broadcast({
                                "type": "crypto_alerts",
                                "data": alerts,
                                "timestamp": datetime.now().isoformat(),
                            })

                except Exception as e:
                    logger.debug(f"[CryptoWS] 推送失敗: {e}")


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str = None):
    """WebSocket 實時行情推送（依 effective_ws_auth_required 決定是否強制認證）"""
    auth_required = settings.effective_ws_auth_required
    user_id = None

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
        user_id = payload.get("user_id")
    elif token:
        from src.core.auth import verify_token
        payload = verify_token(token)
        if not payload:
            await ws.close(code=4001, reason="Token 無效或已過期")
            logger.warning("WebSocket 連接被拒絕：提供了無效 token")
            return
        user_id = payload.get("user_id")

    await manager.connect(ws, user_id=user_id)
    try:
        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception:
        # 修復：捕獲所有異常（ConnectionResetError 等），避免連接洩漏
        manager.disconnect(ws)
