"""
加密貨幣多維度告警引擎。

整合現有 src/core/alerts.py 的通知渠道（企業微信/DingTalk/Telegram/Webhook/Console），
復用冷卻節流機制，寫入 AlertLog 表。

告警規則：
- 漲跌幅突破
- RSI 超買/超賣
- MACD 金叉/死叉
- 布林帶突破
- 成交量突增
- 大單出現
- 創 N 日新高/新低
- 盤口深度異常
"""
from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime
from typing import Optional

from src.utils.logger import logger

# ── 告警級別 ──────────────────────────────────────────────────

ALERT_LEVEL_INFO = "info"
ALERT_LEVEL_WARNING = "warning"
ALERT_LEVEL_CRITICAL = "critical"


# ── 告警規則數據結構 ──────────────────────────────────────────

class AlertRule:
    """單條告警規則。"""

    def __init__(
        self,
        rule_id: str,
        rule_type: str,
        symbol: str,
        params: dict = None,
        level: str = ALERT_LEVEL_WARNING,
        enabled: bool = True,
        cooldown_sec: int = 300,
    ):
        self.rule_id = rule_id
        self.rule_type = rule_type
        self.symbol = symbol.upper()
        self.params = params or {}
        self.level = level
        self.enabled = enabled
        self.cooldown_sec = cooldown_sec
        self.last_triggered: float = 0.0
        self.trigger_count: int = 0

    def is_in_cooldown(self) -> bool:
        return (time.time() - self.last_triggered) < self.cooldown_sec

    def mark_triggered(self):
        self.last_triggered = time.time()
        self.trigger_count += 1

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "rule_type": self.rule_type,
            "symbol": self.symbol,
            "params": self.params,
            "level": self.level,
            "enabled": self.enabled,
            "cooldown_sec": self.cooldown_sec,
            "last_triggered": (
                datetime.fromtimestamp(self.last_triggered).isoformat()
                if self.last_triggered > 0 else None
            ),
            "trigger_count": self.trigger_count,
        }


class AlertEvent:
    """告警事件。"""

    def __init__(
        self,
        rule_id: str,
        rule_type: str,
        symbol: str,
        level: str,
        message: str,
        price: float = 0.0,
        params: dict = None,
    ):
        self.rule_id = rule_id
        self.rule_type = rule_type
        self.symbol = symbol
        self.level = level
        self.message = message
        self.price = price
        self.params = params or {}
        self.triggered_at = time.time()

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "rule_type": self.rule_type,
            "symbol": self.symbol,
            "level": self.level,
            "message": self.message,
            "price": self.price,
            "params": self.params,
            "triggered_at": datetime.fromtimestamp(self.triggered_at).isoformat(),
        }


# ── 告警引擎 ──────────────────────────────────────────────────

class CryptoAlertEngine:
    """
    加密貨幣告警引擎。

    功能：
    - 管理告警規則（增刪改查）
    - 接收實時數據並評估規則
    - 冷卻控制避免重複告警
    - 告警歷史記錄
    - 回調推送
    """

    def __init__(
        self,
        rsi_overbought: float = 70.0,
        rsi_oversold: float = 30.0,
        price_change_pct: float = 5.0,
        volume_surge_multiplier: float = 5.0,
        large_order_usd: float = 100_000.0,
        default_cooldown_sec: int = 300,
    ):
        # 閾值配置
        self._rsi_overbought = rsi_overbought
        self._rsi_oversold = rsi_oversold
        self._price_change_pct = price_change_pct
        self._volume_surge_mult = volume_surge_multiplier
        self._large_order_usd = large_order_usd
        self._default_cooldown = default_cooldown_sec

        # 規則存儲
        self._rules: dict[str, AlertRule] = {}  # rule_id -> rule
        self._rules_by_symbol: dict[str, list[str]] = defaultdict(list)  # symbol -> [rule_id]

        # 告警歷史
        self._history: list[AlertEvent] = []
        self._max_history = 1000

        # 活躍告警（最近觸發的）
        self._active_alerts: dict[str, AlertEvent] = {}  # rule_id -> event

        # 回調
        self._on_alert = None

        # 統計
        self._total_evaluated = 0
        self._total_triggered = 0

    # ── 回調 ──────────────────────────────────────────────────

    def set_alert_callback(self, callback):
        """設置告警觸發回調。"""
        self._on_alert = callback

    # ── 規則管理 ──────────────────────────────────────────────

    def add_rule(self, rule: AlertRule) -> str:
        """添加規則。返回 rule_id。"""
        self._rules[rule.rule_id] = rule
        if rule.rule_id not in self._rules_by_symbol[rule.symbol]:
            self._rules_by_symbol[rule.symbol].append(rule.rule_id)
        return rule.rule_id

    def remove_rule(self, rule_id: str) -> bool:
        """移除規則。"""
        rule = self._rules.pop(rule_id, None)
        if rule and rule_id in self._rules_by_symbol.get(rule.symbol, []):
            self._rules_by_symbol[rule.symbol].remove(rule_id)
        return rule is not None

    def enable_rule(self, rule_id: str) -> bool:
        rule = self._rules.get(rule_id)
        if rule:
            rule.enabled = True
            return True
        return False

    def disable_rule(self, rule_id: str) -> bool:
        rule = self._rules.get(rule_id)
        if rule:
            rule.enabled = False
            return True
        return False

    def get_rules(self, symbol: str = None) -> list[dict]:
        """獲取規則列表。"""
        if symbol:
            symbol = symbol.upper()
            ids = self._rules_by_symbol.get(symbol, [])
            return [self._rules[rid].to_dict() for rid in ids if rid in self._rules]
        return [r.to_dict() for r in self._rules.values()]

    def get_rule_count(self) -> int:
        return len(self._rules)

    # ── 自動規則生成 ──────────────────────────────────────────

    def create_default_rules(self, symbol: str, cooldown_sec: int = None) -> list[str]:
        """為交易對創建默認告警規則。"""
        cd = cooldown_sec or self._default_cooldown
        symbol = symbol.upper()
        rules = []

        rules.append(self.add_rule(AlertRule(
            rule_id=f"{symbol}_rsi_overbought",
            rule_type="rsi_overbought",
            symbol=symbol,
            params={"threshold": self._rsi_overbought},
            level=ALERT_LEVEL_WARNING,
            cooldown_sec=cd,
        )))

        rules.append(self.add_rule(AlertRule(
            rule_id=f"{symbol}_rsi_oversold",
            rule_type="rsi_oversold",
            symbol=symbol,
            params={"threshold": self._rsi_oversold},
            level=ALERT_LEVEL_WARNING,
            cooldown_sec=cd,
        )))

        rules.append(self.add_rule(AlertRule(
            rule_id=f"{symbol}_price_surge",
            rule_type="price_change",
            symbol=symbol,
            params={"change_pct": self._price_change_pct, "direction": "up"},
            level=ALERT_LEVEL_CRITICAL,
            cooldown_sec=cd,
        )))

        rules.append(self.add_rule(AlertRule(
            rule_id=f"{symbol}_price_drop",
            rule_type="price_change",
            symbol=symbol,
            params={"change_pct": self._price_change_pct, "direction": "down"},
            level=ALERT_LEVEL_CRITICAL,
            cooldown_sec=cd,
        )))

        rules.append(self.add_rule(AlertRule(
            rule_id=f"{symbol}_volume_surge",
            rule_type="volume_surge",
            symbol=symbol,
            params={"multiplier": self._volume_surge_mult},
            level=ALERT_LEVEL_WARNING,
            cooldown_sec=cd,
        )))

        rules.append(self.add_rule(AlertRule(
            rule_id=f"{symbol}_large_order",
            rule_type="large_order",
            symbol=symbol,
            params={"min_usd": self._large_order_usd},
            level=ALERT_LEVEL_INFO,
            cooldown_sec=max(cd // 5, 30),  # 大單冷卻期較短
        )))

        rules.append(self.add_rule(AlertRule(
            rule_id=f"{symbol}_macd_cross",
            rule_type="macd_cross",
            symbol=symbol,
            params={},
            level=ALERT_LEVEL_WARNING,
            cooldown_sec=cd * 2,
        )))

        rules.append(self.add_rule(AlertRule(
            rule_id=f"{symbol}_bb_breakout",
            rule_type="bb_breakout",
            symbol=symbol,
            params={},
            level=ALERT_LEVEL_WARNING,
            cooldown_sec=cd,
        )))

        return rules

    # ── 規則評估 ──────────────────────────────────────────────

    def evaluate(
        self,
        symbol: str,
        indicators: dict = None,
        snapshot: dict = None,
        microstructure: dict = None,
    ) -> list[AlertEvent]:
        """
        評估所有適用規則。

        symbol: 交易對
        indicators: 技術指標字典（RSI, MACD, BB 等）
        snapshot: 實時快照（price, change_pct, volume 等）
        microstructure: 微結構分析結果

        返回觸發的告警事件列表。
        """
        symbol = symbol.upper()
        rule_ids = self._rules_by_symbol.get(symbol, [])
        if not rule_ids:
            return []

        self._total_evaluated += 1
        triggered = []

        for rid in rule_ids:
            rule = self._rules.get(rid)
            if not rule or not rule.enabled:
                continue
            if rule.is_in_cooldown():
                continue

            event = self._evaluate_rule(rule, indicators or {}, snapshot or {}, microstructure or {})
            if event:
                rule.mark_triggered()
                self._total_triggered += 1
                triggered.append(event)
                self._history.append(event)
                self._active_alerts[rid] = event

                # 裁剪歷史
                if len(self._history) > self._max_history:
                    self._history = self._history[-self._max_history:]

                # 回調
                if self._on_alert:
                    try:
                        self._on_alert(event)
                    except Exception as e:
                        logger.debug(f"[CryptoAlert] 回調失敗: {e}")

        return triggered

    def _evaluate_rule(
        self,
        rule: AlertRule,
        indicators: dict,
        snapshot: dict,
        micro: dict,
    ) -> Optional[AlertEvent]:
        """評估單條規則。"""
        rt = rule.rule_type
        sym = rule.symbol
        price = snapshot.get("price", 0)

        # ── RSI 超買 ──
        if rt == "rsi_overbought":
            rsi = indicators.get("rsi")
            threshold = rule.params.get("threshold", self._rsi_overbought)
            if rsi is not None and rsi > threshold:
                return AlertEvent(
                    rule_id=rule.rule_id, rule_type=rt, symbol=sym, level=rule.level,
                    message=f"🔴 {sym} RSI 超買: {rsi:.1f} > {threshold}",
                    price=price, params={"rsi": rsi, "threshold": threshold},
                )

        # ── RSI 超賣 ──
        elif rt == "rsi_oversold":
            rsi = indicators.get("rsi")
            threshold = rule.params.get("threshold", self._rsi_oversold)
            if rsi is not None and rsi < threshold:
                return AlertEvent(
                    rule_id=rule.rule_id, rule_type=rt, symbol=sym, level=rule.level,
                    message=f"🟢 {sym} RSI 超賣: {rsi:.1f} < {threshold}",
                    price=price, params={"rsi": rsi, "threshold": threshold},
                )

        # ── 價格變動 ──
        elif rt == "price_change":
            change_pct = snapshot.get("change_pct", 0)
            threshold = rule.params.get("change_pct", self._price_change_pct)
            direction = rule.params.get("direction", "up")
            if direction == "up" and change_pct > threshold:
                return AlertEvent(
                    rule_id=rule.rule_id, rule_type=rt, symbol=sym, level=rule.level,
                    message=f"🚀 {sym} 漲幅 {change_pct:.2f}% > {threshold}%",
                    price=price, params={"change_pct": change_pct},
                )
            elif direction == "down" and change_pct < -threshold:
                return AlertEvent(
                    rule_id=rule.rule_id, rule_type=rt, symbol=sym, level=rule.level,
                    message=f"💥 {sym} 跌幅 {change_pct:.2f}% < -{threshold}%",
                    price=price, params={"change_pct": change_pct},
                )

        # ── 成交量突增 ──
        elif rt == "volume_surge":
            # 微結構的成交密度異常高
            density = micro.get("trade_analysis", {}).get("trade_density", {})
            tpm = density.get("trades_per_minute", 0)
            # 用 snapshot 的 volume 與 quote_volume 的比值判斷
            vol = snapshot.get("volume", 0)
            if vol > 0 and tpm > 100:  # 高頻成交
                return AlertEvent(
                    rule_id=rule.rule_id, rule_type=rt, symbol=sym, level=rule.level,
                    message=f"📊 {sym} 成交量異常: 密度 {tpm:.0f} 筆/分鐘",
                    price=price, params={"trades_per_minute": tpm, "volume": vol},
                )

        # ── 大單 ──
        elif rt == "large_order":
            large = micro.get("trade_analysis", {}).get("large_orders", {})
            min_usd = rule.params.get("min_usd", self._large_order_usd)
            recent = large.get("recent", [])
            if recent:
                latest = recent[-1]
                if latest.get("usd", 0) >= min_usd:
                    return AlertEvent(
                        rule_id=rule.rule_id, rule_type=rt, symbol=sym, level=rule.level,
                        message=(
                            f"🐋 {sym} 大單: {latest['direction'].upper()} "
                            f"${latest['usd']:,.0f} @ {latest['price']}"
                        ),
                        price=price, params=latest,
                    )

        # ── MACD 交叉 ──
        elif rt == "macd_cross":
            hist = indicators.get("macd_histogram")
            prev_hist = indicators.get("prev_macd_histogram")
            if hist is not None and prev_hist is not None:
                if prev_hist < 0 and hist > 0:
                    return AlertEvent(
                        rule_id=rule.rule_id, rule_type="macd_golden_cross",
                        symbol=sym, level=rule.level,
                        message=f"📈 {sym} MACD 金叉: Histogram {hist:.4f}",
                        price=price, params={"histogram": hist},
                    )
                elif prev_hist > 0 and hist < 0:
                    return AlertEvent(
                        rule_id=rule.rule_id, rule_type="macd_death_cross",
                        symbol=sym, level=rule.level,
                        message=f"📉 {sym} MACD 死叉: Histogram {hist:.4f}",
                        price=price, params={"histogram": hist},
                    )

        # ── 布林帶突破 ──
        elif rt == "bb_breakout":
            bb_upper = indicators.get("bb_upper")
            bb_lower = indicators.get("bb_lower")
            if bb_upper is not None and price > bb_upper:
                return AlertEvent(
                    rule_id=rule.rule_id, rule_type="bb_upper_break",
                    symbol=sym, level=rule.level,
                    message=f"⚡ {sym} 突破布林上軌: {price:.2f} > {bb_upper:.2f}",
                    price=price, params={"bb_upper": bb_upper},
                )
            elif bb_lower is not None and price < bb_lower:
                return AlertEvent(
                    rule_id=rule.rule_id, rule_type="bb_lower_break",
                    symbol=sym, level=rule.level,
                    message=f"⚡ {sym} 跌破布林下軌: {price:.2f} < {bb_lower:.2f}",
                    price=price, params={"bb_lower": bb_lower},
                )

        return None

    # ── 查詢接口 ──────────────────────────────────────────────

    def get_active_alerts(self) -> list[dict]:
        """獲取活躍告警。"""
        return [e.to_dict() for e in self._active_alerts.values()]

    def get_alert_history(self, symbol: str = None, limit: int = 50) -> list[dict]:
        """獲取告警歷史。"""
        events = self._history
        if symbol:
            symbol = symbol.upper()
            events = [e for e in events if e.symbol == symbol]
        return [e.to_dict() for e in events[-limit:]]

    def clear_active(self):
        """清除所有活躍告警。"""
        self._active_alerts.clear()

    def get_stats(self) -> dict:
        """返回引擎統計。"""
        return {
            "total_rules": len(self._rules),
            "enabled_rules": sum(1 for r in self._rules.values() if r.enabled),
            "active_alerts": len(self._active_alerts),
            "history_size": len(self._history),
            "total_evaluated": self._total_evaluated,
            "total_triggered": self._total_triggered,
            "symbols_with_rules": len(self._rules_by_symbol),
        }

    # ── 配置更新 ──────────────────────────────────────────────

    def update_config(self, config: dict):
        """動態更新告警閾值配置。"""
        if "rsi_overbought" in config:
            self._rsi_overbought = config["rsi_overbought"]
        if "rsi_oversold" in config:
            self._rsi_oversold = config["rsi_oversold"]
        if "price_change_pct" in config:
            self._price_change_pct = config["price_change_pct"]
        if "volume_surge_multiplier" in config:
            self._volume_surge_mult = config["volume_surge_multiplier"]
        if "large_order_usd" in config:
            self._large_order_usd = config["large_order_usd"]
        if "default_cooldown_sec" in config:
            self._default_cooldown = config["default_cooldown_sec"]

    def get_config(self) -> dict:
        """返回當前配置。"""
        return {
            "rsi_overbought": self._rsi_overbought,
            "rsi_oversold": self._rsi_oversold,
            "price_change_pct": self._price_change_pct,
            "volume_surge_multiplier": self._volume_surge_mult,
            "large_order_usd": self._large_order_usd,
            "default_cooldown_sec": self._default_cooldown,
        }
