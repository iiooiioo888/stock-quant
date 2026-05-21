# -*- coding: utf-8 -*-
"""圖表與策略中文標籤補丁"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _write(rel: str, text: str) -> None:
    (ROOT / rel).write_text(text, encoding="utf-8")
    print(rel)


def patch_backtest():
    p = "static/js/backtest.js"
    t = _read(p)
    insert = """    const stratZh = (typeof SignalLabels !== 'undefined')
      ? SignalLabels.strategyName(strategy, 'short') : strategy;
    const chartTitle = `${code} ${stratZh}`;

"""
    marker = "    // K 線圖\n    const klineContainer"
    if "const chartTitle" not in t:
        t = t.replace(marker, insert + marker, 1)
    t = t.replace(
        "Charts.drawLWKlineChart('btKlineContainer', r.kline, r.signals, `${code} ${strategy}`)",
        "Charts.drawLWKlineChart('btKlineContainer', r.kline, r.signals, chartTitle)",
    )
    t = t.replace(
        "Charts.drawKlineChart('btKlineChart', r.kline, r.signals, `${code} ${strategy}`)",
        "Charts.drawKlineChart('btKlineChart', r.kline, r.signals, chartTitle)",
    )
    if "label: chartTitle" not in t and "label: `${code} ${strategy}`" in t:
        t = t.replace(
            "Charts.drawLineChart('btChart', [{ label: `${code} ${strategy}`, data: r.nav, dates: r.dates }])",
            "Charts.drawLineChart('btChart', [{ label: chartTitle, data: r.nav, dates: r.dates }])",
        )
    if "const stratCell" not in t:
        t = t.replace(
            "document.getElementById('btAllTable').innerHTML = results.map(r =>",
            "const stratCell = (s) => (typeof SignalLabels !== 'undefined')\n"
            "      ? SignalLabels.strategyName(s, 'short') : s;\n"
            "    document.getElementById('btAllTable').innerHTML = results.map(r =>",
            1,
        )
        t = t.replace(
            "<td><strong>${r.strategy}</strong></td>",
            "<td><strong>${stratCell(r.strategy)}</strong></td>",
            1,
        )
        t = t.replace(
            "      label: r.strategy,\n      data: r.nav,",
            "      label: stratCell(r.strategy),\n      data: r.nav,",
            1,
        )
    for a, b in [
        ("<h3>Sortino</h3>", "<h3>索提諾比率</h3>"),
        ("<h3>Calmar</h3>", "<h3>卡瑪比率</h3>"),
        ("<h3>VaR 95%</h3>", "<h3>風險價值 VaR</h3>"),
        ("<h3>CVaR 95%</h3>", "<h3>條件風險 CVaR</h3>"),
        ("<h3>Alpha</h3>", "<h3>Alpha 超額</h3>"),
        ("<h3>Beta</h3>", "<h3>Beta 係數</h3>"),
    ]:
        t = t.replace(a, b)
    _write(p, t)


def patch_app():
    p = "static/js/app.js"
    t = _read(p)
    reps = [
        ("<h3>Sortino</h3>", "<h3>索提諾比率</h3>"),
        ("<h3>平均 OOS 收益</h3>", "<h3>平均樣本外收益</h3>"),
        ("<h3>平均 OOS 夏普</h3>", "<h3>平均樣本外夏普</h3>"),
        ("const oosLabels = wins.map(w => 'W' + w.window);", "const oosLabels = wins.map(w => '窗口 ' + w.window);"),
        ("name: 'Walk-Forward',", "name: '滾動窗口驗證',"),
        ("Walk-Forward 分析", "滾動窗口驗證"),
        ("Walk-Forward 已提交", "滾動窗口驗證已提交"),
        ("Walk-Forward 失敗", "滾動窗口驗證失敗"),
    ]
    for a, b in reps:
        t = t.replace(a, b)
    if "strategyName" not in t or "relative_return" in t:
        old = "series.push({ label: code, data: v.relative_return, dates: v.dates });"
        new = """const relLabel = (typeof SignalLabels !== 'undefined')
        ? `${code} ${SignalLabels.strategyName(code, 'short')}`
        : code;
      series.push({ label: relLabel, data: v.relative_return, dates: v.dates });"""
        if old in t and "relLabel" not in t:
            t = t.replace(old, new)
    _write(p, t)


def patch_crypto():
    p = "static/js/crypto.js"
    t = _read(p)
    if "SignalLabels" not in t or "BTC" in t:
        t = t.replace(
            "label: this._selectedSymbol,",
            "label: this._selectedSymbol || '加密資產',",
        )
    _write(p, t)


def patch_charts():
    p = "static/js/charts.js"
    t = _read(p)
    reps = [
        ("label: '超大单'", "label: '超大單'"),
        ("label: '大单'", "label: '大單'"),
        ("label: '中单'", "label: '中單'"),
        ("label: '小单'", "label: '小單'"),
    ]
    for a, b in reps:
        t = t.replace(a, b)
    _write(p, t)


def patch_signals():
    p = "static/js/signals.js"
    t = _read(p)
    old = "return `<span class=\"chip ${cls}\">${st.strategy}: ${st.signal}</span>`;"
    new = """const stName = SL ? SL.strategyName(st.strategy, 'short') : st.strategy;
        const sigZh = SL ? SL.getSignal(st.signal).zh : st.signal;
        return `<span class="chip ${cls}">${stName}: ${sigZh}</span>`;"""
    if old in t and "stName" not in t:
        t = t.replace(old, new)
    _write(p, t)


def patch_task_common():
    p = "static/js/task-common.js"
    t = _read(p)
    t = t.replace("walkforward: '🔄 Walk-Forward',", "walkforward: '🔄 滾動窗口驗證',")
    _write(p, t)


def patch_stock_picker():
    p = "static/js/stock-picker.js"
    t = _read(p)
    t = t.replace("選擇 Walk-Forward 標的", "選擇滾動窗口驗證標的")
    _write(p, t)


def patch_signal_labels():
    p = "static/js/signal-labels.js"
    t = _read(p)
    extra = """      [/Walk[- ]?Forward/gi, '滾動窗口驗證'],
      [/\\bIS\\b/g, '樣本內'],
"""
    if "Walk[- ]?Forward" not in t:
        t = t.replace(
            "      [/\\bOOS\\b/g, '樣本外'],",
            "      [/\\bOOS\\b/g, '樣本外'],\n" + extra,
        )
    _write(p, t)


def patch_backtest_py():
    p = Path("src/core/backtest.py")
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
    import re
    block = "STRATEGY_NAMES = {\n" + "".join(
        f'    "{k}": "{v}",\n' for k, v in names.items()
    ) + "}\n"
    t2, n = re.subn(
        r"# 策略中文名称映射\nSTRATEGY_NAMES = \{[\s\S]*?\n\}\n\n\n# 策略注册",
        "# 策略中文名称映射\n" + block + "\n# 策略注册",
        t,
        count=1,
    )
    if n == 0:
        t2, n = re.subn(
            r"STRATEGY_NAMES = \{[\s\S]*?\n\}\n\n\n# 策略注册",
            block + "\n# 策略注册",
            t,
            count=1,
        )
    if n:
        p.write_text(t2, encoding="utf-8")
        print("src/core/backtest.py STRATEGY_NAMES")


if __name__ == "__main__":
    patch_backtest_py()
    patch_backtest()
    patch_app()
    patch_crypto()
    patch_charts()
    patch_signals()
    patch_task_common()
    patch_stock_picker()
    patch_signal_labels()
