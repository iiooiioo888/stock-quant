# -*- coding: utf-8 -*-
"""修復 backtest.py STRATEGY_NAMES 為繁體中文"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
p = ROOT / "src/core/backtest.py"
t = p.read_text(encoding="utf-8")

names = {
    "dual_ma": "雙均線金叉策略",
    "macd": "MACD金叉策略",
    "bollinger": "布林帶突破策略",
    "kdj": "KDJ隨機指標策略",
    "rsi": "RSI相對強弱策略",
    "grid": "網格交易策略",
    "turtle": "海龜趨勢跟蹤策略",
    "dual_thrust": "雙軌日內突破策略",
    "momentum": "動量ROC策略",
    "mean_reversion": "均值回歸Z-score策略",
    "volume_price": "量價齊升策略",
    "breakout": "N日高點突破策略",
    "composite": "多策略組合投票策略",
    "vwap": "VWAP成交量加權策略",
    "envelope": "均線通道策略",
    "parabolic_sar": "拋物線SAR策略",
    "obv": "OBV能量潮策略",
    "bollinger_squeeze": "布林帶收窄突破策略",
    "adx_trend": "ADX趨勢強度策略",
}

block = "STRATEGY_NAMES = {\n" + "".join(
    f'    "{k}": "{v}",\n' for k, v in names.items()
) + "}\n"

for pat in [
    r"STRATEGY_NAMES = \{[\s\S]*?\n\}\n",
    r"# 策略中文名称映射\nSTRATEGY_NAMES = \{[\s\S]*?\n\}\n",
]:
    t2, n = re.subn(pat, block, t, count=1)
    if n:
        p.write_text(t2, encoding="utf-8")
        print("OK: STRATEGY_NAMES updated")
        for line in t2.splitlines():
            if '"dual_thrust"' in line and "Strategy" not in line:
                print(line)
        break
else:
    raise SystemExit("STRATEGY_NAMES block not found")
