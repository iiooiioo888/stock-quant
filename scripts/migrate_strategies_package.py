#!/usr/bin/env python3
"""一次性腳本：從 backtest.py 提取策略類至 src/core/strategies/"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKTEST = ROOT / "src/core/backtest.py"
OUT_DIR = ROOT / "src/core/strategies"

CLASS_TO_KEY = {
    "DualMAStrategy": "dual_ma",
    "MACDStrategy": "macd",
    "BollingerStrategy": "bollinger",
    "KDJStrategy": "kdj",
    "RSIStrategy": "rsi",
    "GridStrategy": "grid",
    "TurtleStrategy": "turtle",
    "MomentumStrategy": "momentum",
    "MeanReversionStrategy": "mean_reversion",
    "VolumePriceStrategy": "volume_price",
    "BreakoutStrategy": "breakout",
    "CompositeStrategy": "composite",
    "DualThrustStrategy": "dual_thrust",
    "VWAPStrategy": "vwap",
    "EnvelopeStrategy": "envelope",
    "ParabolicSARStrategy": "parabolic_sar",
    "OBVStrategy": "obv",
    "BollingerSqueezeStrategy": "bollinger_squeeze",
    "ADXTrendStrategy": "adx_trend",
    "EMACrossStrategy": "ema_cross",
    "DonchianStrategy": "donchian",
    "WilliamsRStrategy": "williams_r",
    "CCIStrategy": "cci",
    "SuperTrendStrategy": "supertrend",
    "ATRTrailTrendStrategy": "atr_trail",
    "EMAVolumeStrategy": "ema_volume",
    "TripleMAFilterStrategy": "triple_ma",
    "MacdRsiFilterStrategy": "macd_rsi",
    "PullbackMAStrategy": "pullback_ma",
}

SKIP_CLASSES = {"StrategyWithSLTP"}


def _parse_strategy_names(text: str) -> dict[str, str]:
    m = re.search(r"STRATEGY_NAMES = \{([\s\S]*?)\n\}\n", text)
    if not m:
        raise RuntimeError("STRATEGY_NAMES not found")
    block = m.group(1)
    return dict(re.findall(r'"(\w+)":\s*"([^"]+)"', block))


def _split_classes(block: str) -> list[tuple[str, str]]:
    """按頂層 class 切分（含 _OBV）。"""
    parts: list[tuple[str, str]] = []
    pattern = re.compile(r"^class (\w+)", re.MULTILINE)
    matches = list(pattern.finditer(block))
    for i, match in enumerate(matches):
        name = match.group(1)
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(block)
        parts.append((name, block[start:end].rstrip()))
    return parts


def _snake(name: str) -> str:
    if name in CLASS_TO_KEY:
        return CLASS_TO_KEY[name]
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower().lstrip("_")


def _transform_class_body(body: str, use_base: bool) -> str:
    if use_base and "def notify_order" in body:
        body = re.sub(
            r"\n    def notify_order\(self, order\):[\s\S]*?"
            r"self\.order = None\n",
            "\n",
            body,
            count=1,
        )
    if use_base:
        body = body.replace("(bt.Strategy)", "(OrderManagedStrategy)", 1)
    return body


def main() -> None:
    text = BACKTEST.read_text(encoding="utf-8")
    names_zh = _parse_strategy_names(text)

    start = text.index("# 策略定義")
    end = text.index("# ============================================================\n# 回測執行")
    block = text[start:end]

    sltp_m = re.search(
        r"(# =+\n# 止損/止盈策略包裝器[\s\S]*?class StrategyWithSLTP[\s\S]*?)\n\n\nclass VWAPStrategy",
        block,
    )
    sltp_src = sltp_m.group(1) if sltp_m else ""

    classes_block = block
    if sltp_m:
        classes_block = block[: sltp_m.start()] + block[sltp_m.end() - len("class VWAPStrategy") :]

    pieces = _split_classes(classes_block)
    obv_helpers: list[str] = []

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for cls_name, cls_src in pieces:
        if cls_name in SKIP_CLASSES:
            continue
        if cls_name.startswith("_"):
            if cls_name == "_OBV":
                obv_helpers.append(cls_src)
            continue

        key = CLASS_TO_KEY.get(cls_name)
        if not key:
            print(f"skip unknown class {cls_name}")
            continue

        use_base = "def notify_order" in cls_src and cls_name != "StrategyWithSLTP"
        transformed = _transform_class_body(cls_src, use_base)
        zh = names_zh.get(key, key)

        imports = "import backtrader as bt\n\n"
        if use_base:
            imports += "from src.core.strategies.base import OrderManagedStrategy\n"
            imports += "from src.core.strategies.registry import register_strategy\n\n"
            imports += f'@register_strategy("{key}", "{zh}")\n'
        else:
            imports += "from src.core.strategies.registry import register_strategy\n\n"
            imports += f'@register_strategy("{key}", "{zh}")\n'

        file_body = imports + transformed + "\n"
        if cls_name == "OBVStrategy" and obv_helpers:
            helper = obv_helpers[0].replace("(bt.Indicator)", "(bt.Indicator)")
            file_body = (
                "import backtrader as bt\n\n"
                + helper
                + "\n\n"
                + "from src.core.strategies.base import OrderManagedStrategy\n"
                + "from src.core.strategies.registry import register_strategy\n\n"
                + f'@register_strategy("{key}", "{zh}")\n'
                + _transform_class_body(cls_src, True)
                + "\n"
            )

        out_path = OUT_DIR / f"{key}.py"
        out_path.write_text(file_body, encoding="utf-8")
        print(f"wrote {out_path.name}")

    # base.py with SLTP
    base_path = OUT_DIR / "base.py"
    sltp_body = ""
    if sltp_src:
        sltp_body = "\n\n" + sltp_src.replace("class StrategyWithSLTP(bt.Strategy)", "class StrategyWithSLTP(bt.Strategy)")
    base_content = '''"""策略基類與止損/止盈包裝。"""
import backtrader as bt


class OrderManagedStrategy(bt.Strategy):
    """統一未完成訂單保護；子類在 next() 開頭檢查 self.order。"""

    def __init__(self):
        self.order = None

    def notify_order(self, order):
        if order.status in [order.Completed, order.Canceled, order.Margin, order.Rejected]:
            self.order = None
''' + sltp_body + "\n"
    base_path.write_text(base_content, encoding="utf-8")
    print("wrote base.py")


if __name__ == "__main__":
    main()
