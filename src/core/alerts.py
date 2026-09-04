"""
預警引擎 — 支持多種規則 + 冷卻 + 日誌 + 多通知渠道
"""

import time
from datetime import datetime

from urllib.parse import quote

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
        resp = requests.post(
            webhook_url,
            json={"msgtype": "text", "text": {"content": message}},
            timeout=10,
        )
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
        resp = requests.post(
            webhook_url,
            json={"msgtype": "text", "text": {"content": message}},
            timeout=10,
        )
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
        resp = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML",
            },
            timeout=10,
        )
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


def send_serverchan(sendkey: str, message: str, title: str = "StockQ 通知") -> bool:
    """ServerChan（方糖）微信推送。"""
    key = (sendkey or "").strip()
    if not key:
        return False
    try:
        url = f"https://sctapi.ftqq.com/{key}.send"
        resp = requests.post(
            url,
            data={"title": title[:32], "desp": message[:4096]},
            timeout=10,
        )
        data = resp.json() if resp.content else {}
        if resp.ok and int(data.get("code", 1)) == 0:
            logger.info("ServerChan 通知發送成功")
            return True
        logger.error(f"ServerChan 通知失敗: {data}")
        return False
    except Exception as e:
        logger.error(f"ServerChan 通知異常: {e}")
        return False


def send_bark(bark_url: str, message: str, title: str = "StockQ") -> bool:
    """Bark iOS 推送。bark_url 可為 https://api.day.app/<key> 或完整推送 URL。"""
    base = (bark_url or "").strip().rstrip("/")
    if not base:
        return False
    try:
        # 允許使用者填 device key 或完整 URL
        if base.startswith("http"):
            url = f"{base}/{quote(title)}/{quote(message[:1024])}"
        else:
            url = f"https://api.day.app/{base}/{quote(title)}/{quote(message[:1024])}"
        resp = requests.get(url, timeout=10)
        data = resp.json() if resp.content else {}
        if resp.ok and int(data.get("code", 1)) == 200:
            logger.info("Bark 通知發送成功")
            return True
        logger.error(f"Bark 通知失敗: {data}")
        return False
    except Exception as e:
        logger.error(f"Bark 通知異常: {e}")
        return False


def send_feishu(webhook_url: str, message: str) -> bool:
    """飛書 / Lark 自訂機器人。"""
    try:
        resp = requests.post(
            webhook_url,
            json={"msg_type": "text", "content": {"text": message}},
            timeout=10,
        )
        data = resp.json() if resp.content else {}
        if data.get("code") == 0 or data.get("StatusCode") == 0:
            logger.info("飛書通知發送成功")
            return True
        logger.error(f"飛書通知失敗: {data}")
        return False
    except Exception as e:
        logger.error(f"飛書通知異常: {e}")
        return False


def send_email_alert(message: str, title: str = "StockQ 預警") -> bool:
    host = (settings.smtp_host or "").strip()
    to_addr = (settings.smtp_to or settings.smtp_user or "").strip()
    user = (settings.smtp_user or "").strip()
    if not host or not to_addr or not user:
        return False
    try:
        import smtplib
        from email.mime.text import MIMEText

        msg = MIMEText(message, "plain", "utf-8")
        msg["Subject"] = title
        msg["From"] = user
        msg["To"] = to_addr
        port = int(settings.smtp_port or 465)
        if port == 465:
            smtp = smtplib.SMTP_SSL(host, port, timeout=15)
        else:
            smtp = smtplib.SMTP(host, port, timeout=15)
            smtp.starttls()
        smtp.login(user, settings.smtp_password or "")
        smtp.sendmail(user, [to_addr], msg.as_string())
        smtp.quit()
        logger.info("郵件通知發送成功")
        return True
    except Exception as e:
        logger.error(f"郵件通知異常: {e}")
        return False



def send_notification(message: str, msg_type: str = "alert"):
    """統一通知分發（帶模板渲染 + 節流 + 異步隊列）"""
    rendered = _render_template(msg_type, message)

    if _should_throttle(rendered):
        logger.debug(f"通知被節流: {rendered[:50]}...")
        return

    from src.core.notify_queue import enqueue_notify

    enqueue_notify(lambda: _dispatch_channels(rendered, msg_type))


def _dispatch_channels(rendered: str, msg_type: str) -> None:
    """實際發送各渠道（由隊列執行，含重試與歷史）。"""
    from src.core.notify_queue import log_notification, send_with_retry

    if settings.notify_console:
        logger.info(f"[通知] {rendered}")
        log_notification("console", rendered, status="ok", msg_type=msg_type)

    if settings.notify_webhook and settings.webhook_url:

        def _webhook():
            requests.post(
                settings.webhook_url,
                json={"msgtype": "text", "text": {"content": f"[股票預警] {rendered}"}},
                timeout=5,
            )
            return True

        send_with_retry("webhook", _webhook, rendered, msg_type=msg_type)

    if settings.notify_wechat_work and settings.wechat_work_webhook:
        send_with_retry(
            "wechat_work",
            lambda: send_wechat_work(settings.wechat_work_webhook, rendered),
            rendered,
            msg_type=msg_type,
        )

    if settings.notify_dingtalk and settings.dingtalk_webhook:
        send_with_retry(
            "dingtalk",
            lambda: send_dingtalk(settings.dingtalk_webhook, rendered),
            rendered,
            msg_type=msg_type,
        )

    if (
        settings.notify_telegram
        and settings.telegram_bot_token
        and settings.telegram_chat_id
    ):
        send_with_retry(
            "telegram",
            lambda: send_telegram(
                settings.telegram_bot_token, settings.telegram_chat_id, rendered
            ),
            rendered,
            msg_type=msg_type,
        )

    if settings.notify_serverchan and settings.serverchan_sendkey:
        send_with_retry(
            "serverchan",
            lambda: send_serverchan(settings.serverchan_sendkey, rendered),
            rendered,
            msg_type=msg_type,
        )

    if settings.notify_bark and settings.bark_url:
        send_with_retry(
            "bark",
            lambda: send_bark(settings.bark_url, rendered),
            rendered,
            msg_type=msg_type,
        )

    if settings.notify_feishu and settings.feishu_webhook:
        send_with_retry(
            "feishu",
            lambda: send_feishu(settings.feishu_webhook, rendered),
            rendered,
            msg_type=msg_type,
        )

    if settings.notify_email:
        send_with_retry(
            "email",
            lambda: send_email_alert(rendered),
            rendered,
            msg_type=msg_type,
        )


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
            "configured": bool(
                settings.telegram_bot_token and settings.telegram_chat_id
            ),
        },
        {
            "name": "ServerChan",
            "key": "serverchan",
            "enabled": settings.notify_serverchan,
            "configured": bool(settings.serverchan_sendkey),
        },
        {
            "name": "Bark",
            "key": "bark",
            "enabled": settings.notify_bark,
            "configured": bool(settings.bark_url),
        },
        {
            "name": "飛書",
            "key": "feishu",
            "enabled": settings.notify_feishu,
            "configured": bool(settings.feishu_webhook),
        },
        {
            "name": "郵件",
            "key": "email",
            "enabled": settings.notify_email,
            "configured": bool(settings.smtp_host and settings.smtp_user),
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
                requests.post(
                    settings.webhook_url,
                    json={"msgtype": "text", "text": {"content": test_msg}},
                    timeout=5,
                )
                results[ch["key"]] = "ok"
            elif ch["key"] == "wechat_work":
                ok = send_wechat_work(settings.wechat_work_webhook, test_msg)
                results[ch["key"]] = "ok" if ok else "failed"
            elif ch["key"] == "dingtalk":
                ok = send_dingtalk(settings.dingtalk_webhook, test_msg)
                results[ch["key"]] = "ok" if ok else "failed"
            elif ch["key"] == "telegram":
                ok = send_telegram(
                    settings.telegram_bot_token, settings.telegram_chat_id, test_msg
                )
                results[ch["key"]] = "ok" if ok else "failed"
            elif ch["key"] == "serverchan":
                ok = send_serverchan(settings.serverchan_sendkey, test_msg)
                results[ch["key"]] = "ok" if ok else "failed"
            elif ch["key"] == "bark":
                ok = send_bark(settings.bark_url, test_msg)
                results[ch["key"]] = "ok" if ok else "failed"
            elif ch["key"] == "feishu":
                ok = send_feishu(settings.feishu_webhook, test_msg)
                results[ch["key"]] = "ok" if ok else "failed"
            elif ch["key"] == "email":
                ok = send_email_alert(test_msg, title="StockQ 測試")
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

        vol = row.get("volume")
        avg_vol = row.get("avg_volume")
        vmult = rule.get("volume_mult")
        if vmult and pd.notna(vol) and pd.notna(avg_vol) and avg_vol:
            try:
                if float(vol) >= float(avg_vol) * float(vmult):
                    if _can_fire("volume_spike"):
                        msg = f"📢 {name}({code}) 成交量異動 {float(vol):.0f} / 均量 {float(avg_vol):.0f}"
                        alerts.append(msg)
                        log_alert(code, "volume_spike", msg, price)
            except (TypeError, ValueError):
                pass

        rsi = row.get("rsi")
        if rule.get("rsi_above") and pd.notna(rsi):
            if float(rsi) >= float(rule["rsi_above"]):
                if _can_fire("rsi_above"):
                    msg = f"📈 {name}({code}) RSI {float(rsi):.1f} ≥ {rule['rsi_above']}"
                    alerts.append(msg)
                    log_alert(code, "rsi_above", msg, price)
        if rule.get("rsi_below") and pd.notna(rsi):
            if float(rsi) <= float(rule["rsi_below"]):
                if _can_fire("rsi_below"):
                    msg = f"📉 {name}({code}) RSI {float(rsi):.1f} ≤ {rule['rsi_below']}"
                    alerts.append(msg)
                    log_alert(code, "rsi_below", msg, price)

        if rule.get("macd_cross") and row.get("macd_cross"):
            cross = str(row.get("macd_cross"))
            if _can_fire(f"macd_{cross}"):
                label = "金叉" if cross == "golden" else "死叉"
                msg = f"🔀 {name}({code}) MACD {label}，現價 {price:.2f}"
                alerts.append(msg)
                log_alert(code, f"macd_{cross}", msg, price)

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
