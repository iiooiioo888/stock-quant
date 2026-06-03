"""
預警引擎 — 支持多種規則 + 冷卻 + 日誌 + 多通知渠道
"""
import time
from datetime import datetime

import pandas as pd
import requests

from src.config import settings
from src.core.db import log_alert
from src.utils.logger import logger

# ============================================================
# 通知模板
# ============================================================

TEMPLATES = {
    "alert": "🚨 [股票預警]\n{message}\n時間: {time}",
    "daily_report": "📊 [每日報告]\n{message}",
    "backtest_complete": "📈 [回測完成]\n{message}",
}


def _render_template(msg_type: str, message: str) -> str:
    """渲染通知模板"""
    template = TEMPLATES.get(msg_type, "{message}")
    return template.format(
        message=message,
        time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


# ============================================================
# 節流（5 分鐘內相同消息不重複發送）
# ============================================================

_throttle_cache: dict[str, float] = {}
_THROTTLE_SEC = 300  # 5 分鐘


def _should_throttle(message: str) -> bool:
    """檢查是否應節流（相同消息 5 分鐘內不重複發送）"""
    now = time.time()
    key = message[:200]  # 取前 200 字符做 key
    last_sent = _throttle_cache.get(key, 0)
    if now - last_sent < _THROTTLE_SEC:
        return True
    _throttle_cache[key] = now
    return False


# ============================================================
# 通知渠道實現
# ============================================================

def send_wechat_work(webhook_url: str, message: str) -> bool:
    """發送企業微信機器人消息"""
    try:
        resp = requests.post(webhook_url, json={
            "msgtype": "text",
            "text": {"content": message}
        }, timeout=10)
        data = resp.json()
        if data.get("errcode") == 0:
            logger.info("企業微信通知發送成功")
            return True
        else:
            logger.error(f"企業微信通知失敗: {data}")
            return False
    except Exception as e:
        logger.error(f"企業微信通知異常: {e}")
        return False


def send_dingtalk(webhook_url: str, message: str) -> bool:
    """發送釘釘機器人消息"""
    try:
        resp = requests.post(webhook_url, json={
            "msgtype": "text",
            "text": {"content": message}
        }, timeout=10)
        data = resp.json()
        if data.get("errcode") == 0:
            logger.info("釘釘通知發送成功")
            return True
        else:
            logger.error(f"釘釘通知失敗: {data}")
            return False
    except Exception as e:
        logger.error(f"釘釘通知異常: {e}")
        return False


def send_telegram(bot_token: str, chat_id: str, message: str) -> bool:
    """發送 Telegram Bot 消息"""
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        resp = requests.post(url, json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
        }, timeout=10)
        data = resp.json()
        if data.get("ok"):
            logger.info("Telegram 通知發送成功")
            return True
        else:
            logger.error(f"Telegram 通知失敗: {data}")
            return False
    except Exception as e:
        logger.error(f"Telegram 通知異常: {e}")
        return False


def send_notification(message: str, msg_type: str = "alert"):
    """統一通知分發（帶模板渲染 + 節流）"""
    rendered = _render_template(msg_type, message)

    if _should_throttle(rendered):
        logger.debug(f"通知被節流: {rendered[:50]}...")
        return

    # 控制台
    if settings.notify_console:
        logger.info(f"[通知] {rendered}")

    # Webhook
    if settings.notify_webhook and settings.webhook_url:
        try:
            requests.post(settings.webhook_url, json={
                "msgtype": "text",
                "text": {"content": f"[股票預警] {rendered}"}
            }, timeout=5)
        except Exception as e:
            logger.error(f"Webhook 推送失敗: {e}")

    # 企業微信
    if settings.notify_wechat_work and settings.wechat_work_webhook:
        send_wechat_work(settings.wechat_work_webhook, rendered)

    # 釘釘
    if settings.notify_dingtalk and settings.dingtalk_webhook:
        send_dingtalk(settings.dingtalk_webhook, rendered)

    # Telegram
    if settings.notify_telegram and settings.telegram_bot_token and settings.telegram_chat_id:
        send_telegram(settings.telegram_bot_token, settings.telegram_chat_id, rendered)


def get_notification_channels() -> list[dict]:
    """獲取通知渠道狀態"""
    return [
        {
            "name": "控制台",
            "key": "console",
            "enabled": settings.notify_console,
            "configured": True,
        },
        {
            "name": "Webhook",
            "key": "webhook",
            "enabled": settings.notify_webhook,
            "configured": bool(settings.webhook_url),
        },
        {
            "name": "企業微信",
            "key": "wechat_work",
            "enabled": settings.notify_wechat_work,
            "configured": bool(settings.wechat_work_webhook),
        },
        {
            "name": "釘釘",
            "key": "dingtalk",
            "enabled": settings.notify_dingtalk,
            "configured": bool(settings.dingtalk_webhook),
        },
        {
            "name": "Telegram",
            "key": "telegram",
            "enabled": settings.notify_telegram,
            "configured": bool(settings.telegram_bot_token and settings.telegram_chat_id),
        },
    ]


def test_all_channels() -> dict:
    """向所有已啟用且已配置的渠道發送測試消息"""
    test_msg = f"🔔 測試通知 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    results = {}

    channels = get_notification_channels()
    for ch in channels:
        if not ch["enabled"] or not ch["configured"]:
            results[ch["key"]] = "skipped (not enabled/configured)"
            continue

        try:
            if ch["key"] == "console":
                logger.info(f"[測試] {test_msg}")
                results[ch["key"]] = "ok"
            elif ch["key"] == "webhook":
                requests.post(settings.webhook_url, json={
                    "msgtype": "text", "text": {"content": test_msg}
                }, timeout=5)
                results[ch["key"]] = "ok"
            elif ch["key"] == "wechat_work":
                ok = send_wechat_work(settings.wechat_work_webhook, test_msg)
                results[ch["key"]] = "ok" if ok else "failed"
            elif ch["key"] == "dingtalk":
                ok = send_dingtalk(settings.dingtalk_webhook, test_msg)
                results[ch["key"]] = "ok" if ok else "failed"
            elif ch["key"] == "telegram":
                ok = send_telegram(settings.telegram_bot_token, settings.telegram_chat_id, test_msg)
                results[ch["key"]] = "ok" if ok else "failed"
        except Exception as e:
            results[ch["key"]] = f"error: {e}"

    return results


# ============================================================
# AlertEngine（原有功能 + 新增通知分發）
# ============================================================

class AlertEngine:
    def __init__(self):
        self._last_fired: dict[str, float] = {}
        self._alert_count = 0

    def check(self, row: pd.Series) -> list[str]:
        """檢查單條行情是否觸發預警"""
        code = str(row.get("code", ""))
        rule = settings.alert_rules.get(code)
        if not rule:
            return []

        price = row.get("price", 0)
        change_pct = row.get("change_pct", 0)
        name = rule.get("name", code)

        if pd.isna(price) or price == 0:
            return []

        alerts = []
        now = time.time()

        def _can_fire(rule_key: str) -> bool:
            key = f"{code}:{rule_key}"
            last = self._last_fired.get(key, 0)
            if now - last < settings.alert_cooldown_sec:
                return False
            self._last_fired[key] = now
            return True

        if rule.get("price_above") and price >= rule["price_above"]:
            if _can_fire("price_above"):
                msg = f"🔴 {name}({code}) 突破 {rule['price_above']}，現價 {price:.2f}"
                alerts.append(msg)
                log_alert(code, "price_above", msg, price)

        if rule.get("price_below") and price <= rule["price_below"]:
            if _can_fire("price_below"):
                msg = f"🟢 {name}({code}) 跌破 {rule['price_below']}，現價 {price:.2f}"
                alerts.append(msg)
                log_alert(code, "price_below", msg, price)

        if rule.get("change_pct") and pd.notna(change_pct):
            if abs(change_pct) >= rule["change_pct"]:
                if _can_fire("change_pct"):
                    direction = "暴漲" if change_pct > 0 else "暴跌"
                    msg = f"⚡ {name}({code}) {direction} {change_pct:+.2f}%，現價 {price:.2f}"
                    alerts.append(msg)
                    log_alert(code, "change_pct", msg, price)

        return alerts

    def dispatch(self, messages: list[str]):
        """分發預警到各通知渠道"""
        if not messages:
            return

        self._alert_count += len(messages)

        for msg in messages:
            logger.warning(f"預警觸發: {msg}")
            send_notification(msg, msg_type="alert")

    def process(self, df: pd.DataFrame):
        """處理一批實時行情數據"""
        for _, row in df.iterrows():
            alerts = self.check(row)
            self.dispatch(alerts)

    @property
    def total_alerts(self) -> int:
        return self._alert_count
