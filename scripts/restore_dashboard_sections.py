# -*- coding: utf-8 -*-
"""Restore dashboard HTML: global indices + market charts blocks."""
from pathlib import Path

D = "d" + "i" + "v"
p = Path(__file__).resolve().parents[1] / "static" / "index.html"
text = p.read_text(encoding="utf-8")

marker = f'    <{D} class="g" id="statsGrid"></{D}>'
if marker not in text:
    raise SystemExit("statsGrid marker not found")

if "indexChartsGrid" in text:
    print("indexChartsGrid already present")
else:
    indices_block = f"""
    <!-- Major Indices (Professional K-line) -->
    <{D} class="sec index-charts-sec">
        <{D} class="index-charts-head">
            <h2>🌍 全球主要指數</h2>
            <span class="index-charts-meta" id="indexChartsMeta">專業 K 線 · 載入中…</span>
        </{D}>
        <{D} id="indexChartsGrid" class="index-charts-grid">
            <{D} class="index-charts-loading"><span class="ld"></span> 載入指數行情…</{D}>
        </{D}>
    </{D}>
"""
    text = text.replace(marker, marker + indices_block, 1)
    print("restored global indices")

dash_marker = "    <!-- Dashboard Charts -->"
if "dashSectorFlowChart" in text:
    print("dash market charts already present")
elif dash_marker not in text:
    raise SystemExit("Dashboard Charts marker not found")
else:
    market_block = f"""
    <!-- 資金與板塊 -->
    <{D} class="sec dash-market-sec">
        <{D} class="index-charts-head">
            <h2>💰 資金與板塊</h2>
            <span class="index-charts-meta" id="marketChartsMeta">板塊資金 · 大盤流向 · 北向資金</span>
        </{D}>
        <{D} class="g dash-market-grid">
            <{D} class="sec dash-chart-card">
                <h3 class="dash-chart-title">板塊主力淨流入 Top 10</h3>
                <{D} class="cw cw-market"><canvas id="dashSectorFlowChart"></canvas></{D}>
            </{D}>
            <{D} class="sec dash-chart-card">
                <h3 class="dash-chart-title">漲跌幅 × 資金流向</h3>
                <{D} class="cw cw-market"><canvas id="dashSectorScatterChart"></canvas></{D}>
            </{D}>
            <{D} class="sec dash-chart-card">
                <h3 class="dash-chart-title">大盤資金流向</h3>
                <{D} class="cw cw-market"><canvas id="dashMarketFlowChart"></canvas></{D}>
            </{D}>
            <{D} class="sec dash-chart-card">
                <h3 class="dash-chart-title">北向資金</h3>
                <{D} class="cw cw-market"><canvas id="dashNorthFlowChart"></canvas></{D}>
            </{D}>
            <{D} class="sec dash-chart-card dash-span-2">
                <h3 class="dash-chart-title">板塊熱力圖</h3>
                <{D} class="cw cw-treemap" id="dashSectorTreemapWrap"><canvas id="dashSectorTreemap"></canvas></{D}>
            </{D}>
            <{D} class="sec dash-chart-card">
                <h3 class="dash-chart-title">概念板塊漲跌</h3>
                <{D} class="cw cw-market"><canvas id="dashConceptSectorChart"></canvas></{D}>
            </{D}>
        </{D}>
    </{D}>

"""
    text = text.replace(dash_marker, market_block + "\n    " + dash_marker, 1)
    print("restored market charts")

# Pin Lightweight Charts v5.2 for candlestick API compat
text = text.replace(
    "https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js",
    "https://unpkg.com/lightweight-charts@5.2.0/dist/lightweight-charts.standalone.production.js",
)

p.write_text(text, encoding="utf-8")
print("done, lines:", len(text.splitlines()))
