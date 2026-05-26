#!/usr/bin/env python3
"""從內建策略註冊表生成 static/data/strategy-catalog.json（策略庫 UI）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "static" / "data" / "strategy-catalog.json"

CATS = [
    {"id": "trend", "name": "趨勢跟蹤與動量", "icon": "📈", "color": "#e8b830"},
    {"id": "osc", "name": "振盪與均值回歸", "icon": "〰️", "color": "#38bdf8"},
    {"id": "breakout", "name": "突破與通道", "icon": "🚀", "color": "#f97316"},
    {"id": "ai", "name": "AI / 機器學習", "icon": "🤖", "color": "#a78bfa"},
    {"id": "risk", "name": "風險與資金管理", "icon": "🛡️", "color": "#34d399"},
    {"id": "micro", "name": "微結構與量能", "icon": "📊", "color": "#22d3ee"},
    {"id": "macro", "name": "宏觀與跨資產", "icon": "🌐", "color": "#fb7185"},
    {"id": "quant", "name": "計量與統計套利", "icon": "∑", "color": "#c084fc"},
    {"id": "pattern", "name": "形態與 K 線", "icon": "🕯️", "color": "#fbbf24"},
    {"id": "execution", "name": "演算法執行", "icon": "⚙️", "color": "#94a3b8"},
]

# key -> (cat, tier)
IMPLEMENTED_META: dict[str, tuple[str, str]] = {
    "dual_ma": ("trend", "free"),
    "macd": ("trend", "free"),
    "turtle": ("trend", "pro"),
    "momentum": ("trend", "pro"),
    "adx_trend": ("trend", "pro"),
    "parabolic_sar": ("trend", "pro"),
    "ema_cross": ("trend", "free"),
    "triple_ma": ("trend", "pro"),
    "supertrend": ("trend", "pro"),
    "donchian": ("trend", "pro"),
    "pullback_ma": ("trend", "pro"),
    "bollinger": ("osc", "free"),
    "bollinger_squeeze": ("osc", "pro"),
    "mean_reversion": ("osc", "free"),
    "envelope": ("osc", "free"),
    "rsi": ("osc", "free"),
    "kdj": ("osc", "free"),
    "cci": ("osc", "pro"),
    "williams_r": ("osc", "pro"),
    "macd_rsi": ("osc", "pro"),
    "breakout": ("breakout", "free"),
    "dual_thrust": ("breakout", "pro"),
    "atr_trail": ("breakout", "pro"),
    "volume_price": ("micro", "free"),
    "vwap": ("micro", "pro"),
    "obv": ("micro", "pro"),
    "ema_volume": ("micro", "pro"),
    "grid": ("execution", "pro"),
    "composite": ("trend", "ent"),
}

# 每類別規劃中策略（補足文檔 ~130 條）
PLANNED_BY_CAT: dict[str, list[tuple[str, str]]] = {
    "trend": [
        ("一目均衡表", "雲圖趨勢與轉折"),
        ("Ichimoku 雲帶", "多空雲帶過濾"),
        ("DMI 趨勢強度", "方向運動指標"),
        ("線性回歸通道", "趨勢通道突破"),
        ("價格通道", "高低點通道"),
    ],
    "osc": [
        ("Stochastic RSI", "隨機 RSI 超買超賣"),
        ("DeMarker", "DeM 振盪"),
        ("Ultimate Oscillator", "終極振盪"),
        ("CMO 錢德動量", "Chande Momentum"),
    ],
    "breakout": [
        ("Opening Range Breakout", "開盤區間突破"),
        ("Pivot 突破", "樞軸點突破"),
        ("箱體突破", "橫盤突破"),
        ("波動率突破", "ATR 擴張突破"),
    ],
    "ai": [
        ("LSTM 價格預測", "序列深度學習"),
        ("隨機森林分類", "特徵樹模型"),
        ("XGBoost 信號", "梯度提升"),
        ("強化學習執行", "RL 下單"),
        ("Transformer 因子", "注意力因子"),
        ("AutoML 策略搜索", "自動特徵與模型"),
        ("GAN 合成行情", "數據增強"),
        ("聚類 regime", "市場狀態分群"),
        ("異常檢測", "極端行情識別"),
        ("NLP 新聞情緒", "文本情緒因子"),
        ("圖神經網絡", "關聯股票圖"),
        ("聯邦學習", "分散式訓練"),
        ("知識蒸餾", "輕量模型"),
        ("元學習", "快速適應"),
        ("多任務學習", "聯合優化"),
    ],
    "risk": [
        ("波動率目標", "目標波動倉位"),
        ("最大回撤控制", "動態降倉"),
        ("VaR 限倉", "風險價值"),
        ("Kelly 倉位", "最優下注"),
        ("止損止盈模板", "風控模板"),
        ("組合風險平價", "風險均衡"),
        ("相關性對沖", "配對風險"),
        ("尾部對沖", "極端保護"),
        ("流動性過濾", "成交量門檻"),
        ("黑天鵝預警", "壓力情景"),
    ],
    "micro": [
        ("訂單流不平衡", "買賣盤力量"),
        ("大單追蹤", "主力單偵測"),
        ("價量背離", "量價異常"),
    ],
    "macro": [
        ("利率曲線", "債券曲線因子"),
        ("通脹預期", "CPI 關聯"),
        ("匯率因子", "跨境資金"),
        ("商品週期", "大宗聯動"),
        ("GDP 驚喜", "宏觀意外"),
        ("央行政策", "政策事件"),
        ("信用利差", "信用風險"),
        ("VIX 避險", "波動率指數"),
        ("行業輪動", "板塊輪動"),
        ("全球 beta", "跨市場 beta"),
    ],
    "quant": [
        ("協整配對", "統計套利"),
        ("格蘭傑因果", "領先滯後"),
        ("VAR 預測", "向量自回歸"),
        ("因子中性", "多因子中性"),
        ("PCA 降維", "主成分"),
        ("卡爾曼濾波", "狀態空間"),
        ("小波分解", "多尺度"),
        ("Hurst 指數", "長記憶"),
        ("Copula 相依", "尾部相依"),
        ("事件研究", "公告效應"),
        ("季節性分解", "STL"),
        ("橫截面動量", "截面排序"),
        ("價值因子", "估值因子"),
        ("質量因子", "財務質量"),
        ("低波因子", "低波異象"),
    ],
    "pattern": [
        ("錘頭線", "反轉 K 線"),
        ("吞沒形態", "反轉確認"),
        ("頭肩頂底", "經典形態"),
        ("三角形", "整理突破"),
        ("旗形", "趨勢延續"),
        ("楔形", "反轉楔形"),
        ("缺口策略", "跳空交易"),
        ("三法", "持續形態"),
        ("十字星", "猶豫信號"),
        ("早晨之星", "底部組合"),
        ("黃昏之星", "頂部組合"),
        ("島形反轉", "島形"),
        ("矩形整理", "箱體"),
        ("圓弧底", "緩變反轉"),
        ("V 型反轉", "急反轉"),
    ],
    "execution": [
        ("TWAP", "時間加權"),
        ("冰山單", "隱藏數量"),
        ("POV", "成交量占比"),
        ("Sniper", "流動性捕捉"),
        ("做市模擬", "雙邊報價"),
        ("智能路由", "多交易所"),
        ("滑點優化", "執行成本"),
        ("開盤競價", "集合競價"),
        ("收盤競價", "尾盤執行"),
        ("VWAP 執行", "基準跟蹤"),
        ("Implementation Shortfall", "IS 最小化"),
        ("Participation", "參與率"),
        ("Dark Pool", "暗池"),
        ("Arrival Price", "到達價"),
        ("Limit Chase", "限價追單"),
        ("Stop Limit", "止損限價"),
        ("Bracket Order", "括號單"),
        ("Scale In/Out", "分批建倉"),
    ],
}

CAT_TARGETS = {
    "trend": 15,
    "osc": 12,
    "breakout": 10,
    "ai": 15,
    "risk": 10,
    "micro": 8,
    "macro": 10,
    "quant": 15,
    "pattern": 15,
    "execution": 20,
}


def _doc_first_line(cls) -> str:
    doc = (cls.__doc__ or "").strip()
    if not doc:
        return ""
    return doc.split("\n")[0].strip()


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from src.core.backtest import STRATEGIES, STRATEGY_NAMES  # noqa: WPS433

    strats: list[dict] = []
    sid = 1
    used_keys: set[str] = set()

    for key in sorted(STRATEGIES.keys()):
        cls = STRATEGIES[key]
        cat, tier = IMPLEMENTED_META.get(key, ("trend", "free"))
        display = STRATEGY_NAMES.get(key, key)
        desc = _doc_first_line(cls) or f"{display} 策略"
        strats.append({
            "id": sid,
            "name": display,
            "desc": desc,
            "cat": cat,
            "tier": tier,
            "backend_key": key,
            "status": "implemented",
        })
        used_keys.add(key)
        sid += 1

    for cat_id, target in CAT_TARGETS.items():
        existing = sum(1 for s in strats if s["cat"] == cat_id)
        planned = list(PLANNED_BY_CAT.get(cat_id, []))
        idx = 0
        while existing < target:
            if idx < len(planned):
                name, desc = planned[idx]
                idx += 1
            else:
                name = f"{cat_id.upper()} 策略 {existing + 1}"
                desc = "即將推出"
            slug = f"planned_{cat_id}_{existing + 1}"
            strats.append({
                "id": sid,
                "name": name,
                "desc": desc,
                "cat": cat_id,
                "tier": "pro" if existing % 3 else "free",
                "backend_key": None,
                "status": "planned",
            })
            sid += 1
            existing += 1

    payload = {"cats": CATS, "strats": strats}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    impl = sum(1 for s in strats if s["status"] == "implemented")
    print(f"Wrote {OUT} ({len(strats)} strategies, {impl} implemented)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
