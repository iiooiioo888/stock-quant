"""
Polymarket 概率驅動預警 — 依 yes 機率閾值與變動幅度觸發通知。

與 A 股 AlertEngine 並行：使用 polymarket_alert_rules 表 + 現有 log_alert / send_notification。
"""
import time
from typing import Optional

from src.config import settings
from src.core.alerts import send_notification
from src.core.db import log_alert, get_alert_logs
from src.core.polymarket.alert_store import (
    init_polymarket_alert_tables,
    list_alert_rules,
    load_prob_state,
    save_prob_state,
)
from src.core.polymarket.service import PolymarketDisabledError, get_polymarket_service
from src.utils.logger import logger

_engine_instance: Optional["PolymarketAlertEngine"] = None


class PolymarketAlertEngine:
    """輪詢規則市場並評估 yes 機率條件。"""

    def __init__(self):
        self._last_fired: dict[str, float] = {}
        self._alert_count = 0

    def _can_fire(self, market_key: str, rule_type: str) -> bool:
        key = f"pm:{market_key}:{rule_type}"
        now = time.time()
        last = self._last_fired.get(key, 0)
        cooldown = getattr(settings, "polymarket_alert_cooldown_sec", None) or settings.alert_cooldown_sec
        if now - last < cooldown:
            return False
        self._last_fired[key] = now
        return True

    def _fetch_market(self, market_key: str) -> Optional[dict]:
        try:
            return get_polymarket_service().get_market(market_key)
        except Exception as e:
            logger.debug(f"Polymarket 預警拉取失敗 {market_key}: {e}")
            return None

    def evaluate_rule(self, rule: dict, market: dict) -> list[str]:
        """單條規則對單個市場快照評估，返回觸發消息列表。"""
        if not rule.get("enabled"):
            return []

        key = rule.get("market_key") or market.get("slug") or market.get("market_id") or ""
        yes = float(market.get("yes_price") or 0)
        no = float(market.get("no_price") or 0)
        name = rule.get("name") or market.get("question") or key
        code = f"pm:{key}"
        messages = []

        yes_above = rule.get("yes_above")
        if yes_above is not None and yes >= float(yes_above):
            if self._can_fire(key, "yes_above"):
                pct = yes * 100
                msg = (
                    f"📈 [Polymarket] {name[:80]} — Yes 機率 {pct:.1f}% "
                    f"≥ 閾值 {float(yes_above)*100:.1f}%"
                )
                messages.append(msg)
                log_alert(code, "pm_yes_above", msg, yes)

        yes_below = rule.get("yes_below")
        if yes_below is not None and yes <= float(yes_below):
            if self._can_fire(key, "yes_below"):
                pct = yes * 100
                msg = (
                    f"📉 [Polymarket] {name[:80]} — Yes 機率 {pct:.1f}% "
                    f"≤ 閾值 {float(yes_below)*100:.1f}%"
                )
                messages.append(msg)
                log_alert(code, "pm_yes_below", msg, yes)

        change_thresh = rule.get("prob_change_pct")
        if change_thresh is not None and float(change_thresh) > 0:
            prev = load_prob_state(key)
            if prev and prev.get("yes_price"):
                old_yes = float(prev["yes_price"])
                if old_yes > 0:
                    delta_pct = abs(yes - old_yes) / old_yes * 100.0
                    if delta_pct >= float(change_thresh):
                        if self._can_fire(key, "prob_change"):
                            direction = "上升" if yes > old_yes else "下降"
                            msg = (
                                f"⚡ [Polymarket] {name[:80]} — Yes 機率{direction} "
                                f"{old_yes*100:.1f}% → {yes*100:.1f}%（變動 {delta_pct:.1f}%）"
                            )
                            messages.append(msg)
                            log_alert(code, "pm_prob_change", msg, yes)

        save_prob_state(key, yes, no)
        return messages

    def dispatch(self, messages: list[str]) -> None:
        if not messages:
            return
        self._alert_count += len(messages)
        for msg in messages:
            logger.warning(msg)
            send_notification(msg, msg_type="alert")

    def run_evaluation(self, rules: list[dict] = None) -> dict:
        """
        評估全部啟用規則；返回統計供 API / 定時任務使用。
        """
        if not settings.polymarket_enabled:
            raise PolymarketDisabledError("Polymarket 已關閉")
        if not getattr(settings, "polymarket_alert_enabled", True):
            return {"skipped": True, "reason": "polymarket_alert_enabled=false"}

        init_polymarket_alert_tables()
        rules = rules if rules is not None else list_alert_rules(enabled_only=True)
        if not rules:
            return {"rules": 0, "triggered": 0, "messages": []}

        all_messages = []
        errors = []
        for rule in rules:
            key = rule.get("market_key")
            if not key:
                continue
            market = self._fetch_market(key)
            if not market:
                errors.append(key)
                continue
            msgs = self.evaluate_rule(rule, market)
            all_messages.extend(msgs)

        self.dispatch(all_messages)
        return {
            "rules": len(rules),
            "triggered": len(all_messages),
            "messages": all_messages,
            "errors": errors,
        }

    @property
    def total_alerts(self) -> int:
        return self._alert_count


def get_polymarket_alert_engine() -> PolymarketAlertEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = PolymarketAlertEngine()
    return _engine_instance


def run_polymarket_alert_cycle() -> dict:
    """定時任務入口。"""
    try:
        return get_polymarket_alert_engine().run_evaluation()
    except PolymarketDisabledError as e:
        logger.debug(str(e))
        return {"skipped": True, "reason": str(e)}
    except Exception as e:
        logger.error(f"Polymarket 預警週期失敗: {e}")
        return {"error": str(e)}


def get_polymarket_alert_logs(limit: int = 50) -> list[dict]:
    """僅返回 code 以 pm: 開頭的預警日誌。"""
    logs = get_alert_logs(limit=limit * 3)
    pm_logs = [r for r in logs if str(r.get("code", "")).startswith("pm:")]
    return pm_logs[:limit]
